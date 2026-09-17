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
from .timeutils import to_utc, utc_now
from .constants import (
    CONF_ABSENCE_MIN_BASELINE_SPAN_DAYS,
    CONF_ABSENCE_MIN_OBSERVED_DAYS,
    CONF_ABSENCE_HIGH_CONTINUITY,
    CONF_ABSENCE_MIN_CONTINUITY,
    CONF_ABSENCE_SILENCE_SATURATION_MULTIPLE,
    CONF_CONSISTENCY_THRESHOLD,
    CONF_HIGH_POINTS,
    CONF_MIN_COVERAGE_DAYS_FOR_HIGH,
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
        sorted_ts = sorted(to_utc(ts) for ts in timestamps)
        coverage_days = (sorted_ts[-1] - sorted_ts[0]).days

        # 3. Recency Score (Exponential decay)
        now = utc_now()
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

        # Rule: High points + enough elapsed time + good consistency + decent
        # recency = High.
        #
        # coverage_days was computed and then ignored, so evidence with no
        # duration at all could reach the top label: ten reflections saved in the
        # same second scored 1.0 and 'high' across zero days. Sufficiency counts
        # data points, and data points are not the same thing as observations of
        # a pattern over time — which is the only thing any of these engines
        # claims to measure.
        has_enough_span = coverage_days >= CONF_MIN_COVERAGE_DAYS_FOR_HIGH
        if effective_count >= CONF_HIGH_POINTS and recency >= 0.5 and has_enough_span:
            if not has_direction or consistency >= CONF_CONSISTENCY_THRESHOLD:
                label = 'high'
            else:
                label = 'medium' # High data but conflicting signals
        # Rule: Medium points + Acceptable signals = Medium. Evidence that is
        # plentiful but instantaneous lands here rather than at 'high'.
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

    def compute_absence_confidence(
        self,
        baseline_count: int,
        days_silent: float,
        silence_threshold_days: float,
        observed_days_during: int,
        observed_days_before: int,
        baseline_span_days: float | None = None,
    ) -> dict[str, Any]:
        """How much to trust the claim that a pattern has *stopped*.

        compute_confidence answers "how fresh is the newest evidence", which is
        the right question for a claim about what is happening now and the wrong
        one for a claim about an absence. Silence is not stale evidence about the
        pattern; it *is* the evidence, and it strengthens as it runs. Scoring a
        dissipation on recency inverted that: a theme silent for ninety days
        after twenty occurrences — the most confidently dead thing this system
        can observe — was forced to 'low'.

        Inverting the sign on its own would be worse than the bug. Silence only
        means anything if somebody was watching, or a fortnight's holiday reads
        as a resolved pattern. So the third term is the load-bearing one:

        - support     how well established the pattern was before it stopped
        - silence     how long the quiet has run, against what defines it
        - continuity  whether the user kept logging through the quiet, measured
                      against their own prior rate rather than an absolute one

        Continuity gates the result rather than merely weighting it: below
        CONF_ABSENCE_MIN_CONTINUITY the honest answer is that we stopped looking,
        whatever the other two terms say.

        Two further gates, because a ratio of one day to one day is 1.0 and read
        as perfect watchfulness: `high` needs CONF_ABSENCE_MIN_OBSERVED_DAYS
        distinct days logged *during* the silence, and a baseline confined to
        less than CONF_ABSENCE_MIN_BASELINE_SPAN_DAYS is a burst — ten entries in
        one sitting are ten data points and one observation, so it cannot exceed
        `medium` however many there are. Measured: ten occurrences on one day
        with a day either side scored high/1.0 before this, against 0.82 for
        eight occurrences logged weekly throughout.
        """
        support = min(
            1.0,
            math.log(max(baseline_count, 0) + 1) / math.log(CONF_HIGH_POINTS + 1),
        )

        saturation = max(
            silence_threshold_days * CONF_ABSENCE_SILENCE_SATURATION_MULTIPLE, 1.0
        )
        silence = max(0.0, min(1.0, days_silent / saturation))

        # Compared against the user's own habit over an equal span, so someone
        # who journals weekly is not scored as absent for six days out of seven.
        continuity_known = observed_days_before > 0
        if continuity_known:
            continuity = min(1.0, observed_days_during / observed_days_before)
        else:
            # No prior logging on record to compare against, so how closely we
            # were watching is simply unknown. Activity during the silence is
            # still worth something, but an unknown must not be allowed to
            # produce the top label — that is the direction in which being wrong
            # costs the most.
            continuity = 1.0 if observed_days_during > 0 else 0.0

        # Thin watchfulness cannot be disguised by a flattering ratio.
        watched_enough = observed_days_during >= CONF_ABSENCE_MIN_OBSERVED_DAYS
        spread_enough = (baseline_span_days is None
                         or baseline_span_days >= CONF_ABSENCE_MIN_BASELINE_SPAN_DAYS)
        thin_observation = min(1.0, observed_days_during / CONF_ABSENCE_MIN_OBSERVED_DAYS)

        score = (0.35 * support) + (0.25 * silence) + (0.25 * continuity) + (0.15 * thin_observation)

        if continuity < CONF_ABSENCE_MIN_CONTINUITY or observed_days_during == 0:
            label = 'low'
        elif (continuity_known
                and watched_enough
                and spread_enough
                and baseline_count >= CONF_HIGH_POINTS
                and silence >= 1.0
                and continuity >= CONF_ABSENCE_HIGH_CONTINUITY):
            label = 'high'
        elif baseline_count >= CONF_MIN_POINTS and watched_enough:
            label = 'medium'
        else:
            # Established enough, but watched on too few days to call the
            # silence evidence of anything.
            label = 'low'

        return {
            "confidence_level": label,
            "confidence_score": round(score, 3),
            "data_points_count": baseline_count,
            "time_coverage_days": int(days_silent),
            "consistency_score": round(continuity, 3),
            "recency_score": round(silence, 3),
            "_explanation": {
                "mode": "absence",
                "support": round(support, 3),
                "silence": round(silence, 3),
                "continuity": round(continuity, 3),
                "observed_days_during": observed_days_during,
                "observed_days_before": observed_days_before,
                "baseline_span_days": baseline_span_days,
                "watched_enough": watched_enough,
                "spread_enough": spread_enough,
                "continuity_known": continuity_known,
                "final_score": round(score, 3),
            },
        }

    def _empty_result(self) -> dict:
        return {
            "confidence_level": "low",
            "confidence_score": 0.0,
            "data_points_count": 0,
            "time_coverage_days": 0,
            "consistency_score": 0.0,
            "recency_score": 0.0
        }
