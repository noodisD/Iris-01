"""Postgres sink. Its connection uses a plain cursor, so it is never traced."""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from typing import Any

import psycopg2
from psycopg2.extras import execute_values

from agent.observability.content import strip_nulls

logger = logging.getLogger("agent.observability")

QUEUE_MAX = 10_000
_BATCH = 1_000
_FLUSH_EVERY_S = 1.0
_FLUSH_AT = 500
_PRUNE_EVERY_S = 600.0

_SPAN_SQL = """
INSERT INTO obs_spans (
    trace_id, span_id, parent_span_id, name, component, kind, is_entry, started_at,
    duration_ms, self_ms, status, status_message, db_fingerprint, attributes, events, links,
    module_id, parent_module_id
) VALUES %s
ON CONFLICT (trace_id, span_id) DO NOTHING
"""
_SPAN_TEMPLATE = (
    "(%s,%s,%s,%s,%s,%s,%s,%s::timestamptz,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s)"
)
_LOG_SQL = """
INSERT INTO obs_logs (
    at, source, level, logger, message, exception, trace_id, span_id, attributes
) VALUES %s
"""
_LOG_TEMPLATE = "(%s::timestamptz,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)"
_SAMPLE_SQL = "INSERT INTO obs_samples (at, name, value) VALUES %s"
_SAMPLE_TEMPLATE = "(%s::timestamptz,%s,%s)"
_STATE_SQL = """
INSERT INTO obs_client_state (source, received_at, state) VALUES %s
ON CONFLICT (source) DO UPDATE
   SET received_at = EXCLUDED.received_at, state = EXCLUDED.state
"""
_STATE_TEMPLATE = "(%s,%s::timestamptz,%s::jsonb)"


def connect(application_name: str) -> Any:
    from agent.config import settings

    return psycopg2.connect(
        dbname=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        application_name=application_name,
        connect_timeout=5,
    )


def _json(value: object) -> str:
    return strip_nulls(json.dumps(value, ensure_ascii=False, default=str))


def _text(value: object) -> str | None:
    if value is None:
        return None
    return strip_nulls(str(value))


