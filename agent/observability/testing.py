"""Test capture. Nothing is retained between tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider

from agent.observability import tracing
from agent.observability.hub import hub
from agent.observability.store import sink

_capture: _Capture | None = None


class _Capture(SpanProcessor):
    def __init__(self) -> None:
        self.active = False
        self.spans: list[ReadableSpan] = []

    def on_end(self, span: ReadableSpan) -> None:
        if self.active:
            self.spans.append(span)

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


@contextmanager
def capturing() -> Iterator[list[ReadableSpan]]:
    global _capture
    tracing.setup("server")
    provider = trace.get_tracer_provider()
    if _capture is None:
        _capture = _Capture()
        if isinstance(provider, TracerProvider):
            provider.add_span_processor(_capture)
    _capture.active = True
    collected: list[ReadableSpan] = []
    _capture.spans = collected
    try:
        yield collected
    finally:
        if _capture is not None:
            _capture.active = False
            _capture.spans = []


def reset() -> None:
    hub.clear()
    sink.clear()
    current = tracing.processor()
    if current is not None:
        current.clear()
