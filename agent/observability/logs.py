"""Bridge Python logging into the Observatory and, when configured, OTLP."""

from __future__ import annotations

import logging
import traceback
from datetime import UTC, datetime
from typing import Any

from opentelemetry import trace

from agent.observability.content import MAX_BODY, render_text
from agent.observability.hub import hub
from agent.observability.store import sink
from agent.observability.tracing import enabled, is_suppressed

_otel_handler: logging.Handler | None = None


def _iso(created: float) -> str:
    return datetime.fromtimestamp(created, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class TraceContextFilter(logging.Filter):
    """Puts the current trace id on the record so the file format can print it."""

    def filter(self, record: logging.LogRecord) -> bool:
        context = trace.get_current_span().get_span_context()
        record.trace_id = f"{context.trace_id:032x}" if context.is_valid else "-"  # type: ignore[attr-defined]
        return True


class ObservatoryLogHandler(logging.Handler):
    """INFO+ into the Observatory. Suppressed paths still keep WARNING+."""

    def __init__(self, level: int = logging.INFO) -> None:
        super().__init__(level)
        self._iris_observatory = True

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if not enabled():
                return
            if is_suppressed() and record.levelno < logging.WARNING:
                return
            self._emit(record)
        except Exception:
            hub.note_internal()

    def _emit(self, record: logging.LogRecord) -> None:
        span = trace.get_current_span()
        context = span.get_span_context()
        trace_id = f"{context.trace_id:032x}" if context.is_valid else None
        span_id = f"{context.span_id:016x}" if context.is_valid else None
        exception = None
        if record.exc_info and record.exc_info[0] is not None:
            exception = render_text("".join(traceback.format_exception(*record.exc_info)), MAX_BODY)
        message = render_text(record.getMessage(), MAX_BODY)
        payload: dict[str, Any] = {
            "at": _iso(record.created),
            "source": "server",
            "level": record.levelname,
            "logger": record.name,
            "message": message,
            "exception": exception,
            "trace_id": trace_id,
            "span_id": span_id,
            "attributes": {
                "code.function": record.funcName,
                "code.lineno": record.lineno,
                "thread.name": record.threadName,
            },
        }
        hub.publish_log(payload)
        sink.put_log(payload)
        if record.levelno >= logging.WARNING and span.is_recording():
            span.add_event("log", {
                "log.severity": record.levelname,
                "log.logger": record.name,
                "log.message": message[:4096],
            })
        if _otel_handler is not None:
            _otel_handler.emit(record)


def attach(logger_name: str, level: int) -> None:
    target = logging.getLogger(logger_name)
    if any(getattr(handler, "_iris_observatory", False) for handler in target.handlers):
        return
    target.addHandler(ObservatoryLogHandler(level))


def install_otlp(resource: Any, base: str) -> None:
    global _otel_handler
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{base}/v1/logs"))
    )
    set_logger_provider(provider)
    _otel_handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
