"""The cached answer belongs to the evidence it was computed from.

The fingerprint was a count and two sums. Sums cancel: moving one occurrence a
day earlier and another a day later leaves every total identical while the
distances between them — which is what the cross-theme engines measure — have
changed. The cached result would then be served for evidence that no longer
supports it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from agent.analysis_cache import evidence_fingerprint, remembered
from agent.database import db


def _theme_with_two_occurrences(user_id: int) -> tuple[int, int, int]:
    now = datetime.now()
    theme_id = db.create_theme(user_id, [0.1] * 1536, "A theme",
                               (now - timedelta(days=60)).isoformat(), now.isoformat())
    ids = []
    for offset in (30, 20):
        entry_id = db.create_reflection(user_id, f"entry {offset}")
        db.add_theme_occurrence(theme_id, "reflection", entry_id, "a line", 0.9,
                                (now - timedelta(days=offset)).isoformat())
        ids.append(entry_id)
    return theme_id, ids[0], ids[1]


def test_compensating_date_changes_do_not_preserve_the_fingerprint(test_user):
    user_id = test_user["id"]
    theme_id, first, second = _theme_with_two_occurrences(user_id)
    before = evidence_fingerprint(user_id)

    # One a day earlier, one a day later: every count and sum is unchanged.
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE theme_occurrences SET occurred_at = occurred_at - interval '1 day'
                        WHERE theme_id = %s AND source_id = %s;""", (theme_id, first))
        cur.execute("""UPDATE theme_occurrences SET occurred_at = occurred_at + interval '1 day'
                        WHERE theme_id = %s AND source_id = %s;""", (theme_id, second))
        conn.commit()

    assert evidence_fingerprint(user_id) != before, (
        "one day earlier and one day later is a different week to any pair engine")


def test_unchanged_evidence_is_not_recomputed(test_user):
    user_id = test_user["id"]
    _theme_with_two_occurrences(user_id)
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return [{"engine_name": "tension", "pattern_id": 1}]

    assert remembered("tension", user_id, compute)
    assert remembered("tension", user_id, compute)
    assert calls["n"] == 1, "the same hour over the same evidence is one computation"
