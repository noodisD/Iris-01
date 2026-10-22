"""Repairs the doctor makes on its own: only what its checks class as safe-auto.

A safe-auto repair changes no evidence, sends nothing for reading, and costs at
most a few embeddings: deleting vectors that point at nothing, clearing a
reading copy whose words drifted, embedding an entry that has none, cutting a
long entry's missing passages, re-queueing a failed job once, pruning
telemetry, taking a backup. Everything else stays a suggestion for the owner.

Each repair re-queries what it fixes rather than trusting the report, then the
check runs again, and the outcome is kept in `health_fixes`.

    uv run python -m agent.doctor --fix
"""

from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from psycopg2.extras import Json

from ..database import db

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
#: Failed jobs that may be re-queued without asking: cheap, and evidence-safe.
#: A pattern update can cost dollars and a voices pass sends audio: those are the owner's.
REQUEUE_KINDS = ("reflection", "message", "habit", "discovery", "transcription")
#: A job re-queued once is not re-queued again for this long.
REQUEUE_ONCE_DAYS = 7

#: check id -> (repair, whether it writes the database)
FIXERS: dict[str, tuple[Callable[[], tuple[str, dict]], bool]] = {}


def fixer(check_id: str, writes_data: bool = True):
    def register(fn: Callable[[], tuple[str, dict]]):
        FIXERS[check_id] = (fn, writes_data)
        return fn
    return register


def _rows(sql: str, *args) -> list[tuple]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


@fixer("data.orphan_embeddings")
def orphan_embeddings() -> tuple[str, dict]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""DELETE FROM embeddings e WHERE
              (e.source_type = 'reflection' AND NOT EXISTS (SELECT 1 FROM reflections r WHERE r.id = e.source_id))
           OR (e.source_type = 'message' AND NOT EXISTS (SELECT 1 FROM conversation_messages m WHERE m.id = e.source_id))
           OR (e.source_type = 'session_passage' AND NOT EXISTS (SELECT 1 FROM session_passages p WHERE p.id = e.source_id))
           OR (e.source_type = 'entry_passage' AND NOT EXISTS (SELECT 1 FROM entry_passages p WHERE p.id = e.source_id))
           RETURNING e.source_type""")
        kinds = [row[0] for row in cur.fetchall()]
        conn.commit()
    return f"Deleted {len(kinds)} embedding(s) that pointed at deleted sources.", {"deleted": len(kinds)}


@fixer("data.reading_copies")
def reading_copies() -> tuple[str, dict]:
    from ..readable import same_words

    stale = [rid for rid, content, copy in _rows(
        "SELECT id, content, reading_copy FROM reflections WHERE reading_copy IS NOT NULL")
        if not same_words(content or "", copy)]
    if stale:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("UPDATE reflections SET reading_copy = NULL WHERE id = ANY(%s)", (stale,))
            conn.commit()
    return f"Cleared {len(stale)} reading cop(ies) whose words had drifted; the next read makes new ones.", \
        {"ids": stale}


@fixer("data.unembedded")
def unembedded() -> tuple[str, dict]:
    """Embed only: re-running the whole pipeline would count the entry in its themes twice."""
    from ..markdown_text import for_model
    from ..pipeline import generate_embedding
    from ..prompt_labels import strip_prompt_labels

    rows = _rows("""SELECT r.id, r.content, r.content_format FROM reflections r
                     WHERE r.content_format <> 'session' AND length(btrim(coalesce(r.content, ''))) > 0
                       AND r.processing_status = 'complete'
                       AND NOT EXISTS (SELECT 1 FROM embeddings e
                                        WHERE e.source_type = 'reflection' AND e.source_id = r.id)""")
    done = []
    for rid, content, fmt in rows:
        text = for_model(content, fmt)
        db.add_embedding("reflection", rid, "text-embedding-3-small",
                         generate_embedding(strip_prompt_labels(text).strip() or text))
        done.append(rid)
    return f"Embedded {len(done)} entr(ies) that had no embedding.", {"ids": done}


@fixer("data.passages")
def passages() -> tuple[str, dict]:
    """Long journal entries only; a session's passages are rebuilt by processing it again."""
    from ..entry_passages import MIN_WORDS
    from ..pipeline import _index_entry_passages

    rows = _rows(f"""SELECT r.id, r.user_id, r.content, r.content_format FROM reflections r
                      WHERE r.content_format <> 'session' AND r.processing_status = 'complete'
                        AND array_length(regexp_split_to_array(btrim(coalesce(r.content, '')), '\\s+'), 1) > {MIN_WORDS}
                        AND NOT EXISTS (SELECT 1 FROM entry_passages p WHERE p.reflection_id = r.id)""")
    cut = [rid for rid, uid, content, fmt in rows if _index_entry_passages(uid, rid, content, fmt)]
    return f"Cut passages for {len(cut)} of {len(rows)} long entr(ies) missing them.", {"ids": cut}


