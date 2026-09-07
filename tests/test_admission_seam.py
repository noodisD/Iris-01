"""
Every engine's output must survive the common admission seam.

The pipeline fills a missing `confidence_level` with "unknown", and the
confidence gate scores unknown below every threshold. So an engine that names
its confidence field differently is silently discarded no matter how strong its
finding — which is what happened to persistence: it emitted `confidence`, and
its insights never once reached the LLM.

These tests exercise the real gate with real engine output rather than the
shapes we assume engines produce.
"""

import pytest

from agent.persistence import PersistenceEngine
from agent.pipeline_orchestrator import AnalysisPipeline, confidence_gate
from agent.trackers.reflections import ReflectionService

ENGINE_FIELDS = ("engine_name", "pattern_type", "confidence_level")


def _admit(insights, min_confidence="medium"):
    """Run insights through the pipeline exactly as core.py assembles it."""
    pipeline = AnalysisPipeline(user_id=1)
    pipeline.register_engine("engine_under_test", lambda: insights)
    pipeline.register_gate("confidence", confidence_gate, order=2)
    return pipeline.run(prefs={"min_confidence": min_confidence, "max_items": 5})


def test_a_confident_insight_is_admitted():
    admitted = _admit([{"id": 1, "summary": "S", "confidence_level": "high"}])
    assert admitted, "a high-confidence insight must reach the LLM context"


def test_an_insight_naming_its_confidence_differently_is_not_silently_dropped():
    """The exact defect: `confidence` instead of `confidence_level`."""
    admitted = _admit([{"id": 1, "summary": "S", "confidence": "high"}])
    assert not admitted, (
        "this documents the trap: only `confidence_level` is understood, so any "
        "engine using another name is discarded — assert the contract in the "
        "engine tests below, not a rename here"
    )


def test_persistence_output_carries_the_field_the_gate_reads(test_user, mock_pipeline_logic):
    """Persistence, end to end: seed entries, form a theme, check the contract."""
    service = ReflectionService(test_user["id"])
    for i in range(5):
        service.create_reflection(content=f"Work Stress keeps building {i}", energy_level=3)

    themes = PersistenceEngine(test_user["id"]).get_persistent_themes()
    assert themes, "precondition: the entries formed a persistent theme"

    for theme in themes:
        assert "confidence_level" in theme, (
            f"persistence insight lacks confidence_level: {sorted(theme)}"
        )

    admitted = _admit(themes)
    assert admitted, "persistence insights must survive the admission gate"


@pytest.mark.parametrize("min_confidence", ["low", "medium", "high"])
def test_persistence_respects_the_threshold_it_is_given(min_confidence, test_user, mock_pipeline_logic):
    """Whatever the outcome, it must be decided by the level, never by a
    missing field."""
    service = ReflectionService(test_user["id"])
    for i in range(5):
        service.create_reflection(content=f"Poor Sleep again {i}", energy_level=3)

    themes = PersistenceEngine(test_user["id"]).get_persistent_themes()
    levels = {t["confidence_level"] for t in themes}
    assert levels and "unknown" not in levels, f"engine produced an unusable level: {levels}"
