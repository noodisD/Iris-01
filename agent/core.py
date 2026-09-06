"""Core Orchestrator

This module contains the main `PersonalAICompanion` class that ties together
all the different services (intelligence, memory, journal, etc.).
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Main services
from .conflict import ConflictSuppressionEngine
from .constants import DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE
from .database import (
    db,
    decision_impacts,
    habits,
    journals,
    leverage,
)
from .intelligence import Intelligence
from .journal_entry import JournalEntry
from .memory import ConversationMemory
from .narrative import NarrativeFormatter
from .persistence import PersistenceEngine

# New architecture components
from .pipeline import generate_embedding
from .pipeline_orchestrator import AnalysisPipeline, confidence_gate, engine_enablement_gate
from .preferences import UserPreferencesService
from .preferences_guard import PreferencesGuard
from .prioritization import InsightPrioritizationEngine
from .resolution import ResolutionEngine
from .tension import TensionEngine
from .trajectory import TrajectoryEngine

# Handle both package and direct imports
try:
    from prompts.system_prompt import SYSTEM_PROMPT
except (ImportError, ValueError):
    from prompts.system_prompt import SYSTEM_PROMPT


class PersonalAICompanion:
    """The core AI companion, orchestrating all services."""

    def __init__(self, user_id: int, model: str = None):
        """
        Initialize the companion for a specific user.

        `model` defaults to settings.OPENAI_MODEL. It used to be hardcoded here,
        in persistence and in the review endpoint — three different values —
        so the OPENAI_MODEL setting was read by nothing.
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

        # Initialize preferences guard for validation
        prefs = self.pref_service.get_prefs()
        self.prefs_guard = PreferencesGuard(user_id=self.user_id, prefs_dict=prefs)

        # Session-scoped cache for transparency
        self.last_suppressed_insights = {}

        # Initialize analysis pipeline
        self._init_analysis_pipeline()

        logger.info(f"PersonalAICompanion initialized for user {self.user_id} and session {self.session_id}")

    def _init_analysis_pipeline(self) -> None:
        """Initialize and configure the analysis pipeline with all engines."""
        self.analysis_pipeline = AnalysisPipeline(self.user_id)

        # Register analytical engines
        self.analysis_pipeline.register_engine(
            'persistence',
            lambda: PersistenceEngine(self.user_id).get_persistent_themes()
        )

        self.analysis_pipeline.register_engine(
            'trajectory',
            lambda: TrajectoryEngine(self.user_id).analyze_all_themes()
        )

        self.analysis_pipeline.register_engine(
            'tension',
            lambda: TensionEngine(self.user_id).analyze_all_tensions()
        )

        self.analysis_pipeline.register_engine(
            'resolution',
            lambda: ResolutionEngine(self.user_id).analyze_all_themes()
        )

        self.analysis_pipeline.register_engine(
            'leverage',
            lambda: leverage.get_high_leverage_sources(self.user_id, min_confidence='low')
        )

        self.analysis_pipeline.register_engine(
            'decision_impact',
            lambda: decision_impacts.get_significant_impacts(self.user_id, min_confidence='low')
        )

        # Register gates in order. Budget is deliberately NOT registered here:
        # budget_gate truncates to max_items and its own docstring says it
        # "assumes insights are already ranked by priority", but this pipeline
        # runs before conflict suppression and prioritisation. Registering it
        # here cut the list down in engine-registration order, so whenever
        # persistence and trajectory produced max_items insights between them,
        # resolution — the highest-weighted engine at 1.0 — never reached the
        # ranking step at all. The single budget slice now happens in
        # _get_aggregated_context, after ranking, matching CONTEXT.md's
        # documented order: enablement -> confidence -> conflict ->
        # prioritisation -> budget.
        self.analysis_pipeline.register_gate('enablement', engine_enablement_gate, order=1)
        self.analysis_pipeline.register_gate('confidence', confidence_gate, order=2)

    def shutdown(self):
        """Gracefully closes all backing service connections."""
        logger.info("Shutting down IRIS core services...")
        try:
            db.close_connection()
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
        short_term_context = self.memory.get_context(max_messages=20)

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

        # 2. Fetch Habits, Reflections, and recent Journal context
        habits_context = self._get_habits_context()
        reflections_context = self._get_reflections_context()
        journal_context = self._get_recent_journal_entries_context()

        # 3. Run analysis pipeline with enablement and confidence gates
        gated_insights = self.analysis_pipeline.run(prefs=prefs)

        logger.debug(f"After pipeline.run(): {len(gated_insights)} gated insights")
        for gi in gated_insights:
            logger.debug(f"  - engine={gi.get('engine_name')}, resolution_label={gi.get('resolution_label')}, theme_id={gi.get('theme_id')}")

        # Track suppressions from pipeline
        suppression_log = self.analysis_pipeline.get_suppression_log()
        for reason, items in suppression_log.items():
            for item_str in items:
                self.last_suppressed_insights[item_str] = reason

        # 4. Conflict Suppression (custom logic)
        suppression_result = self.conflict_engine.suppress(gated_insights)
        clean_insights = suppression_result['visible']

        logger.debug(f"After conflict_engine.suppress(): {len(clean_insights)} clean insights")
        for ci in clean_insights:
            logger.debug(f"  - engine={ci.get('engine_name')}, resolution_label={ci.get('resolution_label')}, theme_id={ci.get('theme_id')}")
        for s in suppression_result['suppressed']:
            self._record_suppression(s['insight'], "conflict")

        # 5. Prioritization & Final Ranking
        priority_engine = InsightPrioritizationEngine(self.user_id)
        ranked_insights = priority_engine.rank_insights(clean_insights)

        # Budget slice (User Overridden)
        top_k = min(prefs['max_items'], len(ranked_insights))
        final_insights = ranked_insights[:top_k]

        # Track Budget suppressions
        for i in ranked_insights[top_k:]:
            self._record_suppression(i, "priority_cutoff")

        # 6. Narrative Formatting
        narratives = NarrativeFormatter.format_all(final_insights)

        # 7. Final Assembly
        header = "# Observed Structural Patterns & Observed Temporal Sequences:"
        # Ensure bulleted list
        bulleted_narratives = [f"- {n}" for n in narratives]
        body = "\n".join(bulleted_narratives) if narratives else "No significant patterns observed recently."

        return f"# Recent Journal Entries:\n{journal_context}\n\n# Relevant Long-Term Memory:\n{memories}\n\n# Recent Reflections:\n{reflections_context}\n\n# Current Habits & Streaks:\n{habits_context}\n\n{header}\n{body}"

    def _get_habits_context(self) -> str:
        """Retrieves habit data for context."""
        try:
            habits_list = habits.get_habits(self.user_id, active_only=True)
            if not habits_list:
                return "No active habits tracked yet."

            parts = []
            for h in habits_list:
                parts.append(f"- {h['name']}: {h['current_streak']} day streak ({h['total_completions']} total completions)")
            return "\n".join(parts)
        except Exception as e:
            logger.error(f"Error fetching habits context: {e}")
            return "Could not retrieve habits context."

    def _get_reflections_context(self) -> str:
        """Retrieves recent reflections for context."""
        try:
            reflections = journals.get_reflections(self.user_id, limit=5)
            if not reflections:
                return "No recent reflections found."

            parts = []
            for r in reflections:
                date_str = r['reflection_date'].strftime("%Y-%m-%d") if hasattr(r['reflection_date'], 'strftime') else str(r['reflection_date'])
                parts.append(f"- [{date_str}] Mood: {r['mood'] or 'N/A'}, Energy: {r['energy_level'] or 'N/A'}\n  Content: {r['content']}")
            return "\n".join(parts)
        except Exception as e:
            logger.error(f"Error fetching reflections context: {e}")
            return "Could not retrieve reflections context."

    def _get_recent_journal_entries_context(self, limit: int = 3, max_chars: int = 1200) -> str:
        """Retrieves the most recent journal entries so meta-queries about 'my journal'
        can surface them even when vector search misses on wording."""
        try:
            entries = journals.get_recent_entries(self.user_id, limit=limit)
            if not entries:
                return "No journal entries yet."

            parts = []
            for e in entries:
                date_str = e['created_at'].strftime("%Y-%m-%d") if hasattr(e['created_at'], 'strftime') else str(e['created_at'])
                wb = e.get('wellbeing_data') or {}
                wb_bits = [f"{k}: {v}" for k, v in wb.items() if v not in (None, "")]
                wb_line = f" ({', '.join(wb_bits)})" if wb_bits else ""
                text = (e['raw_text'] or "").strip()
                if len(text) > max_chars:
                    text = text[:max_chars].rstrip() + "..."
                parts.append(f"- [{date_str}]{wb_line}\n  {text}")
            return "\n".join(parts)
        except Exception as e:
            logger.error(f"Error fetching recent journal entries context: {e}")
            return "Could not retrieve recent journal entries."

    def _record_suppression(self, insight: dict, reason: str):
        """Buffers a suppressed insight for transparency audit."""
        key = f"{insight['engine_name']}:{insight['pattern_type']}:{insight['pattern_id']}"
        self.last_suppressed_insights[key] = {
            "insight": insight,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }

    def _filter_by_confidence(self, items: list[dict], min_level: str = "medium") -> list[dict]:
        ranks = {'low': 0, 'medium': 1, 'high': 2}
        min_val = ranks.get(min_level, 1)
        filtered = []
        for item in items:
            label = (item.get('confidence') or item.get('confidence_level') or 'low').lower()
            if ranks.get(label, 0) >= min_val:
                filtered.append(item)
        return filtered

    def _get_relevant_context(self, text: str, n_results: int = 5) -> str:
        logger.info("Retrieving relevant context using pgvector...")
        try:
            query_embedding = generate_embedding(text)
            results = db.search_similar_embeddings(
                user_id=self.user_id,
                query_vector=query_embedding,
                n_results=n_results
            )

            if not results:
                return "No specific long-term memories found."

            context_parts = []
            for r in results:
                content = db.get_content_for_source(r['source_type'], r['source_id'])
                if content:
                    relevance = 1.0 - r['distance']
                    context_parts.append(f"- [{r['source_type']}] (relevance: {relevance:.0%}) {content[:300]}")

            if not context_parts:
                return "No specific long-term memories found."

            return "\n".join(context_parts)
        except Exception as e:
            logger.error(f"Failed to retrieve context: {e}")
            return "Could not retrieve memories."

    def get_conversation_history(self) -> list[dict[str, str]]:
        """Gets the full in-memory history for the current session."""
        return self.memory.get_full_history()

    def generate_initial_greeting(self) -> str:
        """
        Generates a dynamic initial greeting when the user starts a session.
        Distinguishes between first-time welcome and returning greeting.
        """
        # 1. Check if user is brand new (no messages in DB)
        # We check conversation_messages table via db
        history = journals.get_chat_history(self.user_id) # I'll assume this method or similar exists
        # If history is a list of messages
        is_new_user = len(history) == 0

        # 2. Fetch recent context
        aggregated_context = self._get_aggregated_context("Initial session greeting")

        if is_new_user:
            prompt_hint = "The user has just signed up and opened the chat for the first time. Generate a warm, welcoming introduction as Iris. Explain briefly that you are a companion who helps notice patterns in their habits and reflections. Keep it very short (2 sentences)."
        else:
            prompt_hint = "The user is returning for a new session. Generate a warm, very short (1-2 sentences) greeting. If there are interesting recent patterns or reflections in the context, mention them casually. If not, just a warm welcome back."

        system_prompt = f"{SYSTEM_PROMPT}\n\n{aggregated_context}\n\nIMPORTANT: You are just saying hello. Keep it extremely natural and brief."
        messages = [{"role": "user", "content": f"[SYSTEM TRIGGER: {prompt_hint}]"}]

        response_text = self.intelligence.chat(
            messages=messages,
            system_prompt=system_prompt,
            temperature=DEFAULT_TEMPERATURE,
            max_tokens=100
        )

        return response_text

    def generate_proactive_comment(self, action_type: str, details: dict) -> str:
        """
        Generates a proactive comment based on a user action.
        Does not require a user message to trigger.
        """
        if action_type == "reflection":
            prompt_hint = f"The user just shared a reflection: \"{details.get('content')}\". It's marked with mood '{details.get('mood')}' and energy {details.get('energy_level')}. Start a conversation by offering a brief, empathetic observation or a gentle follow-up question."
        elif action_type == "habit_skip":
            prompt_hint = f"The user just skipped their habit '{details.get('habit_name')}' with reason: \"{details.get('reason') or 'No reason provided'}\". Offer a supportive, non-judgmental comment to help them stay encouraged."
        elif action_type == "habit_complete":
            prompt_hint = f"The user just completed their habit '{details.get('habit_name')}'. Give a quick, warm word of encouragement or acknowledge their consistency."
        else:
            prompt_hint = "The user is checking in. Greet them and offer a brief insight based on their recent patterns."

        # Build context
        aggregated_context = self._get_aggregated_context(prompt_hint)

        system_prompt = f"{SYSTEM_PROMPT}\n\n{aggregated_context}\n\nIMPORTANT: You are initiating this thought yourself based on what you just noticed. Keep it short (1-3 sentences) and very human."

        # We use a hidden system prompt to guide the "start" of the conversation
        messages = [{"role": "user", "content": f"[SYSTEM TRIGGER: {prompt_hint}]"}]

        response_text = self.intelligence.chat(
            messages=messages,
            system_prompt=system_prompt,
            temperature=DEFAULT_TEMPERATURE,
            max_tokens=DEFAULT_MAX_TOKENS
        )

        # Record IRIS's comment in memory so the conversation can continue
        self.memory.add_message("assistant", response_text)
        return response_text
