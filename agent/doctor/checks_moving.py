"""Is it moving? The server, the worker, the queue and the pattern update.

Up is not the same as moving: a pattern update ran for hours, was cut short
by restarts three times, and every page still loaded.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import UTC, datetime

from ..database import db
from . import Result, check

SERVER = os.environ.get("IRIS_URL", "http://127.0.0.1:8000")
#: How long one job of each kind may run before it looks stuck, in minutes.
#: A full pattern update on the Flex tier has taken over an hour.
JOB_LIMIT_MIN = {"reflection": 15, "discovery": 45, "personal_dynamics": 360, "session_voices": 90}
DEFAULT_LIMIT_MIN = 30
#: A job due this long ago and not yet taken is waiting behind something.
OVERDUE_MIN = 60
#: A pattern update not finished after this long is reported.
PATTERNS_LIMIT_H = 8


def _worker() -> dict | None:
    """The worker's state: from this process if it runs here, else from the server."""
    from .. import work_queue

    if work_queue.worker._thread is not None:
        return {"alive": work_queue.worker._thread.is_alive(), "current": work_queue.current_item()}
    try:
        with urllib.request.urlopen(f"{SERVER}/api/observatory/overview", timeout=10) as reply:
            return json.load(reply)["probe"]["worker"]
    except Exception:
        return None


def _minutes_since(value) -> float | None:
    if not value:
        return None
    at = datetime.fromisoformat(str(value).replace("Z", "+00:00")) if not isinstance(value, datetime) else value
    return (datetime.now(UTC) - at).total_seconds() / 60


@check("service.up", "moving")
def service_up() -> Result:
    try:
        with urllib.request.urlopen(f"{SERVER}/", timeout=10) as reply:
            ok = reply.status == 200
    except Exception as exc:
        return Result("service.up", "fail", f"IRIS does not answer at {SERVER} ({type(exc).__name__}).",
                      expected="HTTP 200", causes=["The service stopped or failed to start.",
                                                   "It is still starting after a restart."],
                      action="Check `systemctl --user status iris` and the journal; restart only after "
                             "`doctor --can-restart`.", action_class="guarded")
    return Result("service.up", "ok" if ok else "fail", "IRIS answers." if ok else "IRIS answers with an error.",
                  expected="HTTP 200")


@check("worker.alive", "moving")
def worker_alive() -> Result:
    state = _worker()
    if state is None:
        return Result("worker.alive", "unknown", "The worker's state could not be read.",
                      causes=["IRIS is not answering (see service.up)."])
    if not state.get("alive"):
        return Result("worker.alive", "fail", "The queue worker thread is not running.",
                      expected="alive", causes=["The thread crashed; nothing new is being processed."],
                      action="Restart IRIS (guarded).", action_class="guarded")
    return Result("worker.alive", "ok", "The queue worker is running.")


@check("worker.current_job", "moving")
def current_job() -> Result:
    state = _worker() or {}
    job = state.get("current")
    if not job:
        return Result("worker.current_job", "ok", "The worker is idle.", value=0)
    kind = str(job.get("source_type"))
    minutes = _minutes_since(job.get("since")) or 0.0
    limit = JOB_LIMIT_MIN.get(kind, DEFAULT_LIMIT_MIN)
    details = {"source_type": kind, "source_id": job.get("source_id"), "attempt": job.get("attempts")}
    if minutes > limit:
        return Result("worker.current_job", "warn",
                      f"A {kind} job has run {minutes:.0f} min, longer than its usual limit of {limit}.",
                      value=round(minutes), expected=f"under {limit} min", details=details,
                      causes=["A slow provider tier (Flex) on a large job.", "A request that hangs without a timeout."],
                      action="Watch llm.chat spans for progress before doing anything; never restart mid pattern "
                             "update unless its result is already out of date.", action_class="read-only")
    return Result("worker.current_job", "ok", f"Working on a {kind} job for {minutes:.0f} min.",
                  value=round(minutes), expected=f"under {limit} min", details=details)


