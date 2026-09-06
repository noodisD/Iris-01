"""
Insight Prioritization Engine - Signal Selection Layer

This module ranks a list of filtered insights to determine what should be 
presented first. It uses a weighted scorecard considering:
- Confidence (Trust Barrier)
- Recency relevance
- Impact magnitude
- Novelty (Discovery of shifts)
- Engine importance
"""

import logging
import math
from datetime import datetime
from typing import Any

from .timeutils import to_utc, utc_now
from .constants import (
    ENGINE_BASE_WEIGHTS,
    ENGINE_PRIORITY,
    PRIORITY_CONFIDENCE_WEIGHT,
    PRIORITY_ENGINE_WEIGHT,
    PRIORITY_MAGNITUDE_WEIGHT,
    PRIORITY_MAX_ITEMS,
    PRIORITY_NOVELTY_WEIGHT,
    PRIORITY_RECENCY_WEIGHT,
    PRIORITY_RECENT_DECAY_DAYS,
)

# Import database and constants
from .database import db

logger = logging.getLogger(__name__)

class InsightPrioritizationEngine:
    """
    Ranks filtered insights using a standardized scorecard.
    """

    def __init__(self, user_id: int):
        self.user_id = user_id
        # Policy: Low confidence is handled by the gatekeeper before this engine.
        self.confidence_map = {"high": 1.0, "medium": 0.6}
        self.engine_tiebreak_prio = {name: i for i, name in enumerate(ENGINE_PRIORITY)}

    def rank_insights(self, insights: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Calculates priority scores, sorts them, and selects top-N unique patterns.
        """
        if not insights:
            return []

        # 1. Scoring
        scored_list = []
        for ins in insights:
            score_breakdown = self._calculate_score(ins)
            ins['priority_score'] = score_breakdown['total']
            ins['priority_breakdown'] = score_breakdown
            scored_list.append(ins)

        # 2. Sorting (Deterministic Tie-Breaking)
        # Sequence: Score DESC -> Conf -> Recency -> Engine Prio -> ID
        def sort_key(i):
            conf_val = self.confidence_map.get((i.get('confidence') or i.get('confidence_level') or 'low').lower(), 0)

            # Recency (timestamp based)
            # Use 1970-01-01 as a safe fallback instead of datetime.min
            last_at = i.get('last_seen_at') or i.get('computed_at') or datetime(1970, 1, 1)
            if not isinstance(last_at, datetime):
                last_at = datetime.fromisoformat(str(last_at))

            # Ensure naive for timestamp calculation
            last_at = to_utc(last_at)

            engine_prio = self.engine_tiebreak_prio.get(i.get('engine_name'), -1)

            return (
                i['priority_score'],
                conf_val,
                last_at.timestamp(),
                engine_prio,
                -i.get('pattern_id', 0) # Lower ID wins tie
            )

        scored_list.sort(key=sort_key, reverse=True)

        # 3. Diversity Rule: One slot per Pattern ID
        final_list = []
        seen_patterns = set()

        for ins in scored_list:
            p_key = (ins['pattern_type'], ins['pattern_id'])
            if p_key not in seen_patterns:
                final_list.append(ins)
                seen_patterns.add(p_key)

            if len(final_list) >= PRIORITY_MAX_ITEMS:
                break

        # 4. Persistence for audit
        for idx, ins in enumerate(final_list):
            insight_id = f"{ins['engine_name']}:{ins['pattern_type']}:{ins['pattern_id']}"
            db.create_or_update_insight_priority(
                insight_id=insight_id,
                engine_name=ins['engine_name'],
                pattern_type=ins['pattern_type'],
                pattern_id=ins['pattern_id'],
                priority_score=ins['priority_score'],
                rank=idx + 1
            )

        return final_list

    def _calculate_score(self, ins: dict) -> dict:
        """Weighted sum aggregate."""

        # A. Confidence (35%)
        conf_label = (ins.get('confidence') or ins.get('confidence_level') or 'low').lower()
        s_conf = self.confidence_map.get(conf_label, 0.0)

        # B. Recency (20%)
        last_at = ins.get('last_seen_at') or ins.get('computed_at')
        if not last_at:
            s_recency = 0.5
        else:
            if not isinstance(last_at, datetime):
                last_at = datetime.fromisoformat(str(last_at))
            days_since = (utc_now() - to_utc(last_at)).days
            s_recency = math.exp(-max(0, days_since) / PRIORITY_RECENT_DECAY_DAYS)

        # C. Magnitude (20%)
        # Contract: normalization [0,1]
        raw_mag = ins.get('magnitude')
        if raw_mag is None:
            # Fallback to engine-specific delta keys
            mag_keys = ['influence_score', 'attenuation_score', 'trend_score', 'delta_score']
            for k in mag_keys:
                if k in ins:
                    raw_mag = abs(float(ins[k]))
                    break

        s_mag = max(0.0, min(1.0, raw_mag if raw_mag is not None else 0.5))

        # D. Novelty (15%)
        # Heuristic: 1.0 if new/changed classification, 0.5 if stable
        s_nov = ins.get('novelty', 0.5)

        # E. Engine Weight (10%)
        # Multiplier [0.6, 1.0]
        s_engine = ENGINE_BASE_WEIGHTS.get(ins.get('engine_name'), 0.6)

        total = (
            (PRIORITY_CONFIDENCE_WEIGHT * s_conf) +
            (PRIORITY_RECENCY_WEIGHT * s_recency) +
            (PRIORITY_MAGNITUDE_WEIGHT * s_mag) +
            (PRIORITY_NOVELTY_WEIGHT * s_nov) +
            (PRIORITY_ENGINE_WEIGHT * s_engine)
        )

        return {
            "total": round(total, 3),
            "conf": s_conf,
            "recency": s_recency,
            "magnitude": s_mag,
            "novelty": s_nov,
            "engine": s_engine
        }
