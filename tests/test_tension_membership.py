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
