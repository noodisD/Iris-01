"""Bounded function input/output rendering for Observatory spans.

Rendering never calls ``repr`` on an unknown object, never reads a file, and
never advances an iterator. Failures stay inside the helper: callers still
return or raise exactly what the application did.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from pathlib import PurePath
from typing import Any, Literal

from opentelemetry import trace
from opentelemetry.trace import Span

from agent.observability.content import MAX_TEXT, is_vector, render_text
from agent.observability.hub import hub

MAX_VALUES = 4096
MAX_DEPTH = 16
_VECTOR_FIELDS = frozenset({"embedding", "vector", "centroid"})
_TRUNCATION_MARK = "… [truncated "

Side = Literal["input", "output"]
IOFormat = Literal["text", "json"]
IOState = Literal["captured", "metadata_only", "pending", "not_captured"]


@dataclass(frozen=True)
class Rendered:
    text: str
    format: IOFormat
    truncated: bool
    reason: str | None


@dataclass(frozen=True)
class IOPart:
    label: str
    state: IOState
    format: IOFormat
    text: str | None
    truncated: bool | None
    partial: bool
    reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "state": self.state,
            "format": self.format,
            "text": self.text,
            "truncated": self.truncated,
            "partial": self.partial,
            "reason": self.reason,
        }


@dataclass
class _Budget:
    remaining: int
    visited: int = 0
    truncated: bool = False
    reasons: list[str] | None = None
    ancestors: list[int] | None = None

    def __post_init__(self) -> None:
        if self.reasons is None:
            self.reasons = []
        if self.ancestors is None:
            self.ancestors = []

    def note(self, reason: str) -> None:
        self.truncated = True
        assert self.reasons is not None
        if reason not in self.reasons:
            self.reasons.append(reason)

    def exhausted(self) -> bool:
        return self.visited >= MAX_VALUES or self.remaining <= 0


def _reason(budget: _Budget) -> str | None:
    if not budget.reasons:
        return None
    return "; ".join(budget.reasons)


def _type_only(value: object) -> str:
    kind = type(value)
    module = getattr(kind, "__module__", "") or ""
    name = getattr(kind, "__qualname__", None) or getattr(kind, "__name__", "object")
    if module and module != "builtins":
        return f"<{module}.{name}>"
    return f"<{name}>"


def _numpy_description(value: object) -> str | None:
    try:
        import numpy as np  # noqa: PLC0415
    except ImportError:
        return None
    if not isinstance(value, np.ndarray):
        return None
    shape = tuple(int(item) for item in value.shape)
    return f"<ndarray shape={shape} dtype={value.dtype}>"


_NOT_LEAF = object()


def _render_string(value: str, budget: _Budget) -> str:
    cleaned = value.replace("\x00", "")
    if len(cleaned) > budget.remaining:
        budget.note("size limit")
        cleaned = cleaned[: max(budget.remaining, 0)]
    budget.remaining -= len(cleaned)
    return cleaned


def _render_number(value: float) -> str | float:
    if math.isfinite(value):
        return value
    if math.isnan(value):
        return "NaN"
    if value > 0:
        return "Infinity"
    return "-Infinity"


def _key(value: object) -> str:
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        rendered = _render_number(value)
        return rendered if isinstance(rendered, str) else str(rendered)
    return _type_only(value)


def _enter(value: object, budget: _Budget) -> bool:
    """True when this container is a new ancestor. False means cycle."""
    ancestors = budget.ancestors
    if ancestors is None:
        return True
    ident = id(value)
    if ident in ancestors:
        budget.note("cycle")
        return False
    ancestors.append(ident)
    return True


def _leave(budget: _Budget) -> None:
    ancestors = budget.ancestors
    if ancestors:
        ancestors.pop()


def _render_leaf(value: object, budget: _Budget) -> object:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return _render_number(value)
    if isinstance(value, str):
        return _render_string(value, budget)
    return _describe_opaque_leaf(value, budget)


def _describe_opaque_leaf(value: object, budget: _Budget) -> object:
    if isinstance(value, (bytes, bytearray, memoryview)):
        budget.note("metadata-only value")
        return f"<{type(value).__name__} len={len(value)}>"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, PurePath):
        return _render_string(str(value), budget)
    array = _numpy_description(value)
    if array is None:
        return _NOT_LEAF
    budget.note("metadata-only value")
    return array


def _is_container(value: object) -> bool:
    if isinstance(value, (dict, list, tuple)):
        return True
    return bool(is_dataclass(value) and not isinstance(value, type))


def _render(value: object, budget: _Budget, depth: int, field: str | None) -> object:
    if budget.visited >= MAX_VALUES:
        budget.note("traversal limit")
        return "<traversal limit>"
    budget.visited += 1
    if budget.remaining <= 0:
        budget.note("size limit")
        return "<size limit>"
    leaf = _render_leaf(value, budget)
    if leaf is not _NOT_LEAF:
        return leaf
    if not _is_container(value):
        budget.note("metadata-only value")
        return _type_only(value)
    if depth >= MAX_DEPTH:
        budget.note("depth limit")
        return "<depth limit>"
    if not _enter(value, budget):
        return "<cycle>"
    try:
        return _render_container(value, budget, depth, field)
    finally:
        _leave(budget)


def _stop(budget: _Budget) -> None:
    if budget.visited >= MAX_VALUES:
        budget.note("traversal limit")
        return
    budget.note("size limit")


def _render_mapping(value: dict[Any, Any], budget: _Budget, depth: int) -> dict[str, object]:
    rendered: dict[str, object] = {}
    for key, item in value.items():
        if budget.exhausted():
            _stop(budget)
            break
        name = _key(key)
        rendered[name] = _render(item, budget, depth + 1, name)
    return rendered


def _render_sequence(
    value: list[Any] | tuple[Any, ...],
    budget: _Budget,
    depth: int,
    field: str | None,
) -> object:
    if field in _VECTOR_FIELDS and is_vector(value):
        budget.note("metadata-only value")
        return f"<vector dim={len(value)}>"
    items: list[object] = []
    for item in value:
        if budget.exhausted():
            _stop(budget)
            break
        items.append(_render(item, budget, depth + 1, None))
    return items


def _field_value(owner: object, name: str, budget: _Budget, depth: int) -> object:
    try:
        field_value = getattr(owner, name)
    except Exception:
        budget.note("metadata-only value")
        return "<unavailable>"
    return _render(field_value, budget, depth + 1, name)


def _render_dataclass(value: object, budget: _Budget, depth: int) -> dict[str, object]:
    rendered: dict[str, object] = {}
    for field_info in fields(value):  # type: ignore[arg-type]
        if budget.exhausted():
            _stop(budget)
            break
        rendered[field_info.name] = _field_value(value, field_info.name, budget, depth)
    return rendered


def _render_container(value: object, budget: _Budget, depth: int, field: str | None) -> object:
    if isinstance(value, dict):
        return _render_mapping(value, budget, depth)
    if isinstance(value, (list, tuple)):
        return _render_sequence(value, budget, depth, field)
    return _render_dataclass(value, budget, depth)


def render_io(value: object) -> Rendered:
    """JSON text plus truncation metadata. Does not mutate ``value``."""
    budget = _Budget(remaining=MAX_TEXT)
    rendered = _render(value, budget, 0, None)
    try:
        encoded = json.dumps(rendered, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("observatory I/O render produced non-JSON") from exc
    encoded = encoded.replace("\x00", "")
    if len(encoded) > MAX_TEXT:
        budget.note("size limit")
        return Rendered(
            text=encoded[:MAX_TEXT],
            format="text",
            truncated=True,
            reason=_reason(budget),
        )
    return Rendered(
        text=encoded,
        format="json",
        truncated=budget.truncated,
        reason=_reason(budget),
    )


def _target(span: Span | None) -> Span | None:
    current = span if span is not None else trace.get_current_span()
    if current is None or not current.is_recording():
        return None
    return current


def _apply(span: Span, side: Side, rendered: Rendered) -> None:
    span.set_attribute(f"iris.io.{side}", rendered.text)
    span.set_attribute(f"iris.io.{side}.format", rendered.format)
    span.set_attribute(f"iris.io.{side}.truncated", rendered.truncated)
    if rendered.reason is not None:
        span.set_attribute(f"iris.io.{side}.reason", render_text(rendered.reason, 1_024))


def _capture(side: Side, value: object, span: Span | None) -> None:
    target = _target(span)
    if target is None:
        return
    _apply(target, side, render_io(value))


def capture_input(value: object, *, span: Span | None = None) -> None:
    """Record ``value`` on the current or explicit span. Never raises."""
    try:
        _capture("input", value, span)
    except Exception:
        hub.note_internal()


def capture_output(value: object, *, span: Span | None = None) -> None:
    """Record ``value`` on the current or explicit span. Never raises."""
    try:
        _capture("output", value, span)
    except Exception:
        hub.note_internal()


def output_captured(span: Span | None) -> bool:
    target = span if span is not None else trace.get_current_span()
    attributes = getattr(target, "attributes", None)
    if not isinstance(attributes, Mapping):
        return False
    return "iris.io.output" in attributes


def instance_ids(value: object) -> dict[str, object]:
    """user_id and session_id from an instance dict, never via attribute lookup."""
    try:
        raw = object.__getattribute__(value, "__dict__")
    except Exception:
        return {}
    if raw is None:
        return {}
    kept: dict[str, object] = {}
    for key in ("user_id", "session_id"):
        try:
            if key in raw:
                kept[key] = raw[key]
        except Exception:
            continue
    return kept


def legacy_truncated(text: str | None, byte_size: object | None, cap: int) -> bool | None:
    """True/false when the recording proves it; None for an unknown legacy capture."""
    if isinstance(text, str) and _TRUNCATION_MARK in text:
        return True
    if isinstance(byte_size, (int, float)) and not isinstance(byte_size, bool):
        if byte_size > cap:
            return True
        return isinstance(text, str) and byte_size > len(text.encode("utf-8", errors="replace"))
    return None


def _attr(attributes: Mapping[str, Any], key: str) -> Any:
    if key not in attributes:
        return None
    return attributes.get(key)


def _bool_attr(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _generic_part(attributes: Mapping[str, Any], side: Side, label: str) -> IOPart | None:
    key = f"iris.io.{side}"
    if key not in attributes:
        return None
    text = attributes.get(key)
    format_value = attributes.get(f"iris.io.{side}.format")
    fmt: IOFormat = "json" if format_value == "json" else "text"
    reason = attributes.get(f"iris.io.{side}.reason")
    reason_text = reason if isinstance(reason, str) else None
    state: IOState = "captured"
    if reason_text and "metadata-only" in reason_text and not isinstance(text, str):
        state = "metadata_only"
    if (
        isinstance(text, str)
        and text.startswith("<")
        and reason_text
        and "metadata-only" in reason_text
    ):
        parsed_scalar = text
        if fmt == "json":
            try:
                parsed_scalar = json.loads(text)
            except json.JSONDecodeError:
                parsed_scalar = text
        if isinstance(parsed_scalar, str) and parsed_scalar.startswith("<"):
            state = "metadata_only"
    truncated = _bool_attr(attributes.get(f"iris.io.{side}.truncated"))
    partial = _bool_attr(attributes.get(f"iris.io.{side}.partial")) is True
    return IOPart(
        label=label,
        state=state,
        format=fmt,
        text=text if isinstance(text, str) else None,
        truncated=truncated,
        partial=partial,
        reason=reason_text,
    )


def _missing(label: str, reason: str | None = None) -> IOPart:
    return IOPart(
        label=label,
        state="not_captured",
        format="text",
        text=None,
        truncated=None,
        partial=False,
        reason=reason or "Not captured for this invocation",
    )


def _text_part(
    label: str,
    text: object,
    *,
    truncated: bool | None,
    partial: bool = False,
    reason: str | None = None,
    state: IOState = "captured",
    fmt: IOFormat = "text",
) -> IOPart:
    return IOPart(
        label=label,
        state=state,
        format=fmt,
        text=text if isinstance(text, str) else None,
        truncated=truncated,
        partial=partial,
        reason=reason,
    )


_PAYLOAD_KEYS = frozenset(
    {
        "iris.io.input",
        "iris.io.input.format",
        "iris.io.input.truncated",
        "iris.io.input.reason",
        "iris.io.input.partial",
        "iris.io.output",
        "iris.io.output.format",
        "iris.io.output.truncated",
        "iris.io.output.reason",
        "iris.io.output.partial",
        "iris.http.request_body",
        "iris.http.response_body",
        "iris.llm.prompt",
        "iris.llm.output",
        "db.query.text",
        "db.query.parameters",
    }
)


def payload_keys() -> frozenset[str]:
    return _PAYLOAD_KEYS


def strip_payload_attributes(attributes: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in attributes.items() if key not in _PAYLOAD_KEYS}


def parts_for(
    name: str,
    component: str,
    attributes: Mapping[str, Any] | None,
    *,
    status: str = "ok",
    status_message: str | None = None,
    running: bool = False,
) -> list[IOPart]:
    """Inspector parts from generic capture, else the domain attributes already stored."""
    attrs = attributes or {}
    generic_in = _generic_part(attrs, "input", "Arguments")
    generic_out = _generic_part(attrs, "output", "Result")
    if generic_in is not None or generic_out is not None:
        parts: list[IOPart] = []
        parts.append(generic_in or _missing("Arguments"))
        if generic_out is not None:
            parts.append(generic_out)
        elif running:
            parts.append(
                IOPart("Result", "pending", "text", None, None, False, "Waiting for output.")
            )
        elif status == "error":
            parts.append(
                IOPart(
                    "Result",
                    "not_captured",
                    "text",
                    None,
                    None,
                    False,
                    status_message or "The invocation failed before a result was captured.",
                )
            )
        else:
            parts.append(_missing("Result"))
        return parts
    if component == "http" or name.startswith("http:"):
        return _http_parts(attrs, running=running)
    if component == "llm" or name.startswith("llm."):
        return _llm_parts(
            name, attrs, running=running, status=status, status_message=status_message
        )
    if component == "db" or name.startswith(("db.fetch", "SELECT ", "INSERT ")):
        return _db_parts(name, attrs)
    if component in ("web", "android"):
        return _client_parts(component, name, attrs)
    return [_missing("Arguments"), _missing("Result")]


def _http_parts(attrs: Mapping[str, Any], *, running: bool) -> list[IOPart]:
    request = _attr(attrs, "iris.http.request_body")
    response = _attr(attrs, "iris.http.response_body")
    request_complete = _bool_attr(_attr(attrs, "iris.http.request_body_complete"))
    response_complete = _bool_attr(_attr(attrs, "iris.http.response_body_complete"))
    request_truncated = _bool_attr(_attr(attrs, "iris.http.request_body_truncated"))
    response_truncated = _bool_attr(_attr(attrs, "iris.http.response_body_truncated"))
    if request_truncated is None:
        request_truncated = legacy_truncated(
            request if isinstance(request, str) else None,
            _attr(attrs, "http.request.body.size"),
            65_536,
        )
    if response_truncated is None:
        response_truncated = legacy_truncated(
            response if isinstance(response, str) else None,
            _attr(attrs, "http.response.body.size"),
            65_536,
        )
    request_reason = None
    request_state: IOState = "captured" if isinstance(request, str) else "not_captured"
    if request_state == "not_captured":
        if request_complete is False and running:
            request_state = "pending"
            request_reason = "Waiting for the request body."
        else:
            request_reason = "Not captured for this invocation"
    elif request_truncated is None:
        request_reason = "Legacy capture; completeness was not recorded."
    response_state: IOState = "captured" if isinstance(response, str) else "not_captured"
    response_reason = None
    partial = False
    if running and not isinstance(response, str):
        response_state = "pending"
        response_reason = "Waiting for output."
    elif response_state == "not_captured":
        response_reason = "Not captured for this invocation"
    elif response_truncated is None:
        response_reason = "Legacy capture; completeness was not recorded."
    if response_complete is False and not running:
        partial = True
    metadata = {
        "method": _attr(attrs, "http.request.method"),
        "route": _attr(attrs, "http.route"),
        "path": _attr(attrs, "url.path"),
        "query": _attr(attrs, "url.query"),
        "status": _attr(attrs, "http.response.status_code"),
        "request_content_type": _attr(attrs, "iris.http.request_content_type"),
        "response_content_type": _attr(attrs, "iris.http.response_content_type"),
        "request_bytes": _attr(attrs, "http.request.body.size"),
        "response_bytes": _attr(attrs, "http.response.body.size"),
    }
    return [
        _text_part(
            "Request metadata",
            json.dumps(metadata, ensure_ascii=False, default=str),
            truncated=False,
            fmt="json",
        ),
        _text_part(
            "Request body",
            request,
            truncated=request_truncated,
            reason=request_reason,
            state=request_state,
        ),
        _text_part(
            "Response body",
            response,
            truncated=response_truncated,
            partial=partial,
            reason=response_reason,
            state=response_state,
        ),
    ]


def _llm_parts(
    name: str,
    attrs: Mapping[str, Any],
    *,
    running: bool,
    status: str,
    status_message: str | None,
) -> list[IOPart]:
    prompt = _attr(attrs, "iris.llm.prompt")
    output = _attr(attrs, "iris.llm.output")
    prompt_truncated = legacy_truncated(prompt if isinstance(prompt, str) else None, None, MAX_TEXT)
    output_truncated = legacy_truncated(output if isinstance(output, str) else None, None, MAX_TEXT)
    if prompt_truncated is None and isinstance(prompt, str):
        prompt_truncated = False
    if output_truncated is None and isinstance(output, str):
        output_truncated = False
    if name == "llm.embeddings" or _attr(attrs, "gen_ai.operation.name") == "embeddings":
        output_state: IOState = "metadata_only"
        output_text = json.dumps(
            {
                "dimension": _attr(attrs, "iris.llm.dimension")
                or _attr(attrs, "gen_ai.embeddings.dimension"),
                "output_bytes": _attr(attrs, "iris.llm.output_bytes"),
            },
            ensure_ascii=False,
            default=str,
        )
        output_reason: str | None = "Vector values are stored as metadata, not text."
    elif name == "llm.speech" or _attr(attrs, "gen_ai.operation.name") == "speech":
        output_state = "metadata_only"
        output_text = json.dumps(
            {"output_bytes": _attr(attrs, "iris.llm.output_bytes")},
            ensure_ascii=False,
            default=str,
        )
        output_reason = "Audio is stored as a byte length, not content."
    elif isinstance(output, str):
        output_state = "captured"
        output_text = output
        output_reason = (
            None
            if output_truncated is not None
            else "Legacy capture; completeness was not recorded."
        )
    elif running:
        output_state = "pending"
        output_text = None
        output_reason = "Waiting for output."
    elif status == "error":
        output_state = "not_captured"
        output_text = None
        output_reason = status_message or "The invocation failed before a result was captured."
    else:
        output_state = "not_captured"
        output_text = None
        output_reason = "Not captured for this invocation"
    prompt_state: IOState = "captured" if isinstance(prompt, str) else "not_captured"
    return [
        _text_part(
            "Prompt",
            prompt,
            truncated=prompt_truncated if prompt_state == "captured" else None,
            reason=None if prompt_state == "captured" else "Not captured for this invocation",
            state=prompt_state,
        ),
        _text_part(
            "Completion",
            output_text,
            truncated=output_truncated if output_state == "captured" else None,
            reason=output_reason,
            state=output_state,
            fmt="json" if output_state == "metadata_only" else "text",
        ),
    ]


def _db_parts(name: str, attrs: Mapping[str, Any]) -> list[IOPart]:
    if name.startswith("db.fetch"):
        columns = _attr(attrs, "iris.db.columns")
        rows = _attr(attrs, "iris.db.rows")
        if columns is None and rows is None:
            return [_missing("Columns and fetched rows")]
        return [
            _text_part(
                "Columns and fetched rows",
                json.dumps({"columns": columns, "rows": rows}, ensure_ascii=False, default=str),
                truncated=_bool_attr(_attr(attrs, "iris.io.output.truncated")),
                fmt="json",
            )
        ]
    statement = _attr(attrs, "db.query.text")
    parameters = _attr(attrs, "db.query.parameters")
    rows = _attr(attrs, "db.response.returned_rows")
    statement_truncated = legacy_truncated(
        statement if isinstance(statement, str) else None, None, 16_384
    )
    return [
        _text_part(
            "Statement",
            statement,
            truncated=statement_truncated,
            state="captured" if isinstance(statement, str) else "not_captured",
            reason=None if isinstance(statement, str) else "Not captured for this invocation",
        ),
        _text_part(
            "Parameters",
            parameters if isinstance(parameters, str) else None,
            truncated=legacy_truncated(
                parameters if isinstance(parameters, str) else None, None, 16_384
            ),
            state="captured" if isinstance(parameters, str) else "not_captured",
            reason=None if isinstance(parameters, str) else "Not captured for this invocation",
            fmt="json" if isinstance(parameters, str) else "text",
        ),
        _text_part(
            "Affected/result row count",
            json.dumps(rows),
            truncated=False,
            state="captured" if rows is not None else "not_captured",
            reason=None if rows is not None else "Not captured for this invocation",
            fmt="json",
        ),
    ]


def _client_parts(component: str, name: str, attrs: Mapping[str, Any]) -> list[IOPart]:
    if component == "android" and name in ("collector.state", "android.collector.state"):
        return [
            _text_part(
                "Collector state",
                json.dumps(dict(attrs), ensure_ascii=False, default=str),
                truncated=False,
                reason="Snapshot; not a timed invocation.",
                fmt="json",
            )
        ]
    return [
        _text_part(
            "Client metadata",
            json.dumps(dict(attrs), ensure_ascii=False, default=str),
            truncated=False,
            reason="Client metadata is not a captured request body. Server bodies are on the linked HTTP span.",
            fmt="json",
        )
    ]
