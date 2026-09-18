"""Core Orchestrator

This module contains the main `PersonalAICompanion` class that ties together
all the different services (intelligence, memory, journal, etc.).
"""

import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

# Main services
from .conflict import ConflictSuppressionEngine
from .timeutils import utc_now
from .coverage import current_state_gate
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


#: How many of the latest entries the chat sees, and how much of each. Entries
#: now span years, so the prompt is told these are the latest few, not all.
RECENT_ENTRIES_IN_CONTEXT = 5
ENTRY_CHARS_IN_CONTEXT = 1500
MEMORY_CHARS_IN_CONTEXT = 300

_WORD = re.compile(r"[a-z0-9']+")


# Enough to unify the regular forms a person uses across entries — "sleeping"
# with "sleep", "worries" with "worry". Irregular pairs ("sleep"/"slept") are
# out of reach of any suffix rule, and are deliberately not faked: when nothing
# matches, the opening is returned and marked, rather than a guessed middle.
_SUFFIXES = ("ingly", "edly", "ing", "ies", "ed", "es", "ly", "s")


def _stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def _terms(text: str) -> set[str]:
    """Words long enough to carry meaning, lowercased and lightly stemmed."""
    return {_stem(w) for w in _WORD.findall(text.lower()) if len(w) > 3}


