"""
Resolution Engine - Tracks What Is Fading or Stabilizing

This module analyzes whether patterns (themes/tensions) are resolving.
It answers: "Has this pattern weakened, stabilized, or reappeared?"

The engine does not judge. It simply observes direction and consistency.
- Direction: dissipated, stabilized, persisting, reappearing
- Attenuation: numeric measure of weakening
- Confidence: based on data volume
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from .confidence import ConfidenceEngine
from .timeutils import to_utc, utc_now
from .constants import (
    RESOLUTION_BASELINE_DAYS,
    RESOLUTION_CACHE_TTL_HOURS,
    RESOLUTION_DELTA_EPSILON,
    RESOLUTION_MIN_DATA_POINTS,
    RESOLUTION_RECENT_DAYS,
)
from .database import confidence as confidence_repo

# Import database and constants
from .database import resolutions, themes
from .evidence import EvidenceEngine

logger = logging.getLogger(__name__)


class ResolutionEngine:
    """
    Tracks how patterns resolve over time.
    """
    def __init__(self, user_id: int):
        """Initialize the resolution engine for a user."""
        self.user_id = user_id
        self.conf_engine = ConfidenceEngine()
        self.ev_engine = EvidenceEngine()
        self._evidence = []

    @staticmethod
    def _cache_is_fresh(last_computed_at) -> bool:
        """A cached verdict is valid only for RESOLUTION_CACHE_TTL_HOURS.

        A null timestamp means explicitly invalidated. Any other value used to
        count as fresh indefinitely, which is wrong for a rolling window: the
        same data yields a different answer tomorrow, so a verdict that is never
        recomputed stops describing the present.
        """
        if last_computed_at is None:
            return False
        age = utc_now() - to_utc(last_computed_at)
        return age <= timedelta(hours=RESOLUTION_CACHE_TTL_HOURS)

    def emit_evidence(self, ev_type: str, key: str, value: Any):
        """Buffers evidence for later persistence."""
        self._evidence.append({"type": ev_type, "key": key, "value": value})

    def analyze_theme(self, theme_id: int, force_recompute: bool = False) -> dict:
        """
        Returns resolution metrics for a single theme.
        Uses cache if available and not stale.

        Args:
            theme_id: The theme to analyze
            force_recompute: If True, bypass cache

        Returns:
            Dictionary with resolution metrics and label
        """
        if not force_recompute:
            cached = resolutions.get_resolution('theme', theme_id)
            logger.debug(f"Cache lookup for theme {theme_id}: cached={cached is not None}")
            if cached:
                logger.debug(f"  Cached data: {cached}")
                logger.debug(f"  last_computed_at value: {cached.get('last_computed_at')}")
                logger.debug(f"  last_computed_at is not None: {cached.get('last_computed_at') is not None}")

            if cached and self._cache_is_fresh(cached.get('last_computed_at')):
                logger.debug(f"Resolution cache HIT for theme {theme_id}: label={cached.get('resolution_label')}")
                # Add theme summary for convenience
                theme = themes.get_theme(theme_id)
                cached['summary'] = theme['summary'] if theme else "Unknown"
                cached['theme_id'] = theme_id
                logger.debug(f"  Returning cached with theme_id={cached.get('theme_id')}, label={cached.get('resolution_label')}")
                return cached
            elif not cached:
                logger.debug(f"Resolution cache MISS for theme {theme_id}: no cached entry")
            else:
                logger.debug(f"Resolution cache STALE for theme {theme_id}: last_computed_at is {cached.get('last_computed_at')}")

        # Get all occurrences for this theme
        occurrences = themes.get_occurrences(theme_id)
        theme = themes.get_theme(theme_id)
        summary = theme["summary"] if theme else "Unknown"

        if not occurrences:
            return self._empty_result(theme_id, summary)

        # 1. Metric Calculation
        recent_start, baseline_end, baseline_start = self._get_time_windows()
        logger.debug(f"Time windows: recent_start={recent_start}, baseline_start={baseline_start}, baseline_end={baseline_end}")

        recent_count = 0
        past_count = 0
        timestamps = []

        for occ in occurrences:
            occ_at = occ["occurred_at"]
            dt_occ = to_utc(occ_at)

            timestamps.append(dt_occ)

            if dt_occ >= recent_start:
                recent_count += 1
            elif baseline_start <= dt_occ < baseline_end:
                past_count += 1

        logger.debug(f"Computed counts for theme {theme_id}: recent_count={recent_count}, past_count={past_count}, total_occurrences={len(occurrences)}")

        # Calculate rates
        recent_rate = recent_count / RESOLUTION_RECENT_DAYS
        past_rate = past_count / RESOLUTION_BASELINE_DAYS

        # Calculate attenuation score
        attenuation_score = self._calculate_attenuation_score(recent_rate, past_rate)

        # Check for gap (reappearance logic)
        gap_detected = self._get_gap_detected(timestamps, recent_start)

        # 2. Classification
        label = self._classify_resolution(past_count, recent_count, attenuation_score, gap_detected)

        # 3. Confidence using central engine
        self._evidence = [] # Clear buffer
        conf = self.conf_engine.compute_confidence('resolution', theme_id, timestamps)
        confidence = conf['confidence_level']

        # Emit evidence
        self.emit_evidence('count', 'recent_count', recent_count)
        self.emit_evidence('count', 'past_count', past_count)
        self.emit_evidence('delta', 'attenuation_score', attenuation_score)
        self.emit_evidence('rate', 'recent_rate', recent_rate)
        self.emit_evidence('rate', 'past_rate', past_rate)

        # Store in central registry
        confidence_repo.create_or_update(
            'resolution', theme_id,
            conf['confidence_level'], conf['confidence_score'],
            conf['data_points_count'], conf['time_coverage_days'],
            conf['consistency_score'], conf['recency_score']
        )

        # Record evidence bundle
        self.ev_engine.record_evidence('resolution', 'theme', theme_id, self._evidence)

        # Store in cache
        resolutions.create_or_update(
            pattern_type='theme',
            pattern_id=theme_id,
            resolution_label=label,
            attenuation_score=attenuation_score,
            confidence_level=confidence,
            recent_count=recent_count,
            past_count=past_count
        )

        result = {
            "theme_id": theme_id,
            "summary": summary,
            "resolution_label": label,
            "attenuation_score": attenuation_score,
            "confidence_level": confidence,
            "recent_count": recent_count,
            "past_count": past_count,
            "last_computed_at": utc_now()
        }
        logger.debug(f"ResolutionEngine.analyze_theme returning: theme_id={theme_id}, label={label}, result={result}")
        return result

    def analyze_all_themes(self) -> list[dict]:
        """Analyzes all themes for the current user."""
        all_themes = themes.get_all_themes(self.user_id)
        return [self.analyze_theme(t['id']) for t in all_themes]

    def format_for_context(self, max_items: int = 3) -> str:
        """
        Formats resolution insights for LLM context injection.
        Only includes high/medium confidence dissipated or reappearing patterns.
        """
        resolutions = self.analyze_all_themes()

        # Filter for high/medium confidence and interesting labels
        significant = [
            r for r in resolutions
            if r['confidence_level'] in ['high', 'medium']
            and r['resolution_label'] in ['dissipated', 'reappearing']
        ]

        if not significant:
            return ""

        significant = significant[:max_items]

        lines = ["# Observed Patterns:"]
        for res in significant:
            summary = res['summary']
            label = res['resolution_label']

            if label == 'dissipated':
                lines.append(f"- The theme '{summary}' appeared frequently in the past but has not appeared in the last {RESOLUTION_RECENT_DAYS} days.")
            elif label == 'reappearing':
                lines.append(f"- The theme '{summary}' has reappeared recently after a period of absence.")

        return "\n".join(lines)

    # --- Private Helpers ---

    def _get_time_windows(self) -> tuple[datetime, datetime, datetime]:
        """Calculates window boundaries for analysis."""
        now = utc_now()
        recent_start = now - timedelta(days=RESOLUTION_RECENT_DAYS)
        baseline_end = recent_start
        baseline_start = baseline_end - timedelta(days=RESOLUTION_BASELINE_DAYS)
        return recent_start, baseline_end, baseline_start

    def _calculate_attenuation_score(self, recent_rate: float, past_rate: float) -> float:
        """
        Score = 1 - (Recent Rate / Past Rate)
        1.0 = fully dissipated, 0.0 = stable, negative = strengthening
        """
        if past_rate == 0:
            return 0.0 if recent_rate == 0 else -1.0 # Strengthening if past was 0

        score = 1.0 - (recent_rate / past_rate)
        return max(-1.0, min(1.0, score)) # Safety clamp

    def _get_gap_detected(self, timestamps: list[datetime], recent_start: datetime) -> bool:
        """
        Gap Detected if there exists a silence at least as long as 
        RESOLUTION_RECENT_DAYS between baseline and recent activity.
        """
        if not timestamps:
            return False

        timestamps.sort()

        # Find the last occurrence before the recent window
        last_baseline_occ = None
        for ts in reversed(timestamps):
            if ts < recent_start:
                last_baseline_occ = ts
                break

        if last_baseline_occ is None:
            return False

        # Gap exists if last baseline occurrence was more than RESOLUTION_RECENT_DAYS before recent_start
        return last_baseline_occ <= (recent_start - timedelta(days=RESOLUTION_RECENT_DAYS))

    def _classify_resolution(self, past_count: int, recent_count: int,
                            attenuation_score: float, gap_detected: bool) -> str:
        """Prioritized classification logic."""
        # 1. Dissipated: Was there, now gone
        if past_count >= RESOLUTION_MIN_DATA_POINTS and recent_count == 0:
            return 'dissipated'

        # 2. Reappearing: Was there, gone for a bit, now back
        if past_count >= RESOLUTION_MIN_DATA_POINTS and recent_count > 0 and gap_detected:
            return 'reappearing'

        # 3. Stabilized: Little change in rate
        if abs(attenuation_score) <= RESOLUTION_DELTA_EPSILON:
            return 'stabilized'

        # 4. Persisting: Fallback
        return 'persisting'

    def _calculate_confidence(self, total_points: int) -> str:
        """Confidence based on data volume."""
        if total_points >= 2 * RESOLUTION_MIN_DATA_POINTS:
            return 'high'
        elif total_points >= RESOLUTION_MIN_DATA_POINTS:
            return 'medium'
        return 'low'

    def _empty_result(self, theme_id: int, summary: str) -> dict:
        """Standard empty result for themes with no data."""
        return {
            "theme_id": theme_id,
            "summary": summary,
            "resolution_label": "persisting",
            "attenuation_score": 0.0,
            "confidence_level": "low",
            "recent_count": 0,
            "past_count": 0,
            "last_computed_at": utc_now()
        }
