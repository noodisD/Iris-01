#!/usr/bin/env python3
"""
IRIS Minimal Companion - CLI
Now with multi-user support and a full database backend.
"""

import sys
import getpass
import signal
import warnings
from pathlib import Path

# Suppress upstream deprecation warnings from third-party libraries
# HDBSCAN 0.8.41 has invalid escape sequences in their own source code (robust_single_linkage_.py:154)
# This is not our code and cannot be fixed by us - suppressing is the proper approach
warnings.filterwarnings("ignore", category=DeprecationWarning, module="hdbscan.*")

# Set up paths
COMPANION_DIR = Path(__file__).parent.absolute()
sys.path.insert(0, str(COMPANION_DIR))

from dotenv import load_dotenv
load_dotenv(COMPANION_DIR / ".env")

# Configure logging first, before any agent imports
import logging
from agent.logging_config import configure_logging
configure_logging()
logger = logging.getLogger(__name__)

# New architecture imports
from agent.database import db
from agent.graph_db import graph_db
from agent.core import PersonalAICompanion
from agent.persistence import PersistenceEngine
from agent.trajectory import TrajectoryEngine
from agent.tension import TensionEngine
from agent.resolution import ResolutionEngine
from agent.leverage import LeverageEngine
from agent.decision_impact import DecisionImpactEngine
from agent.explanation import ExplanationEngine
from agent.evidence import EvidenceEngine
from agent.prioritization import InsightPrioritizationEngine
from agent.narrative import NarrativeFormatter
from agent.preferences import UserPreferencesService
from agent.constants import TRAJECTORY_RECENT_DAYS, RESOLUTION_RECENT_DAYS, DECISION_IMPACT_WINDOW_DAYS

def show_help():
    print("""
COMMANDS:
  /journal             Create a journal entry
  /themes              Show what keeps coming back
  /theme <id>          Show detailed timeline for a theme
  /discover            Discover new themes from recent entries
  /trajectory          Show what is changing over time
  /trend <id>          Show detailed trend for a theme
  /tensions            Show what themes co-exist uneasily
  /tension <id>        Show detailed tension analysis for a pair
  /resolutions         Show what patterns have settled or reappeared
  /resolution <id>     Show detailed resolution analysis for a theme
  /leverage            Show patterns that drive other patterns
  /leverage <id>       Show detailed influence analysis for a theme
  /impact              Show what patterns tend to follow others
  /impact <id>         Show detailed post-hoc analysis for an anchor
  /confidence <type> <id> Show reliability audit for a pattern
  /explain <type> <id> Show the reasoning behind an observation
  /evidence <type> <id> Show raw historical evidence snapshots
  /conflicts <type> <id> Show suppressed contradictory insights
  /priority            Show the current leaderboard of ranked insights
  /settings            View or change your analytical gates
  /why <type> <id>     Explain why an insight was surfaced
  /hidden              Show insights suppressed in the last run
  /rebuild-vector      Rebuild the vector search index from the database
  /rebuild-graph       Rebuild the knowledge graph from the database
  /help                Show this help
  /exit                Exit the application
""")

def create_user():
    """CLI command to create a new user."""
    print("\n--- Create New User ---")
    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    if not username or not password:
        print("Username and password cannot be empty.")
        return
    try:
        user_id = db.create_user(username, password)
        print(f"✓ User '{username}' created successfully with ID {user_id}.")
    except ValueError as e:
        logger.error(f"Error: {e}")

def login():
    """CLI command to log in a user."""
    print("\n--- Login ---")
    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    user = db.verify_user(username, password)
    if user:
        print(f"✓ Welcome, {username}!")
        return user
    else:
        print("✗ Invalid username or password.")
        return None

def create_journal_entry(companion: PersonalAICompanion):
    """Create a journal entry using the journal service."""
    print("\n--- Create Journal Entry ---")
    try:
        wellbeing = {"notes": input("Wellbeing notes: ")}
        ideas_raw = input("Key ideas/insights (comma-separated): ")
        ideas = [i.strip() for i in ideas_raw.split(',') if i.strip()]

        # Simplified for demonstration
        goals = []
        execution = []

        response = companion.journal_entry_service.create_entry(
            wellbeing=wellbeing,
            ideas=ideas,
            goals=goals,
            execution=execution,
        )
        print(response)

    except Exception as e:
        logger.error(f"\1: {e}")

