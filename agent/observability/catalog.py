"""Stable module identities for the Observatory system map.

The catalog is declarative. Decoration may fill a signature and source line;
it must not import an unloaded subsystem or call the function. Route and table
entries are registered by the API process. This module does not import iris_api
or agent.database.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Lock
from typing import Any, Literal

_ROOT = Path(__file__).resolve().parents[2]
_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
_EXCLUDED_TABLES = frozenset({"schema_migrations", "_iris_test_database"})

Kind = Literal["operation", "route", "table", "client", "state"]
EdgeKind = Literal["call", "flow"]


@dataclass(frozen=True)
class ModuleSpec:
    id: str
    component: str
    label: str
    source: dict[str, Any] | None
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    kind: Kind = "operation"
    signature: str | None = None

    def as_dict(self) -> dict[str, Any]:
        source = None if self.source is None else dict(self.source)
        return {
            "id": self.id,
            "component": self.component,
            "label": self.label,
            "source": source,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "kind": self.kind,
            "signature": self.signature,
        }


@dataclass(frozen=True)
class DeclaredEdge:
    source: str
    target: str
    kind: EdgeKind

    def as_dict(self) -> dict[str, str]:
        return {"source": self.source, "target": self.target, "kind": self.kind}


def _spec(
    module_id: str,
    component: str,
    label: str,
    file: str,
    symbol: str,
    inputs: tuple[str, ...],
    outputs: tuple[str, ...],
    *,
    kind: Kind = "operation",
) -> ModuleSpec:
    return ModuleSpec(
        id=module_id,
        component=component,
        label=label,
        source={"file": file, "symbol": symbol, "line": None},
        inputs=inputs,
        outputs=outputs,
        kind=kind,
    )


def _client(
    module_id: str,
    component: str,
    label: str,
    file: str,
    symbol: str,
    inputs: tuple[str, ...],
    outputs: tuple[str, ...],
    *,
    kind: Kind = "client",
) -> ModuleSpec:
    return _spec(module_id, component, label, file, symbol, inputs, outputs, kind=kind)


_MODULES: dict[str, ModuleSpec] = {
    spec.id: spec
    for spec in (
        _spec(
            "chat.turn",
            "chat",
            "Turn",
            "agent/core.py",
            "PersonalAICompanion.chat",
            ("user/session", "message", "spoken"),
            ("reply",),
        ),
        _spec(
            "chat.begin_turn",
            "chat",
            "Begin turn",
            "agent/core.py",
            "PersonalAICompanion._begin_turn",
            ("user/session", "message", "spoken"),
            ("messages", "enhanced prompt"),
        ),
        _spec(
            "chat.context",
            "chat",
            "Context",
            "agent/core.py",
            "PersonalAICompanion._get_aggregated_context",
            ("user/session",),
            ("assembled context",),
        ),
        _spec(
            "chat.earlier_conversations",
            "chat",
            "Earlier conversations",
            "agent/core.py",
            "PersonalAICompanion._earlier_conversations",
            ("user/session",),
            ("context text",),
        ),
        _spec(
            "chat.habits_context",
            "chat",
            "Habits context",
            "agent/core.py",
            "PersonalAICompanion._get_habits_context",
            ("user/session",),
            ("context text",),
        ),
        _spec(
            "chat.reflections_context",
            "chat",
            "Reflections context",
            "agent/core.py",
            "PersonalAICompanion._get_reflections_context",
            ("user/session",),
            ("context text",),
        ),
        _spec(
            "chat.retrieval",
            "chat",
            "Retrieval",
            "agent/core.py",
            "PersonalAICompanion._get_relevant_context",
            ("user/session", "retrieval text", "count"),
            ("context text",),
        ),
        _spec(
            "chat.stream_reply",
            "chat",
            "Stream reply",
            "agent/core.py",
            "PersonalAICompanion.stream_reply",
            ("messages", "enhanced prompt", "user/session"),
            ("reply",),
        ),
        _spec(
            "chat.approved_context",
            "chat",
            "Approved context",
            "agent/approved_context.py",
            "approved_context",
            ("user id",),
            ("approved context text",),
        ),
        _spec(
            "chat.narrative",
            "chat",
            "Narrative",
            "agent/narrative.py",
            "NarrativeFormatter.format_all",
            ("admitted findings",),
            ("rendered narrative",),
        ),
        _spec(
            "admission.select",
            "admission",
            "Select",
            "agent/prioritization.py",
            "InsightPrioritizationEngine.select",
            ("ranked findings", "max_items", "user"),
            ("selected findings",),
        ),
        _spec(
            "admission.collect",
            "admission",
            "Collect",
            "agent/pipeline_orchestrator.py",
            "collect_findings",
            ("user",),
            ("findings", "unavailable engines"),
        ),
        _spec(
            "admission.admit",
            "admission",
            "Admit",
            "agent/pipeline_orchestrator.py",
            "admit_findings",
            ("findings", "user", "effective preferences"),
            ("admission",),
        ),
        _spec(
            "engine.trajectory",
            "engine",
            "Trajectory",
            "agent/trajectory.py",
            "TrajectoryEngine.analyze_all_themes",
            ("user id",),
            ("findings",),
        ),
        _spec(
            "engine.tension",
            "engine",
            "Tension",
            "agent/tension.py",
            "TensionEngine.analyze_all_tensions",
            ("user id",),
            ("findings",),
        ),
        _spec(
            "engine.resolution",
            "engine",
            "Resolution",
            "agent/resolution.py",
            "ResolutionEngine.analyze_all_themes",
            ("user id",),
            ("findings",),
        ),
        _spec(
            "engine.leverage",
            "engine",
            "Leverage",
            "agent/leverage.py",
            "LeverageEngine.analyze_all_leverage",
            ("user id",),
            ("findings",),
        ),
        _spec(
            "engine.decision_impact",
            "engine",
            "Decision impact",
            "agent/decision_impact.py",
            "DecisionImpactEngine.analyze_all_anchors",
            ("user id",),
            ("findings",),
        ),
        _spec(
            "engine.lifelong",
            "engine",
            "Lifelong",
            "agent/lifelong.py",
            "LifelongEngine.analyze_all_themes",
            ("user id",),
            ("findings",),
        ),
        _spec(
            "admission.coverage",
            "admission",
            "Coverage gate",
            "agent/pipeline_orchestrator.py",
            "AnalysisPipeline.gate",
            ("findings", "user", "effective preferences"),
            ("findings", "suppression reasons"),
        ),
        _spec(
            "admission.enablement",
            "admission",
            "Enablement gate",
            "agent/pipeline_orchestrator.py",
            "AnalysisPipeline.gate",
            ("findings", "user", "effective preferences"),
            ("findings", "suppression reasons"),
        ),
        _spec(
            "admission.confidence",
            "admission",
            "Confidence gate",
            "agent/pipeline_orchestrator.py",
            "AnalysisPipeline.gate",
            ("findings", "user", "effective preferences"),
            ("findings", "suppression reasons"),
        ),
        _spec(
            "admission.conflict",
            "admission",
            "Conflict gate",
            "agent/pipeline_orchestrator.py",
            "admit_findings",
            ("visible findings",),
            ("visible findings", "suppressed conflicts"),
        ),
        _spec(
            "admission.rank",
            "admission",
            "Rank",
            "agent/pipeline_orchestrator.py",
            "admit_findings",
            ("findings",),
            ("ranked findings", "priority breakdown"),
        ),
        _spec(
            "pipeline.run",
            "pipeline",
            "Run",
            "agent/pipeline.py",
            "run_processing_pipeline",
            ("source item", "content"),
            ("processing outcome",),
        ),
        _spec(
            "pipeline.cross_theme_refresh",
            "pipeline",
            "Cross-theme refresh",
            "agent/pipeline.py",
            "_refresh_cross_theme_analyses",
            ("user id",),
            ("refresh outcome",),
        ),
        _spec(
            "pipeline.rebuild_themes",
            "pipeline",
            "Rebuild themes",
            "agent/pipeline.py",
            "rebuild_themes",
            ("user id",),
            ("rebuild counts",),
        ),
        _spec(
            "pipeline.match_theme",
            "pipeline",
            "Match theme",
            "agent/persistence.py",
            "PersistenceEngine.check_persistence",
            ("content", "source", "embedding"),
            ("matched theme id",),
        ),
        _spec(
            "pipeline.discover_themes",
            "pipeline",
            "Discover themes",
            "agent/persistence.py",
            "PersistenceEngine.discover_themes",
            ("user",),
            ("new themes",),
        ),
        _spec(
            "pipeline.theme_summary",
            "pipeline",
            "Theme summary",
            "agent/persistence.py",
            "PersistenceEngine._generate_theme_summary",
            ("source entries",),
            ("theme summary",),
        ),
        _spec(
            "pipeline.constructs",
            "pipeline",
            "Constructs",
            "agent/constructs.py",
            "classify",
            ("source", "content", "embedding"),
            ("matched construct ids",),
        ),
        _spec(
            "insights.discover_constructs",
            "insights",
            "Discover constructs",
            "agent/constructs.py",
            "discover",
            ("user", "include_staged"),
            ("proposed constructs", "citations"),
        ),
        _spec(
            "insights.list",
            "insights",
            "List insights",
            "agent/insights_service.py",
            "InsightsService.list_summaries",
            ("user",),
            ("insight summaries",),
        ),
        _spec(
            "insights.read_archive",
            "insights",
            "Read archive",
            "agent/observations.py",
            "ObservationEngine.read_archive",
            ("user", "include_staged"),
            ("observations", "run id"),
        ),
        _spec(
            "insights.synthesise",
            "insights",
            "Synthesise",
            "agent/observations.py",
            "ObservationEngine.synthesise",
            ("observations",),
            ("merged observations",),
        ),
        _spec(
            "insights.check_support",
            "insights",
            "Check support",
            "agent/observations.py",
            "ObservationEngine.check_support",
            ("observations", "tally"),
            ("supported observations",),
        ),
        _spec(
            "insights.review_letter",
            "insights",
            "Review letter",
            "agent/review_letter.py",
            "compose",
            ("facts", "findings", "week entries", "formats"),
            ("letter text",),
        ),
        _spec(
            "ideas.ask",
            "ideas",
            "Ask",
            "agent/ideas/reader.py",
            "_ask",
            ("prompt", "payload"),
            ("parsed model object",),
        ),
        _spec(
            "ideas.discover",
            "ideas",
            "Discover ideas",
            "agent/ideas/service.py",
            "IdeaService.discover",
            ("user",),
            ("run",),
        ),
        _spec(
            "ideas.discover_links",
            "ideas",
            "Discover links",
            "agent/ideas/service.py",
            "IdeaService.discover_links",
            ("user", "idea id"),
            ("run",),
        ),
        _spec(
            "ideas.discover_meanings",
            "ideas",
            "Discover meanings",
            "agent/ideas/service.py",
            "IdeaService.discover_meanings",
            ("user", "idea id"),
            ("run",),
        ),
        _spec(
            "ideas.critique",
            "ideas",
            "Critique",
            "agent/ideas/service.py",
            "IdeaService.critique",
            ("user", "idea id"),
            ("critique",),
        ),
        _spec(
            "import.create_batch",
            "import",
            "Create batch",
            "agent/importing/service.py",
            "ImportService.create_batch",
            ("upload path", "name", "kind", "adapter"),
            ("staged batch",),
        ),
        _spec(
            "import.reparse",
            "import",
            "Reparse",
            "agent/importing/service.py",
            "ImportService.reparse",
            ("batch", "adapter"),
            ("reparsed batch",),
        ),
        _spec(
            "import.commit",
            "import",
            "Commit import",
            "agent/importing/service.py",
            "ImportService.commit",
            ("batch",),
            ("commit counts",),
        ),
        _spec(
            "import.transcription_job",
            "import",
            "Transcription job",
            "agent/importing/audio.py",
            "run_transcription_job",
            ("item id", "stored audio path"),
            ("item outcome", "transcript"),
        ),
        _spec(
            "import.ffprobe",
            "import",
            "Probe duration",
            "agent/transcription.py",
            "probe_duration",
            ("path",),
            ("duration",),
        ),
        _spec(
            "import.ffmpeg_normalise",
            "import",
            "Normalise audio",
            "agent/transcription.py",
            "normalise",
            ("path",),
            ("normalized path",),
        ),
        _spec(
            "import.ffmpeg_split",
            "import",
            "Split audio",
            "agent/transcription.py",
            "split",
            ("path", "duration"),
            ("chunk paths",),
        ),
        _spec(
            "import.transcribe",
            "import",
            "Transcribe",
            "agent/transcription.py",
            "transcribe",
            ("path", "duration", "model"),
            ("transcript",),
        ),
        _spec(
            "voice.transcribe",
            "voice",
            "Transcribe utterance",
            "agent/voice.py",
            "transcribe_utterance",
            ("audio byte length", "MIME type"),
            ("transcript text",),
        ),
        _spec(
            "sensors.stage_delivery",
            "sensors",
            "Stage delivery",
            "agent/sensors/service.py",
            "SensorService.stage_delivery",
            ("batch", "delivery", "day", "skew"),
            ("batch id",),
        ),
        _spec(
            "sensors.commit_batch",
            "sensors",
            "Commit batch",
            "agent/sensors/service.py",
            "SensorService.commit_batch",
            ("batch", "links", "user", "count"),
            ("committed observation ids",),
        ),
        _spec(
            "sensors.timeline_import",
            "sensors",
            "Timeline import",
            "agent/sensors/timeline.py",
            "stage_export",
            ("file-byte metadata",),
            ("staged batches", "counts"),
        ),
        _spec(
            "sensors.recompute_days",
            "sensors",
            "Recompute days",
            "agent/days/recompute.py",
            "recompute",
            ("user", "dates"),
            ("recomputed dates",),
        ),
        _spec(
            "queue.job",
            "queue",
            "Job",
            "agent/work_queue.py",
            "process_due",
            ("claimed item", "source ids", "generation", "attempt", "due time"),
            ("outcome", "retry delay", "error"),
        ),
        _spec(
            "llm.chat",
            "llm",
            "Chat",
            "agent/observability/llm.py",
            "LlmCall",
            ("prompt", "request", "model"),
            ("completion", "usage", "cancellation/error"),
        ),
        _spec(
            "llm.chat_stream",
            "llm",
            "Chat stream",
            "agent/observability/llm.py",
            "LlmCall",
            ("prompt", "request", "model"),
            ("completion", "usage", "cancellation/error"),
        ),
        _spec(
            "llm.embeddings",
            "llm",
            "Embeddings",
            "agent/observability/llm.py",
            "LlmCall",
            ("request", "model"),
            ("vector metadata", "usage"),
        ),
        _spec(
            "llm.transcription",
            "llm",
            "Transcription",
            "agent/observability/llm.py",
            "LlmCall",
            ("request", "model"),
            ("transcript", "usage"),
        ),
        _spec(
            "llm.speech",
            "llm",
            "Speech",
            "agent/observability/llm.py",
            "LlmCall",
            ("request", "model"),
            ("audio length", "usage"),
        ),
        _spec(
            "system.startup",
            "system",
            "Startup",
            "iris_api.py",
            "lifespan",
            ("role",),
            ("initialization outcome",),
        ),
        _spec(
            "system.migrations",
            "system",
            "Migrations",
            "agent/migrations.py",
            "upgrade",
            ("role",),
            ("applied migration versions",),
        ),
        _client(
            "web.request",
            "web",
            "Web request",
            "frontend/src/lib/telemetry.ts",
            "tracedRequest",
            ("route", "request metadata"),
            ("status", "timing"),
        ),
        _client(
            "web.page_load",
            "web",
            "Page load",
            "frontend/src/lib/telemetry.ts",
            "install",
            ("route",),
            ("timing", "error"),
        ),
        _client(
            "web.other",
            "web",
            "Web other",
            "frontend/src/lib/telemetry.ts",
            "tracedRequest",
            ("request metadata",),
            ("status", "timing", "error"),
        ),
        _client(
            "android.request",
            "android",
            "Android request",
            "android/app/src/main/kotlin/com/iris/android/telemetry/TelemetryInterceptor.kt",
            "intercept",
            ("route", "request metadata"),
            ("status", "timing", "error"),
        ),
        _client(
            "android.other",
            "android",
            "Android other",
            "android/app/src/main/kotlin/com/iris/android/telemetry/TelemetryInterceptor.kt",
            "intercept",
            ("request metadata",),
            ("status", "timing", "error"),
        ),
        _client(
            "android.collector.state",
            "android",
            "Collector state",
            "android/app/src/main/kotlin/com/iris/android/telemetry/Telemetry.kt",
            "collectorState",
            ("collection configuration",),
            ("collector state",),
            kind="state",
        ),
    )
}

_CALLS: tuple[tuple[str, str], ...] = (
    ("chat.turn", "chat.begin_turn"),
    ("chat.begin_turn", "chat.context"),
    ("chat.context", "chat.retrieval"),
    ("chat.context", "chat.earlier_conversations"),
    ("chat.context", "chat.habits_context"),
    ("chat.context", "chat.reflections_context"),
    ("chat.context", "chat.approved_context"),
    ("chat.context", "admission.collect"),
    ("chat.context", "admission.admit"),
    ("chat.context", "admission.select"),
    ("chat.context", "chat.narrative"),
    ("chat.turn", "llm.chat"),
    ("chat.stream_reply", "llm.chat_stream"),
    ("chat.retrieval", "llm.embeddings"),
    ("admission.collect", "engine.trajectory"),
    ("admission.collect", "engine.tension"),
    ("admission.collect", "engine.resolution"),
    ("admission.collect", "engine.leverage"),
    ("admission.collect", "engine.decision_impact"),
    ("admission.collect", "engine.lifelong"),
    ("admission.admit", "admission.coverage"),
    ("admission.admit", "admission.enablement"),
    ("admission.admit", "admission.confidence"),
    ("admission.admit", "admission.conflict"),
    ("admission.admit", "admission.rank"),
    ("queue.job", "pipeline.run"),
    ("queue.job", "import.transcription_job"),
    ("pipeline.run", "llm.embeddings"),
    ("pipeline.run", "pipeline.match_theme"),
    ("pipeline.run", "pipeline.constructs"),
    ("pipeline.run", "pipeline.discover_themes"),
    ("pipeline.run", "pipeline.cross_theme_refresh"),
    ("pipeline.rebuild_themes", "pipeline.cross_theme_refresh"),
    ("pipeline.cross_theme_refresh", "engine.leverage"),
    ("pipeline.cross_theme_refresh", "engine.decision_impact"),
    ("pipeline.discover_themes", "pipeline.theme_summary"),
    ("insights.list", "admission.collect"),
    ("insights.list", "admission.admit"),
    ("insights.discover_constructs", "insights.read_archive"),
    ("insights.read_archive", "insights.synthesise"),
    ("insights.read_archive", "insights.check_support"),
    ("ideas.discover", "ideas.ask"),
    ("ideas.discover_links", "ideas.ask"),
    ("ideas.discover_meanings", "ideas.ask"),
    ("ideas.critique", "ideas.ask"),
    ("ideas.ask", "llm.chat"),
    ("import.transcription_job", "import.transcribe"),
    ("import.transcribe", "import.ffprobe"),
    ("import.transcribe", "import.ffmpeg_normalise"),
    ("import.transcribe", "import.ffmpeg_split"),
    ("import.transcribe", "llm.transcription"),
    ("import.ffmpeg_split", "import.ffprobe"),
    ("voice.transcribe", "llm.transcription"),
    ("system.startup", "system.migrations"),
)

_FLOWS: tuple[tuple[str, str], ...] = (
    ("chat.begin_turn", "chat.stream_reply"),
    ("admission.collect", "admission.coverage"),
    ("admission.coverage", "admission.enablement"),
    ("admission.enablement", "admission.confidence"),
    ("admission.confidence", "admission.conflict"),
    ("admission.conflict", "admission.rank"),
    ("admission.rank", "admission.select"),
    ("admission.select", "chat.narrative"),
)

_lock = Lock()


class _Schema:
    available = False
    read = False


def declared_edges() -> list[DeclaredEdge]:
    edges = [DeclaredEdge(source, target, "call") for source, target in _CALLS]
    edges.extend(DeclaredEdge(source, target, "flow") for source, target in _FLOWS)
    return edges


def specs() -> list[ModuleSpec]:
    with _lock:
        return list(_MODULES.values())


def get(module_id: str) -> ModuleSpec | None:
    with _lock:
        return _MODULES.get(module_id)


def known(module_id: str) -> bool:
    with _lock:
        return module_id in _MODULES


def schema_available() -> bool:
    return _Schema.available


def schema_read() -> bool:
    return _Schema.read


def lookup(module_id: str, component: str | None = None) -> ModuleSpec:
    """Catalog entry, or an ephemeral fallback that is not stored."""
    found = get(module_id)
    if found is not None:
        return found
    return ModuleSpec(
        id=module_id,
        component=component or component_of(module_id),
        label=module_id,
        source=None,
        inputs=_fallback_inputs(module_id),
        outputs=_fallback_outputs(module_id),
        kind=kind_of(module_id),
    )


def component_of(module_id: str) -> str:
    if module_id.startswith("http:"):
        return "http"
    if module_id.startswith("db:"):
        return "db"
    head, _, _rest = module_id.partition(".")
    return head or "system"


def kind_of(module_id: str) -> Kind:
    if module_id.startswith("http:"):
        return "route"
    if module_id.startswith("db:"):
        return "table"
    if module_id == "android.collector.state":
        return "state"
    if module_id.startswith(("web.", "android.")):
        return "client"
    return "operation"


def _fallback_inputs(module_id: str) -> tuple[str, ...]:
    if module_id.startswith("http:"):
        return ("method", "path", "query", "body")
    if module_id.startswith("db:"):
        return ("SQL", "parameters")
    return ()


def _fallback_outputs(module_id: str) -> tuple[str, ...]:
    if module_id.startswith("http:"):
        return ("status", "body")
    if module_id.startswith("db:"):
        return ("row count",)
    return ()


def source_of(fn: Callable[..., Any]) -> dict[str, Any] | None:
    try:
        file = inspect.getsourcefile(fn) or inspect.getfile(fn)
    except (TypeError, OSError):
        return None
    if not isinstance(file, str) or not file:
        return None
    try:
        relative = Path(file).resolve().relative_to(_ROOT).as_posix()
    except ValueError:
        return None
    line: int | None = None
    code = getattr(fn, "__code__", None)
    if code is not None:
        line = int(code.co_firstlineno)
    symbol = getattr(fn, "__qualname__", None) or getattr(fn, "__name__", None)
    if not isinstance(symbol, str):
        return None
    return {"file": relative, "symbol": symbol, "line": line}


def signature_of(fn: Callable[..., Any]) -> str | None:
    try:
        return str(inspect.signature(fn))
    except (TypeError, ValueError):
        return None


def note_callable(module_id: str, component: str, fn: Callable[..., Any]) -> None:
    """Enrich one catalog entry from a decorated callable. Does not call it."""
    source = source_of(fn)
    signature = signature_of(fn)
    with _lock:
        current = _MODULES.get(module_id)
        if current is None:
            _MODULES[module_id] = ModuleSpec(
                id=module_id,
                component=component,
                label=module_id,
                source=source,
                inputs=(),
                outputs=(),
                kind="operation",
                signature=signature,
            )
            return
        _MODULES[module_id] = replace(
            current,
            source=source or current.source,
            signature=signature or current.signature,
        )


def register_route(
    method: str,
    path: str,
    endpoint: Callable[..., Any] | None = None,
) -> None:
    """One catalog node per route template. Observatory and asset routes are omitted."""
    if not path or path.startswith(("/api/observatory", "/assets")):
        return
    if path in ("/observatory", "/observatory/{path:path}") or path.startswith("/observatory"):
        return
    module_id = http_module_id(method, path, resolved=True)
    source = source_of(endpoint) if endpoint is not None else None
    signature = signature_of(endpoint) if endpoint is not None else None
    spec = ModuleSpec(
        id=module_id,
        component="http",
        label=module_id,
        source=source,
        inputs=("method", "path", "query", "body"),
        outputs=("status", "body"),
        kind="route",
        signature=signature,
    )
    with _lock:
        _MODULES[module_id] = spec


def register_routes(routes: Iterable[tuple[str, str, Callable[..., Any] | None]]) -> None:
    for method, path, endpoint in routes:
        register_route(method, path, endpoint)


def register_tables(columns: Sequence[tuple[str, str, str]]) -> None:
    """Replace table nodes from a successful schema read. ``columns`` is table, name, type."""
    grouped: dict[str, list[tuple[str, str]]] = {}
    for table, column, data_type in columns:
        if table.startswith("obs_") or table in _EXCLUDED_TABLES:
            continue
        grouped.setdefault(table, []).append((column, data_type))
    specs_by_id = {
        f"db:{table}": ModuleSpec(
            id=f"db:{table}",
            component="db",
            label=table,
            source=None,
            inputs=("SQL", "parameters"),
            outputs=("row count", *(f"{name}:{data_type}" for name, data_type in cols)),
            kind="table",
        )
        for table, cols in grouped.items()
    }
    with _lock:
        stale = [module_id for module_id, spec in _MODULES.items() if spec.kind == "table"]
        for module_id in stale:
            if module_id not in specs_by_id:
                _MODULES.pop(module_id, None)
        _MODULES.update(specs_by_id)
        _Schema.available = True
        _Schema.read = True


def mark_schema_unavailable() -> None:
    """Keep the last successful table catalog and record that storage coverage is down."""
    _Schema.read = True
    _Schema.available = False


def http_module_id(method: str, route: str | None, *, resolved: bool) -> str:
    verb = (method or "GET").upper()
    if not resolved or not route or route == "<unmatched>":
        return f"http:{verb} <unmatched>"
    return f"http:{verb} {route}"


def http_identity_resolved(attributes: Mapping[str, object] | None) -> bool:
    if not attributes:
        return False
    route = attributes.get("http.route")
    return isinstance(route, str) and bool(route) and route != "<unmatched>"


def db_module_id(name: str, attributes: Mapping[str, object] | None = None) -> str:
    attrs = attributes or {}
    collection = attrs.get("db.collection.name")
    if isinstance(collection, str) and collection:
        return f"db:{collection}"
    if name == "db.fetch":
        return "db:<statement>"
    if name.startswith("db.fetch "):
        table = name[len("db.fetch ") :].strip()
        return f"db:{table}" if table else "db:<statement>"
    if name == "db.connection":
        return "db.connection"
    if " " in name and not name.startswith("db."):
        return f"db:{name.split(' ', 1)[1]}"
    return f"db:{name}"


def client_module_id(name: str, component: str) -> str:
    if component == "web" and name == "page.load":
        return "web.page_load"
    if component == "android" and name in ("collector.state", "android.collector.state"):
        return "android.collector.state"
    head = name.split(" ", 1)[0].upper()
    if head in _HTTP_METHODS:
        return f"{component}.request"
    return f"{component}.other"


def is_transparent(name: str, module_id: str | None = None) -> bool:
    return name == "db.connection" or module_id == "db.connection"


def module_id_for(
    name: str,
    component: str,
    attributes: Mapping[str, object] | None = None,
) -> str:
    """Stable graph id. Raw URL paths never become nodes."""
    attrs = attributes or {}
    if is_transparent(name):
        return "db.connection"
    if component in ("web", "android"):
        return client_module_id(name, component)
    if component == "http" or name.startswith("http:"):
        if name.startswith("http:"):
            return name
        method = attrs.get("http.request.method")
        verb = method if isinstance(method, str) and method else name.split(" ", 1)[0]
        route = attrs.get("http.route")
        resolved = isinstance(route, str) and bool(route)
        return http_module_id(verb, route if isinstance(route, str) else None, resolved=resolved)
    if component == "db" or name.startswith("db.fetch"):
        return db_module_id(name, attrs)
    return name


def clear_dynamic() -> None:
    """Drop route, table, and decoration-only nodes. Static ports stay."""
    with _lock:
        _MODULES.clear()
        _MODULES.update(_STATIC)
        _Schema.available = False
        _Schema.read = False


_STATIC = dict(_MODULES)
