"""
Trajectory Engine - Tracks What Is Changing Over Time

This module analyzes how themes change over time.
It answers: "Is this theme increasing, decreasing, or stable?"

The engine does not judge. It simply observes direction, rate, and recency.
- Direction: increasing, decreasing, stable, emerging, fading
- Rate: trend slope and frequency changes
- Recency: when did it last change materially
"""

import logging
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from .confidence import ConfidenceEngine
from .timeutils import to_utc, utc_now
from .constants import (
    EVIDENCE_WEIGHTS,
    TRAJECTORY_BASELINE_DAYS,
    TRAJECTORY_DELTA_THRESHOLD,
    TRAJECTORY_MIN_DATA_POINTS,
    TRAJECTORY_RECENT_DAYS,
)
from .database import confidence as confidence_repo

# Import database and constants
from .database import themes
from .evidence import EvidenceEngine

logger = logging.getLogger(__name__)


class TrajectoryEngine:
    """
    Tracks how themes change over time.
    """
    def __init__(self, user_id: int):
        """Initialize the trajectory engine for a user."""
        self.user_id = user_id
        self.conf_engine = ConfidenceEngine()
        self.ev_engine = EvidenceEngine()
        self._evidence = []

    def emit_evidence(self, ev_type: str, key: str, value: Any):
        """Buffers evidence for later persistence."""
        self._evidence.append({"type": ev_type, "key": key, "value": value})

    def analyze_theme(self, theme_id: int) -> dict:
        """
        Returns raw metrics + trajectory label for a single theme.

        Args:
            theme_id: The theme to analyze

        Returns:
            Dictionary with trajectory metrics and classification
        """
        # Get all occurrences for this theme
        occurrences = themes.get_occurrences(theme_id)

        # Get theme summary
        theme = themes.get_theme(theme_id)
        theme_summary = theme["summary"] if theme else "Unknown theme"

        if not occurrences:
            return {
                "theme_id": theme_id,
                "trajectory_label": "insufficient data",
                "trend_score": 0.0,
                "recent_count": 0,
                "past_count": 0,
                "frequency_delta": 0.0,
                "confidence_level": "low",
                "data_points_count": 0,
                "theme_summary": theme_summary,
                "evidence": []
            }

        # Calculate time windows
        recent_window_start = utc_now() - timedelta(days=TRAJECTORY_RECENT_DAYS)
        baseline_window_end = recent_window_start
        baseline_window_start = baseline_window_end - timedelta(days=TRAJECTORY_BASELINE_DAYS)

        # Separate occurrences by time window
        recent_occurrences = []
        past_occurrences = []

        for occ in occurrences:
            occurred_at = occ["occurred_at"]
            if isinstance(occurred_at, datetime):
                # If it's already a datetime object, use it directly
                dt_occurred = occurred_at
            else:
                # If it's a string, parse it
                dt_occurred = to_utc(occurred_at)

            if dt_occurred >= recent_window_start:
                recent_occurrences.append(occ)
            elif baseline_window_start <= dt_occurred < baseline_window_end:
                past_occurrences.append(occ)

        # Calculate metrics
        recent_rate = len(recent_occurrences) / TRAJECTORY_RECENT_DAYS if TRAJECTORY_RECENT_DAYS > 0 else 0
        past_rate = len(past_occurrences) / TRAJECTORY_BASELINE_DAYS if TRAJECTORY_BASELINE_DAYS > 0 else 0
        frequency_delta = recent_rate - past_rate

        # Calculate trend slope
        trend_slope = self._calculate_trend_slope(occurrences)

        # Determine trajectory label
        trajectory_label = self._classify_trajectory(
            len(occurrences),
            frequency_delta,
            trend_slope,
            occurrences
        )

        # Calculate confidence using the central engine
        self._evidence = [] # Clear buffer
        timestamps = []
        source_types = []
        for o in occurrences:
            dt = o['occurred_at']
            if not isinstance(dt, datetime):
                dt = datetime.fromisoformat(str(dt))
            timestamps.append(dt)

            # Extract source type for evidence tiering
            st = o['source_type']
            snippet = o.get('snippet', '')
            if st == 'habit_completion' and ("Notes:" in snippet or "Reason:" in snippet):
                source_types.append('habit_completion_with_notes')
            else:
                source_types.append(st)

        # We consider the trajectory label itself as the 'direction' for consistency check
        # Improved: Pass source_types for evidence tiering
        conf = self.conf_engine.compute_confidence('trajectory', theme_id, timestamps, sources=source_types)
        confidence_level = conf['confidence_level']

        # Emit evidence
        self.emit_evidence('rate', 'recent_count', len(recent_occurrences))
        self.emit_evidence('rate', 'past_count', len(past_occurrences))
        self.emit_evidence('delta', 'trend_score', trend_slope)
        self.emit_evidence('count', 'total_occurrences', len(occurrences))

        # Store in central registry
        confidence_repo.create_or_update(
            'trajectory', theme_id,
            conf['confidence_level'], conf['confidence_score'],
            conf['data_points_count'], conf['time_coverage_days'],
            conf['consistency_score'], conf['recency_score']
        )

        # Store in evidence registry
        self.ev_engine.record_evidence('trajectory', 'theme', theme_id, self._evidence)

        # theme_trajectories is deliberately not written. Nothing read it —
        # analyze_theme always recomputes, and no other caller exists — so every
        # analysis paid for a write whose result was never used, while the
        # table's presence implied a caching model the engine did not have. The
        # rule now is: cache only where there is a reader, and never without an
        # expiry. Resolution keeps its cache (it is read, and now expires);
        # trajectory has none. The empty table stays until there is a migration
        # tool to drop it.

        return {
            "theme_id": theme_id,
            "trajectory_label": trajectory_label,
            "trend_score": trend_slope,
            "recent_count": len(recent_occurrences),
            "past_count": len(past_occurrences),
            "frequency_delta": frequency_delta,
            "confidence_level": confidence_level,
            "data_points_count": len(occurrences),
            "theme_summary": theme_summary,
            "evidence": occurrences[:5]  # Sample evidence
        }

    def analyze_all_themes(self) -> list:
        """
        Returns trajectory info for all persistent themes.
        
        Returns:
            List of trajectory analysis for all themes
        """
        # Get all themes for this user
        all_themes = themes.get_all_themes(self.user_id)
        results = []

        for theme in all_themes:
            analysis = self.analyze_theme(theme["id"])
            analysis["theme_summary"] = theme["summary"]
            results.append(analysis)

        return results

    def get_significant_changes(self) -> list:
        """
        Returns themes that are increasing, emerging, or fading.
        
        Returns:
            List of themes with significant trajectory changes
        """
        all_analysis = self.analyze_all_themes()

        significant = []
        for analysis in all_analysis:
            if analysis["trajectory_label"] in ["increasing", "emerging", "fading"]:
                significant.append(analysis)

        # Sort by significance (magnitude of trend score)
        significant.sort(key=lambda x: abs(x["trend_score"]), reverse=True)
        return significant

    #: Occurrences are bucketed this wide before the rate is regressed. A week
    #: is the natural cadence for habits and reflections.
    TREND_BIN_DAYS = 7

    def _calculate_trend_slope(self, occurrences: list[dict]) -> float:
        """Slope of the occurrence *rate*, as a relative change per week.

        This used to regress cumulative count against time. A cumulative count
        only ever rises, so the slope was positive for every real series — a
        constant cadence of one entry a day scored +1.0 — and since the
        classifier falls through to the slope precisely when the recent
        frequency matches the baseline, "stable" was unreachable and steady
        patterns were reported as increasing.

        Binning by week and regressing the weighted count per week measures
        whether the rate itself is changing. Dividing by the mean weekly weight
        makes the result a fraction of the usual rate, so a threshold means the
        same thing for a daily habit and a monthly one.

        Returns 0.0 when the history is too short to span two buckets: no
        direction can honestly be claimed from a single week.
        """
        if len(occurrences) < 2:
            return 0.0

        # Evidence tiering: a reflection counts for more than a bare habit tick.
        weighted = []
        for occ in occurrences:
            occurred_at = to_utc(occ["occurred_at"])
            source_type = occ.get("source_type")
            snippet = occ.get("snippet", "") or ""
            if source_type == "habit_completion" and ("Notes:" in snippet or "Reason:" in snippet):
                weight = EVIDENCE_WEIGHTS.get("habit_completion_with_notes", 0.8)
            else:
                weight = EVIDENCE_WEIGHTS.get(source_type, 0.5)
            weighted.append((occurred_at, weight))

        weighted.sort(key=lambda pair: pair[0])
        first = weighted[0][0]

        # Sum the evidence falling in each week, including the empty weeks —
        # a gap is a fall in rate and has to be represented as one.
        bin_totals: dict[int, float] = {}
        for occurred_at, weight in weighted:
            index = (occurred_at - first).days // self.TREND_BIN_DAYS
            bin_totals[index] = bin_totals.get(index, 0.0) + weight

        last_index = max(bin_totals)
        if last_index < 1:
            return 0.0

        x_values = np.arange(last_index + 1, dtype=float)
        y_values = np.array([bin_totals.get(i, 0.0) for i in range(last_index + 1)], dtype=float)

        mean_rate = float(y_values.mean())
        if mean_rate <= 0:
            return 0.0

        try:
            design = np.vstack([x_values, np.ones_like(x_values)]).T
            slope, _ = np.linalg.lstsq(design, y_values, rcond=None)[0]
        except np.linalg.LinAlgError:
            return 0.0

        return float(slope) / mean_rate

    def _classify_trajectory(self, total_occurrences: int, frequency_delta: float,
                           trend_slope: float, occurrences: list[dict]) -> str:
        """
        Classify the trajectory based on calculated metrics.
        
        Args:
            total_occurrences: Total number of occurrences
            frequency_delta: Difference in frequency between recent and past
            trend_slope: Slope of trend line
            occurrences: List of occurrences for additional analysis
            
        Returns:
            Trajectory classification label: 'emerging', 'increasing', 'stable', 'fading', 'insufficient data'
        """
        if total_occurrences < TRAJECTORY_MIN_DATA_POINTS:
            return "insufficient data"

        # Check if theme is new/emerging
        if occurrences:
            timestamps = []
            for occ in occurrences:
                occurred_at = occ["occurred_at"]
                if isinstance(occurred_at, datetime):
                    # If it's already a datetime object, use it directly
                    dt_occurred = occurred_at
                else:
                    # If it's a string, parse it
                    dt_occurred = to_utc(occurred_at)

                timestamps.append(dt_occurred)

            timestamps.sort()
            first_occurrence = timestamps[0]
            days_since_first = (utc_now() - first_occurrence).days

            # If first occurrence was in last 30 days and has recent activity, it's emerging
            recent_activity = False
            for occ in occurrences:
                occurred_at = occ["occurred_at"]
                if isinstance(occurred_at, datetime):
                    dt_occurred = occurred_at
                else:
                    dt_occurred = to_utc(occurred_at)

                if dt_occurred >= utc_now() - timedelta(days=TRAJECTORY_RECENT_DAYS):
                    recent_activity = True
                    break

            if days_since_first < 30 and recent_activity:
                return "emerging"

        # Use frequency delta as primary classifier
        if frequency_delta > TRAJECTORY_DELTA_THRESHOLD:
            return "increasing"
        elif frequency_delta < -TRAJECTORY_DELTA_THRESHOLD:
            return "fading"
        else:
            # The frequency delta is flat, so the finer-grained signal decides.
            # trend_slope is a relative change per week, which is the same kind
            # of quantity as the delta, so it uses the same threshold.
            if abs(trend_slope) > TRAJECTORY_DELTA_THRESHOLD:
                if trend_slope > 0:
                    return "increasing"
                else:
                    return "fading"
            else:
                return "stable"

    def _calculate_confidence(self, data_points_count: int) -> str:
        """
        Calculate confidence level based on data sufficiency.
        
        Args:
            data_points_count: Number of data points used in calculation
            
        Returns:
            Confidence level: 'low', 'medium', or 'high'
        """
        if data_points_count < TRAJECTORY_MIN_DATA_POINTS:
            return "low"
        elif data_points_count < TRAJECTORY_MIN_DATA_POINTS * 2:
            return "medium"
        else:
            return "high"
