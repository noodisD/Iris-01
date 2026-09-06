"""
Confidence & Reliability Engine - Central Meta-Control

This module provides a standardized, evidence-based reliability layer used by all engines.
Confidence is computed mechanically based on:
- Data Sufficiency (counts)
- Time Coverage (days)
- Recency (exponential decay)
- Consistency (agreement in direction, if applicable)

It does not judge importance, only the reliability of the observation.
"""

import logging
import math
from datetime import datetime
from typing import Any

# Import constants
from .constants import (
    CONF_CONSISTENCY_THRESHOLD,
    CONF_HIGH_POINTS,
    CONF_MIN_POINTS,
    CONF_RECENCY_DAYS,
    CONF_WEIGHT_CONSISTENCY,
    CONF_WEIGHT_RECENCY,
    CONF_WEIGHT_SUFFICIENCY,
    EVIDENCE_WEIGHTS,
)

logger = logging.getLogger(__name__)


class ConfidenceEngine:
    """
    Standardizes how the system trusts its own observations.
    """

    def compute_confidence(
        self,
        pattern_type: str,
        pattern_id: int,
        timestamps: list[datetime],
        directions: list[str] | None = None,
        sources: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Calculates a reliability score and label for a set of evidence.
        
        Args:
            pattern_type: The type of pattern being assessed.
            pattern_id: The ID of the pattern.
            timestamps: List of occurrences.
            directions: Optional list of labels to assess consistency.
            sources: Optional list of source types (e.g. 'journal_entry') to apply evidence tiering.

        Returns:
            Dictionary containing label, score, and raw components.
        """
        if not timestamps:
            return self._empty_result()

        raw_count = len(timestamps)

        # 1. Data Sufficiency (Weighted)
        if sources:
            weighted_count = 0.0
            for s in sources:
                # Handle specific vs general keys (e.g. habit_completion vs habit_completion_with_notes)
                # Ideally caller handles specific logic, but here we just map string to weight.
                # Use base weight if specific not found
                weight = EVIDENCE_WEIGHTS.get(s, 0.5)
                weighted_count += weight

            # Normalize: We want weighted_count to reach ~CONF_HIGH_POINTS
            # But since weights are <= 1.0, weighted_count will be <= count.
            # We treat weighted_count as the effective "N".
            effective_count = weighted_count
        else:
            effective_count = raw_count

        # Logarithmic scale normalized to 0-1
        sufficiency = min(1.0, math.log(effective_count + 1) / math.log(CONF_HIGH_POINTS + 1))

        # 2. Time Coverage
        sorted_ts = sorted([ts.replace(tzinfo=None) if ts.tzinfo else ts for ts in timestamps])
        coverage_days = (sorted_ts[-1] - sorted_ts[0]).days

        # 3. Recency Score (Exponential decay)
        now = datetime.now().replace(tzinfo=None)
        days_since_last = (now - sorted_ts[-1]).days
        # Score = exp(-days / tau)
        recency = math.exp(-max(0, days_since_last) / CONF_RECENCY_DAYS)

        # 4. Consistency Score (Directionalagreement)
        has_direction = directions is not None and len(directions) > 0
        consistency = 0.0

        if has_direction:
            # Find the dominant direction
            counts = {}
            for d in directions:
                counts[d] = counts.get(d, 0) + 1
            dominant_count = max(counts.values()) if counts else 0
            consistency = dominant_count / len(directions)

            # Use standard weights
            w_s, w_c, w_r = CONF_WEIGHT_SUFFICIENCY, CONF_WEIGHT_CONSISTENCY, CONF_WEIGHT_RECENCY
        else:
            # Re-normalize weights to skip consistency
            # Sufficiency and Recency share the remaining 0.4 weight
            total_remaining = CONF_WEIGHT_SUFFICIENCY + CONF_WEIGHT_RECENCY
            w_s = CONF_WEIGHT_SUFFICIENCY / total_remaining
            w_r = CONF_WEIGHT_RECENCY / total_remaining
            w_c = 0.0
            consistency = 0.0

        # 5. Weighted Aggregate Score
        score = (w_s * sufficiency) + (w_c * consistency) + (w_r * recency)

        # 6. Classification (Gatekeeper logic)
        label = 'low'

        # Rule: High points + Good consistency + Decent recency = High
        if effective_count >= CONF_HIGH_POINTS and recency >= 0.5:
            if not has_direction or consistency >= CONF_CONSISTENCY_THRESHOLD:
                label = 'high'
            else:
                label = 'medium' # High data but conflicting signals
        # Rule: Medium points + Acceptable signals = Medium
        elif effective_count >= CONF_MIN_POINTS:
            if not has_direction or consistency >= 0.5:
                label = 'medium'
            else:
                label = 'low'

        # Final override: very old evidence is never high confidence
        if recency < 0.2:
            label = 'low'

        result = {
            "confidence_level": label,
            "confidence_score": round(score, 3),
            "data_points_count": raw_count,
            "time_coverage_days": coverage_days,
            "consistency_score": round(consistency, 3),
            "recency_score": round(recency, 3),
            "_explanation": {
                "sufficiency": { "value": round(sufficiency, 3), "weight": round(w_s, 2) },
                "consistency": { "value": round(consistency, 3), "weight": round(w_c, 2) },
                "recency": { "value": round(recency, 3), "weight": round(w_r, 2) },
                "effective_count": effective_count,
                "final_score": round(score, 3)
            }
        }

        return result

    def _empty_result(self) -> dict:
        return {
            "confidence_level": "low",
            "confidence_score": 0.0,
            "data_points_count": 0,
            "time_coverage_days": 0,
            "consistency_score": 0.0,
            "recency_score": 0.0
        }
