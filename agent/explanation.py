"""
Explanation Engine - Human-Friendly Audit Formatter

This module formats structured evidence into human-friendly bundles.
It performs no logic or inference, only structured recall.
"""

import logging
from typing import Dict, Any, List, Optional

# Import database and evidence
from .database import db, confidence as conf_repo
from .evidence import EvidenceEngine

logger = logging.getLogger(__name__)

class ExplanationEngine:
    """
    Assembles evidence into readable explanation bundles.
    """

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.ev_engine = EvidenceEngine()

    def explain(self, pattern_type: str, pattern_id: int, engine_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves and formats the latest evidence for a pattern.
        """
        # 1. Fetch confidence first to check guardrail
        conf = conf_repo.get_confidence(pattern_type, pattern_id)
        if not conf:
            return {"summary": "No analytical record found.", "evidence": []}

        if conf['confidence_level'] == 'low':
            return {
                "summary": "Insufficient reliable evidence to generate an explanation.",
                "confidence": "Low",
                "evidence": []
            }

        # 2. Fetch the latest bundle
        bundle = self.ev_engine.get_latest_bundle(pattern_type, pattern_id, engine_name)
        if not bundle:
            return {"summary": "Evidence record is missing for this computation.", "evidence": []}

        # 3. Format into human-friendly structure
        formatted_evidence = []
        for rec in bundle:
            formatted_evidence.append({
                "label": self._map_key_to_label(rec['evidence_key']),
                "value": rec['evidence_value'],
                "type": rec['evidence_type'],
                "engine": rec['engine_name']
            })

        # Deterministic ordering
        formatted_evidence.sort(key=lambda x: (x['engine'], x['type'], x['label']))

        return {
            "pattern_type": pattern_type,
            "pattern_id": pattern_id,
            "summary": f"Reliability analysis for {pattern_type}",
            "confidence": conf['confidence_level'].capitalize(),
            "confidence_score": conf['confidence_score'],
            "evidence": formatted_evidence,
            "computed_at": bundle[0]['created_at'].isoformat()
        }

    def _map_key_to_label(self, key: str) -> str:
        """Maps machine keys to human-friendly labels."""
        mapping = {
            # Persistence
            "occurrence_count": "Total occurrences",
            "time_coverage_days": "Time span of evidence",
            "recency_score": "Evidence recency (decayed)",
            
            # Trajectory
            "recent_count": "Recent occurrences (21d)",
            "past_count": "Baseline occurrences (90d)",
            "trend_score": "Linear trend slope",
            "total_occurrences": "Total data points",
            
            # Tension
            "cooccurrence_count": "Times themes appeared together",
            "cooccurrence_rate": "Ratio of co-occurrence",
            "divergence_score": "Pattern divergence",
            "stability_score": "Co-occurrence consistency",
            
            # Resolution
            "attenuation_score": "Rate of weakening",
            "recent_rate": "Daily rate (Recent)",
            "past_rate": "Daily rate (Baseline)",
            
            # Leverage
            "forward_count": "Times Source preceded Target",
            "backward_count": "Times Target preceded Source",
            "simultaneous_count": "Times they occurred together",
            "directional_lift": "Asymmetry (Lift)",
            "p_target_given_source": "Probability Target follows Source",
            
            # Impact
            "avg_baseline_rate": "Baseline frequency",
            "avg_post_rate": "Frequency after anchor",
            "delta_score": "Relative change",
            "anchor_count": "Anchor events analyzed"
        }
        return mapping.get(key, key.replace('_', ' ').capitalize())
