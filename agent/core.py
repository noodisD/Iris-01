"""Core Orchestrator

This module contains the main `PersonalAICompanion` class that ties together
all the different services (intelligence, memory, journal, etc.).
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# Main services
from .intelligence import Intelligence
from .memory import ConversationMemory
from .journal_entry import JournalEntry
from .database import db

# New architecture components
from .vector_store import vector_store
from .pipeline import generate_embedding
from .persistence import PersistenceEngine
from .trajectory import TrajectoryEngine
from .tension import TensionEngine
from .resolution import ResolutionEngine
from .leverage import LeverageEngine
from .decision_impact import DecisionImpactEngine
from .conflict import ConflictSuppressionEngine
from .prioritization import InsightPrioritizationEngine
from .narrative import NarrativeFormatter
from .preferences import UserPreferencesService
from .constants import DEFAULT_TEMPERATURE, DEFAULT_MAX_TOKENS

# Handle both package and direct imports
try:
    from prompts.system_prompt import SYSTEM_PROMPT
except (ImportError, ValueError):
    from prompts.system_prompt import SYSTEM_PROMPT


class PersonalAICompanion:
    """The core AI companion, orchestrating all services."""

    def __init__(self, user_id: int, model: str = "gpt-4.1-mini"):
        """
        Initialize the companion for a specific user.
        """
        if user_id is None:
            raise ValueError("PersonalAICompanion requires a valid user_id.")
        
        self.user_id = user_id
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Initialize the core services for this user/session
        self.intelligence = Intelligence(model=model)
        self.memory = ConversationMemory(user_id=self.user_id, session_id=self.session_id)
        self.journal_entry_service = JournalEntry(user_id=self.user_id)
        self.conflict_engine = ConflictSuppressionEngine()
        self.pref_service = UserPreferencesService(user_id=self.user_id)
        
        # Session-scoped cache for transparency
        self.last_suppressed_insights = {}
        
        logger.info(f"PersonalAICompanion initialized for user {self.user_id} and session {self.session_id}")

    def shutdown(self):
        """Gracefully closes all backing service connections."""
        logger.info("Shutting down IRIS core services...")
        try:
            db.close_connection()
            # Also close graph if active
            from .graph_db import graph_db
            graph_db.close()
            logger.info("Cleanup complete. Epistemic integrity preserved.")
        except Exception as e:
            logger.error(f"Error during shutdown cleanup: {e}")

    def chat(self, user_message: str) -> str:
        """
        Main chat handler. Takes a user message, enriches it with context,
        gets an LLM response, and persists the interaction.
        """
        # 1. Add user message to memory
        self.memory.add_message("user", user_message)

        # 2. Retrieve all insights and apply meta-controls
        try:
            aggregated_context = self._get_aggregated_context(user_message)
        except Exception as e:
            logger.error(f"Failed to retrieve aggregated context: {e}")
            aggregated_context = "# Context Retrieval Error\nCould not retrieve long-term memory."

        # 3. Build the enhanced system prompt
        enhanced_prompt = f"""{SYSTEM_PROMPT}

