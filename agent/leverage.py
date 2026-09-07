"""
Leverage Engine - Tracks What Disproportionately Influences Others

This module analyzes directional influence between patterns using temporal asymmetry.
It answers: "Which patterns tend to act as upstream drivers for others?"

The engine does not judge. It simply observes co-occurrence asymmetry and temporal precedence.
- Directional Lift: P(B|A) - P(A|B)
- Asymmetry: captures which pattern tends to move first
- Network Language: focuses on structural position, not human meaning
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from .confidence import ConfidenceEngine
from .timeutils import to_utc, utc_now
from .constants import (
    LEVERAGE_ASYMMETRY_THRESHOLD,
    LEVERAGE_MIN_CO_OCCURRENCES,
    LEVERAGE_MIN_OCCURRENCES,
    LEVERAGE_TIME_LAG_DAYS,
    LEVERAGE_WINDOW_DAYS,
)
from .database import leverage as leverage_repo

# Import database and constants
from .database import themes
from .evidence import EvidenceEngine

logger = logging.getLogger(__name__)


class LeverageEngine:
    """
    Tracks directional influence between patterns.
    """
    def __init__(self, user_id: int):
        """Initialize the leverage engine for a user."""
        self.user_id = user_id
        self.conf_engine = ConfidenceEngine()
        self.ev_engine = EvidenceEngine()
        self._evidence = []

    def emit_evidence(self, ev_type: str, key: str, value: Any):
        """Buffers evidence for later persistence."""
        self._evidence.append({"type": ev_type, "key": key, "value": value})

    def analyze_all_leverage(self, force_recompute: bool = False) -> list[dict]:
        """
        Performs a global scan for leverage relationships among recent/active themes.
        """
        # 1. Get active themes (O(N) filter)
        active_themes = self._get_active_themes()
        if len(active_themes) < 2:
            return []

        results = []
        # 2. Pairwise scan (O(N^2))
        for source in active_themes:
            for target in active_themes:
                if source['id'] == target['id']:
                    continue

                result = self.analyze_pair('theme', source['id'], 'theme', target['id'])
                if result and result['influence_score'] >= LEVERAGE_ASYMMETRY_THRESHOLD:
                    result['source_summary'] = source['summary']
                    result['target_summary'] = target['summary']
                    # NarrativeFormatter reads `summary` for the pattern name.
                    result['summary'] = source['summary']
                    results.append(result)

        return results

    def analyze_pair(self, source_type: str, source_id: int,
                    target_type: str, target_id: int) -> dict | None:
        """
        Calculates directional lift and influence for a specific pair.
        """
        # 1. Gather occurrences within window
        recent_start = utc_now() - timedelta(days=LEVERAGE_WINDOW_DAYS)

        source_occs = self._get_occurrences(source_type, source_id, recent_start)
        target_occs = self._get_occurrences(target_type, target_id, recent_start)

        if len(source_occs) < LEVERAGE_MIN_OCCURRENCES or len(target_occs) < LEVERAGE_MIN_OCCURRENCES:
            return None

        # 2. Window scan for directional evidence
        # Count *events*, not pairs. This used to increment per matching
        # (source, target) pair and then divide by the number of source events,
        # so one source followed by three targets contributed 3 to the numerator
        # and 1 to the denominator — a "conditional probability" above 1, and the
        # denser the target theme the more inflated the association looked.
        # P(target | source) is: of the times this theme occurred, how often was
        # it followed by the other within the lag.
        lag = timedelta(days=LEVERAGE_TIME_LAG_DAYS)

        def _follows(earlier, later_times):
            # Compared as a duration, not via timedelta.days: truncation made a
            # gap of eight days minus a microsecond register as seven, so a pair
            # just outside the window counted as inside it.
            return any(timedelta(0) < (later - earlier) <= lag for later in later_times)

        forward_count = sum(1 for s_at in source_occs if _follows(s_at, target_occs))
        backward_count = sum(1 for t_at in target_occs if _follows(t_at, source_occs))
        simultaneous_count = sum(
            1 for s_at in source_occs
            if any(self._is_simultaneous(s_at, t_at) for t_at in target_occs)
        )

        total_cooccurrence = forward_count + backward_count + simultaneous_count
        if total_cooccurrence < LEVERAGE_MIN_CO_OCCURRENCES:
            return None

        # 3. Directional lift: both terms are now genuine probabilities in
        # [0, 1], so the difference lies in [-1, 1].
        p_b_given_a = forward_count / len(source_occs)
        p_a_given_b = backward_count / len(target_occs)

        lift = p_b_given_a - p_a_given_b
        influence_score = max(0.0, min(1.0, lift))

        # 4. Confidence level using central engine
        # For leverage, the 'timestamps' are the co-occurrences
        # Confidence in a *relation* has to come from the relation's own
        # evidence. This used to call compute_confidence with only the source's
        # occurrences, so the answer did not depend on the target at all: a
        # reliable relation and a coincidental one scored identically, because
        # both were really measuring how much data the source theme had.
        # _calculate_confidence weighs the co-occurrences against both sides and
        # was already written here, unused.
        self._evidence = []  # Clear buffer
        confidence = self._calculate_confidence(
            total_cooccurrence, len(source_occs), len(target_occs)
        )

        # Emit evidence, including the target: a bundle has to say which pair it
        # describes, since it is stored under the source alone.
        self.emit_evidence('count', 'target_id', target_id)
        self.emit_evidence('count', 'forward_count', forward_count)
        self.emit_evidence('count', 'backward_count', backward_count)
        self.emit_evidence('count', 'simultaneous_count', simultaneous_count)
        self.emit_evidence('delta', 'directional_lift', lift)
        self.emit_evidence('rate', 'p_target_given_source', p_b_given_a)

        # Deliberately not written to pattern_confidence: that registry is keyed
        # by (pattern_type, pattern_id), which cannot express a pair, so every
        # target of the same source overwrote the last. The pair's confidence
        # belongs on the pair row below, which is uniquely keyed by both ends.

        # Store in evidence registry
        # The bundle names the relation it describes. Stored under the source
        # alone, one source's two targets shared a key and the bundle returned
        # for a pair could be another pair's.
        self.ev_engine.record_evidence(
            'leverage', 'theme', source_id, self._evidence,
            related_pattern_id=target_id,
        )

        # 5. Store in DB
        leverage_repo.create_or_update_pair(
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            influence_score=float(influence_score),
            directional_lift=float(lift),
            cooccurrence_count=total_cooccurrence,
            confidence_level=confidence
        )

        return {
            "source_id": source_id,
            "target_id": target_id,
            "influence_score": influence_score,
            "directional_lift": lift,
            "cooccurrence_count": total_cooccurrence,
            "confidence_level": confidence
        }

    def format_for_context(self, max_items: int = 3) -> str:
        """
        Formats top high-leverage patterns for LLM context injection.
        """
        from .resolution import ResolutionEngine
        res_engine = ResolutionEngine(self.user_id)
        resolutions = {r['theme_id']: r for r in res_engine.analyze_all_themes()}

        sources = leverage_repo.get_high_leverage_sources(self.user_id, min_confidence='medium')

        filtered_sources = []
        for s in sources:
            res = resolutions.get(s['source_id'])
            if res and res['resolution_label'] == 'dissipated' and res['confidence_level'] == 'high':
                continue
            filtered_sources.append(s)

        if not filtered_sources:
            return ""

        filtered_sources = filtered_sources[:max_items]

        lines = ["# Observed Structural Drivers:"]
        for s in filtered_sources:
            summary = s['summary']
            lines.append(f"- Pattern '{summary}' frequently precedes several other patterns in your recent history.")

        return "\n".join(lines)

    # --- Private Helpers ---

    def _get_active_themes(self) -> list[dict]:
        """Returns themes active in the leverage window with enough data."""
        all_themes = themes.get_all_themes(self.user_id)
        active = [t for t in all_themes if t['occurrence_count'] >= LEVERAGE_MIN_OCCURRENCES]

        recent_start = utc_now() - timedelta(days=LEVERAGE_WINDOW_DAYS)
        refined = []
        for t in active:
            occs = self._get_occurrences('theme', t['id'], recent_start)
            if len(occs) >= LEVERAGE_MIN_OCCURRENCES:
                t['recent_occs_count'] = len(occs)
                refined.append(t)

        return refined

    def _get_occurrences(self, p_type: str, p_id: int, since: datetime) -> list[datetime]:
        """Fetches timestamps for a pattern within a window."""
        if p_type == 'theme':
            occs = themes.get_occurrences(p_id)
        else:
            return []

        times = []
        for o in occs:
            dt = to_utc(o['occurred_at'])

            if dt >= since:
                times.append(dt)
        return sorted(times)

    def _is_simultaneous(self, dt1: datetime, dt2: datetime) -> bool:
        """Checks if two occurrences are same-day (neutral for leverage)."""
        return dt1.date() == dt2.date()

    def _calculate_confidence(self, co_count: int, s_total: int, t_total: int) -> str:
        """Determines confidence based on evidence volume."""
        if co_count >= 10 and min(s_total, t_total) >= 10:
            return 'high'
        if co_count >= LEVERAGE_MIN_CO_OCCURRENCES:
            return 'medium'
        return 'low'
