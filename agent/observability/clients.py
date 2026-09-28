"""Spans, logs and collector state posted by the web app and the phone."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from agent.observability.catalog import module_id_for
from agent.observability.content import render_text
from agent.observability.hub import hub
from agent.observability.store import sink

_HEX32 = r"^[0-9a-f]{32}$"
_HEX16 = r"^[0-9a-f]{16}$"


class ClientSpan(BaseModel):
    trace_id: str = Field(pattern=_HEX32)
    span_id: str = Field(pattern=_HEX16)
    parent_span_id: str | None = Field(default=None, pattern=_HEX16)
    name: str = Field(max_length=300)
    started_at_ms: int
    duration_ms: float = Field(ge=0, le=86_400_000)
    status: Literal["ok", "error"]
    status_message: str | None = Field(default=None, max_length=4000)
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ClientLog(BaseModel):
    at_ms: int
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    message: str = Field(max_length=65_536)
    exception: str | None = Field(default=None, max_length=65_536)
    trace_id: str | None = Field(default=None, pattern=_HEX32)
    span_id: str | None = Field(default=None, pattern=_HEX16)
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ClientEvents(BaseModel):
    source: Literal["web", "android"]
    spans: list[ClientSpan] = Field(default_factory=list, max_length=500)
    logs: list[ClientLog] = Field(default_factory=list, max_length=500)
    state: dict[str, Any] | None = None


def _iso_ms(millis: int) -> str:
    moment = datetime.fromtimestamp(millis / 1000, tz=UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def ingest(events: ClientEvents) -> int:
    from agent.observability.tracing import enabled

    if not enabled():
        return 0
    accepted = 0
    received = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    for span in events.spans:
        attributes = {"iris.client": events.source, **span.attributes}
        record: dict[str, Any] = {
            "trace_id": span.trace_id,
            "span_id": span.span_id,
            "parent_span_id": span.parent_span_id,
            "name": span.name,
            "component": events.source,
            "kind": "client",
            "is_entry": span.parent_span_id is None,
            "started_at": _iso_ms(span.started_at_ms),
            "duration_ms": span.duration_ms,
            "self_ms": span.duration_ms,
            "status": span.status,
            "status_message": span.status_message,
            "db_fingerprint": None,
            "attributes": attributes,
            "events": [],
            "links": [],
            "module_id": module_id_for(span.name, events.source, attributes),
            "parent_module_id": None,
        }
        hub.publish_span(record)
        sink.put_span(record)
        accepted += 1
    for log in events.logs:
        logged: dict[str, Any] = {
            "at": _iso_ms(log.at_ms),
            "source": events.source,
            "level": log.level,
            "logger": f"{events.source}.client",
            "message": render_text(log.message, 65_536),
            "exception": render_text(log.exception, 65_536) if log.exception else None,
            "trace_id": log.trace_id,
            "span_id": log.span_id,
            "attributes": log.attributes,
        }
        hub.publish_log(logged)
        sink.put_log(logged)
        accepted += 1
    if events.state is not None:
        hub.client_state[events.source] = {"received_at": received, "state": events.state}
        sink.put_client_state(events.source, received, events.state)
        if events.source == "android":
            collector = events.state.get("collector") if isinstance(events.state, dict) else None
            if isinstance(collector, dict):
                rows: list[tuple[str, float]] = []
                for key, name in (
                    ("waiting_payloads", "android.waiting_payloads"),
                    ("rejected_payloads", "android.rejected_payloads"),
                    ("unreachable_streak", "android.unreachable_streak"),
                ):
                    value = collector.get(key)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        rows.append((name, float(value)))
                if rows:
                    hub.publish_samples(received, rows)
                    sink.put_samples(received, rows)
    return accepted
