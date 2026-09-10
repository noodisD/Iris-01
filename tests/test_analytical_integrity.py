"""Regression tests for the analytical-integrity defects found in the pipeline audit.

Each test here encodes a counterexample that the code used to produce. They are
deliberately DB-free: they exercise the real methods with the external boundary
(database, embedding provider) mocked, so they run in any environment and fail
for one reason only.
"""

from unittest.mock import MagicMock, patch




# --- presentation must not invent numbers -----------------------------------


def _service_over(engine_results: dict):
    """An InsightsService whose engines return exactly these results."""
    from agent import insights_service as mod

    service = mod.InsightsService(user_id=1)
    patches = []
    for name, cls in [
        ("trajectory", "TrajectoryEngine"), ("resolution", "ResolutionEngine"),
        ("tension", "TensionEngine"), ("leverage", "LeverageEngine"),
        ("decision_impact", "DecisionImpactEngine"),
    ]:
        instance = MagicMock()
        results = engine_results.get(name, [])
        instance.analyze_all_themes.return_value = results
        instance.analyze_all_tensions.return_value = results
        instance.analyze_all_leverage.return_value = results
        instance.analyze_all_anchors.return_value = results
        patches.append(patch.object(mod, cls, return_value=instance))
    for p in patches:
        p.start()
    try:
        return service, service._normalize()
    finally:
        for p in patches:
            p.stop()


def test_tension_keeps_its_own_recent_and_earlier_split():
    """A tension with four recent and eight earlier shared days was rendered as
    "12 recent · 0 earlier": the all-time total moved into the recent slot and
    the earlier count was invented as zero."""
    service, raw = _service_over({"tension": [{
        "theme_a_id": 1, "theme_b_id": 2,
        "theme_a_summary": "Late nights", "theme_b_summary": "Low energy",
        "cooccurrence_count": 12,
        "recent_cooccurrence_count": 4,
        "past_cooccurrence_count": 8,
        "tension_label": "persistent", "confidence_level": "high",
    }]})

    assert len(raw) == 1
    values = {m["label"]: m["value"] for m in raw[0]["measures"]}
    assert values["Recent"] == 4, values
    assert values["Earlier"] == 8, values
    assert values["All time"] == 12, values

    summary = service._summary(raw[0], 0, None, "2026-09-10T00:00:00Z")
    assert "4 shared days" in summary["headline"]["line3"]
    assert "0 earlier" not in summary["summary"], summary["summary"]
    assert "12 recent" not in summary["summary"], summary["summary"]


def test_leverage_does_not_claim_a_recent_versus_earlier_comparison():
    """Leverage measures association within a lag window. It has no earlier
    window, so it must not report one — least of all a fabricated zero."""
    service, raw = _service_over({"leverage": [{
        "source_id": 1, "target_id": 2,
        "source_summary": "Running", "target_summary": "Good sleep",
        "influence_score": 0.42, "directional_lift": 0.8,
        "cooccurrence_count": 9, "confidence_level": "medium",
    }]})

    labels = {m["label"] for m in raw[0]["measures"]}
    assert "Earlier" not in labels, labels
    assert "Co-occurrences" in labels

    detail_evidence = service._evidence(raw[0])
    comparison = next(e for e in detail_evidence if e["kind"] == "comparison")
    assert all(i["value"] != 0 or i["label"] != "Earlier" for i in comparison["items"])
    assert comparison["label"] == "Temporal association"


def test_decision_impact_reports_relative_change_not_all_history_as_recent():
    """target_total_count is every occurrence the target ever had. It was being
    shown as a recent count against an invented earlier zero."""
    service, raw = _service_over({"decision_impact": [{
        "anchor_id": 1, "target_id": 2,
        "anchor_summary": "Started therapy", "target_summary": "Rumination",
        "effect_direction": "decrease", "delta_score": -0.4,
        "consistency_ratio": 0.75, "target_total_count": 40,
        "confidence_level": "medium",
    }]})

    values = {m["label"]: m["value"] for m in raw[0]["measures"]}
    assert values["Relative change in rate"] == -0.4
    assert values["Target occurrences"] == 40

    total = next(m for m in raw[0]["measures"] if m["label"] == "Target occurrences")
    assert total["sub"] == "all time", "an all-history count must say so"

    summary = service._summary(raw[0], 0, None, "2026-09-10T00:00:00Z")
    assert "40 recent" not in summary["summary"], summary["summary"]
    assert "-40%" in summary["headline"]["line3"], summary["headline"]["line3"]


def test_no_engine_is_presented_as_causal():
    """No engine performs causal identification, so none may be labelled that
    way on screen."""
    from agent.insights_service import KIND_MAP

    assert "causal" not in KIND_MAP.values(), KIND_MAP


def test_confidence_label_reaches_the_screen():
    """The numeric field is an ordinal encoding, not a probability. The real
    label has to be visible somewhere."""
    service, raw = _service_over({"trajectory": [{
        "theme_id": 1, "theme_summary": "Focus", "trajectory_label": "increasing",
        "recent_count": 6, "past_count": 2, "confidence_level": "medium",
    }]})
    summary = service._summary(raw[0], 0, None, "2026-09-10T00:00:00Z")
    assert "medium confidence" in summary["tags"], summary["tags"]
