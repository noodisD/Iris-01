"""Telling a session's speakers apart by voice, when the owner asks (ADR-0028).

A transcript's speaker labels come from whoever made it, and often many turns
are marked uncertain. An uncertain turn is context only, so whatever the owner
said in it is lost as evidence. The recording can settle most of them. With the
owner's click, the audio goes to OpenAI's diarizing transcriber with a few
seconds of each voice, taken from turns the transcript already labels, and
comes back as stretches of speech by speaker. A turn whose time is mostly one
voice gets that speaker's label; a labelled turn the voices contradict is
marked unsure rather than switched. The words are never touched: only the
label of a turn changes, and the owner can put the old labels back.

If the voices do not line up with the labels the transcript is sure of, the
recording is probably of another session, or its times are offset, and nothing
is changed.
"""

from __future__ import annotations

import base64
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import sessions
from .config import settings
from .database import db

logger = logging.getLogger(__name__)

MODEL = "gpt-4o-transcribe-diarize"
#: Dollars per minute of audio heard.
PRICE_PER_MINUTE = 0.006
#: Each request carries this much of the recording, cut at a silence nearby.
PART_SECONDS = 900
#: The share of a turn's speech one voice needs before the turn is called theirs.
SURE_SHARE = 0.7
#: Below this share of agreement with the turns the transcript is sure of, the
#: recording and the transcript are not the same conversation, or not aligned.
MIN_AGREEMENT = 0.6
#: A voice sample is a few seconds of one speaker alone.
SAMPLE_SECONDS = (2.0, 10.0)
MAX_RECORDING_BYTES = 600 * 1024 * 1024
AUDIO_SUFFIXES = {".m4a", ".mp3", ".wav", ".webm", ".ogg", ".oga", ".mp4", ".flac", ".aac"}


class VoicesUnavailable(Exception):
    """Why the voices could not be used, in words the owner can act on."""


@dataclass(frozen=True)
class Heard:
    speaker: str
    start: float
    end: float


def recordings_root() -> Path:
    return Path(settings.DATA_DIR) / "sessions" / "recordings"


def estimate(seconds: float | None) -> dict | None:
    if not seconds:
        return None
    minutes = seconds / 60
    dollars = minutes * PRICE_PER_MINUTE
    return {"minutes": round(minutes), "dollars": round(dollars, 3),
            "text": (f"Sorting out speakers sends the recording ({round(minutes)} minutes) to OpenAI to "
                     f"tell the voices apart, about ${dollars:.2f}. Only speaker labels change; "
                     "the words stay as transcribed.")}


# --- the arithmetic, kept apart from audio and the network --------------------

def _spans(found: list[sessions.Segment]) -> list[tuple[float, float]]:
    """Each segment's time: from its start to the next segment's start."""
    return [(segment.at, found[index + 1].at if index + 1 < len(found) else segment.at + 5)
            for index, segment in enumerate(found)]


def _voice(span: tuple[float, float], heard: list[Heard]) -> tuple[str | None, float]:
    """The speaker heard most during a span, and their share of the speech in it."""
    tally: dict[str, float] = {}
    for stretch in heard:
        overlap = min(span[1], stretch.end) - max(span[0], stretch.start)
        if overlap > 0:
            tally[stretch.speaker] = tally.get(stretch.speaker, 0.0) + overlap
    if not tally:
        return None, 0.0
    speaker = max(tally, key=tally.get)
    return speaker, tally[speaker] / sum(tally.values())


def name_unnamed(heard: list[Heard], found: list[sessions.Segment], names: tuple[str, str]) -> list[Heard]:
    """Voices the samples did not name, named from the turns the transcript is sure of.

    The transcriber names the voices it matched to a sample and letters the
    rest. A lettered voice heard almost only during one speaker's labelled
    turns is that speaker; one that is not stays unnamed and decides nothing.
    """
    spans = _spans(found)
    overlap: dict[str, dict[str, float]] = {}
    for stretch in heard:
        if stretch.speaker in names:
            continue
        for segment, span in zip(found, spans):
            if segment.label in names:
                seconds = min(span[1], stretch.end) - max(span[0], stretch.start)
                if seconds > 0:
                    row = overlap.setdefault(stretch.speaker, dict.fromkeys(names, 0.0))
                    row[segment.label] += seconds
    renamed = {}
    for speaker, row in overlap.items():
        total = sum(row.values())
        best = max(row, key=row.get)
        if total >= 5 and row[best] / total >= 0.8:
            renamed[speaker] = best
    return [Heard(renamed.get(stretch.speaker, stretch.speaker), stretch.start, stretch.end)
            for stretch in heard]


def relabel(found: list[sessions.Segment], heard: list[Heard], names: tuple[str, str],
            unsure: str) -> tuple[list[str], dict]:
    """New labels for every segment, and what changed.

    A segment the transcript was not sure of takes the voice heard for most of
    its time, when that voice holds at least SURE_SHARE of it. A segment it was
    sure of keeps its label, unless the voices clearly say otherwise, and then
    it is marked unsure: context, not someone else's words.
    """
    labels = [segment.label for segment in found]
    report = {"segments": len(found), "heard": 0, "labelled": 0, "agreed": 0, "contradicted": 0,
              "attributed": dict.fromkeys(names, 0), "doubtful": 0}
    for index, (segment, span) in enumerate(zip(found, _spans(found))):
        voice, share = _voice(span, heard)
        report["heard"] += voice is not None
        sure = voice in names and share >= SURE_SHARE
        if segment.label in names:
            if voice in names:
                report["labelled"] += 1
                report["agreed"] += voice == segment.label
            if sure and voice != segment.label:
                labels[index] = f"{segment.label} {unsure}"
                report["contradicted"] += 1
        elif sure:
            labels[index] = voice
            report["attributed"][voice] += 1
        else:
            report["doubtful"] += 1
    return labels, report