def _best_passage(text: str, query: str, limit: int = MEMORY_CHARS_IN_CONTEXT) -> str:
    """The part of an entry that matches what was asked, not its opening.

    An entry is retrieved because its embedding matched, and was then shown as
    its first 300 characters — so an entry found for what it says about sleep
    could arrive as its opening paragraph about work, and the sentence that
    actually matched never reached the model. 102 of the owner's 139 entries are
    longer than that cap.

    The choice is local and lexical: no second embedding call per entry, and the
    same entry and question always give the same passage. Ellipses mark that it
    was taken from inside a longer entry, so no passage reads as the whole of
    what was written.

    Lexical matching has a real limit: an irregular form ("slept" for "sleep")
    shares no stem, so the question and the sentence that answers it can miss
    each other. That case returns the opening — the same thing shown before this
    existed — rather than an arbitrary passage dressed up as the match.
    """
    words = " ".join((text or "").split())
    if len(words) <= limit:
        return words

    wanted = _terms(query or "")
    sentences = re.split(r"(?<=[.!?])\s+", words)

    best_score, best, best_span = -1, "", (0, 0)
    for i in range(len(sentences)):
        window, j = "", i
        while j < len(sentences) and len(window) + len(sentences[j]) + 1 <= limit:
            window = f"{window} {sentences[j]}".strip()
            j += 1
        if not window:  # a single sentence longer than the whole budget
            window, j = sentences[i][:limit].rstrip(), i + 1
        score = len(wanted & _terms(window))
        if score > best_score:
            best_score, best, best_span = score, window, (i, j)

    # Nothing in common: the opening is as honest a guess as any other part.
    if best_score <= 0:
        return words[:limit].rstrip() + " …"

    start, end = best_span
    return ("… " if start > 0 else "") + best + (" …" if end < len(sentences) else "")


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
        self.session_id = utc_now().strftime("%Y%m%d_%H%M%S")

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
        # Order 0: before anything else. A finding about the present is
        # withheld while nothing recent has been logged (agent/coverage.py).
        self.analysis_pipeline.register_gate('coverage', current_state_gate, order=0)
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

        # 2. Fetch Habits and Reflections context. Journal entries are
        # reflections (ADR-0010), so there is one builder, not two.
        habits_context = self._get_habits_context()
        reflections_context = self._get_reflections_context()

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
        body = self._format_pattern_body(narratives, suppression_log, prefs)

        # The model is told the date. Entries span years, and without it
        # "recently" or "last week" is a guess about when today is.
        today = datetime.now().astimezone()
        return (
            f"# Today: {today:%A, %Y-%m-%d}\n\n"
            f"# Relevant Long-Term Memory:\n{memories}\n\n"
            f"# Recent Journal Entries & Reflections (the {RECENT_ENTRIES_IN_CONTEXT} most recently written, newest first):\n{reflections_context}\n\n"
            f"# Current Habits & Streaks:\n{habits_context}\n\n"
            f"{header}\n{body}"
        )

    @staticmethod
    def _format_pattern_body(narratives: list[str], suppression_log: dict, prefs: dict) -> str:
        """Render the patterns block, distinguishing *nothing to say* from
        *something was filtered out*.

        This block used to read "No significant patterns observed recently."
        whenever it was empty — whether the engines had found nothing or the
        user's own confidence threshold had removed everything. Those are
        different facts and the model could not tell them apart, so it would
        tell someone nothing was happening when IRIS had observations their own
        setting had hidden. That became reachable the moment the gates were
        exposed in Settings.

        Only the user's own filters are reported. The budget cut and conflict
        suppression are the system's own limits, not a claim about what is true
        (ADR-0007), so mentioning them would invite IRIS to talk about its
        plumbing.
        """
        by_user = (
            len(suppression_log.get("low_confidence", []))
            + len(suppression_log.get("engine_disabled", []))
        )

        noun = "observation" if by_user == 1 else "observations"
        verb = "was" if by_user == 1 else "were"

        if narratives:
            body = "\n".join(f"- {n}" for n in narratives)
            if by_user:
                body += (
                    f"\n(Also: {by_user} further {noun} {verb} held back by the user's "
                    "own settings, so this list is not everything IRIS has.)"
                )
            return body

        if by_user:
            return (
                f"No observations passed the user's own filters: {by_user} {noun} {verb} "
                f"held back by their minimum-confidence setting "
                f"('{prefs.get('min_confidence')}') or by an engine they switched off. "
                "This is not the same as there being nothing to report — do not tell "
                "them nothing is happening."
            )

        return "No patterns observed yet — there is not enough logged history."

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
            reflections = db.get_latest_reflections(self.user_id, RECENT_ENTRIES_IN_CONTEXT)
            if not reflections:
                return "No journal entries yet."

            parts = []
            for r in reflections:
                # Only what was recorded. "Energy: N/A" on every imported entry
                # read as a value, and invited the model to reason about it.
                # Mood is left out: it is inferred from tags, and with no tags
                # it is "okay", so every imported entry claimed a mood nobody
                # gave it.
                recorded = []
                if r["energy_level"] is not None:
                    recorded.append(f"energy {r['energy_level']}/10")
                if r["clarity_level"] is not None:
                    recorded.append(f"clarity {r['clarity_level']}/10")
                meta = f" ({', '.join(recorded)})" if recorded else ""
                content = r["content"] or ""
                if len(content) > ENTRY_CHARS_IN_CONTEXT:
                    content = content[:ENTRY_CHARS_IN_CONTEXT].rstrip() + " …"
                # Every line indented, so a list inside an entry cannot pass for
                # the next entry.
                body = "\n".join(f"  {line}" for line in content.splitlines())
                parts.append(f"- [{r['reflection_date']:%Y-%m-%d}]{meta}\n{body}")
            return "\n".join(parts)
        except Exception as e:
            logger.error(f"Error fetching reflections context: {e}")
            return "Could not retrieve reflections context."

    def _record_suppression(self, insight: dict, reason: str):
        """Buffers a suppressed insight for transparency audit."""
        key = f"{insight['engine_name']}:{insight['pattern_type']}:{insight['pattern_id']}"
        self.last_suppressed_insights[key] = {
            "insight": insight,
            "reason": reason,
            "timestamp": utc_now().isoformat()
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
            # Over-fetch: entries already shown under Recent Journal Entries are
            # dropped here rather than repeated.
            results = db.search_similar_embeddings(
                user_id=self.user_id,
                query_vector=query_embedding,
                n_results=n_results + RECENT_ENTRIES_IN_CONTEXT,
            )
            if not results:
                return "No specific long-term memories found."

            shown = {r["id"] for r in db.get_latest_reflections(self.user_id, RECENT_ENTRIES_IN_CONTEXT)}
            context_parts = []
            for r in results:
                if r["source_type"] == "reflection" and r["source_id"] in shown:
                    continue
                item = db.get_memory_item(r["source_type"], r["source_id"])
                if not item:
                    continue
                when = f"{item['date']:%Y-%m-%d}" if item["date"] else "undated"
                words = _best_passage(item["text"], text, MEMORY_CHARS_IN_CONTEXT)
                context_parts.append(f"- [{item['kind']}, {when}] {words}")
                if len(context_parts) == n_results:
                    break

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
            # Brevity is asked for in the prompt above; the cap only has to
            # leave room for the answer after a reasoning model has thought.
            max_tokens=600
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
