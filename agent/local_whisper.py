"""A recording written down on this machine, by Whisper (ADR-0030).

The hosted diarizing transcriber hears who is speaking well, but its words
drift on long Polish recordings: phrases repeated many times, whole sentences
that were never said. Whisper large-v3, run locally, writes the words far more
faithfully and sends nothing anywhere. It runs in its own Python environment
(`WHISPER_PYTHON`), so the server neither imports the model nor holds its GPU
memory, and is simply not used where that environment is not set up.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import settings

logger = logging.getLogger(__name__)

WORKER = Path(__file__).resolve().parent.parent / "scripts" / "whisper_words.py"
#: A long session on the CPU takes a while; this is only there to end a hang.
TIMEOUT_SECONDS = 4 * 3600


class WhisperFailed(Exception):
    pass


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str


def available() -> bool:
    return bool(settings.WHISPER_PYTHON) and Path(settings.WHISPER_PYTHON).exists()


def _env(python: Path) -> dict[str, str]:
    """The GPU libraries installed in Whisper's environment, where the loader looks."""
    env = dict(os.environ, PYTHONPATH="")
    libs = sorted(str(p) for p in python.parent.parent.glob("lib/python*/site-packages/nvidia/*/lib"))
    if libs:
        env["LD_LIBRARY_PATH"] = os.pathsep.join([*libs, env.get("LD_LIBRARY_PATH", "")]).rstrip(os.pathsep)
    return env


def words(audio: Path, language: str | None) -> list[Word]:
    """Every word in the recording, with when it was said."""
    python = Path(settings.WHISPER_PYTHON)
    command = [str(python), str(WORKER), str(audio), "--model", settings.WHISPER_MODEL]
    if language and language != "unknown":
        command += ["--language", language]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
                              env=_env(python), check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WhisperFailed(type(exc).__name__) from exc
    if done.returncode != 0:
        tail = (done.stderr or "").strip().splitlines()
        raise WhisperFailed(tail[-1] if tail else f"exit {done.returncode}")
    try:
        result = json.loads(done.stdout)
        found = [Word(float(s), float(e), str(w)) for s, e, w in result["words"]]
    except (ValueError, KeyError, TypeError) as exc:
        raise WhisperFailed("unreadable output") from exc
    logger.info(f"Whisper on the {result.get('device')}: {len(found)} words")
    return found