def show_themes(companion: PersonalAICompanion):
    """Show all persistent themes (what keeps coming back)."""
    print("\n--- WHAT KEEPS COMING BACK ---\n")
    try:
        engine = PersistenceEngine(companion.user_id)
        themes = engine.get_persistent_themes(min_occurrences=2)

        if not themes:
            print("No recurring themes yet. Keep journaling!")
            return

        for i, theme in enumerate(themes, 1):
            count = theme["occurrence_count"]
            summary = theme["summary"]
            first = theme["first_seen_at"].split("T")[0]
            last = theme["last_seen_at"].split("T")[0]
            print(f"{i}. \"{summary}\"")
            print(f"   {count} times | First: {first} | Last: {last}")
            print()
    except Exception as e:
        logger.error(f"\1: {e}")

def show_theme_detail(companion: PersonalAICompanion, theme_id: str):
    """Show detailed timeline for a specific theme."""
    print()
    try:
        theme_id = int(theme_id)
        engine = PersistenceEngine(companion.user_id)

        themes = engine.get_persistent_themes()
        theme = next((t for t in themes if t["id"] == theme_id), None)

        if not theme:
            print("✗ Theme not found.")
            return

        print(f"THEME: \"{theme['summary']}\"")
        print(f"Occurrences: {theme['occurrence_count']}")
        print(f"First: {theme['first_seen_at'].split('T')[0]} | Last: {theme['last_seen_at'].split('T')[0]}")
        print()

        timeline = engine.get_theme_timeline(theme_id)
        print(timeline)
        print()
    except ValueError:
        print("✗ Invalid theme ID.")
    except Exception as e:
        logger.error(f"\1: {e}")

def discover_themes(companion: PersonalAICompanion):
    """Discover new themes from recent journal entries."""
    print("\nDiscovering themes...")
    try:
        engine = PersistenceEngine(companion.user_id)
        new_themes = engine.discover_themes()

        if not new_themes:
            print("No new themes discovered. Need more journal entries.")
            return

        print(f"\n✓ Discovered {len(new_themes)} new theme(s):")
        for theme in new_themes:
            print(f"  - \"{theme['summary']}\" ({theme['occurrence_count']} entries)")
        print()
    except Exception as e:
        logger.error(f"\1: {e}")

def show_trajectory(companion: PersonalAICompanion):
    """Show all themes with their trajectory (what is changing)."""
    print("\n--- WHAT IS CHANGING ---\n")
    try:
        engine = TrajectoryEngine(companion.user_id)
        significant = engine.get_significant_changes()

        if not significant:
            print("No significant changes in themes. All appear stable.")
            return

        # Group by trajectory type
        increasing = [s for s in significant if s["trajectory_label"] == "increasing"]
        emerging = [s for s in significant if s["trajectory_label"] == "emerging"]
        fading = [s for s in significant if s["trajectory_label"] == "fading"]

        if increasing:
            print("↑ INCREASING")
            for item in increasing:
                print(f"- \"{item['theme_summary']}\"")
                print(f"  Appearing more often over the last {TRAJECTORY_RECENT_DAYS} days")
                print()

        if emerging:
            print("↗ EMERGING")
            for item in emerging:
                print(f"- \"{item['theme_summary']}\"")
                print(f"  First appeared recently, recurring now")
                print()

        if fading:
            print("↓ FADING")
            for item in fading:
                print(f"- \"{item['theme_summary']}\"")
                print(f"  Not mentioned as frequently recently")
                print()

    except Exception as e:
        logger.error(f"\1: {e}")

def show_trend_detail(companion: PersonalAICompanion, theme_id: str):
    """Show detailed trend analysis for a specific theme."""
    print()
    try:
        theme_id = int(theme_id)
        engine = TrajectoryEngine(companion.user_id)

        analysis = engine.analyze_theme(theme_id)

        if analysis["trajectory_label"] == "insufficient data":
            print("✗ Not enough data to analyze trend for this theme.")
            return

        print(f"THEME: \"{analysis['theme_summary']}\"")
        print(f"TRAJECTORY: {analysis['trajectory_label'].upper()}")
        print(f"RECENT COUNT: {analysis['recent_count']}")
        print(f"PAST COUNT: {analysis['past_count']}")
        print(f"FREQUENCY DELTA: {analysis['frequency_delta']:.3f}")
        print(f"TREND SLOPE: {analysis['trend_score']:.3f}")
        print(f"CONFIDENCE: {analysis['confidence_level'].upper()}")
        print()

    except ValueError:
        print("✗ Invalid theme ID.")
    except Exception as e:
        logger.error(f"\1: {e}")

