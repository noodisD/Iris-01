"""
Persistence for staged imports.

Deliberately not in `agent/database.py`. That module is the data layer for the
things IRIS is *about* — entries, themes, occurrences — and it is already long
enough that finding anything in it is work. Staging is scaffolding: two tables
that exist only between an upload and a commit, and which nothing else in the
system reads. Keeping them here means the whole feature can be read, and later
removed, in one place.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from psycopg2.extras import Json, execute_values

from ..database import db
from .dates import from_file_time

logger = logging.getLogger(__name__)

_WHITESPACE = re.compile(r"\s+")


def content_hash(text: str) -> str:
    """Identity of an entry's text, for recognising a re-import.

    Whitespace-normalised so the same entry exported twice — once with CRLF
    line endings, once with LF — is recognised as one entry rather than two.
    """
    return hashlib.sha256(_WHITESPACE.sub(" ", (text or "").strip()).encode()).hexdigest()


# --- batches ---------------------------------------------------------------

def create_batch(user_id: int, kind: str, original_filename: str | None,
                 stored_path: str | None) -> int:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO import_batches (user_id, kind, original_filename, stored_path)
               VALUES (%s, %s, %s, %s) RETURNING id;""",
            (user_id, kind, original_filename, stored_path),
        )
        batch_id = cur.fetchone()[0]
        conn.commit()
        return batch_id


def update_batch(batch_id: int, **fields: Any) -> None:
    allowed = {"status", "error", "adapter", "detected", "entry_count", "committed_count"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"cannot set {unknown} on a batch")
    if not fields:
        return
    assignments = ", ".join(f"{k} = %s" for k in fields)
    values = [Json(v) if k == "detected" else v for k, v in fields.items()]
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE import_batches SET {assignments}, updated_at = NOW() WHERE id = %s;",
            (*values, batch_id),
        )
        conn.commit()


_BATCH_COLUMNS = """id, user_id, kind, adapter, detected, original_filename,
                    stored_path, status, error, entry_count, committed_count,
                    created_at, updated_at"""


def _batch_row(row) -> dict:
    keys = ("id", "user_id", "kind", "adapter", "detected", "original_filename",
            "stored_path", "status", "error", "entry_count", "committed_count",
            "created_at", "updated_at")
    return dict(zip(keys, row))


def get_batch(batch_id: int, user_id: int) -> dict | None:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_BATCH_COLUMNS} FROM import_batches WHERE id = %s AND user_id = %s;",
            (batch_id, user_id),
        )
        row = cur.fetchone()
        return _batch_row(row) if row else None


