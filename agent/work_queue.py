"""
Durable ingest queue.

An entry the user writes is stored and acknowledged immediately. Turning it into
evidence — embedding it, matching or discovering a theme, refreshing the
cross-theme caches — happens here instead of inside the request.

Before this, that work ran inline and its failure was caught and logged. If the
embedding provider was down for an hour, everything written in that hour was
stored but never became evidence, and nothing ever went back for it: the entry
was visible in the journal and invisible to every analytical engine, with no
signal that the two disagreed. Silent, permanent, and indistinguishable from
having written nothing.

A row in `processing_queue` means "not yet processed". Success deletes it.
Failure records the error and schedules a retry on a widening backoff, so a
provider outage delays work rather than losing it. After the schedule is
exhausted the row stays, holding its last error, because a stuck item that can
be seen is better than one that has been quietly dropped.
"""

import logging
import threading
from datetime import UTC, datetime
from typing import Any

from opentelemetry.trace import SpanKind

from . import observability as obs
from .database import db
from .pipeline import run_processing_pipeline

logger = logging.getLogger(__name__)

# Widening backoff: a provider blip retries within the minute, a sustained
# outage backs off to hourly rather than hammering it.
BACKOFF_SECONDS = [60, 300, 900, 3600, 6 * 3600, 24 * 3600]
MAX_ATTEMPTS = len(BACKOFF_SECONDS) + 1

# How long a claimed item is leased before another worker may retry it. Longer
# than any single pipeline run, short enough that a killed process recovers.
LEASE_SECONDS = 600

WORKER_POLL_SECONDS = 30


def enqueue(source_type: str, source_id: int, user_id: int) -> None:
    """Queue work that is not itself a write of evidence, and ask for a pass.

    Evidence is queued by the database writer that stores it, in the same
    transaction (Database._queue), so an entry and its job cannot be separated
    by a crash. This remains for jobs with no such writer — transcription — and
    uses the same statement, generation bump included.
    """
    try:
        with db.connection() as conn, conn.cursor() as cur:
            db._queue(cur, user_id, source_type, source_id)
            conn.commit()
    except Exception as e:
        logger.error(
            f"Could not enqueue {source_type} {source_id} for user {user_id}: {e}. "
            "This item will not become evidence until it is re-queued."
        )
        return
    notify()


def notify() -> None:
    """Ask the worker for a pass now, after a write has committed its job.

    Only imports and recordings used to wake it, so a habit ticked or an entry
    written in the app waited up to WORKER_POLL_SECONDS to become evidence —
    unless something else happened to be imported in the meantime. A no-op when
    no worker runs (tests, the CLI drain explicitly).
    """
    worker.wake()