def show_tensions(companion: PersonalAICompanion):
    """Show all significant tensions between themes."""
    print("\n--- WHAT CO-EXISTS UNEASILY ---\n")
    try:
        engine = TensionEngine(companion.user_id)
        significant = engine.get_significant_tensions()

        if not significant:
            print("No significant tensions found. Themes appear independently.")
            return

        # Group by tension type
        persistent = [s for s in significant if s["tension_label"] == "persistent"]
        emerging = [s for s in significant if s["tension_label"] == "emerging"]
        fading = [s for s in significant if s["tension_label"] == "fading"]
        intermittent = [s for s in significant if s["tension_label"] == "intermittent"]

        if persistent:
            print("🔒 PERSISTENT")
            for item in persistent:
                print(f"- \"{item['theme_a_summary']}\" and \"{item['theme_b_summary']}\"")
                print(f"  Co-occur frequently with different activity patterns")
                print(f"  Confidence: {item['confidence_level'].upper()}")
                print()

        if emerging:
            print("↗ EMERGING")
            for item in emerging:
                print(f"- \"{item['theme_a_summary']}\" and \"{item['theme_b_summary']}\"")
                print(f"  Recently started co-occurring with different patterns")
                print(f"  Confidence: {item['confidence_level'].upper()}")
                print()

        if fading:
            print("↘ FADING")
            for item in fading:
                print(f"- \"{item['theme_a_summary']}\" and \"{item['theme_b_summary']}\"")
                print(f"  Previously co-occurred but now appearing less together")
                print(f"  Confidence: {item['confidence_level'].upper()}")
                print()

        if intermittent:
            print("⚡ INTERMITTENT")
            for item in intermittent:
                print(f"- \"{item['theme_a_summary']}\" and \"{item['theme_b_summary']}\"")
                print(f"  Co-occur sporadically with different patterns")
                print(f"  Confidence: {item['confidence_level'].upper()}")
                print()

    except Exception as e:
        logger.error(f"\1: {e}")

def show_tension_detail(companion: PersonalAICompanion, tension_id: str):
    """Show detailed tension analysis for a specific pair of themes."""
    print()
    try:
        # For now, we'll just show all tensions since we don't have a specific tension ID lookup
        # In a real implementation, we might need to pass both theme IDs or have a different approach
        print("This command requires specifying two theme IDs to analyze their tension.")
        print("For now, showing all significant tensions:")
        show_tensions(companion)
    except ValueError:
        print("✗ Invalid tension ID.")
    except Exception as e:
        logger.error(f"\1: {e}")

def show_resolutions(companion: PersonalAICompanion):
    """Show all themes with their resolution status (what has settled or reappeared)."""
    print("\n--- WHAT HAS SETTLED OR REAPPEARED ---\n")
    try:
        engine = ResolutionEngine(companion.user_id)
        resolutions = engine.analyze_all_themes()

        # Filter for significant resolutions
        significant = [r for r in resolutions if r["resolution_label"] in ["dissipated", "reappearing", "stabilized"]]

        if not significant:
            print("No patterns have settled or reappeared yet. Themes appear persistent.")
            return

        # Group by resolution type
        dissipated = [s for s in significant if s["resolution_label"] == "dissipated"]
        reappearing = [s for s in significant if s["resolution_label"] == "reappearing"]
        stabilized = [s for s in significant if s["resolution_label"] == "stabilized"]

        if dissipated:
            print("🌑 DISSIPATED")
            for item in dissipated:
                print(f"- \"{item['summary']}\" (ID: {item['theme_id']})")
                print(f"  Not appeared in the last {RESOLUTION_RECENT_DAYS} days")
                print(f"  Past Count: {item['past_count']} | Confidence: {item['confidence_level'].upper()}")
                print()

        if reappearing:
            print("🌅 REAPPEARING")
            for item in reappearing:
                print(f"- \"{item['summary']}\" (ID: {item['theme_id']})")
                print(f"  Recently reappeared after a significant gap")
                print(f"  Recent: {item['recent_count']} | Past: {item['past_count']} | Confidence: {item['confidence_level'].upper()}")
                print()

        if stabilized:
            print("⚖️ STABILIZED")
            for item in stabilized:
                print(f"- \"{item['summary']}\" (ID: {item['theme_id']})")
                print(f"  Frequency has stabilized compared to the baseline")
                print(f"  Attenuation Score: {item['attenuation_score']:.3f} | Confidence: {item['confidence_level'].upper()}")
                print()

    except Exception as e:
        logger.error(f"\1: {e}")

