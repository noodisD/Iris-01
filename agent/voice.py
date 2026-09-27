"""Talking with IRIS: speech in, speech out, around an ordinary chat turn (ADR-0025).

A spoken turn is a typed turn with two conversions around it. What the owner
says is transcribed and then goes through the same chat route as typed text,
so it is stored, given context and answered exactly as typing would be. IRIS's
reply is turned into speech a sentence at a time by the client.

Audio is never kept. An utterance exists on disk only as a temporary file for
the length of one transcription request, deleted whatever happens, and logs
carry sizes and durations, never words.
"""
from __future__ import annotations

import logging
import tempfile
from collections.abc import Iterator
from pathlib import Path

from prompts.system_prompt import SYSTEM_PROMPT

from .approved_context import approved_context
from .config import settings
from .database import db
from .intelligence import Intelligence
from .transcription import transcribe_file

logger = logging.getLogger(__name__)

#: About five minutes of compressed speech. One turn, not a recording session.
MAX_UTTERANCE_BYTES = 5 * 1024 * 1024
#: One sentence or a few; the client asks for speech a sentence at a time.
MAX_SPEECH_CHARS = 600

#: Added to the system prompt for a turn that will be heard, not read.
SPOKEN_STYLE = (
    "# This turn is spoken aloud\n"
    "The owner is talking with you and will hear your reply, not read it. Answer in "
    "plain spoken English: no markdown, lists, headings, links or symbols read as "
    "words. Keep it to two to four sentences unless they ask for more, and ask at "
    "most one question."
)

#: How IRIS sounds.
VOICE_INSTRUCTIONS = (
    "Speak calmly and warmly, at an unhurried pace, like a thoughtful friend "
    "listening closely. Natural, plain English; no announcer tone."
)

_SUFFIX = {
    "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/wave": ".wav",
    "audio/webm": ".webm", "audio/ogg": ".ogg",
    "audio/mp4": ".m4a", "audio/m4a": ".m4a", "audio/x-m4a": ".m4a",
    "audio/mpeg": ".mp3",
}

# Rough sizes of one turn, for the estimate shown before anything is sent.
_HEARD_SECONDS = 15
_SPOKEN_SECONDS = 20
_REPLY_TOKENS = 300
#: Parts of chat's context that need a model call to build (the memory search
#: embeds the message) or change every turn, as characters.
_UNMEASURED_CONTEXT_CHARS = 5 * 300 + 20 * 400 + 2000


class VoiceError(ValueError):
    """An utterance or a sentence IRIS cannot take. The message says why."""


class TooLong(VoiceError):
    pass


def transcribe_utterance(audio: bytes, mime: str) -> str:
    """What the owner said, as text. The audio is deleted before this returns."""
    if not audio:
        raise VoiceError("Nothing was recorded.")
    if len(audio) > MAX_UTTERANCE_BYTES:
        raise TooLong("That was too long for one turn. Say it in shorter parts.")
    suffix = _SUFFIX.get((mime or "").split(";")[0].strip().lower())
    if suffix is None:
        raise VoiceError(f"IRIS cannot read audio of type {mime or 'unknown'}.")
    workdir = Path(settings.DATA_DIR) / "tmp"
    workdir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=workdir, suffix=suffix, delete=False) as fh:
        fh.write(audio)
        path = Path(fh.name)
    try:
        text = transcribe_file(path, settings.TRANSCRIPTION_MODEL, language="en")
    finally:
        path.unlink(missing_ok=True)
    logger.info("Transcribed an utterance of %d bytes", len(audio))
    return text.strip()


def open_speech(text: str) -> Iterator[bytes]:
    """IRIS's words as audio (MP3), streamed as the provider produces it.

    The request is made here, before the first byte is handed on, so a refusal
    or a missing key is an error the route can report instead of a response
    that starts and then breaks.
    """
    text = (text or "").strip()
    if not text:
        raise VoiceError("Nothing to say.")
    if len(text) > MAX_SPEECH_CHARS:
        raise VoiceError("Too much to say at once; send it a sentence at a time.")
    client = Intelligence().openai_client
    manager = client.audio.speech.with_streaming_response.create(
        model=settings.TTS_MODEL,
        voice=settings.TTS_VOICE,
        input=text,
        instructions=VOICE_INSTRUCTIONS,
        response_format="mp3",
    )
    response = manager.__enter__()

    def chunks() -> Iterator[bytes]:
        try:
            yield from response.iter_bytes(chunk_size=4096)
        finally:
            manager.__exit__(None, None, None)

    return chunks()


def estimate(user_id: int) -> dict:
    """What one spoken turn costs, worked out without sending anything.

    The chat turn dominates: IRIS reads its whole context every turn. The
    parts of that context held here are measured; the parts that need a model
    call to build are counted at their usual size.
    """
    reflections = db.get_latest_reflections(user_id, 5) or []
    measured = len(SYSTEM_PROMPT) + len(approved_context(user_id)) + sum(
        min(len(r.get("content") or ""), 1500) for r in reflections)
    tokens_in = (measured + _UNMEASURED_CONTEXT_CHARS + len(SPOKEN_STYLE)) // 4
    price = Intelligence.PRICE_PER_MTOK.get(settings.OPENAI_MODEL)
    per_minute = Intelligence.AUDIO_PRICE_PER_MINUTE
    parts = [
        price and (tokens_in * price[0] + _REPLY_TOKENS * price[1]) / 1_000_000,
        per_minute.get(settings.TRANSCRIPTION_MODEL) and per_minute[settings.TRANSCRIPTION_MODEL] * _HEARD_SECONDS / 60,
        per_minute.get(settings.TTS_MODEL) and per_minute[settings.TTS_MODEL] * _SPOKEN_SECONDS / 60,
    ]
    known = all(part is not None for part in parts)
    dollars = sum(part or 0 for part in parts)
    return {
        "model": settings.OPENAI_MODEL,
        "transcriptionModel": settings.TRANSCRIPTION_MODEL,
        "speechModel": settings.TTS_MODEL,
        "tokensIn": tokens_in,
        "perTurn": f"about ${dollars:.3f} a turn" if known
        else f"{tokens_in // 1000}k tokens a turn on {settings.OPENAI_MODEL} (price unknown here)",
    }
