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
import math
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import numpy as np

# Import database and constants
from .database import db
from .confidence import ConfidenceEngine
from .evidence import EvidenceEngine
from .constants import (
    TRAJECTORY_RECENT_DAYS,
    TRAJECTORY_BASELINE_DAYS,
    TRAJECTORY_DELTA_THRESHOLD,
    TRAJECTORY_MIN_DATA_POINTS,
    EVIDENCE_WEIGHTS
)

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
        occurrences = db.get_theme_occurrences(theme_id)

        # Get theme summary
        theme = db.get_theme_by_id(theme_id)
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
        recent_window_start = datetime.now() - timedelta(days=TRAJECTORY_RECENT_DAYS)
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
                dt_occurred = datetime.fromisoformat(str(occurred_at))

            # Ensure both datetimes are offset-naive for comparison
            if dt_occurred.tzinfo is not None:
                dt_occurred = dt_occurred.replace(tzinfo=None)

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
        db.create_or_update_confidence(
            'trajectory', theme_id,
            conf['confidence_level'], conf['confidence_score'],
            conf['data_points_count'], conf['time_coverage_days'],
            conf['consistency_score'], conf['recency_score']
        )
        
        # Store in evidence registry
        self.ev_engine.record_evidence('trajectory', 'theme', theme_id, self._evidence)
        
        # Store in theme_trajectories cache
        db.create_theme_trajectory(
            theme_id=theme_id,
            trajectory_label=trajectory_label,
            trend_score=trend_slope,
            recent_count=len(recent_occurrences),
            past_count=len(past_occurrences),
            confidence_level=confidence_level,
            data_points_count=len(occurrences)
        )
        
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
        themes = db.get_themes(self.user_id)
        results = []
        
        for theme in themes:
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

    def format_for_context(self, max_items: int = 5) -> str:
        """
        Formats trajectory insights for LLM context injection.
        
        Args:
            max_items: Maximum number of items to include
            
        Returns:
            Formatted string for system prompt injection
        """
        significant = self.get_significant_changes()[:max_items]
        
        if not significant:
            return ""
        
        lines = ["# Long-Term Trends:"]
        for item in significant:
            summary = item["theme_summary"]
            label = item["trajectory_label"]
            
            if label == "increasing":
                lines.append(f"- \"{summary}\" is increasing in frequency")
            elif label == "fading":
                lines.append(f"- \"{summary}\" is fading")
            elif label == "emerging":
                lines.append(f"- \"{summary}\" is emerging recently")
        
        return "\n".join(lines)

    def _calculate_trend_slope(self, occurrences: List[dict]) -> float:
        """
        Calculate the trend slope using weighted linear regression.
        Weights are determined by Evidence Tiering (reflection > habit).
        
        Args:
            occurrences: List of theme occurrences with timestamps
            
        Returns:
            Slope of the trend line (positive = increasing, negative = decreasing)
        """
        if len(occurrences) < 2:
            return 0.0
        
        # Convert timestamps to days since first occurrence
        timestamps = []
        weights = []
        
        for occ in occurrences:
            occurred_at = occ["occurred_at"]
            if isinstance(occurred_at, datetime):
                timestamps.append(occurred_at)
            else:
                timestamps.append(datetime.fromisoformat(str(occurred_at)))
            
            # Determine weight
            st = occ['source_type']
            snippet = occ.get('snippet', '')
            if st == 'habit_completion' and ("Notes:" in snippet or "Reason:" in snippet):
                weights.append(EVIDENCE_WEIGHTS.get('habit_completion_with_notes', 0.8))
            else:
                weights.append(EVIDENCE_WEIGHTS.get(st, 0.5)) # Default 0.5
        
        if not timestamps:
            return 0.0
        
        # Sort together
        paired = sorted(zip(timestamps, weights), key=lambda x: x[0])
        timestamps = [p[0] for p in paired]
        weights = [p[1] for p in paired]
        
        first_date = timestamps[0]
        
        # X = days since first occurrence, Y = cumulative count
        x_values = []
        y_values = []
        w_values = []
        
        for i, timestamp in enumerate(timestamps):
            days_since_first = (timestamp - first_date).days
            x_values.append(days_since_first)
            y_values.append(i + 1)  # cumulative count
            w_values.append(math.sqrt(weights[i])) # Sqrt for WLS transformation
        
        # Perform weighted linear regression
        if len(x_values) > 1:
            # Construct Weighted A and y
            # A = [x, 1]
            # WA = W * A
            # Wy = W * y
            X = np.array(x_values)
            Y = np.array(y_values)
            W = np.array(w_values)
            
            # Weighted X matrix (column of weighted xs, column of weights)
            A_w = np.vstack([X * W, W]).T
            y_w = Y * W
            
            try:
                slope, _ = np.linalg.lstsq(A_w, y_w, rcond=None)[0]
                return float(slope)
            except:
                return 0.0
        else:
            return 0.0

    def _classify_trajectory(self, total_occurrences: int, frequency_delta: float, 
                           trend_slope: float, occurrences: List[dict]) -> str:
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
                    dt_occurred = datetime.fromisoformat(str(occurred_at))

                # Ensure offset-naive for comparison
                if dt_occurred.tzinfo is not None:
                    dt_occurred = dt_occurred.replace(tzinfo=None)

                timestamps.append(dt_occurred)

            timestamps.sort()
            first_occurrence = timestamps[0]
            days_since_first = (datetime.now().replace(tzinfo=None) - first_occurrence).days

            # If first occurrence was in last 30 days and has recent activity, it's emerging
            recent_activity = False
            for occ in occurrences:
                occurred_at = occ["occurred_at"]
                if isinstance(occurred_at, datetime):
                    dt_occurred = occurred_at
                else:
                    dt_occurred = datetime.fromisoformat(str(occurred_at))

                # Ensure offset-naive for comparison
                if dt_occurred.tzinfo is not None:
                    dt_occurred = dt_occurred.replace(tzinfo=None)

                if dt_occurred >= datetime.now().replace(tzinfo=None) - timedelta(days=TRAJECTORY_RECENT_DAYS):
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
            # If frequency delta is within threshold, use slope as secondary classifier
            if abs(trend_slope) > 0.01:  # Small threshold to avoid noise
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