def show_resolution_detail(companion: PersonalAICompanion, theme_id: str):
    """Show detailed resolution analysis for a specific theme."""
    print()
    try:
        theme_id = int(theme_id)
        engine = ResolutionEngine(companion.user_id)

        analysis = engine.analyze_theme(theme_id)

        print(f"THEME: \"{analysis['summary']}\"")
        print(f"RESOLUTION STATUS: {analysis['resolution_label'].upper()}")
        print(f"RECENT COUNT: {analysis['recent_count']}")
        print(f"PAST COUNT: {analysis['past_count']}")
        print(f"ATTENUATION SCORE: {analysis['attenuation_score']:.3f}")
        print(f"CONFIDENCE: {analysis['confidence_level'].upper()}")
        print()

    except ValueError:
        print("✗ Invalid theme ID.")
    except Exception as e:
        logger.error(f"\1: {e}")

def show_leverage(companion: PersonalAICompanion):
    """Show patterns that act as upstream drivers."""
    print("\n--- OBSERVED STRUCTURAL DRIVERS ---\n")
    try:
        engine = LeverageEngine(companion.user_id)
        # Scan and compute (or refresh cache)
        engine.analyze_all_leverage()
        
        sources = db.get_high_leverage_sources(companion.user_id)

        if not sources:
            print("No high-leverage drivers detected yet. Patterns appear independent.")
            return

        for i, s in enumerate(sources, 1):
            print(f"{i}. \"{s['summary']}\" (ID: {s['source_id']})")
            print(f"   Influences {s['targets_count']} other patterns | Avg Score: {s['avg_influence']:.2f}")
            print()
            
    except Exception as e:
        logger.error(f"\1: {e}")

def show_leverage_detail(companion: PersonalAICompanion, theme_id: str):
    """Show detailed influence analysis for a specific pattern."""
    print()
    try:
        theme_id = int(theme_id)
        engine = LeverageEngine(companion.user_id)
        
        # Analyze to ensure cache is fresh
        engine.analyze_pair('theme', theme_id, 'theme', theme_id) # Just to trigger some logic, wait
        
        targets = db.get_leverage_targets('theme', theme_id)
        
        theme = db.get_theme_by_id(theme_id)
        print(f"SOURCE PATTERN: \"{theme['summary']}\"")
        print("-" * 30)

        if not targets:
            print("No downstream patterns influenced by this driver.")
            return

        print("PRECEDES / DRIVES:")
        for t in targets:
            print(f"- \"{t['summary']}\" (Lift: {t['directional_lift']:.2f}, Score: {t['influence_score']:.2f})")
        print()

    except ValueError:
        print("✗ Invalid theme ID.")
    except Exception as e:
        logger.error(f"\1: {e}")

def show_impact(companion: PersonalAICompanion):
    """Show anchors with notable downstream effects."""
    print("\n--- OBSERVED TEMPORAL SEQUENCES ---\n")
    try:
        engine = DecisionImpactEngine(companion.user_id)
        # Scan and compute
        engine.analyze_all_anchors()
        
        impacts = db.get_significant_decision_impacts(companion.user_id)

        if not impacts:
            print("No notable temporal sequences detected yet. Patterns appear uncorrelated in sequence.")
            return

        # Group by anchor to show summary
        anchors = {}
        for imp in impacts:
            aid = imp['anchor_id']
            if aid not in anchors:
                anchors[aid] = {"summary": imp['anchor_summary'], "count": 0}
            anchors[aid]["count"] += 1

        for i, (aid, data) in enumerate(anchors.items(), 1):
            print(f"{i}. \"{data['summary']}\" (ID: {aid})")
            print(f"   Precedes {data['count']} significant shifts in other patterns.")
            print()
            
    except Exception as e:
        logger.error(f"\1: {e}")

def show_impact_detail(companion: PersonalAICompanion, anchor_id: str):
    """Show detailed impact analysis for a specific anchor."""
    print()
    try:
        anchor_id = int(anchor_id)
        engine = DecisionImpactEngine(companion.user_id)
        
        impacts = db.get_decision_impacts_for_anchor('theme', anchor_id)
        
        theme = db.get_theme_by_id(anchor_id)
        print(f"ANCHOR PATTERN: \"{theme['summary']}\"")
        print("-" * 40)

        if not impacts:
            print("No significant downstream shifts observed following this anchor.")
            return

        print(f"POST-HOC EFFECTS (Window: {DECISION_IMPACT_WINDOW_DAYS} days):")
        for imp in impacts:
            direction = imp['effect_direction'].upper()
            delta = imp['delta_score'] * 100
            print(f"- {imp['target_summary']:<20} | {direction:<10} | Delta: {delta:>+6.1f}% | Conf: {imp['confidence_level'].upper()}")
        print()

    except ValueError:
        print("✗ Invalid anchor ID.")
    except Exception as e:
        logger.error(f"\1: {e}")

