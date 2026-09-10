"""
Keeping a voice journal, and turning it into words.

The recording is kept, not discarded once transcribed. Transcription is lossy
and irreversible: a garbled sentence cannot be recovered from its transcript,
and a better model next year cannot re-read a file that is gone. So the original
bytes are what get stored, conversions happen on throwaway copies, and the
transcript is treated as a derived artefact.

Storage is content-addressed. Uploading the same recording twice writes the same
path, which is the cheapest possible de-duplication and needs no bookkeeping.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from datetime import date
from pathlib import Path

from ..timeutils import to_utc
from ..transcription import probe_duration, transcribe
from . import store
from .service import data_root

logger = logging.getLogger(__name__)

#: What a browser or a phone actually produces.
AUDIO_SUFFIXES = {".m4a", ".mp3", ".wav", ".webm", ".ogg", ".oga", ".mp4",
                  ".mpga", ".mpeg", ".flac", ".aac"}

_MEDIA_TYPES = {
    ".m4a": "audio/mp4", ".mp4": "audio/mp4", ".mp3": "audio/mpeg",
    ".mpga": "audio/mpeg", ".mpeg": "audio/mpeg", ".wav": "audio/wav",
    ".webm": "audio/webm", ".ogg": "audio/ogg", ".oga": "audio/ogg",
    ".flac": "audio/flac", ".aac": "audio/aac",
}


def audio_root() -> Path:
    return data_root() / "audio"


def media_type_for(path: str | Path) -> str:
    return _MEDIA_TYPES.get(Path(path).suffix.lower(), "application/octet-stream")


def resolve(rel_path: str) -> Path:
    """An absolute path inside the audio root, or an error.

    Only relative paths are stored, so the data directory can move. This is also
    the one place a stored value is turned back into a filesystem path, which
    makes it the right place to refuse anything pointing outside.
    """
    root = audio_root()
    target = (root / rel_path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f"{rel_path!r} resolves outside the audio directory")
    return target


def store_recording(user_id: int, src: Path, original_name: str) -> dict:
    """Move a recording into permanent storage, keyed by its own content."""
    digest = hashlib.sha256()
    with src.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    sha = digest.hexdigest()

    suffix = Path(original_name).suffix.lower() or src.suffix.lower() or ".bin"
    rel = f"{user_id}/{sha[:2]}/{sha}{suffix}"
    target = audio_root() / rel
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        # Same bytes, already kept. Nothing to write.
        src.unlink(missing_ok=True)
    else:
        shutil.move(str(src), target)

    return {
        "rel_path": rel,
        "sha256": sha,
        "byte_size": target.stat().st_size,
        "media_type": media_type_for(target),
        "duration_seconds": probe_duration(target),
    }


def stage_recording(user_id: int, batch_id: int, src: Path, original_name: str,
                    recorded_at: str | None = None) -> dict:
    """Store the audio and stage an entry for it, awaiting its transcript.

    The entry is created empty and dated now only when the browser told us when
    the recording was made. An uploaded file whose date is unknown stays
    undated, exactly like an undated text entry, and is refused at commit until
    someone says when it happened.
    """
    stored = store_recording(user_id, src, original_name)

    entry_date: date | None = None
    confidence = "unknown"
    source = "unknown"
    if recorded_at:
        try:
            entry_date = to_utc(recorded_at).date()
            confidence, source = "certain", "user"
        except Exception:
            entry_date = None

    item_id = _append_item(
        batch_id, user_id, stored, original_name, entry_date, confidence, source
    )
    return {"item_id": item_id, **stored}


def _append_item(batch_id: int, user_id: int, stored: dict, original_name: str,
                 entry_date, confidence: str, date_source: str) -> int:
    from ..database import db

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO import_items
               (batch_id, user_id, source_name, title, content, audio_path,
                entry_date, date_source, date_confidence)
               VALUES (%s, %s, %s, %s, '', %s, %s, %s, %s) RETURNING id;""",
            (batch_id, user_id, original_name, original_name,
             stored["rel_path"], entry_date, date_source, confidence),
        )
        item_id = cur.fetchone()[0]
        conn.commit()
        return item_id


def run_transcription_job(item_id: int) -> None:
    """Queue handler: transcribe one staged recording.

    Raises on failure so the durable queue retries it — a provider outage should
    delay a transcript, not lose the recording. The audio is already stored by
    the time this runs, so nothing the owner gave us is at risk either way.
    """
    from ..database import db

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT user_id, audio_path, entry_date FROM import_items WHERE id = %s;",
            (item_id,),
        )
        row = cur.fetchone()
    if not row:
        logger.warning(f"Transcription job for item {item_id}: item is gone")
        return
    user_id, audio_path, entry_date = row
    if not audio_path:
        logger.warning(f"Transcription job for item {item_id}: no audio attached")
        return

    path = resolve(audio_path)
    result = transcribe(path)
    text = result.text.strip()

    if not text:
        # A silent recording is not a failure to retry; it is an empty entry,
        # and saying so is more useful than an endless backoff.
        store.update_item(item_id, user_id, status="failed",
                          error="Nothing could be heard in this recording.")
        return

    warning = None
    if entry_date is None:
        warning = "This recording has no date yet — set one before importing."

    store.update_item(item_id, user_id, content=text,
                      content_hash=store.content_hash(text), error=warning)
    logger.info(
        f"Transcribed item {item_id} with {result.model} "
        f"({result.chunk_count} chunk(s), {len(text)} characters)"
    )


def enqueue_transcription(item_id: int, user_id: int) -> None:
    from ..work_queue import enqueue, worker

    enqueue("transcription", item_id, user_id)
    worker.wake()
