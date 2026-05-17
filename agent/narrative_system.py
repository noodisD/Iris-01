"""
Narrative Formatting and Safety System - Separated Concerns

This module splits narrative generation into three clean components:

1. TemplateRenderer: Converts insights into human-readable text
2. SafetyValidator: Checks output against safety rules (independent of rendering)
3. TemplateRegistry: Manages available templates and validates them at boot

Benefits:
- Safety is enforced proactively (validate templates at boot, not runtime)
- Rendering and validation are independent (swap either without affecting the other)
- Clear data flow: insight -> template -> rendered text -> validation -> output
- Failing validations are logged with context (which template, which insight)
- New templates must pass validation before being registered
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
import logging
import re

logger = logging.getLogger(__name__)

# Safety guardrails: forbidden verbs that suggest causality or unsolicited advice
FORBIDDEN_CAUSAL_VERBS = {
    'caused', 'causes', 'caused by',
    'triggered', 'triggers',
    'led to', 'leads to',
    'resulted in', 'results in',
    'due to', 'because',
    'should', 'must', 'ought',
    'implies', 'suggests responsibility',
    'means', 'indicates',
}

# Compile regex patterns once for efficiency
FORBIDDEN_PATTERNS = [
    re.compile(r'\b' + verb + r'\b', re.IGNORECASE)
    for verb in FORBIDDEN_CAUSAL_VERBS
]


class SafetyValidator:
    """Validates narrative text against safety rules.

    This validator is stateless and can be used independently of rendering.
    It checks for forbidden causal language that might mislead the user.
    """

    @staticmethod
    def validate(text: str) -> Tuple[bool, Optional[str]]:
        """Check if text violates safety rules.

        Args:
            text: Narrative text to validate

        Returns:
            Tuple of (is_safe, violation_reason)
                - is_safe: True if text passes all checks
                - violation_reason: String describing the violation, or None if safe
        """
        for pattern in FORBIDDEN_PATTERNS:
            match = pattern.search(text)
            if match:
                violation = match.group(0)
                return False, f"Contains forbidden causal language: '{violation}'"

        # Check for other patterns that suggest advice
        if re.search(r'you should.*do', text, re.IGNORECASE):
            return False, "Contains unsolicited advice"

        return True, None

    @staticmethod
    def validate_template(template: str) -> Tuple[bool, Optional[str]]:
        """Validate a template string (before runtime).

        Args:
            template: Template string with placeholders like {pattern_name}

        Returns:
            Tuple of (is_valid, error_reason)
        """
        # Try to detect obvious problems
        # (This is a simple check; actual validation happens at render time)
        if not isinstance(template, str):
            return False, "Template must be a string"

        if not template.strip():
            return False, "Template cannot be empty"

        return True, None


class TemplateRenderer:
    """Renders insights into narrative using templates.

    Templates are simple format strings with field placeholders.
    This renderer handles:
    - Field extraction and validation
    - Placeholder substitution
    - Fallback values for missing fields
    - Error handling
    """

    @staticmethod
    def render(template: str, insight: Dict[str, Any]) -> Optional[str]:
        """Render a template with insight data.

        Args:
            template: Format string with {field} placeholders
            insight: Data dict with fields to substitute

        Returns:
            Rendered text, or None if rendering failed
        """
        if not template or not isinstance(template, str):
            return None

        try:
            # Extract fields from insight, providing sensible defaults
            fields = {
                'pattern_name': insight.get('summary', insight.get('label', 'Pattern')),
                'label': insight.get('label', 'Insight'),
                'confidence': insight.get('confidence_level', 'unknown'),
                'metric_value': insight.get('metric_value', 'N/A'),
                'engine': insight.get('engine_name', 'Analysis'),
                'recent_count': insight.get('recent_count', '?'),
                'past_count': insight.get('past_count', '?'),
                'attenuation': insight.get('attenuation_score', 'N/A'),
                'slope': insight.get('slope', 'N/A'),
                'influence': insight.get('influence_score', 'N/A'),
            }

            # Render template
            rendered = template.format(**fields)
            return rendered

        except KeyError as e:
            logger.error(f"Template rendering failed: missing field {e}")
            return None
        except Exception as e:
            logger.error(f"Template rendering error: {e}")
            return None


class TemplateRegistry:
    """Manages narrative templates and validates them at registration.

    Templates must pass safety validation before being registered.
    This ensures all templates are safe at startup, not at runtime.
    """

    def __init__(self):
        """Initialize registry."""
        self.templates: Dict[str, Dict[str, str]] = {}
        self._validation_errors: Dict[str, str] = {}

    def register_template(self, engine_name: str, pattern_type: str,
                         template: str) -> bool:
        """Register a template after validating it.

        Args:
            engine_name: Engine that produced the insight (e.g. 'persistence')
            pattern_type: Type of pattern (e.g. 'theme')
            template: Template string with {placeholders}

        Returns:
            True if registered successfully, False if validation failed
        """
        key = f"{engine_name}:{pattern_type}"

        # Validate template syntax
        is_valid, error = SafetyValidator.validate_template(template)
        if not is_valid:
            logger.error(f"Template validation failed for {key}: {error}")
            self._validation_errors[key] = error
            return False

        # Render a test example to catch formatting issues
        test_insight = {
            'summary': 'Test Pattern',
            'label': 'Test Insight',
            'confidence_level': 'high',
            'engine_name': engine_name,
        }

        test_rendered = TemplateRenderer.render(template, test_insight)
        if not test_rendered:
            error_msg = f"Template rendering failed for {key}"
            logger.error(error_msg)
            self._validation_errors[key] = error_msg
            return False

        # Validate rendered text against safety rules
        is_safe, violation = SafetyValidator.validate(test_rendered)
        if not is_safe:
            logger.error(f"Template safety check failed for {key}: {violation}")
            self._validation_errors[key] = violation
            return False

        # All checks passed
        self.templates[key] = template
        logger.debug(f"Template registered: {key}")
        return True

    def get_template(self, engine_name: str, pattern_type: str) -> Optional[str]:
        """Get template for an engine/pattern combination.

        Args:
            engine_name: Engine name
            pattern_type: Pattern type

        Returns:
            Template string, or None if not found
        """
        key = f"{engine_name}:{pattern_type}"
        return self.templates.get(key)

    def get_validation_errors(self) -> Dict[str, str]:
        """Get all template validation errors (useful for debugging)."""
        return self._validation_errors.copy()

    def is_valid(self) -> bool:
        """Check if all registered templates are valid."""
        return len(self._validation_errors) == 0


class NarrativeFormatter:
    """High-level facade combining rendering and validation.

    Usage:
        formatter = NarrativeFormatter(registry)
        narrative = formatter.format(insight)
        if narrative is None:
            # Insight was suppressed for safety reasons
    """

    def __init__(self, registry: TemplateRegistry):
        """Initialize formatter with a template registry.

        Args:
            registry: Registered and validated templates
        """
        self.registry = registry
        self.validator = SafetyValidator()
        self.renderer = TemplateRenderer()

    def format(self, insight: Dict[str, Any]) -> Optional[str]:
        """Format an insight into a narrative.

        Returns None if the insight cannot be safely formatted.

        Args:
            insight: Insight dict to format

        Returns:
            Formatted narrative string, or None if suppressed
        """
        engine_name = insight.get('engine_name', 'unknown')
        pattern_type = insight.get('pattern_type', 'theme')

        # 1. Get template
        template = self.registry.get_template(engine_name, pattern_type)
        if not template:
            logger.warning(f"No template for {engine_name}:{pattern_type}")
            return None

        # 2. Render
        rendered = self.renderer.render(template, insight)
        if not rendered:
            logger.warning(f"Rendering failed for {engine_name}: {insight.get('label')}")
            return None

        # 3. Validate
        is_safe, violation = self.validator.validate(rendered)
        if not is_safe:
            logger.warning(f"Safety validation failed for {engine_name}: {violation}")
            return None

        return rendered

    def format_batch(self, insights: List[Dict[str, Any]]) -> List[str]:
        """Format multiple insights, filtering out unsafe ones.

        Args:
            insights: List of insight dicts

        Returns:
            List of formatted narratives (safe ones only)
        """
        results = []
        for insight in insights:
            narrative = self.format(insight)
            if narrative is not None:
                results.append(narrative)
        return results


# Default template registry for the system
_default_registry = TemplateRegistry()

# Register standard templates
_default_templates = {
    'persistence:theme': "The pattern '{pattern_name}' has appeared {recent_count} times recently.",
    'trajectory:theme': "The pattern '{pattern_name}' is showing a {label} trend.",
    'tension:theme': "The patterns '{pattern_name}' and another pattern tend to co-occur.",
    'resolution:theme': "The pattern '{pattern_name}' has {label} after appearing regularly before.",
    'leverage:theme': "The pattern '{pattern_name}' tends to precede other patterns.",
    'decision_impact:theme': "The pattern '{pattern_name}' appears to co-occur with changes in other patterns.",
}

for (engine, ptype), template_str in _default_templates.items():
    _default_registry.register_template(engine, ptype, template_str)


def get_default_registry() -> TemplateRegistry:
    """Get the system's default template registry."""
    return _default_registry


def get_default_formatter() -> NarrativeFormatter:
    """Get a formatter using the default registry."""
    return NarrativeFormatter(_default_registry)