# --- audio and the network -----------------------------------------------------

def _ffmpeg(*args: str) -> None:
    if not shutil.which("ffmpeg"):
        raise VoicesUnavailable("ffmpeg is not installed, so the recording cannot be prepared.")
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", *args],
                   check=True, capture_output=True, timeout=900)


def _samples(found: list[sessions.Segment], audio: Path, workdir: Path,
             names: tuple[str, str]) -> list[str]:
    """A few seconds of each named speaker, from a turn the transcript labels, as data URLs."""
    urls = []
    for name in names:
        candidates = [(span[1] - span[0], span) for segment, span in zip(found, _spans(found))
                      if segment.label == name and len(segment.text.split()) >= 6
                      and SAMPLE_SECONDS[0] + 1 <= span[1] - span[0] <= 30]
        if not candidates:
            raise VoicesUnavailable(
                f"No turn labelled {name} is long enough to learn the voice from. The transcript "
                "needs a few seconds of clearly labelled speech from each of you.")
        _, span = min(candidates, key=lambda item: abs(item[0] - 8))
        start = span[0] + 0.3
        length = min(SAMPLE_SECONDS[1], span[1] - span[0] - 0.6)
        out = workdir / f"sample{len(urls)}.wav"
        _ffmpeg("-ss", f"{start:.2f}", "-t", f"{length:.2f}", "-i", str(audio),
                "-ac", "1", "-ar", "16000", str(out))
        urls.append("data:audio/wav;base64," + base64.b64encode(out.read_bytes()).decode())
    return urls


def _parts(audio: Path, workdir: Path) -> list[tuple[float, Path]]:
    """The recording as mono 16 kHz pieces, each with where it starts."""
    from .transcription import normalise, probe_duration, split

    small = normalise(audio, workdir)
    pieces = split(small, workdir, probe_duration(small) or 0.0, chunk_seconds=PART_SECONDS)
    offsets, at = [], 0.0
    for piece in pieces:
        offsets.append((at, piece))
        at += probe_duration(piece) or 0.0
    return offsets


def _diarize(parts: list[tuple[float, Path]], names: tuple[str, str], samples: list[str],
             language: str | None) -> list[Heard]:
    import openai

    from .observability.llm import LlmCall

    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY, timeout=1800)
    heard: list[Heard] = []
    for offset, piece in parts:
        with LlmCall("diarize", MODEL, prompt=f"<audio {piece.stat().st_size} bytes>") as call, \
                piece.open("rb") as fh:
            result = client.audio.transcriptions.create(
                model=MODEL, file=fh, response_format="diarized_json", chunking_strategy="auto",
                known_speaker_names=list(names), known_speaker_references=samples,
                **({"language": language} if language and language != "unknown" else {}))
            stretches = (result.model_dump() if hasattr(result, "model_dump") else result).get("segments") or []
            call.output(f"<{len(stretches)} segments>")
        heard.extend(Heard(str(item.get("speaker")), float(item["start"]) + offset, float(item["end"]) + offset)
                     for item in stretches)
    return heard


def run(import_id: int) -> None:
    """The queued pass: listen, relabel, and keep the old labels to put back.

    A failure is recorded for the owner to see and is not retried by the
    queue: each attempt sends the recording again, and the owner decides
    whether that is worth paying for twice.
    """
    from .session_imports import SessionImports

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE session_imports SET voices_status = 'running', voices_error = NULL,
                              updated_at = NOW()
                        WHERE id = %s AND status IN ('staged', 'imported') AND reflection_id IS NULL
                          AND voices_status = 'queued'
                    RETURNING user_id, transcript, audio_path, owner_label, therapist_label, language;""",
                    (import_id,))
        row = cur.fetchone()
        conn.commit()
    if row is None:
        return
    user_id, transcript, audio_path, owner, therapist, language = row
    workdir = Path(tempfile.mkdtemp(prefix="iris-voices-"))
    try:
        if not audio_path or not owner or not therapist:
            raise VoicesUnavailable("Say which speaker is you and which is the therapist, and add the recording.")
        audio = recordings_root() / audio_path
        if not audio.exists():
            raise VoicesUnavailable("The recording is no longer here. Add it again.")
        found, _ = sessions.segments(transcript)
        names = (owner, therapist)
        samples = _samples(found, audio, workdir, names)
        heard = name_unnamed(_diarize(_parts(audio, workdir), names, samples, language), found, names)
        unsure = "(niepewne)" if language == "pl" else "(unsure)"
        labels, report = relabel(found, heard, names, unsure)
        if report["labelled"] and report["agreed"] / report["labelled"] < MIN_AGREEMENT:
            raise VoicesUnavailable(
                f"The voices agreed with only {report['agreed']} of the {report['labelled']} turns the "
                "transcript labels, so nothing was changed. Is this the recording of this session?")
        if not SessionImports(user_id).apply_voices(import_id, sessions.relabel_segments(transcript, labels),
                                                    report):
            raise VoicesUnavailable("The session changed while its voices were being listened to, "
                                    "so nothing was changed.")
        logger.info(f"Session import {import_id}: speakers sorted out from the recording")
    except Exception as exc:
        reason = str(exc) if isinstance(exc, VoicesUnavailable) else \
            "The recording could not be read for voices. Try again, or import without it."
        logger.warning(f"Session import {import_id}: voices failed ({type(exc).__name__})")
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE session_imports SET voices_status = 'failed', voices_error = %s,
                                  updated_at = NOW() WHERE id = %s;""", (reason, import_id))
            conn.commit()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
