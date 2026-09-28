"""Turn ended spans into Observatory records. Does not import tracing."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor
from opentelemetry.trace import SpanKind, StatusCode

from agent.observability.catalog import http_identity_resolved, is_transparent, module_id_for
from agent.observability.content import MAX_STATUS, render_text
from agent.observability.hub import hub
from agent.observability.store import sink

_CHILD_CAP = 50_000
_PARENT_WALK = 64


def _iso(nanos: int) -> str:
    moment = datetime.fromtimestamp(nanos / 1_000_000_000, tz=UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _jsonable(value: object) -> object:
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _key(trace_id: int, span_id: int) -> tuple[int, int]:
    return (trace_id, span_id)


@dataclass
class _Identity:
    module_id: str
    name: str
    parent_key: tuple[int, int] | None
    parent_module_id: str | None
    provisional: bool


class ObservatorySpanProcessor(SpanProcessor):
    """Computes self time, then publishes and enqueues the record."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.child_ms: OrderedDict[tuple[int, int], float] = OrderedDict()
        self.identities: OrderedDict[tuple[int, int], _Identity] = OrderedDict()

    def on_start(self, span: ReadableSpan, parent_context: object | None = None) -> None:
        try:
            self._on_start(span)
        except Exception:
            hub.note_internal()

    def _on_start(self, span: ReadableSpan) -> None:
        context = span.context
        if context is None:
            return
        attrs = dict(span.attributes or {})
        component = str(attrs.get("iris.component") or "system")
        name = span.name
        module_id = module_id_for(name, component, attrs)
        provisional = component == "http" and not http_identity_resolved(attrs)
        parent = span.parent
        parent_key = (
            _key(parent.trace_id, parent.span_id) if parent is not None and parent.span_id else None
        )
        parent_module_id = self._effective_parent(parent_key)
        own = _key(context.trace_id, context.span_id)
        with self._lock:
            if len(self.identities) >= _CHILD_CAP:
                self.identities.popitem(last=False)
                hub.note_identity_gap()
            self.identities[own] = _Identity(
                module_id=module_id,
                name=name,
                parent_key=parent_key,
                parent_module_id=parent_module_id,
                provisional=provisional,
            )
            self.identities.move_to_end(own)
        hub.note_start(span, parent_module_id)

    def _effective_parent(self, parent_key: tuple[int, int] | None) -> str | None:
        key = parent_key
        with self._lock:
            for _step in range(_PARENT_WALK):
                if key is None:
                    return None
                ident = self.identities.get(key)
                if ident is None:
                    hub.note_identity_gap()
                    return None
                if ident.provisional:
                    return None
                if is_transparent(ident.name, ident.module_id):
                    key = ident.parent_key
                    continue
                return ident.module_id
        hub.note_identity_gap()
        return None

    def on_end(self, span: ReadableSpan) -> None:
        try:
            self._on_end(span)
        except Exception:
            hub.note_internal()

    def _on_end(self, span: ReadableSpan) -> None:
        context = span.context
        if context is None or span.start_time is None or span.end_time is None:
            return
        duration_ms = (span.end_time - span.start_time) / 1_000_000
        own = _key(context.trace_id, context.span_id)
        with self._lock:
            children = self.child_ms.pop(own, 0.0)
            self_ms = max(0.0, duration_ms - children)
            ident = self.identities.pop(own, None)
            parent = span.parent
            if parent is not None and not parent.is_remote and parent.span_id:
                parent_key = _key(parent.trace_id, parent.span_id)
                self.child_ms[parent_key] = self.child_ms.get(parent_key, 0.0) + duration_ms
                self.child_ms.move_to_end(parent_key)
                while len(self.child_ms) > _CHILD_CAP:
                    self.child_ms.popitem(last=False)
        attrs = dict(span.attributes or {})
        component = str(attrs.get("iris.component") or "system")
        module_id = module_id_for(span.name, component, attrs)
        parent_module_id = None if ident is None else ident.parent_module_id
        record = to_record(span, self_ms, module_id=module_id, parent_module_id=parent_module_id)
        hub.finish_sdk(record)
        sink.put_span(record)

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    def clear(self) -> None:
        with self._lock:
            self.child_ms.clear()
            self.identities.clear()


def to_record(
    span: ReadableSpan,
    self_ms: float,
    *,
    module_id: str | None = None,
    parent_module_id: str | None = None,
) -> dict[str, Any]:
    context = span.context
    parent = span.parent
    raw = dict(span.attributes or {})
    component = str(raw.pop("iris.component", None) or "system")
    attributes = {key: _jsonable(value) for key, value in raw.items()}
    kind = span.kind.name.lower() if span.kind is not None else "internal"
    is_entry = (
        parent is None
        or span.kind in (SpanKind.SERVER, SpanKind.CONSUMER)
        or (span.attributes or {}).get("iris.entry") is True
    )
    status = "error" if span.status.status_code is StatusCode.ERROR else "ok"
    status_message = span.status.description or None
    events: list[dict[str, Any]] = []
    for event in span.events:
        event_attrs = {key: _jsonable(value) for key, value in dict(event.attributes or {}).items()}
        events.append({"name": event.name, "at": _iso(event.timestamp), "attributes": event_attrs})
        if not status_message and event.name == "exception":
            message = event_attrs.get("exception.message")
            if message:
                status_message = str(message)
    if status_message:
        status_message = render_text(str(status_message), MAX_STATUS)
    links = [
        {
            "trace_id": f"{link.context.trace_id:032x}",
            "span_id": f"{link.context.span_id:016x}",
        }
        for link in span.links
    ]
    fingerprint = (span.attributes or {}).get("iris.db.fingerprint")
    duration_ms = 0.0
    started_at = _iso(span.start_time or 0)
    if span.start_time is not None and span.end_time is not None:
        duration_ms = (span.end_time - span.start_time) / 1_000_000
    resolved_module = module_id or module_id_for(span.name, component, span.attributes or {})
    return {
        "trace_id": f"{context.trace_id:032x}" if context is not None else "0" * 32,
        "span_id": f"{context.span_id:016x}" if context is not None else "0" * 16,
        "parent_span_id": f"{parent.span_id:016x}"
        if parent is not None and parent.span_id
        else None,
        "name": span.name,
        "component": component,
        "kind": kind,
        "is_entry": is_entry,
        "started_at": started_at,
        "duration_ms": duration_ms,
        "self_ms": self_ms,
        "status": status,
        "status_message": status_message,
        "db_fingerprint": str(fingerprint) if fingerprint else None,
        "attributes": attributes,
        "events": events,
        "links": links,
        "module_id": resolved_module,
        "parent_module_id": parent_module_id,
    }


class SpanMetricsProcessor(SpanProcessor):
    """OTLP-only histogram of operation duration."""

    def __init__(self, histogram: Any) -> None:
        self._histogram = histogram

    def on_end(self, span: ReadableSpan) -> None:
        try:
            if span.start_time is None or span.end_time is None:
                return
            component = (span.attributes or {}).get("iris.component", "system")
            status = "error" if span.status.status_code is StatusCode.ERROR else "ok"
            self._histogram.record(
                (span.end_time - span.start_time) / 1_000_000_000,
                {
                    "iris.component": str(component),
                    "iris.operation": span.name,
                    "iris.status": status,
                },
            )
        except Exception:
            hub.note_internal()

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True
