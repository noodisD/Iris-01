
from datetime import datetime, timedelta

import pytest

from agent.core import PersonalAICompanion
from agent.database import db
from agent.decision_impact import DecisionImpactEngine
from agent.leverage import LeverageEngine
from agent.resolution import ResolutionEngine
from agent.trajectory import TrajectoryEngine


@pytest.fixture
def mock_embedding(monkeypatch):
    monkeypatch.setattr("agent.pipeline.generate_embedding", lambda text, model=None: [0.1] * 1536)
    monkeypatch.setattr("agent.core.generate_embedding", lambda text, model=None: [0.1] * 1536)

def test_final_system_regression_deterministic(test_user, freeze_time, mock_llm, mock_embedding):
    user_id = test_user['id']
    start_time = datetime(2026, 1, 1)
    freeze_time.set_time(start_time)

    # Themes
    t_stress = db.create_theme(user_id, [0.1]*1536, "Work Stress", start_time.isoformat(), start_time.isoformat())
    t_sleep = db.create_theme(user_id, [0.2]*1536, "Poor Sleep", start_time.isoformat(), start_time.isoformat())
    t_med = db.create_theme(user_id, [0.3]*1536, "Meditation", start_time.isoformat(), start_time.isoformat())
    t_habit = db.create_theme(user_id, [0.4]*1536, "Old Habit", start_time.isoformat(), start_time.isoformat())

    # --- 1. LEVERAGE (Driver: Stress, Target: Sleep) ---
    # Window: 100 to 70 days ago
    for i in range(6):
        ds = start_time + timedelta(days=i*5) # day 0 to 25
        dsl = ds + timedelta(days=2)
        ea = db.create_journal_entry(user_id, f"Stress {i}", {})
        db.add_theme_occurrence(t_stress, 'journal_entry', ea, "stress", 0.9, ds.isoformat())
        db.update_theme_stats(t_stress, ds.isoformat())
        eb = db.create_journal_entry(user_id, f"Sleep {i}", {})
        db.add_theme_occurrence(t_sleep, 'journal_entry', eb, "sleep", 0.9, dsl.isoformat())
        db.update_theme_stats(t_sleep, dsl.isoformat())

    # --- 2. IMPACT (Meditation -> Stress Decrease) ---
    # Window: 65 to 40 days ago
    med_dates = [start_time + timedelta(days=40), start_time + timedelta(days=50), start_time + timedelta(days=60)]
    for i, dm in enumerate(med_dates):
        em = db.create_journal_entry(user_id, f"Med {i}", {})
        db.add_theme_occurrence(t_med, 'journal_entry', em, "med", 0.9, dm.isoformat())
        db.update_theme_stats(t_med, dm.isoformat())
        # Stress BEFORE med only
        db.add_theme_occurrence(t_stress, 'journal_entry', 7000+i, "stress", 0.9, (dm - timedelta(days=3)).isoformat())
        db.update_theme_stats(t_stress, (dm - timedelta(days=3)).isoformat())

    # --- 3. DISSIPATED (Habit) ---
    # Day 0 to 30
    for i in range(6):
        dh = start_time + timedelta(days=i*5)
        eh = db.create_journal_entry(user_id, f"Habit {i}", {})
        db.add_theme_occurrence(t_habit, 'journal_entry', eh, "habit", 0.9, dh.isoformat())
        db.update_theme_stats(t_habit, dh.isoformat())

    # Ensure Stress and Sleep are still ACTIVE (last one at day 105)
    d_act = start_time + timedelta(days=105)
    db.add_theme_occurrence(t_stress, 'journal_entry', 8888, "stress", 0.9, d_act.isoformat())
    db.update_theme_stats(t_stress, d_act.isoformat())
    db.add_theme_occurrence(t_sleep, 'journal_entry', 9999, "sleep", 0.9, d_act.isoformat())
    db.update_theme_stats(t_sleep, d_act.isoformat())

    # Now
    current_now = start_time + timedelta(days=110)
    freeze_time.set_time(current_now)

    # Analysis
    TrajectoryEngine(user_id).analyze_all_themes()
    ResolutionEngine(user_id).analyze_all_themes()
    LeverageEngine(user_id).analyze_all_leverage(force_recompute=True)
    DecisionImpactEngine(user_id).analyze_all_anchors()

    # Core
    companion = PersonalAICompanion(user_id=user_id)
    companion.chat("Status report.")
    prompt = mock_llm.chat.call_args[1]['system_prompt']

    # Final Epistemic Check
    print("\n--- FINAL SYSTEM PROMPT ---")
    print(prompt)

    # Assertions:
    # 1. We expect at least the primary anchor 'Work Stress' to be present
    assert "Work Stress" in prompt

    # 2. We expect at least one sequence or driver mention
    assert "following" in prompt.lower() or "preceded" in prompt.lower()

    # 3. "No Advice" Guarantee
    for word in ["you should", "I suggest", "means that", "because"]:
        assert word not in prompt.lower(), f"Safety violation: {word}"

    print("\nSUCCESS")
