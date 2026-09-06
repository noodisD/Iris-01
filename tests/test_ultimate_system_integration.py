
import logging
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from agent.core import PersonalAICompanion
from agent.database import db
from agent.decision_impact import DecisionImpactEngine
from agent.leverage import LeverageEngine
from agent.prioritization import InsightPrioritizationEngine
from agent.resolution import ResolutionEngine
from agent.tension import TensionEngine
from agent.trajectory import TrajectoryEngine

# Setup logging
logger = logging.getLogger("UltimateTest")

class SystemReport:
    def __init__(self):
        self.stages = []
        self.start_time = time.time()

    def add_stage(self, name, duration, status="OK"):
        self.stages.append({"name": name, "duration": duration, "status": status})

    def print_report(self):
        print("\n" + "═"*60)
        print(" IRIS ULTIMATE SYSTEM INTEGRATION REPORT ")
        print("═"*60)
        total_dur = time.time() - self.start_time
        for s in self.stages:
            print(f"║ {s['name']:<30} │ {s['duration']:>8.4f}s │ {s['status']:<6} ║")
        print("╟" + "─"*58 + "╢")
        print(f"║ {'TOTAL EXECUTION TIME':<30} │ {total_dur:>8.4f}s │ {'DONE':<6} ║")
        print("═"*60 + "\n")

@pytest.fixture
def mock_pipeline(monkeypatch):
    def mock_embed(text, model=None):
        if "Stress" in text: return [0.1] * 1536
        if "Sleep" in text: return [0.2] * 1536
        if "Yoga" in text: return [0.3] * 1536
        if "Meditation" in text: return [0.4] * 1536
        if "Habit" in text: return [0.5] * 1536
        return [0.9] * 1536

    monkeypatch.setattr("agent.pipeline.generate_embedding", mock_embed)
    monkeypatch.setattr("agent.core.generate_embedding", mock_embed)
    monkeypatch.setattr("agent.persistence.PersistenceEngine._generate_theme_summary", lambda s, e: "Dynamic Insight")

