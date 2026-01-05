
import pytest
import time
import logging
import os
from datetime import datetime, timedelta
from agent.core import PersonalAICompanion
from agent.database import db
from agent.persistence import PersistenceEngine
from agent.trajectory import TrajectoryEngine
from agent.tension import TensionEngine
from agent.resolution import ResolutionEngine
from agent.leverage import LeverageEngine
from agent.decision_impact import DecisionImpactEngine
from agent.pipeline import run_processing_pipeline

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LiveSystemTest")

def test_live_system_flow(test_user):
    """
    LIVE E2E: Uses real OpenAI API for embeddings and chat.
    """
    user_id = test_user['id']
    now = datetime.now()
    
    print("\n" + "═"*60)
    print(" STARTING LIVE SYSTEM INTEGRATION TEST ")
    print(" Using real OpenAI API keys and models ")
    print("═"*60)

    # 1. Ingest Data (Real Language)
    print("\n[1/5] Ingesting real-world journal entries...")
    
    # Pattern: Intense coding leads to physical fatigue
    entries = [
        (now - timedelta(days=40), "Spent 10 hours today building a recursive descent parser in Rust. My brain is on fire but I love it.", "coding"),
        (now - timedelta(days=38), "My neck and shoulders are incredibly stiff from that long coding session. Need to rest.", "fatigue"),
        (now - timedelta(days=33), "Rust compiler progress: implemented type checking. Very intense mental work.", "coding"),
        (now - timedelta(days=31), "Feeling physically drained. The long hours at the desk are catching up with me.", "fatigue"),
        (now - timedelta(days=26), "Refactoring the borrow checker logic. Deep focus for 8 hours straight.", "coding"),
        (now - timedelta(days=24), "Complete physical exhaustion today. I can barely stay awake at my desk.", "fatigue"),
        # Most recent
        (now - timedelta(days=5), "Starting the code generation phase of the compiler. Exciting but demanding.", "coding"),
        (now - timedelta(days=3), "Back pain is back. The pattern of long sessions is clearly taking a toll.", "fatigue")
    ]

    for dt, text, tag in entries:
        eid = db.create_journal_entry(user_id, text, {"tag": tag})
        # Set historical date
        conn = db.get_connection()
        with conn.cursor() as cur:
            cur.execute("UPDATE journal_entries SET created_at = %s WHERE id = %s", (dt, eid))
            conn.commit()
        
        # Run real pipeline (Generates real OpenAI embeddings)
        run_processing_pipeline('journal_entry', eid)

    # 2. Theme Discovery
    print("\n[2/5] Running Theme Discovery (HDBSCAN on real vectors)...")
    p_engine = PersistenceEngine(user_id)
    p_engine.min_cluster_size = 2
    new_themes = p_engine.discover_themes()
    print(f"✓ Discovered {len(new_themes)} live themes")

    # 3. Full Analytical Stack
    print("\n[3/5] Executing full analytical stack...")
    TrajectoryEngine(user_id).analyze_all_themes()
    TensionEngine(user_id).analyze_all_tensions()
    ResolutionEngine(user_id).analyze_all_themes()
    LeverageEngine(user_id).analyze_all_leverage(force_recompute=True)
    DecisionImpactEngine(user_id).analyze_all_anchors()

    # 4. Core Orchestration (Live Chat)
    print("\n[4/5] Calling IRIS for live pattern analysis...")
    companion = PersonalAICompanion(user_id=user_id, model="gpt-4o-mini")
    
    start_time = time.time()
    response = companion.chat("I've been working on my Rust compiler again and I'm starting to feel that familiar exhaustion. What do you see in my patterns?")
    duration = time.time() - start_time

    # 5. Verification
    print("\n[5/5] Verifying System Output...")
    print(f"\n--- IRIS LIVE RESPONSE ({duration:.2f}s) ---")
    print(response)
    print("-" * 40)

    assert len(response) > 10
    assert "Rust" in response or "coding" in response.lower() or "exhaustion" in response.lower() or "fatigue" in response.lower()
    
    print("\n" + "═"*60)
    print(" LIVE SYSTEM INTEGRITY TEST: SUCCESS ")
    print("═"*60 + "\n")
