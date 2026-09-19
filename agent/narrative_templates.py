"""
Narrative Templates - Evidence-Only Phrasing

Static templates for rendering verified facts into neutral natural language.
No interpretation slots allowed.
"""

from .constants import ENGINE_PRIORITY

# Every engine whose findings reach a conversation. Persistence used to be added
# here; it still finds themes, but lifelong reports on them now.
ENGINE_NAMES = set(ENGINE_PRIORITY)

NARRATIVE_TEMPLATES = {
    "trajectory": "The pattern '{pattern_name}' {label}: {recent_count} times in the last {trajectory_recent_days} days, against {past_count} in the {trajectory_baseline_days} days before.",

    "tension": "The patterns '{pattern_name}' and '{target_name}' appeared on {cooccurrence_count} of the same days, with diverging activity levels.",

    "resolution": "The pattern '{pattern_name}' appeared {past_count} times in the {resolution_baseline_days} days before the last {resolution_recent_days}, and {recent_count} times in them; it {label}.",

    "leverage": "The pattern '{pattern_name}' was followed by '{target_name}' within {leverage_lag_days} days more often than the reverse, across {cooccurrence_count} co-occurrences.",

    "decision_impact": "Following occurrences of '{pattern_name}', the pattern '{target_name}' {label} in the subsequent {decision_window_days} days.",

    # Says when it started and how the occurrences sat across the span, never
    # how things are now — this engine makes no present-tense claim, which is
    # what lets it past the coverage gate.
    #
    # Two phrasings, because there are two findings. The undated one has no
    # span to quote, and the default template would have filled {time_window}
    # from a fallback reading "the recent period" — dating, in a sentence, the
    # writing whose whole distinguishing property is that its date is unknown.
    # It says where the number came from instead.
    "lifelong": {
        "default": "The pattern '{pattern_name}' appeared {metric_value} times since {time_window}; its occurrences were {label}.",
        # A span, and undated occurrences beside it. The label is scoped to
        # "those occurrences" — the dated ones — because concentration is
        # measured by year, and an occurrence with no year cannot be
        # concentrated or spread. The undated count is added as its own clause
        # rather than into the number the span is quoted beside (ADR-0009).
        "with_undated": "The pattern '{pattern_name}' appeared {metric_value} times since {time_window}, and those occurrences were {label}; it appeared {undated_count} more times in writing that carries no date.",
        # Says how many of the occurrences are undated, not that all of them
        # are. A theme with ten undated occurrences and two dated ones reaches
        # this phrasing because two cannot carry a span — and "appeared 12
        # times in writing that carries no date" would be false about two of
        # them. A count and a claim about where it came from are two
        # measurements (ADR-0009).
        "undated": "The pattern '{pattern_name}' appeared {metric_value} times, {undated_count} of them in writing that carries no date; no span is given.",
    },
}

# Runtime coverage check
assert set(NARRATIVE_TEMPLATES.keys()) == ENGINE_NAMES, \
    f"Missing templates for: {ENGINE_NAMES - set(NARRATIVE_TEMPLATES.keys())}"

# A variant set must be able to answer a request it has no phrasing for, or an
# engine emitting an unknown variant would render nothing and the insight would
# vanish silently rather than fail.
assert all("default" in v for v in NARRATIVE_TEMPLATES.values() if isinstance(v, dict)), \
    "every set of template variants needs a 'default'"