def _claim_due(limit: int) -> list[dict[str, Any]]:
    """Take a lease on up to `limit` items whose retry time has arrived."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """WITH due AS (
                   SELECT id, next_attempt_at AS due_at FROM processing_queue
                   WHERE next_attempt_at <= NOW() AND attempts < %s
                   ORDER BY next_attempt_at
                   FOR UPDATE SKIP LOCKED
                   LIMIT %s
               )
               UPDATE processing_queue q
                  SET next_attempt_at = NOW() + make_interval(secs => %s),
                      attempts = q.attempts + 1
                 FROM due
                WHERE q.id = due.id
            RETURNING q.id, q.user_id, q.source_type, q.source_id, q.attempts, q.generation,
                      q.origin_traceparent, due.due_at, q.created_at;""",
            (MAX_ATTEMPTS, limit, LEASE_SECONDS),
        )
        rows = cur.fetchall()
        conn.commit()
    return [
        {
            "id": row[0], "user_id": row[1], "source_type": row[2], "source_id": row[3],
            "attempts": row[4], "generation": row[5], "origin_traceparent": row[6],
            "due_at": row[7], "created_at": row[8],
        }
        for row in rows
    ]


def _succeed(item_id: int, generation: int) -> bool:
    """Retire a job — only if the source is still the version it ran on.

    If the source was edited while the job ran, the generation moved on and the
    row stays, re-armed to run now: the edit is processed rather than lost with
    the job that read the old text. True when the row was deleted.
    """
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM processing_queue WHERE id = %s AND generation = %s;",
            (item_id, generation),
        )
        deleted = isinstance(cur.rowcount, int) and cur.rowcount > 0
        if not deleted:
            cur.execute(
                "UPDATE processing_queue SET next_attempt_at = NOW() WHERE id = %s;",
                (item_id,),
            )
        conn.commit()
    return deleted


def _fail(item_id: int, attempts: int, error: str, generation: int) -> int | None:
    """Back off only this generation; an edit must retain its newer job."""
    if attempts <= len(BACKOFF_SECONDS):
        delay: int | None = BACKOFF_SECONDS[attempts - 1]
    else:
        delay = None

    with db.connection() as conn, conn.cursor() as cur:
        if delay is None:
            cur.execute(
                """UPDATE processing_queue SET last_error = %s
                    WHERE id = %s AND generation = %s""",
                (error[:2000], item_id, generation),
            )
        else:
            cur.execute(
                """UPDATE processing_queue
                   SET last_error = %s,
                       next_attempt_at = NOW() + make_interval(secs => %s)
                   WHERE id = %s AND generation = %s""",
                (error[:2000], delay, item_id, generation),
            )
        if cur.rowcount:
            cur.execute("""UPDATE discovery_state SET stage = 'failed',
                          error_kind = %s, updated_at = NOW()
                          WHERE user_id = (SELECT user_id FROM processing_queue
                                            WHERE id = %s AND source_type = 'personal_dynamics')""",
                        (error if error.isidentifier() and len(error) <= 64
                         else "synthesis_failure", item_id))
        conn.commit()
    return delay


_leased: set[int] = set()
_current: dict[str, Any] | None = None


def leased_ids() -> list[int]:
    return list(_leased)


def current_item() -> dict[str, Any] | None:
    return _current


def _age_ms(value: object) -> float:
    if not isinstance(value, datetime):
        return 0.0
    moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - moment).total_seconds() * 1000)


def _run(source_type: str, source_id: int) -> None:
    """Dispatch one claimed job. Transcription is not evidence; everything else is."""
    if source_type == "transcription":
        from .importing.audio import run_transcription_job

        run_transcription_job(source_id)
        return
    if source_type == "session_voices":
        # A staged session's speakers, from its recording (ADR-0028). Its own
        # failures are recorded for the owner and not retried here.
        from .session_voices import run as sort_out_voices

        sort_out_voices(source_id)
        return
    if source_type == "discovery":
        from .discovery_worker import process_reflection
        from .episodes import ReadUnavailable

        try:
            process_reflection(source_id)
        except ReadUnavailable:
            raise
        except Exception:
            raise ReadUnavailable("invalid_read_store") from None
        return
    if source_type == "personal_dynamics":
        from .discovery import process_user
        from .episodes import ReadUnavailable

        try:
            process_user(source_id)
        except ReadUnavailable:
            raise
        except Exception:
            raise ReadUnavailable("synthesis_failure") from None
        return
    run_processing_pipeline(source_type, source_id)


def process_due(limit: int = 20) -> tuple[int, int]:
    """Process items whose retry time has arrived. Returns (succeeded, failed)."""
    global _current
    succeeded = failed = 0
    from .discovery import ensure_pending

    ensure_pending()
    with obs.suppressed():
        claimed = _claim_due(limit)
    for item in claimed:
        item_id = item.get("id")
        if isinstance(item_id, int):
            _leased.add(item_id)
    for item in claimed:
        item_id = item.get("id")
        _current = {**item, "since": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")}
        attrs = {
            "iris.queue.item_id": item.get("id"),
            "iris.queue.source_type": item.get("source_type"),
            "iris.queue.source_id": item.get("source_id"),
            "iris.queue.attempt": item.get("attempts"),
            "iris.queue.max_attempts": MAX_ATTEMPTS,
            "iris.queue.generation": item.get("generation"),
            "iris.queue.wait_ms": _age_ms(item.get("due_at")),
            "iris.queue.age_ms": _age_ms(item.get("created_at")),
        }
        try:
            with obs.span(
                "queue.job", "queue", attrs, kind=SpanKind.CONSUMER,
                links=obs.links_from_traceparent(item.get("origin_traceparent")),
                entry=True, root=True,
            ) as current:
                obs.capture_input({
                    "item": item,
                    "source_type": item.get("source_type"),
                    "source_id": item.get("source_id"),
                    "generation": item.get("generation"),
                    "attempt": item.get("attempts"),
                    "due_at": item.get("due_at"),
                }, span=current)
                try:
                    _run(str(item.get("source_type")), int(item.get("source_id") or 0))
                    retired = _succeed(int(item_id or 0), int(item.get("generation") or 0))
                    outcome = "retired" if retired else "superseded"
                    obs.set_attributes({"iris.queue.outcome": outcome})
                    obs.capture_output({"outcome": outcome}, span=current)
                    succeeded += 1
                except Exception as exc:
                    failed += 1
                    delay = _fail(int(item_id or 0), int(item.get("attempts") or 0),
                                  str(exc), int(item.get("generation") or 0))
                    obs.mark_error(current, exc)
                    if delay is None:
                        outcome = "exhausted"
                        obs.set_attributes({"iris.queue.outcome": outcome})
                        obs.capture_output({"outcome": outcome, "error": str(exc)}, span=current)
                    else:
                        outcome = "retry_scheduled"
                        obs.set_attributes({
                            "iris.queue.outcome": outcome,
                            "iris.queue.retry_in_s": delay,
                        })
                        obs.capture_output(
                            {"outcome": outcome, "retry_in_s": delay, "error": str(exc)},
                            span=current,
                        )
                    attempts = int(item.get("attempts") or 0)
                    level = logger.warning if attempts < MAX_ATTEMPTS else logger.error
                    level(
                        f"Processing {item.get('source_type')} {item.get('source_id')} failed "
                        f"(attempt {attempts}/{MAX_ATTEMPTS}): {exc}"
                    )
        finally:
            if isinstance(item_id, int):
                _leased.discard(item_id)
            _current = None
    return succeeded, failed


def drain(max_passes: int = 50) -> int:
    """Process everything currently due. Returns the number processed.

    Used by the CLI and by tests, where ingestion has to have finished before
    the assertion runs.
    """
    total = 0
    for _ in range(max_passes):
        succeeded, failed = process_due()
        total += succeeded
        if succeeded == 0:
            break
    return total


def pending(user_id: int | None = None) -> list[dict]:
    """Items not yet processed, newest attempt first. For diagnostics and the UI."""
    sql = """SELECT source_type, source_id, attempts, last_error,
                    next_attempt_at, created_at
             FROM processing_queue"""
    params: tuple = ()
    if user_id is not None:
        sql += " WHERE user_id = %s"
        params = (user_id,)
    sql += " ORDER BY created_at;"

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return [
            {"source_type": r[0], "source_id": r[1], "attempts": r[2],
             "last_error": r[3], "next_attempt_at": r[4], "created_at": r[5],
             "exhausted": r[2] >= MAX_ATTEMPTS}
            for r in cur.fetchall()
        ]


class QueueWorker:
    """Background thread that drains the queue on a poll interval."""

    def __init__(self, poll_seconds: int = WORKER_POLL_SECONDS):
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="iris-queue-worker", daemon=True
        )
        self._thread.start()
        logger.info(f"Ingest queue worker started (every {self.poll_seconds}s)")

    def wake(self) -> None:
        """Ask for a pass now rather than at the next poll.

        For work that arrives in a burst — an import committing several hundred
        entries — where waiting out a 30-second interval would leave the page
        saying nothing is happening. A no-op when no worker is running, which is
        the case in tests: there, whoever wants the work done drains explicitly.

        Deliberately not a second thread doing the draining. One did exist here
        first, and it raced: it claimed items under a ten-minute lease, so a
        caller that then drained itself found nothing due and concluded the
        entries had never been queued.
        """
        self._wake.set()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        logger.info("Ingest queue worker stopped")

    def _run(self) -> None:
        # Run once immediately so a restart picks up anything left behind by the
        # previous process rather than waiting out a poll interval.
        while True:
            try:
                succeeded, failed = process_due()
                if succeeded or failed:
                    logger.info(
                        f"Ingest queue: {succeeded} processed, {failed} deferred"
                    )
            except Exception as e:
                # A worker that dies leaves every future entry unprocessed, so
                # it must survive anything a single pass can raise.
                logger.error(f"Ingest queue worker pass failed: {e}")
            if self._stop.is_set():
                return
            # Wait out the interval, unless someone asks for a pass sooner.
            self._wake.wait(self.poll_seconds)
            self._wake.clear()


worker = QueueWorker()
