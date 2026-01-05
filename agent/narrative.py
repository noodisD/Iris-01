"""
Narrative Formatter - Non-Interpretive Fact Rendering

This module does not interpret, explain, infer, advise, or connect insights.
It only renders pre-validated facts into neutral language.
Any violation is treated as a system error.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from .narrative_policy import FORBIDDEN_REGEX, NARRATIVE_FAIL_MODE
from .narrative_templates import NARRATIVE_TEMPLATES

logger = logging.getLogger(__name__)

class NarrativeFormatter:
    """
    Standardizes the natural language expression of analytical insights.
    """

    @staticmethod
    def format_all(insights: List[Dict[str, Any]]) -> List[str]:
        """
        Renders a prioritized list of insights into narratives while 
        strictly preserving list order.
        """
        narratives = []
        for ins in insights:
            text = NarrativeFormatter.format_insight(ins)
            if text:
                narratives.append(text)
        return narratives

    @staticmethod
    def format_insight(insight: Dict[str, Any]) -> Optional[str]:
        """
        Selects a template and populates it using evidence fields.
        """
        engine = insight.get('engine_name')
        template = NARRATIVE_TEMPLATES.get(engine)
        
        if not template:
            logger.error(f"No narrative template found for engine: {engine}")
            return None

        try:
            # 1. Prepare data mapping
            data = NarrativeFormatter._prepare_template_data(engine, insight)
            
            # 2. Interpolate
            rendered = template.format(**data)
            
            # 3. Validate safety
            NarrativeFormatter._validate_safety(rendered)
            
            return rendered
            
        except Exception as e:
            if NARRATIVE_FAIL_MODE == "raise":
                raise e
            logger.error(f"Narrative failure for {engine}: {e}")
            return None

    @staticmethod
    def _prepare_template_data(engine: str, ins: Dict[str, Any]) -> Dict[str, Any]:
        """Maps insight fields to template placeholders."""
        # Generic mappings
        data = {
            "pattern_name": ins.get('summary') or ins.get('theme_summary') or "Unknown Pattern",
            "target_name": ins.get('target_summary') or ins.get('theme_b_summary') or "Related Pattern",
            "metric_value": ins.get('occurrence_count') or ins.get('delta_score') or 0,
            "label": NarrativeFormatter._sanitize_label(ins),
            "time_window": NarrativeFormatter._get_time_description(ins)
        }
        return data

    @staticmethod
    def _sanitize_label(ins: Dict) -> str:
        """Extracts and normalizes classification labels."""
        raw = (ins.get('resolution_label') or 
               ins.get('trajectory_label') or 
               ins.get('effect_direction') or 
               ins.get('label') or "")
        
        # Normalize common labels into descriptive fragments
        mappings = {
            "increasing": "increased",
            "fading": "decreased",
            "emerging": "emerged",
            "dissipated": "has not appeared",
            "reappearing": "has reappeared",
            "stabilized": "stabilized",
            "emergence": "emerged",
            "increase": "increased",
            "fade": "decreased"
        }
        return mappings.get(raw.lower(), raw)

    @staticmethod
    def _get_time_description(ins: Dict) -> str:
        """Extracts temporal bounds from insight."""
        first = ins.get('first_seen_at')
        if first:
            if not isinstance(first, datetime):
                first = datetime.fromisoformat(str(first))
            return first.strftime("%Y-%m-%d")
        
        # Fallback for engine-specific window constants
        if ins.get('engine_name') == 'decision_impact':
            return "14"
        return "the recent period"

    @staticmethod
    def _validate_safety(text: str):
        """
        Enforces the cognitive firewall using lemma-safe regex.
        Raises ValueError if forbidden language is detected.
        """
        match = FORBIDDEN_REGEX.search(text)
        if match:
            forbidden_word = match.group()
            raise ValueError(
                f"Narrative violation: Forbidden word '{forbidden_word}' detected in output: '{text}'"
            )
