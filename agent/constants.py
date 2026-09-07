"""Minimal configuration constants for IRIS Companion (Essential Only)"""

# LLM Settings
DEFAULT_TEMPERATURE = 0.7  # Ignored by models that accept only their default
# A cap, not a reservation: you pay for tokens generated, not for headroom. On a
# reasoning model the thinking is drawn from this same budget, so a cap that
# looks generous for the visible answer can leave nothing for it — the call
# still succeeds and returns "". These are sized so that cannot happen.
DEFAULT_MAX_TOKENS = 2000

# Persistence Engine Configuration
PERSISTENCE_MATCH_THRESHOLD = 0.70    # Loose threshold for matching new entries to EXISTING themes
PERSISTENCE_CLUSTER_THRESHOLD = 0.78  # Strict threshold for creating NEW themes
PERSISTENCE_MIN_CLUSTER_SIZE = 5      # Minimum entries required to form a theme (Proto-Theme boundary)
PERSISTENCE_DORMANT_MONTHS = 3        # Themes inactive for this long go dormant (future feature)

# Evidence Weights (Source Reliability)
EVIDENCE_WEIGHTS = {
    "reflection": 1.0,
    "journal_entry": 0.9,
    "habit_completion": 0.5,          # Default tick
    "habit_completion_with_notes": 0.8 # Tick with context
}

# Trajectory Engine Configuration
TRAJECTORY_RECENT_DAYS = 14
TRAJECTORY_BASELINE_DAYS = 60
TRAJECTORY_DELTA_THRESHOLD = 0.05
TRAJECTORY_MIN_DATA_POINTS = 3  # Minimum occurrences for reliable classification
TRAJECTORY_MIN_SLOPE_POINTS = 2  # Minimum points for slope calculation

# Tension Engine Configuration
TENSION_MIN_COOCCURRENCE = 3
TENSION_RECENT_DAYS = 14
TENSION_BASELINE_DAYS = 60
TENSION_MIN_STABILITY = 0.3
# CONTEXT.md: "Themes must show divergence (trajectory directions differ)". A
# dead zone, so noise around zero is not read as a direction: below this the two
# themes are treated as moving together, which is correlation, not tension.
TENSION_MIN_DIVERGENCE = 0.05
TENSION_MIN_OCCURRENCES = 5  # Minimum occurrences for a theme to be considered
TENSION_MAX_THEMES_FOR_PAIRS = 20  # Soft upper bound on theme pairs to consider

# Resolution Engine Configuration
# Time windows for detecting resolution states
RESOLUTION_RECENT_DAYS = 21         # Longer window (3 weeks) to confirm silence isn't just a pause
RESOLUTION_BASELINE_DAYS = 90       # Look back 3 months to establish a baseline
RESOLUTION_DELTA_EPSILON = 0.05     # Threshold for "stable" vs "changing" (5% deviation)
RESOLUTION_MIN_DATA_POINTS = 3      # Minimum occurrences to even attempt classification
# Resolution compares a rolling recent window against a rolling baseline, so the
# answer changes as time passes even when no new data arrives — a theme goes
# quiet and becomes 'dissipated' by the calendar alone. A cached verdict is
# therefore only good for a day; without this, a non-null computation timestamp
# counted as fresh forever and a 2020 verdict could be served in 2026.
RESOLUTION_CACHE_TTL_HOURS = 24

# Leverage Engine Configuration
LEVERAGE_WINDOW_DAYS = 60          # Timeframe to analyze influence (last 2 months)
LEVERAGE_TIME_LAG_DAYS = 7         # Max lag to consider influence (A precedes B within 7 days)
LEVERAGE_MIN_OCCURRENCES = 5       # Minimum total occurrences for a pattern to be considered
LEVERAGE_MIN_CO_OCCURRENCES = 3    # Minimum evidence threshold for a pair
LEVERAGE_ASYMMETRY_THRESHOLD = 0.15 # Minimum lift to consider as directional leverage

# Decision Impact Engine Configuration
DECISION_IMPACT_WINDOW_DAYS = 14        # Post-anchor observation window
DECISION_IMPACT_BASELINE_DAYS = 60      # Prior behavior reference establishing "normal"
DECISION_IMPACT_MIN_ANCHORS = 3         # Minimum anchor events to analyze
DECISION_IMPACT_MIN_DELTA = 0.15        # Minimum relative change to count
DECISION_IMPACT_MIN_DATA_POINTS = 5     # Per target pattern for reliability
DECISION_IMPACT_BASELINE_EPSILON = 0.01 # Threshold below which rate is treated as zero

# Confidence & Reliability Engine Configuration
# 1. Scoring Weights (Must sum to 1.0 when consistency is present)
CONF_WEIGHT_SUFFICIENCY = 0.4
CONF_WEIGHT_CONSISTENCY = 0.4
CONF_WEIGHT_RECENCY = 0.2

# 2. Classification Policy (Gatekeeper thresholds)
CONF_MIN_POINTS = 3
CONF_MEDIUM_POINTS = 5
CONF_HIGH_POINTS = 10

CONF_RECENCY_DAYS = 30          # Evidence older than this decays (1/e at 30 days)
CONF_CONSISTENCY_THRESHOLD = 0.7 # Minimum ratio for "high" consistency

# Conflict Suppression Configuration
CONFLICT_SUPPRESSION_ENABLED = True
CONFLICT_MIN_CONFIDENCE = "medium"

# Priority order (higher index = higher priority)
ENGINE_PRIORITY = [
    "tension",
    "leverage",
    "decision_impact",
    "trajectory",
    "resolution"
]

# Insight Prioritization Engine Configuration
# 1. Scoring Weights
PRIORITY_CONFIDENCE_WEIGHT = 0.35
PRIORITY_RECENCY_WEIGHT = 0.20
PRIORITY_MAGNITUDE_WEIGHT = 0.20
PRIORITY_NOVELTY_WEIGHT = 0.15
PRIORITY_ENGINE_WEIGHT = 0.10

# 2. Engine Base Weights (Multiplier bounded 0.6 - 1.0)
ENGINE_BASE_WEIGHTS = {
    "resolution": 1.0,
    "trajectory": 0.9,
    "decision_impact": 0.85,
    "leverage": 0.8,
    "tension": 0.7,
    "persistence": 0.6
}

PRIORITY_MAX_ITEMS = 5
PRIORITY_MIN_CONFIDENCE = "medium"
PRIORITY_RECENT_DECAY_DAYS = 30
PRIORITY_NOVELTY_LOOKBACK_DAYS = 90

# Note: Weights must sum to 1.0
_priority_weights_sum = (
    PRIORITY_CONFIDENCE_WEIGHT +
    PRIORITY_RECENCY_WEIGHT +
    PRIORITY_MAGNITUDE_WEIGHT +
    PRIORITY_NOVELTY_WEIGHT +
    PRIORITY_ENGINE_WEIGHT
)
assert abs(_priority_weights_sum - 1.0) < 1e-6, f"Priority weights must sum to 1.0, got {_priority_weights_sum}"

# Note: Rates are normalized per-day counts over their respective windows
