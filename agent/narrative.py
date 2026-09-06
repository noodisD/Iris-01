"""
Narrative Formatter - Non-Interpretive Fact Rendering

This module does not interpret, explain, infer, advise, or connect insights.
It only renders pre-validated facts into neutral language.
Any violation is treated as a system error.
"""

import logging
from datetime import datetime
from typing import Any

from .narrative_policy import FORBIDDEN_REGEX, NARRATIVE_FAIL_MODE
from .narrative_templates import NARRATIVE_TEMPLATES

logger = logging.getLogger(__name__)

class NarrativeFormatter:
    """
    Standardizes the natural language expression of analytical insights.
    """

    @staticmethod
    def format_all(insights: list[dict[str, Any]]) -> list[str]:
        """
        Renders a prioritized list of insights into narratives while
        strictly preserving list order.
        """
        logger.debug(f"NarrativeFormatter.format_all received {len(insights)} insights")
        for i, ins in enumerate(insights):
            logger.debug(f"  Insight {i}: engine={ins.get('engine_name')}, resolution_label={ins.get('resolution_label')}, trajectory_label={ins.get('trajectory_label')}, theme_id={ins.get('theme_id')}")

        narratives = []
        for ins in insights:
            text = NarrativeFormatter.format_insight(ins)
            if text:
                narratives.append(text)
        return narratives

    @staticmethod
    def format_insight(insight: dict[str, Any]) -> str | None:
        """
        Selects a template and populates it using evidence fields.
        """
        engine = insight.get('engine_name')
        template = NARRATIVE_TEMPLATES.get(engine)

        if not template:
            logger.error(f"No narrative template found for engine: {engine}")
            logger.debug(f"  Insight: {insight}")
            return None

        try:
            # 1. Prepare data mapping
            data = NarrativeFormatter._prepare_template_data(engine, insight)
            logger.debug(f"Format_insight: engine={engine}, insight_keys={list(insight.keys())}, data={data}")

            # 2. Interpolate
            rendered = template.format(**data)

            # 3. Validate safety
            NarrativeFormatter._validate_safety(rendered)

            logger.debug(f"Rendered narrative: {rendered}")
            return rendered

        except Exception as e:
            if NARRATIVE_FAIL_MODE == "raise":
                raise e
            logger.error(f"Narrative failure for {engine}: {e}", exc_info=True)
            return None

    @staticmethod
    def _prepare_template_data(engine: str, ins: dict[str, Any]) -> dict[str, Any]:
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
    def _sanitize_label(ins: dict) -> str:
        """Extracts and normalizes classification labels."""
        resolution_label = ins.get('resolution_label')
        trajectory_label = ins.get('trajectory_label')
        effect_direction = ins.get('effect_direction')
        generic_label = ins.get('label')

        raw = resolution_label or trajectory_label or effect_direction or generic_label or ""

        logger.debug(f"Sanitize label: resolution_label={resolution_label}, trajectory_label={trajectory_label}, effect_direction={effect_direction}, generic_label={generic_label}, selected_raw={raw}")

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
        result = mappings.get(raw.lower(), raw)
        logger.debug(f"Sanitize result: {result} (mapped from raw={raw})")
        return result

    @staticmethod
    def _get_time_description(ins: dict) -> str:
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