@fixer("queue.exhausted")
def requeue_exhausted() -> tuple[str, dict]:
    from ..work_queue import MAX_ATTEMPTS

    recent = {(kind, int(sid)) for kind, sid in _rows(
        """SELECT j->>0, j->>1 FROM health_fixes, jsonb_array_elements(details->'requeued') j
            WHERE check_id = 'queue.exhausted' AND fixed_at > NOW() - make_interval(days => %s)""",
        REQUEUE_ONCE_DAYS)}
    rows = _rows("""SELECT id, source_type, source_id FROM processing_queue
                     WHERE attempts >= %s AND last_error IS NOT NULL""", MAX_ATTEMPTS)
    requeued, left = [], []
    for qid, kind, sid in rows:
        if kind in REQUEUE_KINDS and (kind, sid) not in recent:
            with db.connection() as conn, conn.cursor() as cur:
                cur.execute("""UPDATE processing_queue SET attempts = 0, next_attempt_at = NOW()
                                WHERE id = %s""", (qid,))
                conn.commit()
            requeued.append([kind, sid])
        else:
            left.append([kind, sid])
    return (f"Re-queued {len(requeued)} failed job(s) once; {len(left)} left for the owner "
            "(costly kinds, or already re-queued this week)."), {"requeued": requeued, "left": left}


@fixer("resources.telemetry", writes_data=False)
def prune_telemetry() -> tuple[str, dict]:
    from ..config import settings
    from ..observability.store import connect

    conn = connect("iris-doctor")
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM obs_spans WHERE started_at < NOW() - make_interval(days => %s)",
                        (settings.OBS_RETENTION_DAYS,))
            deleted = cur.rowcount
        conn.commit()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("VACUUM (ANALYZE) obs_spans")
    finally:
        conn.close()
    return f"Pruned {deleted} span(s) past {settings.OBS_RETENTION_DAYS} days and vacuumed the table.", \
        {"deleted": deleted}


@fixer("resources.backups", writes_data=False)
def take_backup() -> tuple[str, dict]:
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "backup_db.py"), "doctor"], cwd=ROOT,
                          capture_output=True, text=True, timeout=1800, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"backup failed ({done.returncode})")
    return "Took a backup.", {"file": Path(done.stdout.strip().split(" ")[0]).name}


def apply(results: list[dict], run_id: str | None) -> list[dict]:
    """Run each safe-auto repair a failing check has, then check again. Worst first, one at a time."""
    from . import CHECKS, Result, _load  # noqa: F401

    _load()
    by_id = {c.id: c for c in CHECKS}
    wanted = [r for r in results if r["status"] in ("fail", "warn") and r["action_class"] == "safe-auto"
              and r["id"] in FIXERS]
    if any(FIXERS[r["id"]][1] for r in wanted):
        # A repair that writes the database is preceded by a backup, once per run.
        try:
            take_backup()
        except Exception as exc:
            logger.warning(f"Doctor backup before repairs failed: {exc}")
            return [_record(run_id, r["id"], "failed", "Not repaired: the backup before repairs failed.", {})
                    for r in wanted]
    done = []
    for r in wanted:
        repair, _ = FIXERS[r["id"]]
        try:
            summary, details = repair()
            after = by_id[r["id"]].run()
            outcome = "fixed" if after.status == "ok" else \
                "partly" if (after.value or 0) < (r["value"] or 0) else "unchanged"
            details = {**details, "after": after.status}
        except Exception as exc:
            logger.warning(f"Doctor repair {r['id']} failed: {type(exc).__name__}: {exc}")
            summary, details, outcome = f"The repair failed ({type(exc).__name__}).", {}, "failed"
        done.append(_record(run_id, r["id"], outcome, summary, details))
    return done


def _record(run_id: str | None, check_id: str, outcome: str, summary: str, details: dict) -> dict:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO health_fixes (run_id, check_id, outcome, summary, details)
                       VALUES (%s, %s, %s, %s, %s)""", (run_id, check_id, outcome, summary, Json(details)))
        conn.commit()
    return {"id": check_id, "outcome": outcome, "summary": summary, "details": details}
