import os
import sys
import time
import uuid
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.core import PersonalAICompanion
from agent.database import db
from agent.trackers.reflections import ReflectionService
from agent.persistence import PersistenceEngine

load_dotenv()

def test_system_health_invariant():
    """
    INVARIANT TEST: Proto-Theme Threshold Enforcement
    Goal: Verify that the 5-occurrence threshold is strictly enforced.
    Verify: 
    1. Cluster of 4 items -> HIDDEN
    2. Cluster of 5 items -> SURFACED
    """
    print("\n=== SYSTEM HEALTH INVARIANT TEST ===")
    
    # 1. Setup two users
    user_a_name = f"user_proto_{uuid.uuid4().hex[:8]}"
    user_b_name = f"user_theme_{uuid.uuid4().hex[:8]}"
    
    id_a = db.create_user(user_a_name, "pass")
    id_b = db.create_user(user_b_name, "pass")
    
    print(f"User A (Proto): {id_a} | User B (Theme): {id_b}")
    
    # 2. Inject Data
    # CASE A: 4 items (Suppressed)
    print("> CASE A: Injecting 4 identical reflections (User A)...")
    text_a = f"This is a specific repetitive thought about A: {uuid.uuid4().hex}"
    refl_a = ReflectionService(id_a)
    for _ in range(4):
        refl_a.create_reflection(text_a, energy_level=8)
    
    # CASE B: 5 items (Visible)
    print("> CASE B: Injecting 5 identical reflections (User B)...")
    text_b = f"This is a specific repetitive thought about B: {uuid.uuid4().hex}"
    refl_b = ReflectionService(id_b)
    for _ in range(5):
        refl_b.create_reflection(text_b, energy_level=8)

    # 3. Trigger Discovery
    print("\n> Running Discovery...")
    PersistenceEngine(id_a).discover_themes()
    PersistenceEngine(id_b).discover_themes()

    # 4. Examine Context Injection
    print("\n=== INVARIANT VERIFICATION ===")
    
    # Verify User A (4 items -> 0 visible)
    comp_a = PersonalAICompanion(id_a)
    ctx_a = comp_a._get_aggregated_context("check")
    # Count patterns
    header = "# Observed Structural Patterns"
    if header in ctx_a:
        section = ctx_a.split(header)[1]
        patterns_a = [l for l in section.split("\n") if l.strip().startswith("- ")]
    else:
        patterns_a = []
        
    print(f"  - User A (Count 4) patterns surfaced: {len(patterns_a)}")
    assert len(patterns_a) == 0 or "No significant patterns observed" in ctx_a
    print("  [PASS] Proto-theme (n=4) correctly suppressed.")

    # Verify User B (5 items -> 1 visible)
    comp_b = PersonalAICompanion(id_b)
    ctx_b = comp_b._get_aggregated_context("check")
    if header in ctx_b:
        section = ctx_b.split(header)[1]
        patterns_b = [l for l in section.split("\n") if l.strip().startswith("- ")]
    else:
        patterns_b = []
        
    print(f"  - User B (Count 5) patterns surfaced: {len(patterns_b)}")
    assert len(patterns_b) == 1
    print("  [PASS] Genuine theme (n=5) correctly surfaced.")

    print("\n=== SYSTEM SEALED & STABLE ===")

if __name__ == "__main__":
    try:
        test_system_health_invariant()
    except Exception as e:
        print(f"\n[FAIL] Invariant Violation: {e}")
        sys.exit(1)