def list_batches(user_id: int, limit: int = 25) -> list[dict]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""SELECT {_BATCH_COLUMNS} FROM import_batches
                WHERE user_id = %s ORDER BY created_at DESC LIMIT %s;""",
            (user_id, limit),
        )
        return [_batch_row(r) for r in cur.fetchall()]


def delete_batch(batch_id: int, user_id: int) -> bool:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM import_batches WHERE id = %s AND user_id = %s;",
            (batch_id, user_id),
        )
        deleted = cur.rowcount > 0
        conn.commit()
        return deleted


# --- items -----------------------------------------------------------------

_ITEM_COLUMNS = """id, batch_id, user_id, source_name, title, content, content_hash,
                   audio_path, entry_date, date_source, date_confidence, tags,
                   warnings, status, reflection_id, error, file_modified_at,
                   metrics"""
_ITEM_KEYS = ("id", "batch_id", "user_id", "source_name", "title", "content",
              "content_hash", "audio_path", "entry_date", "date_source",
              "date_confidence", "tags", "warnings", "status", "reflection_id", "error",
              "file_modified_at", "metrics")


def _item_row(row) -> dict:
    return dict(zip(_ITEM_KEYS, row))


def replace_items(batch_id: int, user_id: int, items: list[dict]) -> int:
    """Stage a batch's entries, discarding anything staged before.

    Used by both the first parse and a re-parse under a different adapter, so
    changing format cannot leave a mixture of two readings behind.
    """
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM import_items WHERE batch_id = %s;", (batch_id,))
        if items:
            execute_values(
                cur,
                """INSERT INTO import_items
                   (batch_id, user_id, source_name, title, content, content_hash,
                    audio_path, entry_date, date_source, date_confidence, tags, warnings,
                    status, file_modified_at, metrics)
                   VALUES %s""",
                [
                    (batch_id, user_id, i.get("source_name"), i.get("title"),
                     i.get("content", ""), i.get("content_hash"), i.get("audio_path"),
                     i.get("entry_date"), i.get("date_source"),
                     i.get("date_confidence", "unknown"),
                     Json(i.get("tags") or []), Json(i.get("warnings") or []),
                     i.get("status", "staged"), i.get("file_modified_at"),
                     Json(i["metrics"]) if i.get("metrics") else None)
                    for i in items
                ],
            )
        conn.commit()
        return len(items)


def list_items(batch_id: int, user_id: int, status: str | None = None,
               limit: int = 500, offset: int = 0) -> list[dict]:
    clause = " AND status = %s" if status else ""
    params = [batch_id, user_id] + ([status] if status else []) + [limit, offset]
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""SELECT {_ITEM_COLUMNS} FROM import_items
                WHERE batch_id = %s AND user_id = %s{clause}
                ORDER BY entry_date NULLS FIRST, id LIMIT %s OFFSET %s;""",
            params,
        )
        return [_item_row(r) for r in cur.fetchall()]


def get_item(item_id: int, user_id: int) -> dict | None:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT {_ITEM_COLUMNS} FROM import_items WHERE id = %s AND user_id = %s;",
            (item_id, user_id),
        )
        row = cur.fetchone()
        return _item_row(row) if row else None


def update_item(item_id: int, user_id: int, **fields: Any) -> dict | None:
    allowed = {"entry_date", "date_source", "date_confidence", "content",
               "content_hash", "status", "reflection_id", "error", "audio_path"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"cannot set {unknown} on an item")
    if not fields:
        return get_item(item_id, user_id)
    assignments = ", ".join(f"{k} = %s" for k in fields)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE import_items SET {assignments} WHERE id = %s AND user_id = %s;",
            (*fields.values(), item_id, user_id),
        )
        conn.commit()
    return get_item(item_id, user_id)


def bulk_update(item_ids: list[int], user_id: int, **fields: Any) -> int:
    if not item_ids or not fields:
        return 0
    allowed = {"entry_date", "date_source", "date_confidence", "status"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"cannot bulk-set {unknown}")
    assignments = ", ".join(f"{k} = %s" for k in fields)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE import_items SET {assignments} WHERE id = ANY(%s) AND user_id = %s;",
            (*fields.values(), item_ids, user_id),
        )
        changed = cur.rowcount
        conn.commit()
        return changed


def batches_of(item_ids: list[int], user_id: int) -> list[int]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT batch_id FROM import_items
               WHERE id = ANY(%s) AND user_id = %s;""",
            (item_ids, user_id),
        )
        return [r[0] for r in cur.fetchall()]


def use_file_dates(item_ids: list[int], user_id: int) -> int:
    """Date undated entries by the day their file was last saved, as a guess.

    Only entries with no date and a recorded file time. A file time never
    replaces a date the export gave: that date came from the writing, this one
    from the filesystem.
    """
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id, file_modified_at FROM import_items
               WHERE id = ANY(%s) AND user_id = %s
                 AND entry_date IS NULL AND file_modified_at IS NOT NULL;""",
            (item_ids, user_id),
        )
        rows = cur.fetchall()
        for item_id, modified in rows:
            guess = from_file_time(modified)
            cur.execute(
                """UPDATE import_items
                   SET entry_date = %s, date_source = %s, date_confidence = %s
                   WHERE id = %s;""",
                (guess.value, guess.source, guess.confidence, item_id),
            )
        conn.commit()
    return len(rows)


