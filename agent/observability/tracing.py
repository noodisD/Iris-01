"""The tracing API every call site uses.

Telemetry bookkeeping never changes what IRIS does: a failure while rendering
attributes or publishing a span is counted and swallowed. An exception from
the wrapped function always propagates.
"""

from __future__ import annotations

import functools
import importlib.metadata
import inspect
import os
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Literal, ParamSpec, TypeVar, get_args

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanLimits, TracerProvider
from opentelemetry.trace import Link, Span, SpanContext, SpanKind, Status, StatusCode, TraceFlags

from agent.observability.catalog import note_callable
from agent.observability.content import MAX_STATUS, MAX_TEXT, json_attr, render_text
from agent.observability.hub import hub
from agent.observability.io import capture_input, capture_output, instance_ids, output_captured

Component = Literal[
    "http",
    "db",
    "queue",
    "pipeline",
    "engine",
    "admission",
    "chat",
    "voice",
    "llm",
    "import",
    "sensors",
    "ideas",
    "insights",
    "system",
    "web",
    "android",
]
COMPONENTS: tuple[Component, ...] = get_args(Component)

P = ParamSpec("P")
R = TypeVar("R")

MAX_DB_SPANS_PER_TRACE = 1000
MAX_DB_FETCH_SPANS_PER_TRACE = 1000
_TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")

_CONFIGURED = False
_ENABLED = False
_TRACER: trace.Tracer | None = None
_PROVIDER: TracerProvider | None = None
_PROCESSOR: Any = None
_SUPPRESSED: ContextVar[bool] = ContextVar("iris_obs_suppressed", default=False)


@dataclass
class Budget:
    entry: SpanContext
    db_spans: int = 0
    db_queries: int = 0
    db_fetch_spans: int = 0
    db_fetch_spans_dropped: int = 0
    db_ms: float = 0.0
    llm_calls: int = 0
    llm_tokens: int = 0


_BUDGET: ContextVar[Budget | None] = ContextVar("iris_obs_budget", default=None)


def enabled() -> bool:
    return _ENABLED


def is_suppressed() -> bool:
    return _SUPPRESSED.get()


def recording() -> bool:
    return _ENABLED and not _SUPPRESSED.get()


def current_budget() -> Budget | None:
    return _BUDGET.get()


def processor() -> Any:
    return _PROCESSOR


def provider() -> TracerProvider | None:
    return _PROVIDER


def _note(exc: BaseException) -> None:
    del exc
    hub.note_internal()


def setup(role: Literal["server", "cli"]) -> None:
    """Idempotent. A disabled Observatory leaves enabled() false."""
    global _CONFIGURED, _ENABLED, _TRACER, _PROVIDER, _PROCESSOR
    if _CONFIGURED:
        return
    _CONFIGURED = True
    from agent.config import settings

    if not settings.OBS_ENABLED:
        return
    try:
        version = importlib.metadata.version("iris-minimal")
    except importlib.metadata.PackageNotFoundError:
        version = "0.1.0"
    resource = Resource.create(
        {
            "service.name": "iris",
            "service.version": version,
            "service.instance.id": f"{role}-{os.getpid()}",
            "deployment.environment.name": "local",
        }
    )
    from agent.observability.processors import ObservatorySpanProcessor

    built = TracerProvider(
        resource=resource,
        span_limits=SpanLimits(max_span_attributes=256, max_events=256, max_links=16),
    )
    span_processor = ObservatorySpanProcessor()
    built.add_span_processor(span_processor)
    endpoint = settings.OBS_OTLP_ENDPOINT.strip().rstrip("/")
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        from agent.observability import logs, metrics

        built.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
        )
        metrics.install(resource, endpoint, built)
        logs.install_otlp(resource, endpoint)
    trace.set_tracer_provider(built)
    _PROVIDER = built
    _PROCESSOR = span_processor
    _TRACER = built.get_tracer("iris")
    _ENABLED = True


def _tracer() -> trace.Tracer:
    if _TRACER is None:
        return trace.get_tracer("iris")
    return _TRACER


@contextmanager
def suppressed() -> Iterator[None]:
    token = _SUPPRESSED.set(True)
    try:
        yield
    finally:
        _SUPPRESSED.reset(token)


def _convert(attrs: Mapping[str, object] | None) -> dict[str, str | bool | int | float]:
    if not attrs:
        return {}
    converted: dict[str, str | bool | int | float] = {}
    for key, value in attrs.items():
        if value is None:
            continue
        if isinstance(value, bool):
            converted[key] = value
        elif isinstance(value, int):
            converted[key] = value
        elif isinstance(value, float):
            converted[key] = value
        elif isinstance(value, str):
            converted[key] = render_text(value, MAX_TEXT)
        elif isinstance(value, (Mapping, list, tuple)):
            converted[key] = json_attr(value, MAX_TEXT)
        else:
            converted[key] = str(value)
    return converted


def apply_budget(span: Span, budget: Budget | None = None) -> None:
    chosen = current_budget() if budget is None else budget
    if chosen is None or not span.is_recording():
        return
    span.set_attribute("iris.db.queries", chosen.db_queries)
    span.set_attribute("iris.db.spans_dropped", chosen.db_queries - chosen.db_spans)
    span.set_attribute("iris.db.fetch_spans_dropped", chosen.db_fetch_spans_dropped)
    span.set_attribute("iris.db.time_ms", chosen.db_ms)
    span.set_attribute("iris.llm.calls", chosen.llm_calls)
    span.set_attribute("iris.llm.tokens", chosen.llm_tokens)


def open_budget(span: Span) -> Token[Budget | None]:
    return _BUDGET.set(Budget(entry=span.get_span_context()))