{aggregated_context}
"""
        # 4. Get short-term conversation context
        short_term_context = self.memory.get_context(max_messages=10)

        # 5. Call the LLM
        response_text = self.intelligence.chat(
            messages=short_term_context,
            system_prompt=enhanced_prompt,
            temperature=DEFAULT_TEMPERATURE,
            max_tokens=DEFAULT_MAX_TOKENS
        )

        # 6. Add the assistant's response to memory
        self.memory.add_message("assistant", response_text)

        return response_text

    def _get_aggregated_context(self, user_message: str) -> str:
        """
        Orchestrates context retrieval through all meta-control layers.
        Respects User Preferences at every gate.
        """
        # 0. Load Preferences
        prefs = self.pref_service.get_prefs()
        self.last_suppressed_insights = {} # Reset buffer
        
        # 1. Fetch relevant memories (vector search)
        memories = self._get_relevant_context(user_message)
        
        # 2. Fetch raw analytical insights
        raw_insights = []
        try:
            # Persistence
            pers_ins = PersistenceEngine(self.user_id).get_persistent_themes(min_occurrences=2)
            for i in pers_ins:
                i['engine_name'] = 'persistence'; i['pattern_type'] = 'theme'; i['pattern_id'] = i['id']
            raw_insights.extend(pers_ins)

            # Trajectory
            traj_ins = TrajectoryEngine(self.user_id).analyze_all_themes()
            for i in traj_ins:
                i['engine_name'] = 'trajectory'; i['pattern_type'] = 'theme'; i['pattern_id'] = i['theme_id']
            raw_insights.extend(traj_ins)
            
            # Tension
            tens_ins = TensionEngine(self.user_id).analyze_all_tensions()
            for i in tens_ins:
                i['engine_name'] = 'tension'; i['pattern_type'] = 'theme'; i['pattern_id'] = i['theme_a_id']
            raw_insights.extend(tens_ins)

            # Resolution
            res_ins = ResolutionEngine(self.user_id).analyze_all_themes()
            for i in res_ins:
                i['engine_name'] = 'resolution'; i['pattern_type'] = 'theme'; i['pattern_id'] = i['theme_id']
            raw_insights.extend(res_ins)
            
            # Leverage & Impact
            lev_sources = db.get_high_leverage_sources(self.user_id, min_confidence='low')
            for s in lev_sources:
                s['engine_name'] = 'leverage'; s['pattern_type'] = 'theme'; s['pattern_id'] = s['source_id']; s['label'] = 'high'
            raw_insights.extend(lev_sources)
            
            impacts = db.get_significant_decision_impacts(self.user_id, min_confidence='low')
            for i in impacts:
                i['engine_name'] = 'decision_impact'; i['pattern_type'] = 'theme'; i['pattern_id'] = i['anchor_id']; i['label'] = i['effect_direction']
            raw_insights.extend(impacts)
        except Exception as e:
            logger.error(f"Error fetching raw insights: {e}")

        # GATE 1: Allowlist Gate
        enabled = prefs.get('enabled_engines')
        filtered_by_engine = []
        for i in raw_insights:
            if enabled is None or i['engine_name'] in enabled:
                filtered_by_engine.append(i)
            else:
                self._record_suppression(i, "engine_disabled")

        # GATE 2: Confidence Gate (User Overridden)
        reliable_insights = self._filter_by_confidence(filtered_by_engine, min_level=prefs['min_confidence'])
        
        # Track Confidence suppressions
        for i in filtered_by_engine:
            if i not in reliable_insights:
                self._record_suppression(i, "low_confidence")

        # GATE 3: Conflict Suppression
        suppression_result = self.conflict_engine.suppress(reliable_insights)
        clean_insights = suppression_result['visible']
        for s in suppression_result['suppressed']:
            self._record_suppression(s['insight'], "conflict")

        # GATE 4: Prioritization & Budget Gate
        priority_engine = InsightPrioritizationEngine(self.user_id)
        ranked_insights = priority_engine.rank_insights(clean_insights)
        
        # Budget slice (User Overridden)
        top_k = min(prefs['max_items'], len(ranked_insights))
        final_insights = ranked_insights[:top_k]
        
        # Track Budget suppressions
        for i in ranked_insights[top_k:]:
            self._record_suppression(i, "priority_cutoff")

        # 5. Narrative Formatting
        narratives = NarrativeFormatter.format_all(final_insights)
        
        # 6. Final Assembly
        header = "# Observed Structural Patterns & Observed Temporal Sequences:"
        # Ensure bulleted list
        bulleted_narratives = [f"- {n}" for n in narratives]
        body = "\n".join(bulleted_narratives) if narratives else "No significant patterns observed recently."
        
        return f"# Relevant Long-Term Memory & Journal Entries:\n{memories}\n\n{header}\n{body}"

    def _record_suppression(self, insight: Dict, reason: str):
        """Buffers a suppressed insight for transparency audit."""
        key = f"{insight['engine_name']}:{insight['pattern_type']}:{insight['pattern_id']}"
        self.last_suppressed_insights[key] = {
            "insight": insight,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }

    def _filter_by_confidence(self, items: List[Dict], min_level: str = "medium") -> List[Dict]:
        ranks = {'low': 0, 'medium': 1, 'high': 2}
        min_val = ranks.get(min_level, 1)
        filtered = []
        for item in items:
            label = (item.get('confidence') or item.get('confidence_level') or 'low').lower()
            if ranks.get(label, 0) >= min_val:
                filtered.append(item)
        return filtered

    def _get_relevant_context(self, text: str, n_results: int = 5) -> str:
        logger.info("Retrieving relevant context from vector store...")
        try:
            query_embedding = generate_embedding(text)
            journal_results = vector_store.query(vector=query_embedding, n_results=n_results, source_type='journal_entry')
            context_parts = []
            if journal_results and journal_results.get('ids'):
                context_parts.append("Similar thoughts from your journal:")
                for j_id in journal_results['ids'][0]:
                    context_parts.append(f"- (Journal Entry ID: {j_id})")
            return "\n".join(context_parts) if context_parts else "No specific long-term memories found."
        except Exception as e:
            logger.error(f"Failed to retrieve context: {e}")
            return "Could not retrieve memories."

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Gets the full in-memory history for the current session."""
        return self.memory.get_full_history()
