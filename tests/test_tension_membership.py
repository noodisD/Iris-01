"""
Tension is about themes appearing in the same periods, not in the same entry.

_calculate_cooccurrence_metrics matched occurrences by source_id — the same
journal entry appearing in both themes. But check_persistence stops at the
first theme above threshold ("one entry -> one theme max") and discovery
assigns each embedding to exactly one cluster, so no entry is ever in two
themes and the count was structurally always zero. The tension engine could
not fire at all.

Everything else in the project already said "period": CONTEXT.md defines
co_occurrence_count as "# of overlapping windows", and the narrative the engine
prints reads "frequently appeared during the same periods". Only the code
disagreed.
"""

from datetime import timedelta


from agent.database import themes
from agent.tension import TensionEngine
from agent.timeutils import utc_now


def _theme(user_id, name, vector, days_ago):
    now = utc_now()
    theme_id = themes.create_theme(
        user_id=user_id, centroid_embedding=[vector] * 1536, summary=name,
        first_seen_at=(now - timedelta(days=max(days_ago) + 1)).isoformat(),
        last_seen_at=now.isoformat(), occurrence_count=0,
    )
    for i, d in enumerate(days_ago):
        themes.add_occurrence(
            theme_id=theme_id, source_type="reflection",
            source_id=abs(hash((name, i))) % 10_000_000,
            snippet=f"{name} {i}", similarity_score=0.9,
            occurred_at=(now - timedelta(days=d)).isoformat(),
        )
    return theme_id


def test_themes_active_on_the_same_days_co_occur(test_user):
    """Two themes recorded on the same days, in separate entries."""
    user_id = test_user["id"]
    days = [40, 35, 30, 25, 20, 15, 10, 5]
    a = _theme(user_id, "Work Stress", 0.1, days)
    b = _theme(user_id, "Poor Sleep", 0.2, days)

    metrics = TensionEngine(user_id)._calculate_cooccurrence_metrics(a, b)
    assert metrics["cooccurrence_count"] >= 3, (
        f"themes active on the same days must co-occur, got {metrics['cooccurrence_count']}"
    )


def test_themes_active_on_different_days_do_not_co_occur(test_user):
    user_id = test_user["id"]
    a = _theme(user_id, "Morning Theme", 0.3, [40, 35, 30, 25])
    b = _theme(user_id, "Other Theme", 0.4, [39, 34, 29, 24])

    metrics = TensionEngine(user_id)._calculate_cooccurrence_metrics(a, b)
    assert metrics["cooccurrence_count"] == 0, (
        f"themes with no shared day must not co-occur, got {metrics['cooccurrence_count']}"
    )


def test_a_busy_day_counts_once(test_user):
    """Counting pairs rather than days would let a single dense day dominate —
    the same error that inflated leverage's probabilities."""
    user_id = test_user["id"]
    now = utc_now()
    a = themes.create_theme(user_id, [0.5] * 1536, "Dense A",
                            (now - timedelta(days=10)).isoformat(), now.isoformat(), 0)
    b = themes.create_theme(user_id, [0.6] * 1536, "Dense B",
                            (now - timedelta(days=10)).isoformat(), now.isoformat(), 0)
    for i in range(4):
        themes.add_occurrence(a, "reflection", 980000 + i, f"a{i}", 0.9,
                              (now - timedelta(days=5, hours=i)).isoformat())
    for i in range(4):
        themes.add_occurrence(b, "reflection", 981000 + i, f"b{i}", 0.9,
                              (now - timedelta(days=5, hours=i)).isoformat())

    metrics = TensionEngine(user_id)._calculate_cooccurrence_metrics(a, b)
    assert metrics["cooccurrence_count"] == 1, (
        f"one shared day is one co-occurrence, got {metrics['cooccurrence_count']}"
    )


# ---------------------------------------------------------------------------
# CONTEXT.md states two invariants for a tension that the classifier ignored:
#
#   "Must have >= TENSION_MIN_COOCCURRENCE (3) overlapping windows"
#   "Themes must show divergence (trajectory directions differ)"
#
# Below the minimum it returned "intermittent" — a label meaning "these
# sometimes occur together" — for pairs that had *never* occurred together.
# And divergence_score was a parameter the classifier accepted and never read,
# so two themes rising in step were reported as being in tension with each
# other.
# ---------------------------------------------------------------------------


def test_a_pair_that_never_co_occurred_is_not_labelled(test_user):
    """Zero evidence must produce no tension, not the mildest label."""
    engine = TensionEngine(test_user["id"])
    # Distinct weeks, so the two themes never share a day.
    a = _theme(test_user["id"], "Alpha", 0.11, [40, 39, 38, 37, 36, 3])
    b = _theme(test_user["id"], "Beta", 0.77, [30, 29, 28, 27, 26, 8])

    metrics = engine._calculate_cooccurrence_metrics(a, b)
    assert metrics["cooccurrence_count"] == 0, "precondition: they never overlap"

    assert engine.analyze_tension(a, b) is None, (
        "a pair with no shared days must not be given a tension label"
    )


def test_below_the_minimum_is_not_enough_to_be_labelled(test_user):
    """One shared day is evidence, but not the three CONTEXT.md requires."""
    engine = TensionEngine(test_user["id"])
    a = _theme(test_user["id"], "Gamma", 0.13, [40, 39, 38, 37, 36, 5])
    b = _theme(test_user["id"], "Delta", 0.79, [30, 29, 28, 27, 26, 5])

    metrics = engine._calculate_cooccurrence_metrics(a, b)
    assert metrics["cooccurrence_count"] == 1, "precondition: exactly one shared day"

    assert engine.analyze_tension(a, b) is None


def test_two_themes_moving_together_are_not_in_tension(test_user):
    """Identical histories are a correlation. This used to be reported as a
    tension because divergence was computed and then ignored."""
    engine = TensionEngine(test_user["id"])
    days = [40, 39, 38, 37, 36, 20, 6, 5, 4]
    a = _theme(test_user["id"], "Epsilon", 0.15, days)
    b = _theme(test_user["id"], "Zeta", 0.81, days)

    metrics = engine._calculate_cooccurrence_metrics(a, b)
    assert metrics["cooccurrence_count"] >= 3, "precondition: plenty of overlap"

    assert engine.analyze_tension(a, b) is None, (
        "themes with identical trajectories are correlated, not in tension"
    )


def test_themes_that_overlap_and_diverge_are_a_tension(test_user):
    """The case that must still be reported: shared days, opposite directions —
    one winding down while the other picks up."""
    engine = TensionEngine(test_user["id"])
    user_id = test_user["id"]
    # Shared days early on; then Eta stops while Theta accelerates.
    shared = [50, 49, 48, 47, 46]
    fading = _theme(user_id, "Eta", 0.17, shared + [45, 44])
    rising = _theme(user_id, "Theta", 0.83, shared + [6, 5, 4, 3, 2, 1])

    metrics = engine._calculate_cooccurrence_metrics(fading, rising)
    assert metrics["cooccurrence_count"] >= 3, "precondition: enough overlap"

    result = engine.analyze_tension(fading, rising)
    assert result is not None, (
        "two themes that overlap and then move in opposite directions are the "
        "case tension exists to describe"
    )
    assert result["tension_label"] in {"persistent", "emerging", "fading", "intermittent"}
