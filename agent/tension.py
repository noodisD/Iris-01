"""
Tension Engine - Tracks What Co-Exists Uneasily

This module analyzes when two or more themes co-occur and exhibit contrasting patterns.
It answers: "What themes appear together but show different behavioral signals?"

The engine does not judge. It simply observes co-occurrence and divergence.
- Co-occurrence: themes that appear together in the same temporal windows
- Divergence: contrasting behavioral signals (frequency, trajectory, etc.)
- Stability: how consistently this pattern appears over time
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import numpy as np

# Import database and constants
from .database import db
from .confidence import ConfidenceEngine
from .evidence import EvidenceEngine
from .constants import (
    TENSION_MIN_COOCCURRENCE,
    TENSION_RECENT_DAYS,
    TENSION_BASELINE_DAYS,
    TENSION_MIN_STABILITY,
    TENSION_MIN_OCCURRENCES,
    TENSION_MAX_THEMES_FOR_PAIRS
)

logger = logging.getLogger(__name__)


class TensionEngine:
    """
    Tracks when themes co-exist uneasily (co-occur but show contrasting patterns).
    """
    def __init__(self, user_id: int):
        """Initialize the tension engine for a user."""
        self.user_id = user_id
        self.conf_engine = ConfidenceEngine()
        self.ev_engine = EvidenceEngine()
        self._evidence = []

    def emit_evidence(self, ev_type: str, key: str, value: Any):
        """Buffers evidence for later persistence."""
        self._evidence.append({"type": ev_type, "key": key, "value": value})

    def _get_time_windows(self):
        """
        Define all time windows in one place to prevent mismatches.
        Returns: (recent_start, baseline_end, baseline_start)
        """
        recent_start = datetime.now() - timedelta(days=TENSION_RECENT_DAYS)
        baseline_end = recent_start
        baseline_start = baseline_end - timedelta(days=TENSION_BASELINE_DAYS)
        return recent_start, baseline_end, baseline_start

    def _get_stability_time_windows(self):
        """
        Define time windows for stability calculation.
        Uses weekly buckets for stability assessment.
        """
        # Stability windows use weekly buckets for consistent time slices
        now = datetime.now()
        return now

    def _get_active_themes(self) -> List[Dict]:
        """
        Get active themes that meet minimum occurrence criteria.
        Limits to top N most active themes to keep runtime predictable.
        """
        all_themes = db.get_themes(self.user_id)
        
        # Filter themes that have minimum occurrences
        active_themes = [t for t in all_themes if t["occurrence_count"] >= TENSION_MIN_OCCURRENCES]
        
        # Sort by occurrence count (descending) and take top N
        active_themes.sort(key=lambda x: x["occurrence_count"], reverse=True)
        return active_themes[:TENSION_MAX_THEMES_FOR_PAIRS]

    def _generate_candidate_pairs(self) -> List[Dict]:
        """
        Generate candidate theme pairs for tension analysis.
        """
        active_themes = self._get_active_themes()
        
        # Generate all unique pairs (combinations)
        pairs = []
        for i in range(len(active_themes)):
            for j in range(i + 1, len(active_themes)):
                pairs.append({
                    "theme_a": active_themes[i],
                    "theme_b": active_themes[j]
                })
        
        return pairs

    def _calculate_cooccurrence_metrics(self, theme_a_id: int, theme_b_id: int) -> Dict:
        """
        Calculate co-occurrence metrics for a theme pair.
        """
        # Get occurrences for both themes
        occurrences_a = db.get_theme_occurrences(theme_a_id)
        occurrences_b = db.get_theme_occurrences(theme_b_id)
        
        # Find co-occurrences (same source_id means same journal entry)
        cooccurrences = []
        for occ_a in occurrences_a:
            for occ_b in occurrences_b:
                if (occ_a["source_type"] == occ_b["source_type"] and 
                    occ_a["source_id"] == occ_b["source_id"]):
                    # Same entry, so they co-occur
                    cooccurrences.append({
                        "occurred_at": occ_a["occurred_at"],
                        "source_type": occ_a["source_type"],
                        "source_id": occ_a["source_id"]
                    })
        
        # Calculate time windows
        recent_start, baseline_end, baseline_start = self._get_time_windows()
        
        # Separate co-occurrences by time window
        recent_cooccurrences = []
        past_cooccurrences = []
        
        for coocc in cooccurrences:
            occurred_at = coocc["occurred_at"]
            if isinstance(occurred_at, datetime):
                dt_occurred = occurred_at
            else:
                dt_occurred = datetime.fromisoformat(str(occurred_at))
            
            # Ensure offset-naive for comparison
            if dt_occurred.tzinfo is not None:
                dt_occurred = dt_occurred.replace(tzinfo=None)
            
            if dt_occurred >= recent_start:
                recent_cooccurrences.append(coocc)
            elif baseline_start <= dt_occurred < baseline_end:
                past_cooccurrences.append(coocc)
        
        # Calculate metrics
        cooccurrence_count = len(cooccurrences)
        recent_count = len(recent_cooccurrences)
        past_count = len(past_cooccurrences)
        
        # Calculate co-occurrence rate (relative to individual theme occurrences)
        total_occurrences_a = len(occurrences_a)
        total_occurrences_b = len(occurrences_b)
        min_theme_occurrences = min(total_occurrences_a, total_occurrences_b)
        
        cooccurrence_rate = cooccurrence_count / min_theme_occurrences if min_theme_occurrences > 0 else 0
        
        return {
            "cooccurrence_count": cooccurrence_count,
            "recent_cooccurrence_count": recent_count,
            "past_cooccurrence_count": past_count,
            "cooccurrence_rate": cooccurrence_rate,
            "cooccurrences": cooccurrences
        }

    def _calculate_divergence_metrics(self, theme_a_id: int, theme_b_id: int) -> float:
        """
        Calculate divergence score between two themes.
        Uses trajectory information if available, otherwise frequency imbalance.
        """
        try:
            # Try to get trajectory information for both themes
            from .trajectory import TrajectoryEngine
            trajectory_engine = TrajectoryEngine(self.user_id)
            
            # Get trajectory analysis for both themes
            analysis_a = trajectory_engine.analyze_theme(theme_a_id)
            analysis_b = trajectory_engine.analyze_theme(theme_b_id)
            
            # If both have trajectory data, use trend scores
            if analysis_a and analysis_b:
                # Calculate divergence as absolute difference in trend scores
                divergence_score = abs(analysis_a.get("trend_score", 0) - analysis_b.get("trend_score", 0))
                return divergence_score
        except Exception:
            # If trajectory engine is not available or fails, use frequency-based divergence
            pass
        
        # Fallback: use frequency-based divergence
        # Get occurrences for both themes
        occurrences_a = db.get_theme_occurrences(theme_a_id)
        occurrences_b = db.get_theme_occurrences(theme_b_id)
        
        # Calculate recent vs past ratios for both themes
        recent_start, baseline_end, baseline_start = self._get_time_windows()
        
        # Count recent and past occurrences for theme A
        recent_a = 0
        past_a = 0
        for occ in occurrences_a:
            occurred_at = occ["occurred_at"]
            if isinstance(occurred_at, datetime):
                dt_occurred = occurred_at
            else:
                dt_occurred = datetime.fromisoformat(str(occurred_at))
            
            if dt_occurred.tzinfo is not None:
                dt_occurred = dt_occurred.replace(tzinfo=None)
            
            if dt_occurred >= recent_start:
                recent_a += 1
            elif baseline_start <= dt_occurred < baseline_end:
                past_a += 1
        
        # Count recent and past occurrences for theme B
        recent_b = 0
        past_b = 0
        for occ in occurrences_b:
            occurred_at = occ["occurred_at"]
            if isinstance(occurred_at, datetime):
                dt_occurred = occurred_at
            else:
                dt_occurred = datetime.fromisoformat(str(occurred_at))
            
            if dt_occurred.tzinfo is not None:
                dt_occurred = dt_occurred.replace(tzinfo=None)
            
            if dt_occurred >= recent_start:
                recent_b += 1
            elif baseline_start <= dt_occurred < baseline_end:
                past_b += 1
        
        # Calculate frequency ratios
        ratio_a = recent_a / (past_a + 1)  # +1 to avoid division by zero
        ratio_b = recent_b / (past_b + 1)
        
        # Divergence is the absolute difference in ratios
        divergence_score = abs(ratio_a - ratio_b)
        return divergence_score

    def _calculate_stability_metrics(self, cooccurrences: List[Dict]) -> float:
        """
        Calculate stability score for a theme pair.
        Stability answers: "Is this tension persistent or sporadic?"
        """
        if not cooccurrences:
            return 0.0
        
        # Extract occurrence times
        occurrence_times = []
        for coocc in cooccurrences:
            occurred_at = coocc["occurred_at"]
            if isinstance(occurred_at, datetime):
                dt_occurred = occurred_at
            else:
                dt_occurred = datetime.fromisoformat(str(occurred_at))
            
            if dt_occurred.tzinfo is not None:
                dt_occurred = dt_occurred.replace(tzinfo=None)
            
            occurrence_times.append(dt_occurred)
        
        if len(occurrence_times) < 2:
            return 1.0 if len(occurrence_times) > 0 else 0.0
        
        # Sort by time
        occurrence_times.sort()
        
        # Calculate intervals between consecutive occurrences
        intervals = []
        for i in range(1, len(occurrence_times)):
            interval = (occurrence_times[i] - occurrence_times[i-1]).days
            intervals.append(interval)
        
        # Calculate stability as inverse of coefficient of variation
        # Higher stability means more consistent intervals
        if len(intervals) == 0:
            return 1.0
        
        mean_interval = sum(intervals) / len(intervals)
        if mean_interval == 0:
            return 1.0  # All occurrences at same time
        
        std_interval = np.std(intervals) if len(intervals) > 1 else 0
        coefficient_of_variation = std_interval / mean_interval if mean_interval > 0 else 0
        
        # Stability is inverse of variation, bounded between 0 and 1
        stability_score = 1.0 / (1.0 + coefficient_of_variation)
        return min(stability_score, 1.0)  # Ensure it's not greater than 1

    def _classify_tension(self, cooccurrence_count: int, recent_count: int, past_count: int,
                         stability_score: float, divergence_score: float) -> str:
        """
        Classify the tension based on calculated metrics.
        """
        if cooccurrence_count < TENSION_MIN_COOCCURRENCE:
            return "intermittent"  # Not enough co-occurrences to be significant
        
        # Calculate time-based classification
        has_recent_activity = recent_count > 0
        has_past_activity = past_count > 0
        
        if stability_score >= TENSION_MIN_STABILITY and has_recent_activity:
            return "persistent"
        elif has_recent_activity and not has_past_activity:
            return "emerging"
        elif has_past_activity and not has_recent_activity:
            return "fading"
        else:
            return "intermittent"

    def _calculate_confidence(self, cooccurrence_count: int, stability_score: float) -> str:
        """
        Calculate confidence level based on data sufficiency.
        """
        if cooccurrence_count < TENSION_MIN_COOCCURRENCE or stability_score < TENSION_MIN_STABILITY:
            return "low"
        elif cooccurrence_count < TENSION_MIN_COOCCURRENCE * 2:  # Arbitrary threshold
            return "medium"
        else:
            return "high"

    def analyze_tension(self, theme_a_id: int, theme_b_id: int) -> Dict:
        """
        Analyze tension between two themes.
        
        Args:
            theme_a_id: First theme ID
            theme_b_id: Second theme ID
            
        Returns:
            Dictionary with tension metrics and classification
        """
        # Calculate co-occurrence metrics
        cooccurrence_metrics = self._calculate_cooccurrence_metrics(theme_a_id, theme_b_id)
        
        # Calculate divergence metrics
        divergence_score = self._calculate_divergence_metrics(theme_a_id, theme_b_id)
        
        # Calculate stability metrics
        stability_score = self._calculate_stability_metrics(cooccurrence_metrics["cooccurrences"])
        
        # Classify tension
        tension_label = self._classify_tension(
            cooccurrence_metrics["cooccurrence_count"],
            cooccurrence_metrics["recent_cooccurrence_count"],
            cooccurrence_metrics["past_cooccurrence_count"],
            stability_score,
            divergence_score
        )
        
        # Calculate confidence using central engine
        self._evidence = [] # Clear buffer
        cooccs = cooccurrence_metrics["cooccurrences"]
        timestamps = []
        for c in cooccs:
            dt = c['occurred_at']
            if not isinstance(dt, datetime):
                dt = datetime.fromisoformat(str(dt))
            timestamps.append(dt)
        
        conf = self.conf_engine.compute_confidence('tension', theme_a_id, timestamps)
        confidence_level = conf['confidence_level']
        
        # Emit evidence
        self.emit_evidence('count', 'cooccurrence_count', cooccurrence_metrics["cooccurrence_count"])
        self.emit_evidence('rate', 'cooccurrence_rate', cooccurrence_metrics["cooccurrence_rate"])
        self.emit_evidence('delta', 'divergence_score', divergence_score)
        self.emit_evidence('delta', 'stability_score', stability_score)
        
        # Record evidence bundle (using the first theme as primary ID for registry)
        self.ev_engine.record_evidence('tension', 'theme', theme_a_id, self._evidence)
        
        # Create result (convert numpy types to Python native types)
        result = {
            "theme_a_id": theme_a_id,
            "theme_b_id": theme_b_id,
            "cooccurrence_count": int(cooccurrence_metrics["cooccurrence_count"]),
            "recent_cooccurrence_count": int(cooccurrence_metrics["recent_cooccurrence_count"]),
            "past_cooccurrence_count": int(cooccurrence_metrics["past_cooccurrence_count"]),
            "cooccurrence_rate": float(cooccurrence_metrics["cooccurrence_rate"]),
            "divergence_score": float(divergence_score),
            "stability_score": float(stability_score),
            "tension_label": tension_label,
            "confidence_level": confidence_level,
            "evidence": cooccurrence_metrics["cooccurrences"][:5]  # Sample evidence
        }
        
        # Store in cache (convert numpy types to Python native types)
        db.create_or_update_tension(
            theme_a_id=theme_a_id,
            theme_b_id=theme_b_id,
            cooccurrence_count=int(result["cooccurrence_count"]),
            recent_cooccurrence_count=int(result["recent_cooccurrence_count"]),
            past_cooccurrence_count=int(result["past_cooccurrence_count"]),
            divergence_score=float(result["divergence_score"]),
            stability_score=float(result["stability_score"]),
            tension_label=result["tension_label"],
            confidence_level=result["confidence_level"]
        )
        
        # Now we can store in pattern_confidence using the tension record ID
        # We need to fetch the ID we just created/updated
        # For MVP simplicity, we'll let theme_tensions keep the label.
        
        return result

    def analyze_all_pairs(self) -> List[Dict]:
        """
        Alias for analyze_all_tensions to maintain backward compatibility.
        """
        return self.analyze_all_tensions()

    def analyze_all_pairs(self) -> List[Dict]:
        """
        Alias for analyze_all_tensions to maintain backward compatibility.
        """
        return self.analyze_all_tensions()

    def analyze_all_tensions(self) -> List[Dict]:
        """
        Analyze tensions for all valid theme pairs.
        
        Returns:
            List of tension analyses for all theme pairs
        """
        candidate_pairs = self._generate_candidate_pairs()
        results = []
        
        for pair in candidate_pairs:
            theme_a = pair["theme_a"]
            theme_b = pair["theme_b"]
            
            analysis = self.analyze_tension(theme_a["id"], theme_b["id"])
            analysis["theme_a_summary"] = theme_a["summary"]
            analysis["theme_b_summary"] = theme_b["summary"]
            results.append(analysis)
        
        return results

    def get_significant_tensions(self) -> List[Dict]:
        """
        Get tensions that are above confidence threshold.
        
        Returns:
            List of high-confidence tension analyses
        """
        all_analysis = self.analyze_all_tensions()
        
        significant = [analysis for analysis in all_analysis 
                      if analysis["confidence_level"] == "high"]
        
        # Sort by stability and co-occurrence count
        significant.sort(key=lambda x: (x["stability_score"], x["cooccurrence_count"]), reverse=True)
        return significant

    def format_for_context(self, max_items: int = 3) -> str:
        """
        Format significant tensions for LLM context injection.
        
        Args:
            max_items: Maximum number of items to include
            
        Returns:
            Formatted string for system prompt injection
        """
        significant = self.get_significant_tensions()[:max_items]
        
        if not significant:
            return ""
        
        lines = ["# Theme Tensions:"]
        for item in significant:
            summary_a = item["theme_a_summary"]
            summary_b = item["theme_b_summary"]
            label = item["tension_label"]
            
            lines.append(f"- \"{summary_a}\" and \"{summary_b}\" frequently appear together and show different recent activity patterns")
        
        return "\n".join(lines)