def counts(batch_id: int) -> dict[str, int]:
    """How the batch stands: totals by status, plus how many still lack a date."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT status, COUNT(*) FROM import_items WHERE batch_id = %s GROUP BY status;",
            (batch_id,),
        )
        by_status = {row[0]: row[1] for row in cur.fetchall()}
        cur.execute(
            """SELECT COUNT(*) FROM import_items
               WHERE batch_id = %s AND status = 'staged' AND entry_date IS NULL;""",
            (batch_id,),
        )
        by_status["needs_date"] = cur.fetchone()[0]
        # A recording whose transcript has not arrived has nothing to commit
        # yet. Counted separately from needs_date because the remedy is
        # different: a missing date is something the owner supplies, a missing
        # transcript is something to wait for.
        cur.execute(
            """SELECT COUNT(*) FROM import_items
               WHERE batch_id = %s AND status = 'staged'
                 AND audio_path IS NOT NULL AND btrim(content) = '';""",
            (batch_id,),
        )
        by_status["awaiting_transcript"] = cur.fetchone()[0]
        cur.execute(
            "SELECT MIN(entry_date), MAX(entry_date) FROM import_items WHERE batch_id = %s;",
            (batch_id,),
        )
        first, last = cur.fetchone()
    by_status["total"] = sum(
        v for k, v in by_status.items()
        if k not in ("needs_date", "awaiting_transcript")
    )
    by_status["earliest"] = first
    by_status["latest"] = last
    return by_status


def mark_duplicates(batch_id: int, user_id: int) -> int:
    """Flag entries already present, so a second import of the same export is
    visibly skipped rather than silently doubling the journal.

    Two sources of collision: another entry in this same batch, and a reflection
    that already exists. Marked rather than deleted — the owner can still include
    one deliberately, and seeing what was skipped is part of trusting the import.
    """
    with db.connection() as conn, conn.cursor() as cur:
        # Against reflections already stored, matched on the same key the unique
        # index uses, plus legacy rows that predate content_hash.
        cur.execute(
            """UPDATE import_items i SET status = 'duplicate'
               WHERE i.batch_id = %s AND i.user_id = %s AND i.status = 'staged'
                 AND i.entry_date IS NOT NULL AND i.content_hash IS NOT NULL
                 AND EXISTS (
                     SELECT 1 FROM reflections r
                     WHERE r.user_id = i.user_id
                       AND r.reflection_date = i.entry_date
                       AND (r.content_hash = i.content_hash
                            OR encode(sha256(regexp_replace(btrim(r.content), '\\s+', ' ', 'g')::bytea), 'hex') = i.content_hash)
                 );""",
            (batch_id, user_id),
        )
        against_existing = cur.rowcount

        # Against each other: keep the first, mark the rest.
        cur.execute(
            """UPDATE import_items SET status = 'duplicate'
               WHERE id IN (
                   SELECT id FROM (
                       SELECT id, ROW_NUMBER() OVER (
                           PARTITION BY entry_date, content_hash ORDER BY id
                       ) AS rn
                       FROM import_items
                       WHERE batch_id = %s AND status = 'staged'
                         AND entry_date IS NOT NULL AND content_hash IS NOT NULL
                   ) ranked WHERE rn > 1
               );""",
            (batch_id,),
        )
        within_batch = cur.rowcount
        conn.commit()

    total = against_existing + within_batch
    if total:
        logger.info(
            f"Batch {batch_id}: {against_existing} already imported, "
            f"{within_batch} repeated inside the upload"
        )
    return total


def reflection_ids_for_batch(batch_id: int, user_id: int) -> list[int]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT reflection_id FROM import_items
               WHERE batch_id = %s AND user_id = %s AND reflection_id IS NOT NULL;""",
            (batch_id, user_id),
        )
        return [r[0] for r in cur.fetchall()]
