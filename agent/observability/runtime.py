"""Process, database and queue probe. The CLI starts the sink without the probe."""

from __future__ import annotations

import asyncio
import gc
import os
import resource
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agent.observability.hub import hub
from agent.observability.store import connect, sink
from agent.observability.tracing import enabled

_PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
_HISTORY_KEEP = 120


@dataclass
class LoopState:
    lag_ms_max: float = 0.0
    threadpool_busy: int = 0
    threadpool_total: int = 0
    updated_at: float = 0.0


loop_state = LoopState()


async def watch_event_loop(interval_s: float = 0.25) -> None:
    import anyio

    loop = asyncio.get_running_loop()
    while True:
        started = loop.time()
        await asyncio.sleep(interval_s)
        lag = (loop.time() - started - interval_s) * 1000
        loop_state.lag_ms_max = max(loop_state.lag_ms_max, max(0.0, lag))
        try:
            limiter = anyio.to_thread.current_default_thread_limiter()
            loop_state.threadpool_busy = int(limiter.borrowed_tokens)
            loop_state.threadpool_total = int(limiter.total_tokens)
        except Exception:
            hub.note_internal()
        loop_state.updated_at = time.monotonic()


def _iso(moment: datetime | None = None) -> str:
    chosen = moment or datetime.now(UTC)
    return chosen.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _rss() -> int | None:
    try:
        with open("/proc/self/statm", encoding="ascii") as handle:
            parts = handle.read().split()
        return int(parts[1]) * _PAGE
    except OSError:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return int(usage.ru_maxrss) * 1024


def _open_fds() -> int | None:
    try:
        return len(os.listdir("/proc/self/fd"))
    except OSError:
        return None


