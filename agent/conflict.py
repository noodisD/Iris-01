"""
Conflict Suppression Engine - Epistemic Guardrail

This module identifies and suppresses logically incompatible insights about the 
same pattern to preserve system integrity.

It runs after all engines compute and follow deterministic priority rules.
"""

import logging
from typing import Any

# Import rules and constants
from .conflicts import CONFLICT_RULES
from .timeutils import utc_now
from .constants import CONFLICT_MIN_CONFIDENCE, ENGINE_PRIORITY

logger = logging.getLogger(__name__)

class ConflictSuppressionEngine:
    """
    Identifies and silences contradictory evidence using set-based rule matching.
    """

    def __init__(self):
        self.rules = CONFLICT_RULES
        self.priority = {name: i for i, name in enumerate(ENGINE_PRIORITY)}
        self.confidence_ranks = {'low': 0, 'medium': 1, 'high': 2}
        self.min_conf_val = self.confidence_ranks.get(CONFLICT_MIN_CONFIDENCE, 1)

    def suppress(self, insights: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Groups insights by pattern and resolves any detected contradictions.
        
        Input: List of insights, each with:
               pattern_type, pattern_id, engine_name, resolution_label/trajectory_label...
        """
        # 1. Grouping by (type, id)
        groups = {}
        for insight in insights:
            key = (insight['pattern_type'], insight['pattern_id'])
            if key not in groups:
                groups[key] = []
            groups[key].append(insight)

        visible = []
        suppressed = []

        # 2. Process each group
        for _key, group_insights in groups.items():
            resolved_group, suppressed_from_group = self._resolve_group(group_insights)
            visible.extend(resolved_group)
            suppressed.extend(suppressed_from_group)

        return {
            "visible": visible,
            "suppressed": suppressed,
            "timestamp": utc_now().isoformat()
        }

    def _resolve_group(self, insights: list[dict]) -> tuple[list[dict], list[dict]]:
        """
        Resolves conflicts within a single pattern group.
        """
        if len(insights) < 2:
            return insights, []

        # Filter by confidence floor first
        # Only insights >= medium participate in conflict logic
        candidates = [i for i in insights if self._get_conf_val(i) >= self.min_conf_val]
        too_low = [i for i in insights if self._get_conf_val(i) < self.min_conf_val]

        if len(candidates) < 2:
            return insights, []

        to_remove = set()
        suppression_meta = []

        # Pairwise check against rules
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                if i in to_remove or j in to_remove:
                    continue

                ins_a = candidates[i]
                ins_b = candidates[j]

                # Check for rule match
                conflict_rule = self._find_conflict(ins_a, ins_b)
                if conflict_rule:
                    winner_idx, loser_idx, reason = self._apply_tiebreak(i, j, candidates, conflict_rule['reason'])

                    if winner_idx is None:
                        # Tie-break failed, suppress BOTH
                        to_remove.add(i)
                        to_remove.add(j)
                        suppression_meta.append({"insight": ins_a, "reason": "Ambiguous tie: both suppressed"})
                        suppression_meta.append({"insight": ins_b, "reason": "Ambiguous tie: both suppressed"})
                    else:
                        to_remove.add(loser_idx)
                        suppression_meta.append({
                            "insight": candidates[loser_idx],
                            "reason": reason,
                            "winner_engine": candidates[winner_idx]['engine_name']
                        })

        resolved = [candidates[idx] for idx in range(len(candidates)) if idx not in to_remove]
        # Include the ones that were below the confidence floor originally
        resolved.extend(too_low)

        return resolved, suppression_meta

    def _find_conflict(self, a: dict, b: dict) -> dict | None:
        """Matches a pair of insights against the unordered rule sets."""
        engine_a = a['engine_name']
        label_a = self._get_label(a)

        engine_b = b['engine_name']
        label_b = self._get_label(b)

        pair = {(engine_a, label_a), (engine_b, label_b)}

        for rule in self.rules:
            if rule['patterns'] == pair:
                return rule
        return None

    def _apply_tiebreak(self, idx_a: int, idx_b: int, candidates: list[dict], rule_reason: str) -> tuple[int | None, int | None, str]:
        """
        Determines winner based on Confidence > Priority.
        Returns: (winner_idx, loser_idx, reason)
        """
        a = candidates[idx_a]
        b = candidates[idx_b]

        conf_a = self._get_conf_val(a)
        conf_b = self._get_conf_val(b)

        # 1. Higher Confidence Wins
        if conf_a > conf_b:
            return idx_a, idx_b, rule_reason
        if conf_b > conf_a:
            return idx_b, idx_a, rule_reason

        # 2. Tie -> Engine Priority
        prio_a = self.priority.get(a['engine_name'], -1)
        prio_b = self.priority.get(b['engine_name'], -1)

        if prio_a > prio_b:
            return idx_a, idx_b, f"{rule_reason} (Priority: {a['engine_name']} > {b['engine_name']})"
        if prio_b > prio_a:
            return idx_b, idx_a, f"{rule_reason} (Priority: {b['engine_name']} > {a['engine_name']})"

        # 3. True Tie -> Suppress Both
        return None, None, rule_reason

    def _get_conf_val(self, insight: dict) -> int:
        label = insight.get('confidence') or insight.get('confidence_level') or 'low'
        return self.confidence_ranks.get(label.lower(), 0)

    def _get_label(self, insight: dict) -> str:
        """Extracts the status label regardless of engine-specific key names."""
        # Check common label keys
        keys = ['resolution_label', 'trajectory_label', 'tension_label', 'effect_direction', 'label']
        for k in keys:
            if k in insight:
                return insight[k]
        return "unknown"