def test_ultimate_end_to_end_flow(test_user, mock_pipeline):
    report = SystemReport()
    user_id = test_user['id']
    now = datetime.now()

    # --- STAGE 1: DATA INGESTION (90 Days) ---
    t0 = time.time()
    # Themes
    t_stress = db.create_theme(user_id, [0.1]*1536, "Work Stress", (now-timedelta(days=120)).isoformat(), now.isoformat())
    t_sleep = db.create_theme(user_id, [0.2]*1536, "Poor Sleep", (now-timedelta(days=120)).isoformat(), now.isoformat())
    t_yoga = db.create_theme(user_id, [0.3]*1536, "Yoga Practice", (now-timedelta(days=120)).isoformat(), now.isoformat())
    t_med = db.create_theme(user_id, [0.4]*1536, "Meditation", (now-timedelta(days=120)).isoformat(), now.isoformat())
    t_habit = db.create_theme(user_id, [0.5]*1536, "Old Habit", (now-timedelta(days=120)).isoformat(), (now-timedelta(days=40)).isoformat())

    # SCENARIO A: Leverage (Stress -> Sleep)
    for i in range(6):
        d_s = now - timedelta(days=80 - (i*10))
        eid = db.create_journal_entry(user_id, f"Stress {i}", {})
        db.add_theme_occurrence(t_stress, 'journal_entry', eid, "stress", 0.95, d_s.isoformat())
        db.update_theme_stats(t_stress, d_s.isoformat())
        eid_sl = db.create_journal_entry(user_id, f"Sleep {i}", {})
        db.add_theme_occurrence(t_sleep, 'journal_entry', eid_sl, "sleep", 0.95, (d_s + timedelta(days=2)).isoformat())
        db.update_theme_stats(t_sleep, (d_s + timedelta(days=2)).isoformat())

    # SCENARIO B: Tension (Stress & Yoga co-occur)
    for i in range(7):
        d_t = now - timedelta(days=45 - i*5)
        eid = db.create_journal_entry(user_id, f"Stress & Yoga {i}", {})
        db.add_theme_occurrence(t_stress, 'journal_entry', eid, "stress", 0.95, d_t.isoformat())
        db.add_theme_occurrence(t_yoga, 'journal_entry', eid, "yoga", 0.95, d_t.isoformat())

    # SCENARIO C: Dissipated (Habit)
    for i in range(8):
        d_h = now - timedelta(days=90 - i*5)
        eid = db.create_journal_entry(user_id, f"Habit {i}", {})
        db.add_theme_occurrence(t_habit, 'journal_entry', eid, "habit", 0.95, d_h.isoformat())

    # SCENARIO D: Decision Impact (Meditation -> Stress decrease)
    med_dates = [now - timedelta(days=100), now - timedelta(days=70), now - timedelta(days=40)]
    for i, dm in enumerate(med_dates):
        em = db.create_journal_entry(user_id, f"Meditation {i}", {})
        db.add_theme_occurrence(t_med, 'journal_entry', em, "med", 0.95, dm.isoformat())
        for j in range(2):
            db.add_theme_occurrence(t_stress, 'journal_entry', 5000+i+j, "stress", 0.9, (dm - timedelta(days=5+j)).isoformat())

    report.add_stage("Data Ingestion", time.time() - t0)

    # --- STAGE 2: ANALYTICAL EXECUTION ---
    t1 = time.time()
    TrajectoryEngine(user_id).analyze_all_themes()
    TensionEngine(user_id).analyze_all_tensions()
    ResolutionEngine(user_id).analyze_all_themes()
    LeverageEngine(user_id).analyze_all_leverage(force_recompute=True)
    DecisionImpactEngine(user_id).analyze_all_anchors()
    report.add_stage("Analytical Execution", time.time() - t1)

    # --- STAGE 3: META-CONTROL VALIDATION ---
    t2 = time.time()
    # 1. Verification of Conflict Suppression
    # Force a 'increasing' trajectory for Yoga which is actually 'stable'
    db.create_or_update_confidence('trajectory', t_yoga, 'medium', 0.6, 5, 20, 1.0, 0.5)
    # Actually Yoga is stable, but we force a fake conflict

    # 2. Priority Ranking
    priority_engine = InsightPrioritizationEngine(user_id)
    # We will fetch raw from all engines and rank
    all_raw = []
    all_raw.extend(TrajectoryEngine(user_id).analyze_all_themes())
    all_raw.extend(ResolutionEngine(user_id).analyze_all_themes())

    # Standardize them for ranker
    for i in all_raw:
        i['engine_name'] = i.get('engine_name') or ('trajectory' if 'trajectory_label' in i else 'resolution')
        i['pattern_type'] = 'theme'
        i['pattern_id'] = i.get('theme_id')

    ranked = priority_engine.rank_insights(all_raw)
    report.add_stage("Meta-Control & Ranking", time.time() - t2)

    # --- STAGE 4: FULL PIPELINE INTEGRITY ---
    t3 = time.time()
    companion = PersonalAICompanion(user_id=user_id)
    companion.intelligence.chat = MagicMock(return_value="OK")
    companion.chat("Complete system check.")

    prompt = companion.intelligence.chat.call_args[1]['system_prompt']
    report.add_stage("Full Context Enrichment", time.time() - t3)

    # --- FINAL VALIDATIONS ---
    print("\n" + "─"*40)
    print(" SYSTEM INTEGRITY VALIDATION ")
    print("─"*40)

    # 1. Confidence Registry Check
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM pattern_confidence")
        conf_count = cur.fetchone()[0]
        print(f"Confidence Records: {conf_count} [OK]")
        assert conf_count > 0

    # 2. Evidence Integrity
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM pattern_evidence")
        ev_count = cur.fetchone()[0]
        print(f"Evidence Snapshots: {ev_count} [OK]")
        assert ev_count > 0

    # 3. Choke Point Filtering
    print(f"Ranked Insights in Context: {len(ranked)}")
    assert len(ranked) <= 5, "Priority Engine failed to truncate top items"

    # 4. Prompt Integrity & Suppression Check
    # We verify that 'Old Habit' or 'Meditation' reached the prompt (they were prioritized)
    assert "Old Habit" in prompt or "Meditation" in prompt, "Prioritized themes missing from context"
    print("Prioritized context integrity verified [OK]")

    # 5. Verify Conflict Suppression actually worked
    # 'Work Stress' should NOT have an 'increasing' trajectory because it was suppressed by our manual dissipated resolution
    assert "is increasing in frequency" not in prompt, "Conflict Suppression failed to silence contradictory insight"
    print("Conflict suppression verified [OK]")

    report.print_report()
    logger.info("ULTIMATE SYSTEM TEST: PASSED")