class Probe(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name="iris-obs-probe", daemon=True)
        self._halt = threading.Event()
        self._cpu_time = 0.0
        self._cpu_at = 0.0
        self._db_stats: dict[str, float] | None = None
        self._db_stats_at = 0.0
        self._ticks = 0
        self._size_bytes: int | None = None
        self._blocked_streak = 0
        self._history: list[dict[str, float]] = []
        self._conn: Any = None

    def stop(self) -> None:
        self._halt.set()

    def run(self) -> None:
        self.tick()
        while not self._halt.wait(10.0):
            self.tick()

    def tick(self) -> None:
        self._ticks += 1
        now = time.time()
        snapshot = self._snapshot(now)
        hub.latest_probe = snapshot
        rows = _sample_rows(snapshot)
        at = snapshot["at"]
        hub.publish_samples(at, rows)
        if self._ticks % 6 == 0 and rows:
            sink.put_samples(at, rows)

    def _connection(self) -> Any:
        if self._conn is None or bool(getattr(self._conn, "closed", True)):
            self._conn = connect("iris-observatory-probe")
            self._conn.autocommit = True
        return self._conn

    def _reset_connection(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = None

    def _snapshot(self, now: float) -> dict[str, Any]:
        process = self._process(now)
        loop = self._loop()
        worker = self._worker()
        pool = self._pool()
        observatory = self._observatory(now)
        db_section: dict[str, Any] = {"reachable": False, "error": None}
        queue: dict[str, Any] = {
            "due": None, "leased": None, "scheduled_retry": None, "exhausted": None,
            "total": None, "oldest_due_age_s": None, "by_source_type": [],
        }
        phone: dict[str, Any] = {}
        try:
            conn = self._connection()
            with conn.cursor() as cur:
                queue = self._queue(cur)
                db_section = self._database(cur, now)
                phone = self._phone(cur, now)
        except Exception as exc:
            self._reset_connection()
            db_section = {"reachable": False, "error": f"{type(exc).__name__}: {exc}"}
        return {
            "at": _iso(),
            "stale": False,
            "process": process,
            "loop": loop,
            "worker": worker,
            "pool": pool,
            "queue": queue,
            "db": db_section,
            "listeners": self._listeners(),
            "phone": phone,
            "observatory": observatory,
        }

    def _process(self, now: float) -> dict[str, Any]:
        cpu = time.process_time()
        percent = None
        if self._cpu_at:
            elapsed = now - self._cpu_at
            if elapsed > 0:
                percent = (cpu - self._cpu_time) / elapsed * 100
        self._cpu_time = cpu
        self._cpu_at = now
        return {
            "rss_bytes": _rss(),
            "cpu_percent": percent,
            "threads": threading.active_count(),
            "open_fds": _open_fds(),
            "gc": list(gc.get_count()),
        }

    def _loop(self) -> dict[str, Any]:
        lag = loop_state.lag_ms_max
        loop_state.lag_ms_max = 0.0
        age = time.monotonic() - loop_state.updated_at if loop_state.updated_at else None
        return {
            "lag_ms_max": lag,
            "threadpool_busy": loop_state.threadpool_busy,
            "threadpool_total": loop_state.threadpool_total,
            "stale": age is None or age > 5,
        }

    def _worker(self) -> dict[str, Any]:
        from agent import work_queue

        thread = work_queue.worker._thread
        current = work_queue.current_item() if hasattr(work_queue, "current_item") else None
        return {
            "alive": thread is not None and thread.is_alive(),
            "current": current,
        }

    def _pool(self) -> dict[str, Any]:
        from agent.database import db

        pool = getattr(db, "_pool", None)
        if pool is None or getattr(pool, "closed", True):
            return {"initialized": False, "in_use": None, "idle": None, "max": None}
        return {
            "initialized": True,
            "in_use": len(getattr(pool, "_used", {}) or {}),
            "idle": len(getattr(pool, "_pool", []) or []),
            "max": getattr(pool, "maxconn", None),
        }

    def _queue(self, cur: Any) -> dict[str, Any]:
        from agent import work_queue

        leased = work_queue.leased_ids() if hasattr(work_queue, "leased_ids") else []
        cur.execute(
            """
            SELECT
                count(*) FILTER (
                    WHERE next_attempt_at <= now() AND attempts < %s AND id <> ALL(%s)
                ),
                count(*) FILTER (
                    WHERE next_attempt_at > now() AND attempts > 0 AND attempts < %s
                ),
                count(*) FILTER (WHERE attempts >= %s),
                count(*),
                EXTRACT(EPOCH FROM (
                    now() - min(next_attempt_at) FILTER (
                        WHERE next_attempt_at <= now() AND attempts < %s AND id <> ALL(%s)
                    )
                ))
            FROM processing_queue
            """,
            (
                work_queue.MAX_ATTEMPTS, leased,
                work_queue.MAX_ATTEMPTS,
                work_queue.MAX_ATTEMPTS,
                work_queue.MAX_ATTEMPTS, leased,
            ),
        )
        due, retry, exhausted, total, oldest = cur.fetchone()
        cur.execute(
            """
            SELECT source_type,
                   count(*) FILTER (
                       WHERE next_attempt_at <= now() AND attempts < %s AND id <> ALL(%s)
                   ),
                   count(*) FILTER (
                       WHERE next_attempt_at > now() AND attempts > 0 AND attempts < %s
                   ),
                   count(*) FILTER (WHERE attempts >= %s)
            FROM processing_queue
            GROUP BY source_type
            ORDER BY source_type
            """,
            (work_queue.MAX_ATTEMPTS, leased, work_queue.MAX_ATTEMPTS, work_queue.MAX_ATTEMPTS),
        )
        return {
            "due": due,
            "leased": len(leased),
            "scheduled_retry": retry,
            "exhausted": exhausted,
            "total": total,
            "oldest_due_age_s": float(oldest) if oldest is not None else None,
            "by_source_type": [
                {"source_type": row[0], "due": row[1], "scheduled_retry": row[2], "exhausted": row[3]}
                for row in cur.fetchall()
            ],
        }

    def _database(self, cur: Any, now: float) -> dict[str, Any]:
        cur.execute(
            """
            SELECT
                count(*) FILTER (WHERE state = 'active'),
                count(*) FILTER (WHERE state = 'idle'),
                count(*) FILTER (WHERE state = 'idle in transaction'),
                count(*) FILTER (WHERE wait_event_type = 'Lock'),
                count(*) FILTER (WHERE cardinality(pg_blocking_pids(pid)) > 0),
                EXTRACT(EPOCH FROM max(now() - xact_start)),
                EXTRACT(EPOCH FROM max(now() - query_start) FILTER (WHERE state = 'active')),
                EXTRACT(EPOCH FROM max(now() - state_change) FILTER (WHERE state = 'idle in transaction'))
            FROM pg_stat_activity
            WHERE datname = current_database()
              AND pid <> pg_backend_pid()
              AND backend_type = 'client backend'
            """
        )
        active, idle, idle_xact, waiting, blocked, xact, query, idle_age = cur.fetchone()
        if blocked and blocked > 0:
            self._blocked_streak += 1
        else:
            self._blocked_streak = 0
        size = self._size_bytes
        if self._ticks % 6 == 1 or size is None:
            cur.execute("SELECT pg_database_size(current_database())")
            size = cur.fetchone()[0]
            self._size_bytes = size
        cur.execute(
            """
            SELECT xact_commit, xact_rollback, blks_hit, blks_read, deadlocks, temp_bytes
            FROM pg_stat_database WHERE datname = current_database()
            """
        )
        commit, rollback, hit, read, deadlocks, temp = cur.fetchone()
        commits_per_s = rollbacks_per_s = cache_hit = None
        current = {
            "commit": float(commit or 0), "rollback": float(rollback or 0),
            "hit": float(hit or 0), "read": float(read or 0),
        }
        if self._db_stats is not None:
            elapsed = now - self._db_stats_at
            if elapsed > 0:
                commits_per_s = (current["commit"] - self._db_stats["commit"]) / elapsed
                rollbacks_per_s = (current["rollback"] - self._db_stats["rollback"]) / elapsed
                d_hit = current["hit"] - self._db_stats["hit"]
                d_read = current["read"] - self._db_stats["read"]
                if d_hit + d_read > 0:
                    cache_hit = d_hit / (d_hit + d_read)
        self._db_stats = current
        self._db_stats_at = now
        return {
            "reachable": True,
            "error": None,
            "active": active,
            "idle": idle,
            "idle_in_transaction": idle_xact,
            "waiting": waiting,
            "blocked": blocked,
            "longest_xact_s": float(xact) if xact is not None else None,
            "longest_query_s": float(query) if query is not None else None,
            "oldest_idle_in_xact_s": float(idle_age) if idle_age is not None else None,
            "size_bytes": size,
            "commits_per_s": commits_per_s,
            "rollbacks_per_s": rollbacks_per_s,
            "cache_hit_ratio": cache_hit,
            "deadlocks": deadlocks,
            "temp_bytes": temp,
            "blocked_streak": self._blocked_streak,
        }

    def _phone(self, cur: Any, now: float) -> dict[str, Any]:
        from agent.mobile_auth import connection_status

        status = connection_status(cur)
        seen = status.get("last_seen_at")
        intake = status.get("last_intake_at")
        age = None
        if isinstance(seen, datetime):
            age = max(0.0, now - seen.timestamp())
        return {
            "paired": status.get("paired"),
            "last_seen_at": _iso(seen) if isinstance(seen, datetime) else seen,
            "last_intake_at": _iso(intake) if isinstance(intake, datetime) else intake,
            "pending_batches": status.get("pending_batches"),
            "last_rejection": status.get("last_rejection"),
            "last_seen_age_s": age,
        }

    def _listeners(self) -> dict[str, Any]:
        from agent.config import settings

        if settings.LAN_URL:
            lan = "listening"
        elif settings.LAN_LISTENER_ERROR:
            lan = "failed"
        elif settings.LAN_BIND_HOST:
            lan = "not_started"
        else:
            lan = "not_configured"
        if settings.TAILNET_LISTENER_ERROR:
            tailnet = "failed"
        elif settings.tailnet_owners:
            tailnet = "listening"
        else:
            tailnet = "not_configured"
        return {
            "lan": lan,
            "lan_error": settings.LAN_LISTENER_ERROR,
            "tailnet": tailnet,
            "tailnet_error": settings.TAILNET_LISTENER_ERROR,
        }

    def _observatory(self, now: float) -> dict[str, Any]:
        point = {"at": now, "dropped": float(sink.dropped), "write_failures": float(sink.write_failures)}
        self._history.append(point)
        cutoff = now - 3600
        self._history = [item for item in self._history if item["at"] >= cutoff][-_HISTORY_KEEP:]
        return {
            "sink_backlog": sink.backlog,
            "dropped": sink.dropped,
            "written": sink.written,
            "write_failures": sink.write_failures,
            "internal_errors": hub.internal_errors,
            "history": list(self._history),
            "history_now": now,
        }


_SAMPLE_PATHS = (
    ("process.rss_bytes", ("process", "rss_bytes")),
    ("process.cpu_percent", ("process", "cpu_percent")),
    ("process.threads", ("process", "threads")),
    ("loop.lag_ms_max", ("loop", "lag_ms_max")),
    ("threadpool.busy", ("loop", "threadpool_busy")),
    ("db.pool.in_use", ("pool", "in_use")),
    ("db.server.active", ("db", "active")),
    ("db.server.idle_in_transaction", ("db", "idle_in_transaction")),
    ("db.server.blocked", ("db", "blocked")),
    ("db.server.longest_query_s", ("db", "longest_query_s")),
    ("db.server.size_bytes", ("db", "size_bytes")),
    ("db.server.cache_hit_ratio", ("db", "cache_hit_ratio")),
    ("db.server.commits_per_s", ("db", "commits_per_s")),
    ("db.server.rollbacks_per_s", ("db", "rollbacks_per_s")),
    ("queue.due", ("queue", "due")),
    ("queue.scheduled_retry", ("queue", "scheduled_retry")),
    ("queue.exhausted", ("queue", "exhausted")),
    ("queue.oldest_due_age_s", ("queue", "oldest_due_age_s")),
    ("obs.sink_backlog", ("observatory", "sink_backlog")),
    ("obs.dropped", ("observatory", "dropped")),
)


def _sample_rows(snapshot: dict[str, Any]) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    for name, path in _SAMPLE_PATHS:
        section = snapshot.get(path[0]) or {}
        value = section.get(path[1]) if isinstance(section, dict) else None
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            rows.append((name, float(value)))
    return rows


_probe: Probe | None = None


def start_background(*, probe: bool) -> None:
    global _probe
    if not enabled():
        return
    sink.start()
    if not probe:
        return
    if _probe is None or not _probe.is_alive():
        _probe = Probe()
        _probe.start()


def stop_background() -> None:
    global _probe
    current = _probe
    if current is not None:
        current.stop()
        current.join(12.0)
        _probe = None
    sink.stop()