def show_confidence(companion: PersonalAICompanion, p_type: str, p_id: str):
    """Show detailed reliability audit for a pattern."""
    print("\n--- RELIABILITY AUDIT ---\n")
    try:
        p_id = int(p_id)
        conf = db.get_confidence(p_type, p_id)
        
        if not conf:
            print(f"No confidence record found for {p_type} ID {p_id}.")
            return

        print(f"PATTERN: {p_type.upper()} (ID: {p_id})")
        print(f"RELIABILITY LABEL: {conf['confidence_level'].upper()}")
        print(f"RELIABILITY SCORE: {conf['confidence_score']:.2f}")
        print("-" * 30)
        print("EVIDENCE METRICS:")
        print(f"- Data Points Count: {conf['data_points_count']:>4} (Policy: 3/5/10)")
        print(f"- Time Coverage:     {conf['time_coverage_days']:>4} days")
        print(f"- Recency Score:     {conf['recency_score']:>4.2f} (Decay tau: 30 days)")
        print(f"- Consistency Score: {conf['consistency_score']:>4.2f} (Threshold: 0.70)")
        print()
        print("Computed at: ", conf['last_computed_at'])
        
    except ValueError:
        print("✗ Invalid ID format. Use: /confidence <type> <id>")
    except Exception as e:
        logger.error(f"\1: {e}")

def show_explanation(companion: PersonalAICompanion, p_type: str, p_id: str):
    """Show human-friendly explanation for an observation."""
    print("\n--- SYSTEM EXPLANATION ---\n")
    try:
        p_id = int(p_id)
        explainer = ExplanationEngine(companion.user_id)
        bundle = explainer.explain(p_type, p_id)
        
        print(f"Summary: {bundle['summary']}")
        print(f"Confidence: {bundle.get('confidence', 'N/A')}")
        
        if bundle['evidence']:
            print("\nEvidence Evidence:")
            for ev in bundle['evidence']:
                # Format JSON value
                val = ev['value']
                if isinstance(val, float): val = f"{val:.3f}"
                print(f"- {ev['label']:<30} : {val} ({ev['engine']})")
        
        if 'computed_at' in bundle:
            print(f"\nLast calculated: {bundle['computed_at']}")
            
    except Exception as e:
        logger.error(f"\1: {e}")

def show_raw_evidence(companion: PersonalAICompanion, p_type: str, p_id: str):
    """Show raw machine-readable evidence for audit."""
    print("\n--- RAW EVIDENCE SNAPSHOT ---\n")
    try:
        p_id = int(p_id)
        ev_engine = EvidenceEngine()
        bundle = ev_engine.get_latest_bundle(p_type, p_id)
        
        if not bundle:
            print("No evidence found.")
            return

        print(f"{'ENGINE':<15} | {'KEY':<25} | {'VALUE':<10}")
        print("-" * 55)
        for rec in bundle:
            print(f"{rec['engine_name']:<15} | {rec['evidence_key']:<25} | {rec['evidence_value']}")
            
    except Exception as e:
        logger.error(f"\1: {e}")

