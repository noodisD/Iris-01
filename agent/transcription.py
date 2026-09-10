"""
Turning a spoken journal into text.

The provider boundary for audio, shaped like `pipeline.generate_embedding`: one
decorated call that retries only what is worth retrying, and raises everything
else so the durable queue can decide.

A transcript is not a convenience here. It becomes a reflection, gets embedded,
clustered, and quoted back to the owner as something they said — so a
mis-transcribed word is not a typo, it is evidence IRIS will reason from. That
is why the default model is the accurate one rather than the cheap one, and why
long recordings are cut on silence rather than at an arbitrary offset.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import openai
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import settings
from .pipeline import _TRANSIENT_OPENAI_ERRORS

logger = logging.getLogger(__name__)

#: The API rejects anything larger. Kept under it with room to spare, because
#: the limit is on the encoded upload and our estimate of that is approximate.
MAX_UPLOAD_BYTES = 24 * 1024 * 1024
#: Target length of a chunk when a recording has to be split.
CHUNK_SECONDS = 600
#: Where a silence-aware cut is allowed to land relative to the target.
CHUNK_SLACK_SECONDS = 120


class TranscriptionUnavailable(RuntimeError):
    """ffmpeg is missing, so audio cannot be prepared for transcription."""


@dataclass
class Transcript:
    text: str
    model: str
    chunk_count: int
    duration_seconds: float | None


def _require_ffmpeg() -> str:
    """Checked up front, so a missing tool is a clear message rather than a
    confusing failure on the first long recording."""
    path = shutil.which("ffmpeg")
    if not path:
        raise TranscriptionUnavailable(
            "ffmpeg is not installed, so audio cannot be converted for "
            "transcription. Install it and retry the recording."
        )
    return path


def _run(args: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    # Always a list, never a shell string: these paths come from filenames the
    # owner supplied.
    return subprocess.run(args, check=True, capture_output=True, timeout=timeout)


def probe_duration(path: Path) -> float | None:
    if not shutil.which("ffprobe"):
        return None
    try:
        out = _run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ], timeout=60)
        return round(float(out.stdout.decode().strip()), 3)
    except (subprocess.SubprocessError, ValueError):
        return None


def normalise(src: Path, workdir: Path) -> Path:
    """A mono 16 kHz MP3 copy, which is what actually gets sent.

    Speech carries no information above 16 kHz and none in the second channel of
    a phone recording, so this loses nothing a transcriber uses while making the
    upload roughly 14 MB an hour. Most recordings therefore never need splitting
    at all, and a browser's webm and a phone's m4a become the same thing here —
    so nothing downstream has to care how the audio arrived.

    The original is untouched; this is a working copy.
    """
    _require_ffmpeg()
    workdir.mkdir(parents=True, exist_ok=True)
    out = workdir / f"{src.stem}.normalised.mp3"
    _run(["ffmpeg", "-nostdin", "-y", "-i", str(src), "-vn",
          "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "32k", str(out)])
    return out


def _silences(path: Path) -> list[float]:
    """Ends of detected silences, as candidate cut points."""
    try:
        proc = subprocess.run(
            ["ffmpeg", "-nostdin", "-i", str(path), "-af",
             "silencedetect=noise=-35dB:d=0.5", "-f", "null", "-"],
            capture_output=True, timeout=900,
        )
    except subprocess.SubprocessError:
        return []
    points = []
    for line in proc.stderr.decode(errors="replace").splitlines():
        if "silence_end:" in line:
            try:
                points.append(float(line.split("silence_end:")[1].split()[0]))
            except (IndexError, ValueError):
                continue
    return points


def split(path: Path, workdir: Path, duration: float | None) -> list[Path]:
    """Cut a long recording into transcribable pieces.

    Prefers a silence near each target boundary. A hard cut lands mid-word, and
    the transcriber will confidently produce a different word — which then gets
    embedded and becomes evidence. One extra pass over the audio is cheap next
    to that.
    """
    if not duration:
        duration = probe_duration(path) or 0.0
    if duration <= CHUNK_SECONDS:
        return [path]

    candidates = _silences(path)
    cuts: list[float] = []
    target = CHUNK_SECONDS
    while target < duration - 1:
        near = [s for s in candidates
                if abs(s - target) <= CHUNK_SLACK_SECONDS and s > (cuts[-1] if cuts else 0) + 30]
        cuts.append(min(near, key=lambda s: abs(s - target)) if near else float(target))
        target = cuts[-1] + CHUNK_SECONDS

    bounds = [0.0, *cuts, duration]
    pieces = []
    for i, (start, end) in enumerate(zip(bounds, bounds[1:])):
        piece = workdir / f"{path.stem}.part{i:03d}.mp3"
        _run(["ffmpeg", "-nostdin", "-y", "-i", str(path), "-ss", f"{start:.3f}",
              "-to", f"{end:.3f}", "-c", "copy", str(piece)])
        pieces.append(piece)
    logger.info(f"Split {path.name} into {len(pieces)} pieces for transcription")
    return pieces


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(_TRANSIENT_OPENAI_ERRORS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def transcribe_file(path: Path, model: str) -> str:
    """One request to the provider. The only place this module talks out."""
    with path.open("rb") as fh:
        return str(openai.audio.transcriptions.create(
            model=model, file=fh, response_format="text"
        )).strip()


def transcribe(src: Path, model: str | None = None) -> Transcript:
    """Prepare, transcribe, and join. The original file is never modified."""
    model = model or settings.TRANSCRIPTION_MODEL
    workdir = src.parent / ".transcode"
    duration = probe_duration(src)
    try:
        prepared = normalise(src, workdir)
        pieces = split(prepared, workdir, probe_duration(prepared) or duration)
        oversized = [p for p in pieces if p.stat().st_size > MAX_UPLOAD_BYTES]
        if oversized:
            raise RuntimeError(
                f"{oversized[0].name} is still {oversized[0].stat().st_size} bytes "
                "after conversion, which the transcription API will refuse."
            )
        text = "\n\n".join(t for t in (transcribe_file(p, model) for p in pieces) if t)
        return Transcript(text=text, model=model, chunk_count=len(pieces),
                          duration_seconds=duration)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