@check("queue.exhausted", "moving")
def exhausted() -> Result:
    from ..work_queue import MAX_ATTEMPTS

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT source_type, source_id, last_error FROM processing_queue
                        WHERE attempts >= %s AND last_error IS NOT NULL""", (MAX_ATTEMPTS,))
        rows = cur.fetchall()
    if not rows:
        return Result("queue.exhausted", "ok", "No job has given up.", value=0, expected="0")
    # The kind of failure, never the message: messages can quote a source.
    kinds = sorted({f"{kind}: {re.match(r'[A-Za-z_]+', err or '')[0] if re.match(r'[A-Za-z_]+', err or '') else '?'}"
                    for kind, _, err in rows})
    return Result("queue.exhausted", "fail", f"{len(rows)} job(s) failed every retry and stopped.",
                  value=len(rows), expected="0", details={"jobs": [[k, i] for k, i, _ in rows], "kinds": kinds},
                  evidence="SELECT source_type, source_id, attempts FROM processing_queue "
                           "WHERE last_error IS NOT NULL AND attempts >= MAX_ATTEMPTS",
                  causes=["A bug that fails the same way each time (read last_error locally).",
                          "The provider was unavailable for every retry."],
                  action="Read last_error for the job locally, fix the cause, then re-queue it once.",
                  action_class="safe-auto")


@check("queue.overdue", "moving")
def overdue() -> Result:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT count(*), max(EXTRACT(EPOCH FROM (NOW() - next_attempt_at)) / 60)
                         FROM processing_queue
                        WHERE next_attempt_at < NOW() - make_interval(mins => %s)""", (OVERDUE_MIN,))
        count, oldest = cur.fetchone()
    if not count:
        return Result("queue.overdue", "ok", "Nothing is waiting long to be taken.", value=0, expected="0")
    return Result("queue.overdue", "warn", f"{count} job(s) due for over {OVERDUE_MIN} min, the oldest {oldest:.0f} min.",
                  value=count, expected="0",
                  causes=["One long job holds the worker (see worker.current_job).", "The worker stopped."],
                  action="See worker.current_job first.", action_class="read-only")


@check("patterns.progress", "moving")
def patterns_progress() -> Result:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT stage, updated_at, error_kind FROM discovery_state ORDER BY user_id LIMIT 1")
        row = cur.fetchone()
        cur.execute("SELECT attempts FROM processing_queue WHERE source_type = 'personal_dynamics' LIMIT 1")
        queued = cur.fetchone()
    if row is None:
        return Result("patterns.progress", "unknown", "No pattern state yet.")
    stage, updated, error_kind = row
    hours = (_minutes_since(updated) or 0) / 60
    attempts = queued[0] if queued else 0
    details = {"stage": stage, "attempts": attempts, "error_kind": error_kind}
    if stage == "failed":
        return Result("patterns.progress", "fail", f"The pattern update failed ({error_kind}).", details=details,
                      causes=["The provider failed every retry.", "A bug in synthesis."],
                      action="Check the journal for the synthesis error, then re-queue personal_dynamics once.",
                      action_class="safe-auto")
    if stage == "ready":
        return Result("patterns.progress", "ok", "Patterns are up to date.", value=0, details=details)
    if attempts and attempts > 2:
        return Result("patterns.progress", "warn",
                      f"The pattern update is on attempt {attempts}: earlier attempts were cut short.",
                      value=attempts, expected="1 or 2 attempts", details=details,
                      causes=["Restarts while it ran: each one throws away its progress."],
                      action="Do not restart until it finishes (doctor --can-restart).", action_class="read-only")
    if hours > PATTERNS_LIMIT_H:
        return Result("patterns.progress", "warn",
                      f"Patterns have been '{stage}' for {hours:.1f} h.", value=round(hours, 1),
                      expected=f"under {PATTERNS_LIMIT_H} h", details=details,
                      causes=["A very large rebuild on the Flex tier.", "Reads still pending (see data.unread)."],
                      action="See worker.current_job and data.unread.", action_class="read-only")
    return Result("patterns.progress", "ok", f"The pattern update is {stage} ({hours:.1f} h).",
                  value=round(hours, 1), details=details)