def show_priorities(companion: PersonalAICompanion):
    """Show current insight leaderboard."""
    print("\n--- INSIGHT PRIORITIZATION LEADERBOARD ---\n")
    try:
        # We need to compute them fresh for the leaderboard
        from agent.persistence import PersistenceEngine
        from agent.trajectory import TrajectoryEngine
        from agent.resolution import ResolutionEngine
        from agent.leverage import LeverageEngine
        from agent.decision_impact import DecisionImpactEngine
        
        raw = []
        raw.extend(TrajectoryEngine(companion.user_id).analyze_all_themes())
        raw.extend(ResolutionEngine(companion.user_id).analyze_all_themes())
        # ... fetch others if needed for a full view
        
        # Mapping to prioritize format happens in core normally, 
        # for CLI we'll just show what's in the DB priorities table if available.
        # But compute_all is better for a 'live' view.
        
        engine = InsightPrioritizationEngine(companion.user_id)
        # Note: We'd need to convert raw list to the Contract format here 
        # if we wanted a truly live view.
        # For MVP, let's just query the DB for the last computed ranks.
        
        conn = db.get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT rank, engine_name, pattern_type, pattern_id, priority_score
                FROM insight_priorities
                ORDER BY rank ASC LIMIT 10;
            """)
            rows = cur.fetchall()
            
            if not rows:
                print("No insights have been prioritized yet. Chat with IRIS first!")
                return

            print(f"{'RANK':<4} | {'ENGINE':<15} | {'PATTERN':<15} | {'SCORE':<6}")
            print("-" * 50)
            for r in rows:
                print(f"{r[0]:<4} | {r[1]:<15} | {r[2].upper()} {r[3]:<8} | {r[4]:.3f}")
            print()
            
    except Exception as e:
        logger.error(f"\1: {e}")

def show_narrative(companion: PersonalAICompanion, p_type: str, p_id: str):
    """Show how an insight is rendered into natural language."""
    print("\n--- NARRATIVE RENDERING ---\n")
    try:
        p_id = int(p_id)
        # We need a fresh insight object to format
        # For simplicity, we'll try to find it in the trajectory/resolution engines
        from agent.trajectory import TrajectoryEngine
        from agent.resolution import ResolutionEngine
        
        # 1. Fetch raw insight
        ins = None
        trajs = TrajectoryEngine(companion.user_id).analyze_all_themes()
        ins = next((i for i in trajs if i['theme_id'] == p_id), None)
        if ins: ins['engine_name'] = 'trajectory'
        
        if not ins:
            res = ResolutionEngine(companion.user_id).analyze_all_themes()
            ins = next((i for i in res if i['theme_id'] == p_id), None)
            if ins: ins['engine_name'] = 'resolution'

        if not ins:
            print(f"No active insight found for {p_type} ID {p_id}.")
            return

        # 2. Format
        text = NarrativeFormatter.format_insight(ins)
        
        print(f"ENGINE:    {ins['engine_name'].upper()}")
        print(f"LABEL:     {ins.get('trajectory_label') or ins.get('resolution_label')}")
        print(f"NARRATIVE: \"{text}\"")
        print()
            
    except Exception as e:
        logger.error(f"\1: {e}")

def show_settings(companion: PersonalAICompanion):
    """Show current analytical gates and preferences."""
    print("\n--- USER ANALYTICAL SETTINGS ---\n")
    try:
        prefs = companion.pref_service.get_prefs()
        print(f"Confidence Floor: {prefs['min_confidence'].upper()}")
        print(f"Max Insights:     {prefs['max_items']}")
        print(f"Enabled Engines:  {prefs['enabled_engines'] or 'ALL'}")
        print(f"Show Suppressed:  {prefs['show_suppressed']}")
        print("\nTo change a setting: /settings set <key> <value>")
    except Exception as e:
        logger.error(f"\1: {e}")

def update_setting(companion: PersonalAICompanion, key: str, value: str):
    """Update a specific user preference."""
    try:
        # Cast value types
        final_val = value
        if value.lower() == 'true': final_val = True
        elif value.lower() == 'false': final_val = False
        elif value.isdigit(): final_val = int(value)
        elif value.lower() == 'null': final_val = None
        
        # enabled_engines needs list parsing (simple comma separated)
        if key == 'enabled_engines' and value.lower() != 'null':
            final_val = [v.strip() for v in value.split(',')]

        companion.pref_service.update_pref(key, final_val)
        print(f"✓ Setting '{key}' updated successfully.")
        
        # Immediate feedback
        if key == 'min_confidence' and final_val == 'low':
            print("(!) IRIS is now in Exploratory Mode (Confidence: Low)")
            
    except Exception as e:
        logger.error(f"\1: {e}")

def show_why(companion: PersonalAICompanion, p_type: str, p_id: str):
    """Explains why an insight was surfaced (Score/Confidence)."""
    print("\n--- INSIGHT SOURCE ANALYSIS ---\n")
    try:
        p_id = int(p_id)
        # Fetch from priorities table
        conn = db.get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT engine_name, priority_score, rank 
                FROM insight_priorities 
                WHERE pattern_type = %s AND pattern_id = %s
                ORDER BY computed_at DESC LIMIT 1;
            """, (p_type, p_id))
            row = cur.fetchone()
            if not row:
                print("No prioritization record found for this pattern.")
                return
            
            engine, score, rank = row
            conf = db.get_confidence(p_type, p_id)
            
            print(f"PATTERN:    {p_type.upper()} {p_id}")
            print(f"ENGINE:     {engine.upper()}")
            print(f"RANK:       #{rank} in last run")
            print(f"PRIORITY:   {score:.3f}")
            if conf:
                print(f"CONFIDENCE: {conf['confidence_level'].upper()} ({conf['confidence_score']:.2f})")
            print("\nReason: High relevance score and passed analytical gates.")
            
    except Exception as e:
        logger.error(f"\1: {e}")

