"""OTLP metrics. Absent unless OBS_OTLP_ENDPOINT is set; recording is a no-op then."""

from __future__ import annotations

from typing import Any

from agent.observability.hub import hub

_http: Any = None
_tokens: Any = None
_installed = False

_OPERATION_BUCKETS = [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120]
_HTTP_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10]


def install(resource: Any, base: str, tracer_provider: Any = None) -> None:
    global _http, _tokens, _installed
    if _installed:
        return
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View

    from agent.observability.processors import SpanMetricsProcessor

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{base}/v1/metrics"),
        export_interval_millis=15_000,
    )
    provider = MeterProvider(
        resource=resource,
        metric_readers=[reader],
        views=[
            View(
                instrument_name="iris.operation.duration",
                aggregation=ExplicitBucketHistogramAggregation(_OPERATION_BUCKETS),
            ),
            View(
                instrument_name="http.server.request.duration",
                aggregation=ExplicitBucketHistogramAggregation(_HTTP_BUCKETS),
            ),
        ],
    )
    metrics.set_meter_provider(provider)
    meter = provider.get_meter("iris")
    histogram = meter.create_histogram("iris.operation.duration", unit="s")
    _http = meter.create_histogram("http.server.request.duration", unit="s")
    _tokens = meter.create_counter("iris.llm.tokens", unit="{token}")
    _observe(meter)
    target = tracer_provider if tracer_provider is not None else trace.get_tracer_provider()
    add = getattr(target, "add_span_processor", None)
    if add is not None:
        add(SpanMetricsProcessor(histogram))
    _installed = True


def record_http(seconds: float, method: str, route: str, status: int, door: str) -> None:
    if _http is None:
        return
    try:
        _http.record(seconds, {
            "http.request.method": method,
            "http.route": route,
            "http.response.status_code": status,
            "iris.door": door,
        })
    except Exception:
        hub.note_internal()


def record_tokens(model: str, prompt: int, completion: int) -> None:
    if _tokens is None:
        return
    try:
        if prompt:
            _tokens.add(prompt, {"gen_ai.request.model": model, "gen_ai.token.type": "input"})
        if completion:
            _tokens.add(completion, {"gen_ai.request.model": model, "gen_ai.token.type": "output"})
    except Exception:
        hub.note_internal()


def _observe(meter: Any) -> None:
    from opentelemetry.metrics import Observation

    def queue_items(_options: Any) -> list[Observation]:
        queue = _section("queue")
        return [
            Observation(float(queue.get(state) or 0), {"state": state})
            for state in ("due", "leased", "scheduled_retry", "exhausted")
        ]

    def oldest(_options: Any) -> list[Observation]:
        queue = _section("queue")
        value = queue.get("oldest_due_age_s")
        if value is None:
            return []
        return [Observation(float(value))]

    def pool(_options: Any) -> list[Observation]:
        section = _section("pool")
        return [
            Observation(float(section.get("in_use") or 0), {"state": "in_use"}),
            Observation(float(section.get("idle") or 0), {"state": "idle"}),
        ]

    def sessions(_options: Any) -> list[Observation]:
        server = _section("db")
        return [
            Observation(float(server.get(key) or 0), {"state": state})
            for key, state in (
                ("active", "active"),
                ("idle", "idle"),
                ("idle_in_transaction", "idle_in_transaction"),
                ("waiting", "waiting"),
                ("blocked", "blocked"),
            )
        ]

    def lag(_options: Any) -> list[Observation]:
        loop = _section("loop")
        value = loop.get("lag_ms_max")
        if value is None:
            return []
        return [Observation(float(value) / 1000)]

    def threads(_options: Any) -> list[Observation]:
        loop = _section("loop")
        return [Observation(float(loop.get("threadpool_busy") or 0))]

    def rss(_options: Any) -> list[Observation]:
        process = _section("process")
        value = process.get("rss_bytes")
        if value is None:
            return []
        return [Observation(float(value))]

    meter.create_observable_gauge("iris.queue.items", callbacks=[queue_items], unit="{item}")
    meter.create_observable_gauge("iris.queue.oldest_due_age", callbacks=[oldest], unit="s")
    meter.create_observable_gauge("iris.db.pool.connections", callbacks=[pool], unit="{connection}")
    meter.create_observable_gauge("iris.db.server.sessions", callbacks=[sessions], unit="{session}")
    meter.create_observable_gauge("iris.process.loop.lag", callbacks=[lag], unit="s")
    meter.create_observable_gauge("iris.process.threadpool.busy", callbacks=[threads], unit="{thread}")
    meter.create_observable_gauge("iris.process.memory.rss", callbacks=[rss], unit="By")


def _section(name: str) -> dict[str, Any]:
    probe = hub.latest_probe or {}
    section = probe.get(name) or {}
    return section if isinstance(section, dict) else {}
