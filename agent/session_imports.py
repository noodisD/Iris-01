"""A session waiting for the owner, and the click that brings it in (ADR-0028).

A transcript arrives with speaker labels and nothing else: no date, and no word
on which speaker is the owner. Both decide what IRIS may conclude from it, so a
session is staged here, sent nowhere, until the owner has given the day and the
time and said which speaker they are. Importing is the owner's click. Only then
is the session indexed for chat and read for patterns, at the cost shown before
the click.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
from datetime import UTC, datetime, timedelta

import psycopg2

from . import sessions
from .database import db
from .session_voices import estimate as voices_estimate, recordings_root

logger = logging.getLogger(__name__)

#: A session transcript is tens of kilobytes; anything near this is not one.
MAX_TRANSCRIPT_BYTES = 2_000_000
#: text-embedding-3-small, dollars per million tokens.
EMBEDDING_PRICE_PER_MTOK = 0.02
#: A voices pass takes minutes; one still "running" after this was cut off.
VOICES_STALE = timedelta(minutes=45)
_WHITESPACE = re.compile(r"\s+")
_STARTED = "%Y-%m-%dT%H:%M"
_COLUMNS = ("id", "status", "kind", "original_filename", "transcript", "transcript_hash",
            "started_at", "language", "owner_label", "therapist_label", "original_transcript",
            "audio_path", "audio_seconds", "voices_status", "voices_report", "voices_error",
            "reflection_id", "created_at", "updated_at")


class SessionImportError(Exception):
    """Something the owner can put right, said so they can."""


def transcript_hash(text: str) -> str:
    """The transcript's identity: its words, not its labels or layout.

    So the same session is recognised when it is uploaded twice, and still
    after its speakers have been corrected.
    """
    found, _ = sessions.segments(text)
    words = " ".join(segment.text for segment in found) if found else (text or "")
    return hashlib.sha256(_WHITESPACE.sub(" ", words.strip()).encode()).hexdigest()


def estimate(content: str) -> dict:
    """What importing this session will cost, worked out without sending anything.

    Two things are sent: the passages, to be embedded for chat, and the whole
    session once to the reader, followed by one field check per account found.
    The number of accounts is not known until the reader has run, so it is
    counted generously from how much the owner said.
    """
    from .config import settings
    from .connections import FIELD_PROMPT
    from .episodes import SYSTEM_PROMPT as READ_PROMPT
    from .intelligence import Intelligence

    cut = sessions.passages(content)
    # Polish and other inflected languages run to more tokens per character
    # than English; three characters a token keeps the guess on the high side.
    indexing = sum(len(passage.text) for passage in cut) / 3 / 1_000_000 * EMBEDDING_PRICE_PER_MTOK
    accounts = max(4, len(sessions.owner_words(content)) // 500)
    tokens_in = (len(READ_PROMPT) + len(sessions.for_model(content))) // 3 \
        + accounts * (len(FIELD_PROMPT) + 1500) // 3
    tokens_out = 4000 + accounts * 400
    model, tier = settings.OPENAI_WORKER_MODEL, settings.OPENAI_WORKER_SERVICE_TIER or None
    price = Intelligence.PRICE_PER_MTOK.get(model)
    factor = Intelligence.TIER_PRICE_FACTOR.get(tier or "", 1.0)
    reading = (tokens_in * price[0] + tokens_out * price[1]) / 1_000_000 * factor if price else None
    where = f"{model} on {tier.capitalize()}" if tier in Intelligence.TIER_PRICE_FACTOR else model
    read_text = f"about ${reading:.3f}" if reading is not None else "price unknown here"
    return {
        "passages": len(cut),
        "indexingDollars": round(indexing, 5),
        "readingDollars": round(reading, 4) if reading is not None else None,
        "text": (f"Importing sends the session to OpenAI: {len(cut)} passages indexed for chat "
                 f"(about ${indexing:.4f}), and one reading for patterns with {where} ({read_text}). "
                 "Updating your patterns afterwards usually adds a few cents."),
    }


class SessionImports:
    def __init__(self, user_id: int):
        self.user_id = user_id

    # --- reading rows -------------------------------------------------------

    def _row(self, cur, import_id: int, lock: bool = False) -> dict:
        cur.execute(f"""SELECT {', '.join(_COLUMNS)} FROM session_imports
                         WHERE id = %s AND user_id = %s{' FOR UPDATE' if lock else ''};""",
                    (import_id, self.user_id))
        row = cur.fetchone()
        if row is None:
            raise LookupError("No such session import.")
        found = dict(zip(_COLUMNS, row, strict=True))
        if (found["voices_status"] == "running"
                and found["updated_at"] < datetime.now(UTC) - VOICES_STALE):
            # The pass was cut off (IRIS restarted mid-way) and will not finish
            # on its own; saying "listening" forever would also hold the import.
            found["voices_status"] = "failed"
            found["voices_error"] = "The last attempt stopped before it finished. Try again."
        return found

    def get(self, import_id: int) -> dict:
        with db.connection() as conn, conn.cursor() as cur:
            row = self._row(cur, import_id)
            earlier = self._imported_twin(cur, row)
        return self.describe(row, earlier)

    def list(self, limit: int = 10) -> list[dict]:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute(f"""SELECT {', '.join(_COLUMNS)} FROM session_imports
                             WHERE user_id = %s AND status <> 'discarded'
                             ORDER BY created_at DESC, id DESC LIMIT %s;""",
                        (self.user_id, limit))
            rows = [dict(zip(_COLUMNS, row, strict=True)) for row in cur.fetchall()]
            twins = {row["id"]: self._imported_twin(cur, row) for row in rows}
        return [self.describe(row, twins[row["id"]]) for row in rows]

    def _imported_twin(self, cur, row: dict) -> dict | None:
        """Another import of the same transcript that is in the journal now."""
        cur.execute("""SELECT id, updated_at FROM session_imports
                        WHERE user_id = %s AND transcript_hash = %s AND id <> %s
                          AND status = 'imported' AND reflection_id IS NOT NULL
                        ORDER BY updated_at DESC LIMIT 1;""",
                    (self.user_id, row["transcript_hash"], row["id"]))
        twin = cur.fetchone()
        return {"importId": str(twin[0]), "on": twin[1].date().isoformat()} if twin else None

    # --- the contract -------------------------------------------------------

    @staticmethod
    def _missing(row: dict, labels: set[str]) -> list[str]:
        missing = []
        if row["started_at"] is None:
            missing.append("the day and time of the session")
        if not row["owner_label"] or row["owner_label"] not in labels:
            missing.append("which speaker is you")
        return missing

    @staticmethod
    def _content(row: dict, found: list[sessions.Segment]) -> str:
        started = row["started_at"].strftime(_STARTED) if row["started_at"] else "unknown"
        return sessions.compose(found, kind=row["kind"], started=started,
                                language=row["language"] or "unknown",
                                owner=row["owner_label"] or "unknown",
                                therapist=row["therapist_label"])

    def describe(self, row: dict, earlier: dict | None = None) -> dict:
        found, preamble = sessions.segments(row["transcript"])
        labels = {segment.label for segment in found}

        def role(label: str) -> str:
            if label == row["owner_label"]:
                return "owner"
            return "therapist" if label == row["therapist_label"] else "unclear"

        turns = sum(1 for index, segment in enumerate(found)
                    if index == 0 or found[index - 1].label != segment.label)
        removed = row["status"] == "imported" and row["reflection_id"] is None
        return {
            "id": str(row["id"]),
            "status": "staged" if removed else row["status"],
            "kind": row["kind"],
            "filename": row["original_filename"],
            "createdAt": row["created_at"].isoformat(),
            "startedAt": row["started_at"].strftime(_STARTED) if row["started_at"] else None,
            "language": row["language"],
            "owner": row["owner_label"],
            "therapist": row["therapist_label"],
            "speakers": [{**speaker, "role": role(speaker["label"])} for speaker in sessions.speakers(found)],
            "segments": len(found),
            "turns": turns,
            "durationSeconds": found[-1].at if found else None,
            "leftOut": preamble,
            "missing": self._missing(row, labels),
            "alreadyImported": earlier,
            "estimate": estimate(self._content(row, found)) if found else None,
            "reflectionId": str(row["reflection_id"]) if row["reflection_id"] else None,
            "voices": {"status": row["voices_status"], "report": row["voices_report"],
                       "error": row["voices_error"], "hasRecording": bool(row["audio_path"]),
                       "estimate": voices_estimate(row["audio_seconds"]) if row["audio_path"] else None},
        }

    # --- staging ------------------------------------------------------------

    def stage(self, text: str, filename: str | None = None) -> dict:
        """Keep an uploaded transcript for the owner to check. Nothing is sent."""
        found, _ = sessions.segments(text)
        if len(found) < 2 or len({segment.label for segment in found}) < 2:
            raise SessionImportError(
                "No conversation was found in that file. A session transcript marks each turn "
                "with its time and speaker, like **[00:01:02] Name:**, with the words below it.")
        owner, therapist = sessions.guess_roles(found)
        language = sessions.guess_language(" ".join(segment.text for segment in found))
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO session_imports
                               (user_id, original_filename, transcript, transcript_hash,
                                language, owner_label, therapist_label)
                           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;""",
                        (self.user_id, filename, text, transcript_hash(text), language, owner, therapist))
            import_id = cur.fetchone()[0]
            conn.commit()
        logger.info(f"Session import {import_id} staged: {len(found)} segments")
        return self.get(import_id)

    def update(self, import_id: int, changes: dict) -> dict:
        """Set the day and time, the language, or who is who, before importing.

        `changes` holds only what the owner changed: startedAt ("YYYY-MM-DDTHH:MM"),
        language, owner and therapist (a label, or null for none).
        """
        with db.connection() as conn, conn.cursor() as cur:
            row = self._row(cur, import_id, lock=True)
            self._require_staged(row)
            labels = {segment.label for segment in sessions.segments(row["transcript"])[0]}
            sets: dict[str, object] = {}
            if "startedAt" in changes:
                try:
                    sets["started_at"] = datetime.strptime(changes["startedAt"] or "", _STARTED)
                except ValueError:
                    raise SessionImportError("Give the day and time as YYYY-MM-DDTHH:MM.") from None
            if "language" in changes:
                language = (changes["language"] or "").strip().lower()
                if not re.fullmatch(r"[a-z]{2,3}", language):
                    raise SessionImportError("Give the language as a two-letter code, like pl or en.")
                sets["language"] = language
            for key, column in (("owner", "owner_label"), ("therapist", "therapist_label")):
                if key in changes:
                    label = changes[key]
                    if label is not None and label not in labels:
                        raise SessionImportError(f"No speaker in this transcript is called {label!r}.")
                    sets[column] = label
            owner = sets.get("owner_label", row["owner_label"])
            if owner is not None and owner == sets.get("therapist_label", row["therapist_label"]):
                raise SessionImportError("One speaker cannot be both you and the therapist.")
            if sets:
                assignments = ", ".join(f"{column} = %s" for column in sets)
                cur.execute(f"""UPDATE session_imports SET {assignments}, updated_at = NOW()
                                 WHERE id = %s AND user_id = %s;""",
                            (*sets.values(), import_id, self.user_id))
            conn.commit()
        return self.get(import_id)

    # --- the owner's click --------------------------------------------------

    def commit(self, import_id: int) -> dict:
        """Put the session in the journal. This is the click that sends it out.

        Claimed before the reflection is written, so a double click cannot
        import one session twice; released again if writing it fails.
        """
        with db.connection() as conn, conn.cursor() as cur:
            row = self._row(cur, import_id, lock=True)
            self._require_staged(row)
            if row["voices_status"] in ("queued", "running"):
                raise SessionImportError("The speakers are being sorted out from the recording. "
                                         "Import when that has finished.")
            found, _ = sessions.segments(row["transcript"])
            missing = self._missing(row, {segment.label for segment in found})
            if missing:
                raise SessionImportError("Before importing, say " + " and ".join(missing) + ".")
            twin = self._imported_twin(cur, row)
            if twin:
                raise SessionImportError(f"This transcript is already in your journal (imported {twin['on']}).")
            cur.execute("""UPDATE session_imports SET status = 'importing', updated_at = NOW()
                            WHERE id = %s AND user_id = %s;""", (import_id, self.user_id))
            conn.commit()
        content = self._content(row, found)
        try:
            from .importing.store import content_hash
            reflection_id = db.create_reflection(
                self.user_id, content, reflection_date=row["started_at"].date(),
                source="session", content_format="session", content_hash=content_hash(content),
                date_source="user", date_confidence="certain")
        except psycopg2.errors.UniqueViolation:
            self._release(import_id)
            raise SessionImportError("This session is already in your journal.") from None
        except Exception:
            self._release(import_id)
            raise
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE session_imports SET status = 'imported', reflection_id = %s, updated_at = NOW()
                            WHERE id = %s AND user_id = %s;""", (reflection_id, import_id, self.user_id))
            conn.commit()
        logger.info(f"Session import {import_id} became reflection {reflection_id}")
        self._drop_recording(import_id)
        from .importing.service import _kick_the_queue
        _kick_the_queue()
        return self.get(import_id)

    def _release(self, import_id: int) -> None:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE session_imports SET status = 'staged', updated_at = NOW()
                            WHERE id = %s AND user_id = %s AND reflection_id IS NULL;""",
                        (import_id, self.user_id))
            conn.commit()

    @staticmethod
    def _require_staged(row: dict) -> None:
        """Only a session still waiting for the owner can change or be imported.

        An imported session whose entry has since been deleted is waiting again.
        """
        if row["status"] == "discarded":
            raise SessionImportError("This session was discarded. Upload it again to import it.")
        if row["status"] == "importing":
            raise SessionImportError("This session is being imported.")
        if row["reflection_id"] is not None:
            raise SessionImportError("This session is already in your journal. Undo the import to change it.")

    def discard(self, import_id: int) -> dict:
        """Drop a staged session. One already in the journal is undone instead."""
        with db.connection() as conn, conn.cursor() as cur:
            row = self._row(cur, import_id, lock=True)
            if row["reflection_id"] is not None:
                raise SessionImportError("This session is in your journal. Undo the import first.")
            cur.execute("""UPDATE session_imports SET status = 'discarded', updated_at = NOW()
                            WHERE id = %s AND user_id = %s;""", (import_id, self.user_id))
            conn.commit()
        self._drop_recording(import_id)
        return self.get(import_id)

    def undo(self, import_id: int) -> dict:
        """Take the session out of the journal and back to staged, to fix and import again."""
        with db.connection() as conn, conn.cursor() as cur:
            row = self._row(cur, import_id, lock=True)
        if row["reflection_id"] is not None:
            db.delete_reflection(row["reflection_id"])
        self._release(import_id)
        return self.get(import_id)

    # --- the recording, and the voices pass ---------------------------------

    def keep_recording(self, import_id: int, src, filename: str) -> dict:
        """Keep the session's recording here, for the voices pass. Nothing is sent."""
        from pathlib import Path

        from .transcription import probe_duration

        with db.connection() as conn, conn.cursor() as cur:
            row = self._row(cur, import_id, lock=True)
            self._require_staged(row)
            if row["voices_status"] in ("queued", "running"):
                raise SessionImportError("The speakers are being sorted out from the recording already.")
            root = recordings_root()
            root.mkdir(parents=True, exist_ok=True)
            name = f"{import_id}{Path(filename).suffix.lower()}"
            target = root / name
            shutil.move(str(src), target)
            if row["audio_path"] and row["audio_path"] != name:
                (root / row["audio_path"]).unlink(missing_ok=True)
            cur.execute("""UPDATE session_imports SET audio_path = %s, audio_seconds = %s,
                                  voices_status = CASE WHEN voices_status = 'done' THEN 'done' ELSE 'none' END,
                                  voices_error = NULL, updated_at = NOW()
                            WHERE id = %s AND user_id = %s;""",
                        (name, probe_duration(target), import_id, self.user_id))
            conn.commit()
        return self.get(import_id)

    def start_voices(self, import_id: int) -> dict:
        """The owner's click that sends the recording to tell the voices apart."""
        from .work_queue import enqueue, worker

        with db.connection() as conn, conn.cursor() as cur:
            row = self._row(cur, import_id, lock=True)
            self._require_staged(row)
            if not row["audio_path"]:
                raise SessionImportError("Add the recording first.")
            if not row["owner_label"] or not row["therapist_label"]:
                raise SessionImportError("Say which speaker is you and which is the therapist first.")
            if row["voices_status"] in ("queued", "running"):
                raise SessionImportError("The speakers are being sorted out already.")
            cur.execute("""UPDATE session_imports SET voices_status = 'queued', voices_error = NULL,
                                  updated_at = NOW() WHERE id = %s AND user_id = %s;""",
                        (import_id, self.user_id))
            conn.commit()
        enqueue("session_voices", import_id, self.user_id)
        worker.wake()
        return self.get(import_id)

    def apply_voices(self, import_id: int, transcript: str, report: dict) -> bool:
        """Keep the relabelled transcript, and the one it replaced to put back.

        False when the session moved on while it was being listened to (it was
        imported or discarded): nothing is changed then.
        """
        from psycopg2.extras import Json

        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE session_imports
                              SET original_transcript = COALESCE(original_transcript, transcript),
                                  transcript = %s, voices_status = 'done', voices_report = %s,
                                  voices_error = NULL, updated_at = NOW()
                            WHERE id = %s AND user_id = %s AND status IN ('staged', 'imported')
                              AND reflection_id IS NULL AND transcript_hash = %s;""",
                        (transcript, Json(report), import_id, self.user_id, transcript_hash(transcript)))
            applied = cur.rowcount == 1
            conn.commit()
        return applied

    def undo_voices(self, import_id: int) -> dict:
        """Put the transcriber's own speaker labels back."""
        with db.connection() as conn, conn.cursor() as cur:
            row = self._row(cur, import_id, lock=True)
            self._require_staged(row)
            if row["voices_status"] in ("queued", "running"):
                raise SessionImportError("The speakers are being sorted out; wait for it to finish.")
            cur.execute("""UPDATE session_imports
                              SET transcript = COALESCE(original_transcript, transcript),
                                  original_transcript = NULL, voices_status = 'none',
                                  voices_report = NULL, voices_error = NULL, updated_at = NOW()
                            WHERE id = %s AND user_id = %s;""", (import_id, self.user_id))
            conn.commit()
        return self.get(import_id)

    def _drop_recording(self, import_id: int) -> None:
        """A recording is kept only while it can still be used; the journal keeps the words."""
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT audio_path FROM session_imports WHERE id = %s AND user_id = %s FOR UPDATE;",
                        (import_id, self.user_id))
            row = cur.fetchone()
            cur.execute("""UPDATE session_imports SET audio_path = NULL, audio_seconds = NULL,
                                  updated_at = NOW() WHERE id = %s AND user_id = %s;""",
                        (import_id, self.user_id))
            conn.commit()
        if row and row[0]:
            (recordings_root() / row[0]).unlink(missing_ok=True)
