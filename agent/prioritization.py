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
    PRIORITY_RECENCY_WEIGHT,
    PRIORITY_RECENT_DECAY_DAYS,
)

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

    def rank(self, insights: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Score and order every admitted finding. No cut, no writes.

        This used to keep one finding per pattern and stop at
        PRIORITY_MAX_ITEMS = 5 before the caller's own budget was applied, so
        an owner who set Settings to 10 got 5 and never learned why — and the
        Insights screen, which ranks nothing away, could not share it. Ordering
        is the shared step; how many to keep is the caller's.
        """
        scored_list = []
        for ins in insights:
            score_breakdown = self._calculate_score(ins)
            ins['priority_score'] = score_breakdown['total']
            ins['priority_breakdown'] = score_breakdown
            scored_list.append(ins)

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
        return scored_list

    def select(self, ranked: list[dict[str, Any]], max_items: int) -> list[dict[str, Any]]:
        """What fits in a prompt: one finding per pattern, at most `max_items`.

        One per pattern because a prompt has room for a few things and two
        engines describing the same theme would spend both. A pattern is a
        theme, or for the pair engines the pair — a tension between A and B is
        not one more thing said about A. The selection is recorded for audit.
        """
        if not ranked:
            # Nothing selected means the previous selection is no longer
            # current, so it is retired rather than left looking live.
            try:
                db.retire_insight_priorities([])
            except Exception as e:
                logger.warning(f"Could not retire superseded priorities: {e}")
            return []

        final_list, seen = [], set()
        for ins in ranked:
            key = (ins['pattern_type'], ins.get('pattern_key', ins['pattern_id']))
            if key in seen:
                continue
            final_list.append(ins)
            seen.add(key)
            if len(final_list) >= max_items:
                break

        ids = [self._audit_id(i) for i in final_list]
        try:
            db.retire_insight_priorities(ids)
        except Exception as e:
            logger.warning(f"Could not retire superseded priorities: {e}")
        for idx, (ins, insight_id) in enumerate(zip(final_list, ids)):
            db.create_or_update_insight_priority(
                insight_id=insight_id,
                engine_name=ins['engine_name'],
                pattern_type=ins['pattern_type'],
                pattern_id=ins['pattern_id'],
                priority_score=ins['priority_score'],
                rank=idx + 1
            )
        return final_list

    @staticmethod
    def _audit_id(ins: dict[str, Any]) -> str:
        return f"{ins['engine_name']}:{ins['pattern_type']}:{ins.get('pattern_key', ins['pattern_id'])}"

    def _calculate_score(self, ins: dict) -> dict:
        """Weighted sum aggregate."""

        # A. Confidence
        conf_label = (ins.get('confidence') or ins.get('confidence_level') or 'low').lower()
        s_conf = self.confidence_map.get(conf_label, 0.0)

        # B. Recency
        last_at = ins.get('last_seen_at') or ins.get('computed_at')
        if not last_at:
            s_recency = 0.5
        else:
            if not isinstance(last_at, datetime):
                last_at = datetime.fromisoformat(str(last_at))
            days_since = (utc_now() - to_utc(last_at)).days
            s_recency = math.exp(-max(0, days_since) / PRIORITY_RECENT_DECAY_DAYS)

        # C. Magnitude
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

        # D. Engine Weight
        # Multiplier [0.6, 1.0]
        s_engine = ENGINE_BASE_WEIGHTS.get(ins.get('engine_name'), 0.6)

        total = (
            (PRIORITY_CONFIDENCE_WEIGHT * s_conf) +
            (PRIORITY_RECENCY_WEIGHT * s_recency) +
            (PRIORITY_MAGNITUDE_WEIGHT * s_mag) +
            (PRIORITY_ENGINE_WEIGHT * s_engine)
        )

        return {
            "total": round(total, 3),
            "conf": s_conf,
            "recency": s_recency,
            "magnitude": s_mag,
            "engine": s_engine
        }