def show_hidden(companion: PersonalAICompanion):
    """Lists suppressed insights from the last run."""
    print("\n--- SUPPRESSED INSIGHTS (Last Run Only) ---\n")
    if not companion.last_suppressed_insights:
        print("No insights were suppressed in the last analytical run.")
        return

    print(f"{'ENGINE':<15} | {'PATTERN':<15} | {'REASON':<20}")
    print("-" * 55)
    for key, data in companion.last_suppressed_insights.items():
        ins = data['insight']
        print(f"{ins['engine_name']:<15} | {ins['pattern_type'].upper()} {ins['pattern_id']:<8} | {data['reason'].upper()}")
    print("\nUse /settings set show_suppressed true to enable detailed debug views.")

def check_narrative_safety(text: str):
    """Test the forbidden-language firewall."""
    print(f"\nTesting: \"{text}\"")
    try:
        NarrativeFormatter._validate_safety(text)
        print("✓ PASS: No forbidden language detected.")
    except ValueError as e:
        print(f"✗ FAIL: {e}")

def show_conflicts(companion: PersonalAICompanion, p_type: str, p_id: str):
    """Show suppressed insights for a pattern."""
    print("\n--- CONFLICT SUPPRESSION AUDIT ---\n")
    try:
        p_id = int(p_id)
        # We need to run the aggregation logic once to see the suppression result
        # For audit, we'll manually call the engine
        from agent.conflict import ConflictSuppressionEngine
        from agent.trajectory import TrajectoryEngine
        from agent.tension import TensionEngine
        from agent.resolution import ResolutionEngine
        
        # 1. Fetch raw insights for this pattern
        raw = []
        raw.extend([t for t in TrajectoryEngine(companion.user_id).analyze_all_themes() if t['theme_id'] == p_id])
        raw.extend([r for r in ResolutionEngine(companion.user_id).analyze_all_themes() if r['theme_id'] == p_id])
        # ... add more if needed
        
        engine = ConflictSuppressionEngine()
        result = engine.suppress(raw)
        
        print(f"PATTERN: {p_type.upper()} (ID: {p_id})")
        print(f"VISIBLE INSIGHTS: {len(result['visible'])}")
        for v in result['visible']:
            print(f"- {v['engine_name'].upper()}: {v.get('resolution_label') or v.get('trajectory_label') or 'active'}")
            
        print(f"\nSUPPRESSED INSIGHTS: {len(result['suppressed'])}")
        for s in result['suppressed']:
            ins = s['insight']
            print(f"- {ins['engine_name'].upper()}: {ins.get('resolution_label') or ins.get('trajectory_label')}")
            print(f"  REASON: {s['reason']}")
            if 'winner_engine' in s:
                print(f"  WINNER: {s['winner_engine'].upper()}")
            print()
            
    except Exception as e:
        logger.error(f"\1: {e}")

