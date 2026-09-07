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
    """Register work to be done. Safe to call twice for the same source."""
    try:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO processing_queue (user_id, source_type, source_id)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (source_type, source_id) DO NOTHING;""",
                (user_id, source_type, source_id),
            )
            conn.commit()
    except Exception as e:
        # The entry itself is already stored; failing to queue must not fail the
        # write. This is the one loss this module cannot prevent, so it is loud.
        logger.error(
            f"Could not enqueue {source_type} {source_id} for user {user_id}: {e}. "
            "This item will not become evidence until it is re-queued."
        )


def _claim_due(limit: int) -> list[dict]:
    """Take a lease on up to `limit` items whose retry time has arrived."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE processing_queue
               SET next_attempt_at = NOW() + make_interval(secs => %s),
                   attempts = attempts + 1
               WHERE id IN (
                   SELECT id FROM processing_queue
                   WHERE next_attempt_at <= NOW() AND attempts < %s
                   ORDER BY next_attempt_at
                   FOR UPDATE SKIP LOCKED
                   LIMIT %s
               )
               RETURNING id, user_id, source_type, source_id, attempts;""",
            (LEASE_SECONDS, MAX_ATTEMPTS, limit),
        )
        rows = cur.fetchall()
        conn.commit()
    return [
        {"id": r[0], "user_id": r[1], "source_type": r[2],
         "source_id": r[3], "attempts": r[4]}
        for r in rows
    ]


def _succeed(item_id: int) -> None:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM processing_queue WHERE id = %s;", (item_id,))
        conn.commit()


def _fail(item_id: int, attempts: int, error: str) -> None:
    """Schedule the next attempt, or park the item once the schedule runs out."""
    if attempts <= len(BACKOFF_SECONDS):
        delay = BACKOFF_SECONDS[attempts - 1]
    else:
        delay = None  # exhausted: leave it parked, visible, not retried

    with db.connection() as conn, conn.cursor() as cur:
        if delay is None:
            cur.execute(
                "UPDATE processing_queue SET last_error = %s WHERE id = %s;",
                (error[:2000], item_id),
            )
        else:
            cur.execute(
                """UPDATE processing_queue
                   SET last_error = %s,
                       next_attempt_at = NOW() + make_interval(secs => %s)
                   WHERE id = %s;""",
                (error[:2000], delay, item_id),
            )
        conn.commit()


def process_due(limit: int = 20) -> tuple[int, int]:
    """Process items whose retry time has arrived. Returns (succeeded, failed)."""
    succeeded = failed = 0
    for item in _claim_due(limit):
        try:
            run_processing_pipeline(item["source_type"], item["source_id"])
            _succeed(item["id"])
            succeeded += 1
        except Exception as e:
            failed += 1
            _fail(item["id"], item["attempts"], str(e))
            level = logger.warning if item["attempts"] < MAX_ATTEMPTS else logger.error
            level(
                f"Processing {item['source_type']} {item['source_id']} failed "
                f"(attempt {item['attempts']}/{MAX_ATTEMPTS}): {e}"
            )
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
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="iris-queue-worker", daemon=True
        )
        self._thread.start()
        logger.info(f"Ingest queue worker started (every {self.poll_seconds}s)")

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
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
            if self._stop.wait(self.poll_seconds):
                return


worker = QueueWorker()