class Sink:
    """Background writer. Items accumulate within the caps before start()."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._spans: deque[dict[str, Any]] = deque()
        self._logs: deque[dict[str, Any]] = deque()
        self._samples: deque[tuple[str, str, float]] = deque()
        self._state: deque[tuple[str, str, dict[str, Any]]] = deque()
        self.dropped = 0
        self.written = 0
        self.write_failures = 0
        self._stop = False
        self._thread: threading.Thread | None = None
        self._last_prune = 0.0
        self._backoff = 0.0
        self._backoff_until = 0.0
        self._failing = False

    @property
    def backlog(self) -> int:
        with self._lock:
            return self._pending_locked()

    def _pending_locked(self) -> int:
        return len(self._spans) + len(self._logs) + len(self._samples) + len(self._state)

    def _append(self, queue: deque[Any], item: Any) -> None:
        with self._wake:
            if len(queue) >= QUEUE_MAX:
                queue.popleft()
                self.dropped += 1
            queue.append(item)
            if self._pending_locked() >= _FLUSH_AT:
                self._wake.notify()

    def put_span(self, record: dict[str, Any]) -> None:
        self._append(self._spans, record)

    def put_log(self, record: dict[str, Any]) -> None:
        self._append(self._logs, record)

    def put_samples(self, at: str, rows: list[tuple[str, float]]) -> None:
        for name, value in rows:
            self._append(self._samples, (at, name, value))

    def put_client_state(self, source: str, received_at: str, state: dict[str, Any]) -> None:
        self._append(self._state, (source, received_at, state))

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop = False
        self._thread = threading.Thread(target=self._run, name="iris-obs-sink", daemon=True)
        self._thread.start()

    def stop(self, timeout_s: float = 3.0) -> None:
        self._stop = True
        with self._wake:
            self._wake.notify()
        thread = self._thread
        if thread is not None:
            thread.join(timeout_s)
        self.flush_now()
        self._thread = None
        self._stop = False

    def clear(self) -> None:
        with self._lock:
            self._spans.clear()
            self._logs.clear()
            self._samples.clear()
            self._state.clear()

    def flush_now(self) -> None:
        with self._lock:
            batches = self._take_locked()
        if any(batches):
            self._write(batches)

    def _take_locked(self) -> tuple[list[Any], list[Any], list[Any], list[Any]]:
        spans = [self._spans.popleft() for _ in range(min(_BATCH, len(self._spans)))]
        logs = [self._logs.popleft() for _ in range(min(_BATCH, len(self._logs)))]
        samples = [self._samples.popleft() for _ in range(min(_BATCH, len(self._samples)))]
        state = [self._state.popleft() for _ in range(min(_BATCH, len(self._state)))]
        return spans, logs, samples, state

    def _restore(self, batches: tuple[list[Any], list[Any], list[Any], list[Any]]) -> None:
        queues: tuple[deque[Any], deque[Any], deque[Any], deque[Any]] = (
            self._spans,
            self._logs,
            self._samples,
            self._state,
        )
        with self._lock:
            for queue, batch in zip(queues, batches, strict=True):
                for item in reversed(batch):
                    if len(queue) >= QUEUE_MAX:
                        self.dropped += 1
                        continue
                    queue.appendleft(item)

    def _write(self, batches: tuple[list[Any], list[Any], list[Any], list[Any]]) -> None:
        if self._backoff_until and time.monotonic() < self._backoff_until:
            self._restore(batches)
            return
        conn = None
        try:
            conn = connect("iris-observatory")
            with conn.cursor() as cur:
                if batches[0]:
                    execute_values(
                        cur,
                        _SPAN_SQL,
                        [_span_row(item) for item in batches[0]],
                        template=_SPAN_TEMPLATE,
                    )
                if batches[1]:
                    execute_values(
                        cur,
                        _LOG_SQL,
                        [_log_row(item) for item in batches[1]],
                        template=_LOG_TEMPLATE,
                    )
                if batches[2]:
                    execute_values(cur, _SAMPLE_SQL, batches[2], template=_SAMPLE_TEMPLATE)
                if batches[3]:
                    execute_values(
                        cur,
                        _STATE_SQL,
                        [(source, at, _json(state)) for source, at, state in batches[3]],
                        template=_STATE_TEMPLATE,
                    )
            conn.commit()
            self.written += sum(len(batch) for batch in batches)
            if self._failing:
                logger.info("observatory sink recovered")
                self._failing = False
            self._backoff = 0.0
            self._backoff_until = 0.0
        except psycopg2.Error as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except psycopg2.Error:
                    pass
                try:
                    conn.close()
                except psycopg2.Error:
                    pass
                conn = None
            self._restore(batches)
            self.write_failures += 1
            if not self._failing:
                logger.warning("observatory sink write failed: %s", exc)
                self._failing = True
            self._backoff = 5.0 if self._backoff <= 0 else min(60.0, self._backoff * 2)
            self._backoff_until = time.monotonic() + self._backoff
        finally:
            if conn is not None:
                conn.close()

    def prune(self) -> None:
        from agent.config import settings

        days = settings.OBS_RETENTION_DAYS
        conn = connect("iris-observatory")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM obs_spans WHERE started_at < now() - make_interval(days => %s)",
                    (days,),
                )
                cur.execute(
                    "DELETE FROM obs_logs WHERE at < now() - make_interval(days => %s)",
                    (days,),
                )
                cur.execute(
                    "DELETE FROM obs_samples WHERE at < now() - make_interval(days => %s)",
                    (days,),
                )
            conn.commit()
        finally:
            conn.close()

    def _maybe_prune(self) -> None:
        now = time.monotonic()
        if self._last_prune and now - self._last_prune < _PRUNE_EVERY_S:
            return
        self._last_prune = now
        try:
            self.prune()
        except psycopg2.Error as exc:
            logger.warning("observatory prune failed: %s", exc)

    def _run(self) -> None:
        while not self._stop:
            wait = _FLUSH_EVERY_S
            if self._backoff_until:
                remaining = self._backoff_until - time.monotonic()
                if remaining > 0:
                    wait = remaining
            with self._wake:
                if not self._stop and self._pending_locked() < _FLUSH_AT:
                    self._wake.wait(timeout=wait)
                if (
                    self._backoff_until
                    and time.monotonic() < self._backoff_until
                    and not self._stop
                ):
                    continue
                batches = self._take_locked()
            if any(batches):
                self._write(batches)
            if not self._stop:
                self._maybe_prune()


def _span_row(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        _text(record.get("trace_id")),
        _text(record.get("span_id")),
        _text(record.get("parent_span_id")),
        _text(record.get("name")) or "",
        _text(record.get("component")) or "system",
        _text(record.get("kind")) or "internal",
        bool(record.get("is_entry")),
        record.get("started_at"),
        record.get("duration_ms"),
        record.get("self_ms"),
        _text(record.get("status")) or "ok",
        _text(record.get("status_message")),
        _text(record.get("db_fingerprint")),
        _json(record.get("attributes") or {}),
        _json(record.get("events") or []),
        _json(record.get("links") or []),
        _text(record.get("module_id")) or _text(record.get("name")) or "",
        _text(record.get("parent_module_id")),
    )


def _log_row(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        record.get("at"),
        _text(record.get("source")) or "server",
        _text(record.get("level")) or "INFO",
        _text(record.get("logger")) or "",
        _text(record.get("message")) or "",
        _text(record.get("exception")),
        _text(record.get("trace_id")),
        _text(record.get("span_id")),
        _json(record.get("attributes") or {}),
    )


sink = Sink()