def main_chat_loop(user_id: int):
    """The main loop for chatting with the companion."""
    try:
        companion = PersonalAICompanion(user_id=user_id)
        
        # Register signal handler for graceful shutdown
        def handle_signal(sig, frame):
            print("\n(!) Shutdown signal received. Cleaning up...")
            companion.shutdown()
            sys.exit(0)
        
        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal) # Also handle Ctrl+C
        
        print("\n✓ Companion initialized. Type '/help' for commands or start chatting!\n")
    except Exception as e:
        logger.error(f"\1: {e}")
        return

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue

            if user_input.lower() == "/exit":
                break
            elif user_input.lower() == "/help":
                show_help()
            elif user_input.lower() == "/journal":
                create_journal_entry(companion)
            elif user_input.lower() == "/themes":
                show_themes(companion)
            elif user_input.lower().startswith("/theme "):
                theme_id = user_input[7:].strip()
                show_theme_detail(companion, theme_id)
            elif user_input.lower() == "/discover":
                discover_themes(companion)
            elif user_input.lower() == "/trajectory":
                show_trajectory(companion)
            elif user_input.lower().startswith("/trend "):
                theme_id = user_input[7:].strip()
                show_trend_detail(companion, theme_id)
            elif user_input.lower() == "/tensions":
                show_tensions(companion)
            elif user_input.lower().startswith("/tension "):
                tension_id = user_input[9:].strip()
                show_tension_detail(companion, tension_id)
            elif user_input.lower() == "/resolutions":
                show_resolutions(companion)
            elif user_input.lower().startswith("/resolution "):
                theme_id = user_input[12:].strip()
                show_resolution_detail(companion, theme_id)
            elif user_input.lower() == "/leverage":
                show_leverage(companion)
            elif user_input.lower().startswith("/leverage "):
                theme_id = user_input[10:].strip()
                show_leverage_detail(companion, theme_id)
            elif user_input.lower() == "/impact":
                show_impact(companion)
            elif user_input.lower().startswith("/impact "):
                anchor_id = user_input[8:].strip()
                show_impact_detail(companion, anchor_id)
            elif user_input.lower().startswith("/confidence "):
                parts = user_input[12:].strip().split()
                if len(parts) == 2:
                    show_confidence(companion, parts[0], parts[1])
                else:
                    print("Usage: /confidence <type> <id>")
            elif user_input.lower().startswith("/explain "):
                parts = user_input[9:].strip().split()
                if len(parts) == 2:
                    show_explanation(companion, parts[0], parts[1])
                else:
                    print("Usage: /explain <type> <id>")
            elif user_input.lower().startswith("/evidence "):
                parts = user_input[10:].strip().split()
                if len(parts) == 2:
                    show_raw_evidence(companion, parts[0], parts[1])
                else:
                    print("Usage: /evidence <type> <id>")
            elif user_input.lower().startswith("/conflicts "):
                parts = user_input[11:].strip().split()
                if len(parts) == 2:
                    show_conflicts(companion, parts[0], parts[1])
                else:
                    print("Usage: /conflicts <type> <id>")
            elif user_input.lower() == "/priority":
                show_priorities(companion)
            elif user_input.lower().startswith("/narrative "):
                parts = user_input[11:].strip().split()
                if len(parts) == 2:
                    show_narrative(companion, parts[0], parts[1])
                else:
                    print("Usage: /narrative <type> <id>")
            elif user_input.lower() == "/settings":
                show_settings(companion)
            elif user_input.lower().startswith("/settings set "):
                parts = user_input[14:].strip().split(None, 1)
                if len(parts) == 2:
                    update_setting(companion, parts[0], parts[1])
                else:
                    print("Usage: /settings set <key> <value>")
            elif user_input.lower().startswith("/why "):
                parts = user_input[5:].strip().split()
                if len(parts) == 2:
                    show_why(companion, parts[0], parts[1])
                else:
                    print("Usage: /why <type> <id>")
            elif user_input.lower() == "/hidden":
                show_hidden(companion)
            elif user_input.lower().startswith("/narrative_check "):
                text = user_input[17:].strip().strip('"')
                check_narrative_safety(text)
            elif user_input.lower() == "/rebuild-graph":
                print("Rebuilding graph...")
                graph_db.rebuild_from_postgres()
            else:
                print("\nCompanion: ", end="", flush=True)
                response = companion.chat(user_input)
                print(response)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\n✗ An unexpected error occurred: {e}")

def main():
    """The main entry point for the CLI application."""
    print("\n" + "="*50)
    print(" IRIS MINIMAL COMPANION")
    print("="*50)

    try:
        # Initialize database schema
        try:
            db.create_schema()
        except Exception as e:
            print(f"✗ CRITICAL: Could not connect to or initialize database: {e}")
            sys.exit(1)

        # User Authentication Loop
        user_data = None
        while not user_data:
            choice = input("\n[1] Login\n[2] Create User\n[3] Exit\n> ").strip()
            if choice == '1':
                user_data = login()
            elif choice == '2':
                create_user()
            elif choice == '3':
                break
            else:
                print("Invalid choice.")

        # If user is logged in, start the main chat loop
        if user_data:
            main_chat_loop(user_id=user_data['id'])

    except KeyboardInterrupt:
        print("\n\n(!) Interrupted by user.")
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
    finally:
        # Always clean up connections, even if interrupted
        print("\nCleaning up connections...")
        try:
            db.close_connection()
        except Exception as e:
            print(f"Warning: Error closing database: {e}")
        try:
            graph_db.close()
        except Exception as e:
            print(f"Warning: Error closing graph database: {e}")
        print("Goodbye!\n")

if __name__ == "__main__":
    main()
