from datetime import datetime, timedelta

import pytest

from agent.database import db
from agent.decision_impact import DecisionImpactEngine


@pytest.fixture
def impact_engine(test_user):
    return DecisionImpactEngine(test_user['id'])

def test_impact_emergence_detected(test_user, impact_engine):
    now = datetime.now()
    user_id = test_user['id']
    t_a = db.create_theme(user_id, [0.1]*1536, "Anchor A", (now-timedelta(days=400)).isoformat(), now.isoformat())
    t_b = db.create_theme(user_id, [0.2]*1536, "Target B", (now-timedelta(days=400)).isoformat(), now.isoformat())
    # The third anchor was 10 days old, inside the 14-day follow-up window, so
    # its effect could not yet be observed — it is now excluded as
    # right-censored, which left too few anchors to analyse. Aged to 20 days
    # so all three can actually be judged.
    anchor_dates = [now - timedelta(days=210), now - timedelta(days=110), now - timedelta(days=20)]
    for i, d_a in enumerate(anchor_dates):
        eid_a = db.create_journal_entry(user_id, f"A {i}", {})
        db.add_theme_occurrence(t_a, 'journal_entry', eid_a, "a", 0.9, d_a.isoformat())
        db.update_theme_stats(t_a, d_a.isoformat())
        for j in range(2):
            d_b = d_a + timedelta(days=2 + j)
            eid_b = db.create_journal_entry(user_id, f"B {i}-{j}", {})
            db.add_theme_occurrence(t_b, 'journal_entry', eid_b, "b", 0.9, d_b.isoformat())
            db.update_theme_stats(t_b, d_b.isoformat())
    impacts = impact_engine.analyze_anchor('theme', t_a)
    target_b_impact = next((i for i in impacts if i['target_id'] == t_b), None)
    assert target_b_impact is not None
    assert target_b_impact['effect_direction'] == 'emergence'

def test_impact_fade_detected(test_user, impact_engine):
    now = datetime.now()
    user_id = test_user['id']
    t_a = db.create_theme(user_id, [0.1]*1536, "Anchor A", (now-timedelta(days=400)).isoformat(), now.isoformat())
    t_b = db.create_theme(user_id, [0.2]*1536, "Target B", (now-timedelta(days=400)).isoformat(), now.isoformat())
    # The third anchor was 10 days old, inside the 14-day follow-up window, so
    # its effect could not yet be observed — it is now excluded as
    # right-censored, which left too few anchors to analyse. Aged to 20 days
    # so all three can actually be judged.
    anchor_dates = [now - timedelta(days=210), now - timedelta(days=110), now - timedelta(days=20)]
    for i, d_a in enumerate(anchor_dates):
        eid_a = db.create_journal_entry(user_id, f"A {i}", {})
        db.add_theme_occurrence(t_a, 'journal_entry', eid_a, "a", 0.9, d_a.isoformat())
        db.update_theme_stats(t_a, d_a.isoformat())
        for j in range(3):
            d_b = d_a - timedelta(days=5 + j)
            eid_b = db.create_journal_entry(user_id, f"B {i}-{j}", {})
            db.add_theme_occurrence(t_b, 'journal_entry', eid_b, "b", 0.9, d_b.isoformat())
            db.update_theme_stats(t_b, d_b.isoformat())
    impacts = impact_engine.analyze_anchor('theme', t_a)
    target_b_impact = next((i for i in impacts if i['target_id'] == t_b), None)
    assert target_b_impact is not None
    assert target_b_impact['effect_direction'] == 'fade'

def test_noise_rejection(test_user, impact_engine):
    now = datetime.now()
    user_id = test_user['id']
    t_a = db.create_theme(user_id, [0.1]*1536, "Anchor A", (now-timedelta(days=400)).isoformat(), now.isoformat())
    t_b = db.create_theme(user_id, [0.2]*1536, "Random B", (now-timedelta(days=400)).isoformat(), now.isoformat())
    # Spaced more than 90 days apart. Targets sit 30 days after their anchor and
    # the baseline window is 60 days, so a closer spacing would drop the previous
    # anchor's targets into this anchor's baseline and manufacture the very
    # signal this test asserts is absent.
    anchor_dates = [now - timedelta(days=240), now - timedelta(days=130), now - timedelta(days=20)]
    for i, d_a in enumerate(anchor_dates):
        eid_a = db.create_journal_entry(user_id, f"A {i}", {})
        db.add_theme_occurrence(t_a, 'journal_entry', eid_a, "a", 0.9, d_a.isoformat())
        db.update_theme_stats(t_a, d_a.isoformat())
    for i, d_a in enumerate(anchor_dates):
        for j in range(2):
            d_b = d_a + timedelta(days=30 + j)
            eid_b = db.create_journal_entry(user_id, f"B {i}-{j}", {})
            db.add_theme_occurrence(t_b, 'journal_entry', eid_b, "b", 0.9, d_b.isoformat())
            db.update_theme_stats(t_b, d_b.isoformat())
    impacts = impact_engine.analyze_anchor('theme', t_a)
    target_b_impact = next((i for i in impacts if i['target_id'] == t_b), None)
    assert target_b_impact is None

def test_cache_invalidation(test_user, impact_engine):
    now = datetime.now()
    user_id = test_user['id']
    t_a = db.create_theme(user_id, [0.1]*1536, "Anchor", (now-timedelta(days=100)).isoformat(), now.isoformat())
    t_b = db.create_theme(user_id, [0.2]*1536, "Target", (now-timedelta(days=100)).isoformat(), now.isoformat())
    for i in range(3):
        d_a = now - timedelta(days=210 - (i*95))  # 210, 115, 20 — all past the follow-up window
        eid_a = db.create_journal_entry(user_id, f"A {i}", {})
        db.add_theme_occurrence(t_a, 'journal_entry', eid_a, "a", 0.9, d_a.isoformat())
        db.update_theme_stats(t_a, d_a.isoformat())
        for j in range(2):
            d_b = d_a + timedelta(days=2 + j)
            eid_b = db.create_journal_entry(user_id, f"B {i}-{j}", {})
            db.add_theme_occurrence(t_b, 'journal_entry', eid_b, "b", 0.9, d_b.isoformat())
            db.update_theme_stats(t_b, d_b.isoformat())
    impact_engine.analyze_anchor('theme', t_a)
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT last_computed_at FROM decision_impacts WHERE anchor_id = %s", (t_a,))
        assert cur.fetchone()[0] is not None
    db.add_theme_occurrence(t_a, 'journal_entry', 9999, "new", 0.9, now.isoformat())
    with conn.cursor() as cur:
        cur.execute("SELECT last_computed_at FROM decision_impacts WHERE anchor_id = %s", (t_a,))
        assert cur.fetchone()[0] is None