def close_budget(token: Token[Budget | None], span: Span) -> None:
    try:
        apply_budget(span)
    finally:
        _BUDGET.reset(token)


@contextmanager
def span(
    name: str,
    component: Component,
    attrs: Mapping[str, object] | None = None,
    *,
    kind: SpanKind = SpanKind.INTERNAL,
    links: Sequence[Link] = (),
    entry: bool = False,
    root: bool = False,
) -> Iterator[Span]:
    if not recording():
        yield trace.INVALID_SPAN
        return
    try:
        attributes = {"iris.component": component, **_convert(attrs)}
    except Exception as exc:
        _note(exc)
        attributes = {"iris.component": component}
    kwargs: dict[str, Any] = {}
    if root:
        kwargs["context"] = Context()
    with _tracer().start_as_current_span(
        name,
        kind=kind,
        attributes=attributes,
        links=list(links),
        record_exception=True,
        set_status_on_exception=True,
        **kwargs,
    ) as current:
        budget_token: Token[Budget | None] | None = None
        if entry:
            try:
                current.set_attribute("iris.entry", True)
            except Exception as exc:
                _note(exc)
            budget_token = open_budget(current)
        try:
            yield current
        finally:
            if budget_token is not None:
                try:
                    close_budget(budget_token, current)
                except Exception as exc:
                    _note(exc)


def _reject_async(fn: Callable[..., Any]) -> None:
    if inspect.isgeneratorfunction(fn) or inspect.iscoroutinefunction(fn):
        raise TypeError(f"{fn.__qualname__} is a generator or coroutine; use start_detached")


def _note_callable(name: str, component: Component, fn: Callable[..., Any]) -> None:
    try:
        note_callable(name, component, fn)
    except Exception as exc:
        _note(exc)


def _recorded_call(
    signature: inspect.Signature,
    names: Sequence[str],
    call_args: tuple[Any, ...],
    call_kwargs: dict[str, Any],
) -> tuple[dict[str, object], dict[str, object] | None]:
    recorded: dict[str, object] = {}
    try:
        bound = signature.bind(*call_args, **call_kwargs)
        bound.apply_defaults()
    except Exception as exc:
        _note(exc)
        return recorded, None
    for arg_name in names:
        if arg_name in bound.arguments:
            recorded[f"iris.arg.{arg_name}"] = bound.arguments[arg_name]
    return recorded, _bound_input(bound)


def _capture_bound(current: Span, payload: dict[str, object] | None) -> None:
    if payload is None:
        return
    try:
        capture_input(payload, span=current)
    except Exception as exc:
        _note(exc)


def _capture_return(
    current: Span,
    value: Any,
    result: Callable[[Any], Mapping[str, object]] | None,
) -> None:
    if result is not None:
        with suppress(Exception):
            set_attributes(result(value))
    try:
        if not output_captured(current):
            capture_output(value, span=current)
    except Exception as exc:
        _note(exc)


def traced(
    name: str,
    component: Component,
    *,
    args: Sequence[str] = (),
    result: Callable[[Any], Mapping[str, object]] | None = None,
    entry: bool = False,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        _reject_async(fn)
        signature = inspect.signature(fn)
        _note_callable(name, component, fn)

        @functools.wraps(fn)
        def wrapper(*call_args: P.args, **call_kwargs: P.kwargs) -> R:
            if not recording():
                return fn(*call_args, **call_kwargs)
            recorded, payload = _recorded_call(signature, args, call_args, call_kwargs)
            with span(name, component, recorded, entry=entry) as current:
                _capture_bound(current, payload)
                value = fn(*call_args, **call_kwargs)
                _capture_return(current, value, result)
                return value

        return wrapper

    return decorator


def _bound_input(bound: inspect.BoundArguments) -> dict[str, object]:
    payload: dict[str, object] = {}
    ids: dict[str, object] = {}
    for arg_name, arg_value in bound.arguments.items():
        if arg_name in ("self", "cls"):
            ids = instance_ids(arg_value)
            continue
        payload[arg_name] = arg_value
    for key, item in ids.items():
        payload.setdefault(key, item)
    return payload


def start_detached(
    name: str,
    component: Component,
    attrs: Mapping[str, object] | None = None,
    *,
    kind: SpanKind = SpanKind.INTERNAL,
) -> Span:
    if not recording():
        return trace.INVALID_SPAN
    try:
        attributes = {"iris.component": component, **_convert(attrs)}
    except Exception as exc:
        _note(exc)
        attributes = {"iris.component": component}
    return _tracer().start_span(name, kind=kind, attributes=attributes)


def set_attributes(attrs: Mapping[str, object]) -> None:
    current = trace.get_current_span()
    if not current.is_recording():
        return
    try:
        for key, value in _convert(attrs).items():
            current.set_attribute(key, value)
    except Exception as exc:
        _note(exc)


def mark_error(span: Span, error: BaseException) -> None:
    try:
        span.record_exception(error)
        span.set_status(Status(StatusCode.ERROR, f"{type(error).__name__}: {error}"[:MAX_STATUS]))
    except Exception as exc:
        _note(exc)


def current_traceparent() -> str | None:
    budget = _BUDGET.get()
    if budget is not None and budget.entry.is_valid:
        context = budget.entry
    else:
        context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return f"00-{context.trace_id:032x}-{context.span_id:016x}-01"


def links_from_traceparent(value: str | None) -> list[Link]:
    if not value:
        return []
    match = _TRACEPARENT.match(value.strip())
    if match is None:
        return []
    context = SpanContext(
        trace_id=int(match.group(1), 16),
        span_id=int(match.group(2), 16),
        is_remote=True,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    return [Link(context)]
