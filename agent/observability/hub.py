"""In-memory rings and live subscribers. Imports nothing from processors."""

from __future__ import annotations

import asyncio
import json
import secrets
import threading
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agent.observability.catalog import is_transparent, module_id_for

SPAN_RING = 2000
LOG_RING = 1000
SAMPLE_RING = 360
ACTIVE_CAP = 1024
DETAIL_CAP = 256
DETAIL_BYTES = 16 * 1024 * 1024

_SUMMARY_ATTRS = (
    "http.response.status_code",
    "http.route",
    "iris.door",
    "iris.client",
    "iris.http.streaming",
    "gen_ai.request.model",
    "iris.llm.ttft_ms",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "iris.queue.outcome",
    "db.response.returned_rows",
    "iris.db.queries",
    "iris.db.spans_dropped",
    "iris.db.fetch_spans_dropped",
    "iris.admission.failed_closed",
    "iris.admission.unavailable",
)

_WARNING_LEVELS = frozenset({"WARNING", "ERROR", "CRITICAL"})


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _iso_nanos(nanos: int | None) -> str:
    if not nanos:
        return _now()
    moment = datetime.fromtimestamp(nanos / 1_000_000_000, tz=UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def to_summary(record: dict[str, Any]) -> dict[str, Any]:
    """The live-screen shape: identity, timing, and a short attribute set."""
    attributes = record.get("attributes") or {}
    kept: dict[str, Any] = {}
    if isinstance(attributes, dict):
        for key in _SUMMARY_ATTRS:
            if key in attributes:
                kept[key] = attributes[key]
    for event in record.get("events") or []:
        if not isinstance(event, dict) or event.get("name") != "exception":
            continue
        event_attrs = event.get("attributes") or {}
        if isinstance(event_attrs, dict) and event_attrs.get("exception.type"):
            kept["exception.type"] = event_attrs["exception.type"]
        break
    message = record.get("status_message")
    if isinstance(message, str) and len(message) > 300:
        message = message[:300]
    links = record.get("links") if isinstance(record.get("links"), list) else []
    return {
        "trace_id": record.get("trace_id"),
        "span_id": record.get("span_id"),
        "parent_span_id": record.get("parent_span_id"),
        "name": record.get("name"),
        "component": record.get("component"),
        "kind": record.get("kind"),
        "started_at": record.get("started_at"),
        "duration_ms": record.get("duration_ms"),
        "self_ms": record.get("self_ms"),
        "status": record.get("status"),
        "status_message": message,
        "attrs": kept,
        "module_id": record.get("module_id"),
        "parent_module_id": record.get("parent_module_id"),
        "links": links,
    }


def matches(kind: str, item: dict[str, Any], wanted: set[str], errors_only: bool) -> bool:
    """An empty component set matches everything. Starts are not errors."""
    if kind in ("span", "span_start"):
        component = str(item.get("component") or "system")
        if errors_only and (kind == "span_start" or item.get("status") != "error"):
            return False
    else:
        source = item.get("source")
        component = source if source in ("web", "android") else "system"
        if errors_only and item.get("level") not in _WARNING_LEVELS:
            return False
    return not wanted or component in wanted


def format_sse(kind: str, item: dict[str, Any]) -> str:
    payload = json.dumps(item, ensure_ascii=False, default=str)
    return f"event: {kind}\ndata: {payload}\n\n"


def _ids(span: Any) -> tuple[str, str]:
    context = span.context
    trace_id = f"{context.trace_id:032x}" if context is not None else "0" * 32
    span_id = f"{context.span_id:016x}" if context is not None else "0" * 16
    return trace_id, span_id


def _component(span: Any) -> str:
    attributes = getattr(span, "attributes", None) or {}
    return str(attributes.get("iris.component") or "system")


@dataclass
class Subscription:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[tuple[str, dict[str, Any]]]
    lifecycle: bool = False
    lagged: bool = False


@dataclass
class _Active:
    span: Any
    parent_module_id: str | None
    started_at: str


@dataclass
class Hub:
    latest_probe: dict[str, Any] | None = None
    client_state: dict[str, dict[str, Any]] = field(default_factory=dict)
    internal_errors: int = 0
    identity_incomplete: bool = False
    instance_id: str = field(default_factory=lambda: secrets.token_hex(8))
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _spans: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=SPAN_RING))
    _logs: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=LOG_RING))
    _samples: dict[str, deque[tuple[str, float]]] = field(default_factory=dict)
    _subs: list[Subscription] = field(default_factory=list)
    _active: OrderedDict[tuple[str, str], _Active] = field(default_factory=OrderedDict)
    _details: OrderedDict[tuple[str, str], bytes] = field(default_factory=OrderedDict)
    _detail_bytes: int = 0
    _sequence: int = 0
    _sdk_inflight: int = 0
    _active_complete: bool = True

    def note_internal(self) -> None:
        self.internal_errors += 1

    def note_identity_gap(self) -> None:
        self.identity_incomplete = True

    def note_start(self, span: Any, parent_module_id: str | None) -> None:
        """Track one SDK span. Connection wrappers are not active module calls."""
        name = str(getattr(span, "name", "") or "")
        if is_transparent(name):
            return
        trace_id, span_id = _ids(span)
        started_at = _iso_nanos(getattr(span, "start_time", None))
        summary = self._running_summary(span, parent_module_id, started_at)
        lifecycle: list[Subscription] = []
        with self._lock:
            self._sdk_inflight += 1
            key = (trace_id, span_id)
            if key not in self._active and len(self._active) >= ACTIVE_CAP:
                self._active.popitem(last=False)
                self._active_complete = False
            self._active[key] = _Active(
                span=span, parent_module_id=parent_module_id, started_at=started_at
            )
            self._active.move_to_end(key)
            self._sequence += 1
            summary["sequence"] = self._sequence
            lifecycle = [item for item in self._subs if item.lifecycle]
        self._fanout(lifecycle, ("span_start", summary))

    def publish_span(self, record: dict[str, Any]) -> None:
        """Client ingestion and any non-SDK completion. Does not change the SDK-active count."""
        self._publish(record, sdk=False)

    def finish_sdk(self, record: dict[str, Any]) -> None:
        self._publish(record, sdk=True)

    def _publish(self, record: dict[str, Any], *, sdk: bool) -> None:
        summary = to_summary(record)
        name = str(record.get("name") or "")
        module_id = record.get("module_id")
        transparent = is_transparent(name, module_id if isinstance(module_id, str) else None)
        key = (str(record.get("trace_id") or ""), str(record.get("span_id") or ""))
        with self._lock:
            if sdk:
                self._sdk_inflight = max(0, self._sdk_inflight - 1)
                self._active.pop(key, None)
                if self._sdk_inflight == 0:
                    self._active_complete = True
                    self.identity_incomplete = False
            self._spans.append(summary)
            if not transparent:
                self._remember_locked(key, record)
            self._sequence += 1
            summary["sequence"] = self._sequence
            subs = list(self._subs)
        self._fanout(subs, ("span", summary), hide_transparent=transparent)

    def publish_log(self, record: dict[str, Any]) -> None:
        with self._lock:
            self._logs.append(record)
            subs = list(self._subs)
        self._fanout(subs, ("log", record))

    def publish_samples(self, at: str, rows: list[tuple[str, float]]) -> None:
        with self._lock:
            for name, value in rows:
                ring = self._samples.get(name)
                if ring is None:
                    ring = deque(maxlen=SAMPLE_RING)
                    self._samples[name] = ring
                ring.append((at, value))

    def recent_spans(self, limit: int) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._spans)
        return items[-limit:]

    def recent_logs(self, limit: int) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._logs)
        return items[-limit:]

    def series(self, name: str) -> list[tuple[str, float]]:
        with self._lock:
            ring = self._samples.get(name)
            return list(ring) if ring is not None else []

    def active_summaries(self) -> list[dict[str, Any]]:
        with self._lock:
            entries = list(self._active.values())
        return [
            self._running_summary(entry.span, entry.parent_module_id, entry.started_at)
            for entry in entries
        ]

    def active_complete(self) -> bool:
        with self._lock:
            return self._active_complete and not self.identity_incomplete

    def lifecycle_snapshot(self) -> dict[str, Any]:
        with self._lock:
            active = [
                self._running_summary(entry.span, entry.parent_module_id, entry.started_at)
                for entry in self._active.values()
            ]
            recent = [
                item
                for item in self._spans
                if not is_transparent(
                    str(item.get("name") or ""),
                    item.get("module_id") if isinstance(item.get("module_id"), str) else None,
                )
            ][-200:]
            return {
                "instance_id": self.instance_id,
                "sequence": self._sequence,
                "at": _now(),
                "active": active,
                "recent": recent,
                "active_complete": self._active_complete and not self.identity_incomplete,
            }

    def invocation_record(self, trace_id: str, span_id: str) -> dict[str, Any] | None:
        """Active attribute snapshot, else a cached completed record. Copies once per inspect."""
        key = (trace_id, span_id)
        with self._lock:
            active = self._active.get(key)
            cached = self._details.get(key)
        if active is not None:
            return self._record_from_span(active)
        if cached is None:
            return None
        loaded = json.loads(cached)
        return loaded if isinstance(loaded, dict) else None

    def clear(self) -> None:
        with self._lock:
            self._spans.clear()
            self._logs.clear()
            self._samples.clear()
            self._active.clear()
            self._details.clear()
            self._detail_bytes = 0
            self._sequence = 0
            self._sdk_inflight = 0
            self._active_complete = True
            self.identity_incomplete = False
            self.instance_id = secrets.token_hex(8)
            self.latest_probe = None
            self.client_state.clear()

    def subscribe(
        self, loop: asyncio.AbstractEventLoop, *, lifecycle: bool = False
    ) -> Subscription:
        sub = Subscription(loop=loop, queue=asyncio.Queue(maxsize=1000), lifecycle=lifecycle)
        with self._lock:
            self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            self._subs = [item for item in self._subs if item is not sub]

    def offer(self, sub: Subscription, item: tuple[str, dict[str, Any]]) -> None:
        try:
            sub.queue.put_nowait(item)
        except asyncio.QueueFull:
            sub.lagged = True

    def _fanout(
        self,
        subs: list[Subscription],
        item: tuple[str, dict[str, Any]],
        *,
        hide_transparent: bool = False,
    ) -> None:
        kind, _payload = item
        for sub in subs:
            if kind == "span_start" and not sub.lifecycle:
                continue
            if hide_transparent and sub.lifecycle:
                continue
            try:
                sub.loop.call_soon_threadsafe(self.offer, sub, item)
            except RuntimeError:
                self.note_internal()

    def backlog(self, wanted: set[str], errors_only: bool) -> list[tuple[str, dict[str, Any]]]:
        with self._lock:
            spans = list(self._spans)
            logs = list(self._logs)
        matched_spans = [item for item in spans if matches("span", item, wanted, errors_only)][
            -200:
        ]
        matched_logs = [item for item in logs if matches("log", item, wanted, errors_only)][-100:]
        return [("span", item) for item in matched_spans] + [("log", item) for item in matched_logs]

    def _remember_locked(self, key: tuple[str, str], record: dict[str, Any]) -> None:
        encoded = json.dumps(record, ensure_ascii=False, default=str).encode("utf-8")
        previous = self._details.pop(key, None)
        if previous is not None:
            self._detail_bytes -= len(previous)
        self._details[key] = encoded
        self._detail_bytes += len(encoded)
        while self._details and (
            len(self._details) > DETAIL_CAP or self._detail_bytes > DETAIL_BYTES
        ):
            _old_key, old = self._details.popitem(last=False)
            self._detail_bytes -= len(old)

    def _running_summary(
        self, span: Any, parent_module_id: str | None, started_at: str
    ) -> dict[str, Any]:
        attributes = dict(getattr(span, "attributes", None) or {})
        component = str(attributes.get("iris.component") or "system")
        name = str(getattr(span, "name", "") or "")
        module_id = module_id_for(name, component, attributes)
        trace_id, span_id = _ids(span)
        parent = getattr(span, "parent", None)
        parent_span_id = f"{parent.span_id:016x}" if parent is not None and parent.span_id else None
        started_ns = getattr(span, "start_time", None)
        elapsed = 0.0
        if isinstance(started_ns, int) and started_ns:
            elapsed = max(
                0.0, (datetime.now(UTC).timestamp() * 1_000_000_000 - started_ns) / 1_000_000
            )
        kept = {key: attributes[key] for key in _SUMMARY_ATTRS if key in attributes}
        links = [
            {
                "trace_id": f"{link.context.trace_id:032x}",
                "span_id": f"{link.context.span_id:016x}",
            }
            for link in getattr(span, "links", ()) or ()
        ]
        return {
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "name": name,
            "component": component,
            "kind": span.kind.name.lower()
            if getattr(span, "kind", None) is not None
            else "internal",
            "started_at": started_at,
            "duration_ms": elapsed,
            "self_ms": None,
            "status": "running",
            "status_message": None,
            "attrs": kept,
            "module_id": module_id,
            "parent_module_id": parent_module_id,
            "links": links,
        }

    def _record_from_span(self, active: _Active) -> dict[str, Any]:
        span = active.span
        summary = self._running_summary(span, active.parent_module_id, active.started_at)
        attributes = dict(getattr(span, "attributes", None) or {})
        events = []
        for event in getattr(span, "events", ()) or ():
            events.append(
                {
                    "name": event.name,
                    "at": _iso_nanos(getattr(event, "timestamp", None)),
                    "attributes": dict(event.attributes or {}),
                }
            )
        summary["attributes"] = attributes
        summary["events"] = events
        summary["is_entry"] = bool(attributes.get("iris.entry"))
        return summary


hub = Hub()
