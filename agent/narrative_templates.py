"""
Narrative Templates - Evidence-Only Phrasing

Static templates for rendering verified facts into neutral natural language.
No interpretation slots allowed.
"""

from .constants import ENGINE_PRIORITY

# Add persistence to the list of engines requiring templates
ENGINE_NAMES = set(ENGINE_PRIORITY) | {"persistence"}

NARRATIVE_TEMPLATES = {
    "persistence": "The pattern '{pattern_name}' appeared frequently, totaling {metric_value} occurrences since {time_window}.",

    "trajectory": "The pattern '{pattern_name}' {label} in frequency over the recent period.",

    "tension": "The patterns '{pattern_name}' and '{target_name}' frequently appeared during the same periods with diverging activity levels.",

    "resolution": "The pattern '{pattern_name}' appeared frequently in the past but {label} recently.",

    "leverage": "The pattern '{pattern_name}' frequently preceded other patterns within a short temporal window.",

    "decision_impact": "Following occurrences of '{pattern_name}', the pattern '{target_name}' {label} in the subsequent {time_window} days."
}

# Runtime coverage check
assert set(NARRATIVE_TEMPLATES.keys()) == ENGINE_NAMES, \
    f"Missing templates for: {ENGINE_NAMES - set(NARRATIVE_TEMPLATES.keys())}"
