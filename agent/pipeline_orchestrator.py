"""
One way to decide what IRIS has noticed.

Chat and the Insights screen are two answers to the same question — what has
IRIS noticed — so they collect the same findings and admit them through the
same policy (ADR-0007). They used not to. Each called the engines itself, at
different grains (leverage averaged per source in chat, per pair on screen;
decision impact from a cache in chat, recomputed on screen), and each
re-implemented the gates in its own order. Chat registered leverage and then
labelled its rows so the confidence gate discarded every one at the default
setting. The two surfaces disagreed about the owner's life for reasons that were
plumbing.

So there is one list of engines, one grain each, and one admission:

    collect_findings(user_id)          what the engines found
    admit_findings(findings, ...)      coverage -> enablement -> confidence
                                       -> conflict -> rank
    admit(user_id, prefs)              both, for callers that need no seam

What differs between the surfaces is only what they do with the admitted list:
chat keeps one finding per pattern and cuts to the owner's `max_items`, because
a prompt has room for a few; the screen shows everything, because it is a list
the owner scrolls. A budget is a limit on space, not a statement about what is
true, so it is the one step that belongs to the caller.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .conflict import ConflictSuppressionEngine
from .coverage import current_state_gate
from .preferences import UserPreferencesService
from .prioritization import InsightPrioritizationEngine

logger = logging.getLogger(__name__)

CONFIDENCE_LEVELS = {"low": 0, "medium": 1, "high": 2}


@dataclass
class Engine:
    """A registered analytical engine and how its findings are identified."""
    name: str
    callable: Callable[[], list[dict[str, Any]]]
    identify: Callable[[dict[str, Any]], None] | None = None


@dataclass
class Gate:
    """A filtering step: (insights, context) -> insights."""
    name: str
    callable: Callable
    order: int = 100  # lower runs first


class AnalysisPipeline:
    """Runs registered engines and applies gates, in order."""

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.engines: dict[str, Engine] = {}
        self.gates: list[Gate] = []
        self._suppression_log: dict[str, list[str]] = {}

    def register_engine(self, name: str, callable: Callable,
                        identify: Callable[[dict[str, Any]], None] | None = None) -> None:
        if name in self.engines:
            logger.warning(f"Engine '{name}' already registered, replacing")
        self.engines[name] = Engine(name=name, callable=callable, identify=identify)

    def register_gate(self, name: str, callable: Callable, order: int = 100) -> None:
        self.gates.append(Gate(name=name, callable=callable, order=order))
        self.gates.sort(key=lambda g: g.order)

    def collect(self) -> list[dict[str, Any]]:
        """Every finding every engine produced, identified and labelled.

        An engine that fails is logged and skipped, so one broken engine costs
        its own findings and not everyone else's.
        """
        findings: list[dict[str, Any]] = []
        for name, engine in self.engines.items():
            try:
                produced = engine.callable()
            except Exception as e:
                logger.error(f"Engine '{name}' failed: {e}")
                continue
            for insight in produced:
                insight.setdefault("engine_name", name)
                if engine.identify:
                    engine.identify(insight)
                insight.setdefault("pattern_type", "theme")
                insight.setdefault("pattern_key", str(insight.get("pattern_id")))
                insight.setdefault("confidence_level", "low")
                # The engine's own word for what it found. This used to fall
                # back to the *summary*, so a row with no label key was
                # labelled with its theme's name, or with "Insight".
                if "label" not in insight:
                    insight["label"] = (insight.get(f"{name}_label")
                                        or insight.get("effect_direction") or "observed")
                findings.append(insight)
        return findings

    def gate(self, findings: list[dict[str, Any]],
             prefs: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Apply the registered gates in order, recording why things were held back."""
        self._suppression_log = {}
        context = {"user_id": self.user_id, "prefs": prefs or {},
                   "suppression_log": self._suppression_log}
        for gate in self.gates:
            try:
                findings = gate.callable(findings, context)
            except Exception as e:
                logger.error(f"Gate '{gate.name}' failed: {e}")
        return findings

    def run(self, prefs: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self.gate(self.collect(), prefs)

    def get_suppression_log(self) -> dict[str, list[str]]:
        return self._suppression_log


# --- one floor, one allow-list -----------------------------------------------

def default_min_confidence() -> str:
    """The floor when the owner has not set one: the same default Settings shows.

    The gate used to fall back to 'low' when the key was absent while the
    preferences default was 'medium' — two floors, depending on which caller
    forgot to pass prefs.
    """
    return str(UserPreferencesService.DEFAULT_PREFS["min_confidence"])


def meets_floor(confidence_level: str | None, prefs: dict[str, Any]) -> bool:
    minimum = CONFIDENCE_LEVELS.get(prefs.get("min_confidence") or default_min_confidence(), 1)
    return CONFIDENCE_LEVELS.get((confidence_level or "low").lower(), 0) >= minimum


def engine_enabled(engine: str, prefs: dict[str, Any]) -> bool:
    enabled = prefs.get("enabled_engines")  # None means every engine
    return enabled is None or engine in enabled


def engine_enablement_gate(insights: list[dict[str, Any]],
                           context: dict[str, Any]) -> list[dict[str, Any]]:
    """Drop findings from engines the owner switched off."""
    prefs, log = context.get("prefs", {}), context["suppression_log"]
    kept = []
    for insight in insights:
        if engine_enabled(insight.get("engine_name", "unknown"), prefs):
            kept.append(insight)
        else:
            log.setdefault("engine_disabled", []).append(
                f"{insight.get('engine_name')}: {insight.get('label', 'N/A')}")
    return kept


def confidence_gate(insights: list[dict[str, Any]],
                    context: dict[str, Any]) -> list[dict[str, Any]]:
    """Drop findings below the owner's confidence floor."""
    prefs, log = context.get("prefs", {}), context["suppression_log"]
    kept = []
    for insight in insights:
        if meets_floor(insight.get("confidence_level"), prefs):
            kept.append(insight)
        else:
            log.setdefault("low_confidence", []).append(
                f"{insight.get('engine_name')}: {insight.get('label')} "
                f"({insight.get('confidence_level')})")
    return kept


# --- the engines, one grain each ---------------------------------------------

def _theme(insight: dict[str, Any]) -> None:
    insight["pattern_type"] = "theme"
    insight["pattern_id"] = insight["theme_id"]
    insight["pattern_key"] = str(insight["theme_id"])


def _pair(first: str, second: str, label: str | None = None) -> Callable[[dict[str, Any]], None]:
    """Identity for an engine that measures two themes together.

    `pattern_id` stays the first theme so the audit table keeps its integer
    column; `pattern_key` names the pair. Conflict grouping and the one-slot
    rule read the key, so a tension between A and B is its own finding rather
    than one more thing said about A.
    """
    def identify(insight: dict[str, Any]) -> None:
        insight["pattern_type"] = "theme"
        insight["pattern_id"] = insight[first]
        insight["pattern_key"] = f"{insight[first]}-{insight[second]}"
        if label:
            insight.setdefault("label", label)
    return identify


def canonical_pipeline(user_id: int) -> AnalysisPipeline:
    """The engines and gates both surfaces use. Change them here, once."""
    from .decision_impact import DecisionImpactEngine
    from .leverage import LeverageEngine
    from .lifelong import LifelongEngine
    from .resolution import ResolutionEngine
    from .tension import TensionEngine
    from .trajectory import TrajectoryEngine

    pipeline = AnalysisPipeline(user_id)
    pipeline.register_engine("trajectory",
                             lambda: TrajectoryEngine(user_id).analyze_all_themes(), _theme)
    pipeline.register_engine("tension",
                             lambda: TensionEngine(user_id).analyze_all_tensions(),
                             _pair("theme_a_id", "theme_b_id"))
    pipeline.register_engine("resolution",
                             lambda: ResolutionEngine(user_id).analyze_all_themes(), _theme)
    # Pairs, which carry their own confidence. The per-source average chat used
    # to read had no confidence field at all, so the gate scored every row 0 and
    # leverage never reached a conversation at the default setting.
    pipeline.register_engine("leverage",
                             lambda: LeverageEngine(user_id).analyze_all_leverage(),
                             _pair("source_id", "target_id", label="associated"))
    # Computed, which also writes the cache. Reading the cache instead left chat
    # silent on decision impact after a boot until something else had warmed it.
    pipeline.register_engine("decision_impact",
                             lambda: DecisionImpactEngine(user_id).analyze_all_anchors(),
                             _pair("anchor_id", "target_id"))
    pipeline.register_engine("lifelong",
                             lambda: LifelongEngine(user_id).analyze_all_themes(), _theme)

    # Coverage first: a finding about now needs something logged now.
    pipeline.register_gate("coverage", current_state_gate, order=0)
    pipeline.register_gate("enablement", engine_enablement_gate, order=1)
    pipeline.register_gate("confidence", confidence_gate, order=2)
    return pipeline


# --- admission ---------------------------------------------------------------

@dataclass
class Admission:
    """What passed, best first, and why the rest did not."""
    findings: list[dict[str, Any]]
    suppression_log: dict[str, list[str]] = field(default_factory=dict)
    conflicts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def held_back_by_owner(self) -> int:
        """Findings the owner's own settings removed — their confidence floor or
        an engine they switched off. Distinct from what the system withheld."""
        return (len(self.suppression_log.get("low_confidence", []))
                + len(self.suppression_log.get("engine_disabled", [])))


def collect_findings(user_id: int) -> list[dict[str, Any]]:
    return canonical_pipeline(user_id).collect()


def admit_findings(findings: list[dict[str, Any]], user_id: int,
                   prefs: dict[str, Any] | None = None) -> Admission:
    """The admission policy. Every surface that says what IRIS noticed uses this."""
    if prefs is None:
        prefs = UserPreferencesService(user_id).get_prefs()
    pipeline = canonical_pipeline(user_id)
    gated = pipeline.gate(findings, prefs)
    resolved = ConflictSuppressionEngine().suppress(gated)
    ranked = InsightPrioritizationEngine(user_id).rank(resolved["visible"])
    return Admission(findings=ranked, suppression_log=pipeline.get_suppression_log(),
                     conflicts=resolved["suppressed"])


def admit(user_id: int, prefs: dict[str, Any] | None = None) -> Admission:
    return admit_findings(collect_findings(user_id), user_id, prefs)

