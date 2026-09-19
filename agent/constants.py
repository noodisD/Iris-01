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

# Once a user has enough evidence, themes are compared on what differs between
# entries: the user's average embedding (their shared voice) is removed first,
# and these thresholds apply in that space (ADR-0014). Measured on the owner's
# real journal, where raw thresholds put 121 of 132 grouped entries in one theme.
PERSISTENCE_STYLE_MIN_ENTRIES = 30        # Below this the average is mostly the entries themselves
PERSISTENCE_STYLE_MATCH_THRESHOLD = 0.40  # Join an existing theme, shared voice removed
PERSISTENCE_STYLE_CLUSTER_THRESHOLD = 0.50  # Form a new theme, shared voice removed

# Evidence Weights (Source Reliability)
EVIDENCE_WEIGHTS = {
    "reflection": 1.0,
    "habit_completion": 0.5,          # Default tick
    "habit_completion_with_notes": 0.8 # Tick with context
}

# Trajectory Engine Configuration
TRAJECTORY_RECENT_DAYS = 14
TRAJECTORY_BASELINE_DAYS = 60
TRAJECTORY_DELTA_THRESHOLD = 0.05
TRAJECTORY_MIN_DATA_POINTS = 3  # Minimum occurrences for reliable classification

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
# The same bound for a theme's stored confidence, which was reused forever once
# written: recency is one of its components, so the same evidence scores
# differently tomorrow, and a record that is never recomputed stops describing it.
CONFIDENCE_CACHE_TTL_HOURS = 24

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
# A baseline shorter than the follow-up window cannot establish what "normal"
# was: the before/after comparison would have less evidence before than after.
DECISION_IMPACT_MIN_BASELINE_DAYS = DECISION_IMPACT_WINDOW_DAYS

# Confidence & Reliability Engine Configuration
# 1. Scoring Weights (Must sum to 1.0 when consistency is present)
CONF_WEIGHT_SUFFICIENCY = 0.4
CONF_WEIGHT_CONSISTENCY = 0.4
CONF_WEIGHT_RECENCY = 0.2

# 2. Classification Policy (Gatekeeper thresholds)
CONF_MIN_POINTS = 3
CONF_HIGH_POINTS = 10

CONF_RECENCY_DAYS = 30          # Evidence older than this decays (1/e at 30 days)
# A pattern is a claim about behaviour over time, so "high confidence" has to
# mean the evidence spans some. Ten entries written in one sitting are ten data
# points and one observation.
CONF_MIN_COVERAGE_DAYS_FOR_HIGH = 7
CONF_CONSISTENCY_THRESHOLD = 0.7 # Minimum ratio for "high" consistency

# --- Confidence in an observed absence --------------------------------------
# "This stopped happening" is not the same claim as "this happened recently",
# and the ordinary recency decay scores it backwards: the longer a silence runs,
# the *more* it confirms a dissipation, but the lower recency drives the score.
# A freshly computed dissipation needs RESOLUTION_RECENT_DAYS of silence, at
# which point exp(-21/30) = 0.4966 — permanently below the 0.5 the 'high' branch
# requires — so a dissipation could never be high-confidence at all.
#
# Silence is maximally convincing once it has run twice the length that defines
# it. Beyond that, more silence adds nothing.
CONF_ABSENCE_SILENCE_SATURATION_MULTIPLE = 2.0
# Below this share of the user's own prior logging rate, we were not watching
# closely enough to call the silence evidence of anything.
CONF_ABSENCE_MIN_CONTINUITY = 0.34
CONF_ABSENCE_HIGH_CONTINUITY = 0.67
# Continuity as a bare ratio is maxed out by a single day: one entry either side
# of a silence scored 1.0, so ten occurrences written in one sitting and one
# entry yesterday came back "high, 1.0" — higher than eight occurrences with
# weekly logging right through the quiet (0.82). Watching means watching on
# several days, and a claim that something *stopped* needs the baseline to have
# lasted longer than one afternoon.
CONF_ABSENCE_MIN_OBSERVED_DAYS = 3      # distinct days logged during the silence
CONF_ABSENCE_MIN_BASELINE_SPAN_DAYS = 7  # a burst on one day is one observation

# How many distinct days must be logged in the recent window before IRIS may
# describe the present at all. One entry after months of silence is a sign of
# life, not a basis for saying how things are (agent/coverage.py).
COVERAGE_MIN_OBSERVED_DAYS = 3

# --- Lifelong scale (agent/lifelong.py) -------------------------------------
# The other engines look through a 14-to-90-day window. On an archive spanning
# 27 months that is a keyhole: 0 of 19 themes had an occurrence in the last 90
# days, while 14 of them had three or more across the whole record. The evidence
# was there and no engine could reach it.
#
# This scale counts the same occurrences over the whole span. It makes no claim
# about the present — it says what recurred and when — so the coverage gate
# lets it through where it withholds a present-tense finding.
LIFELONG_MIN_OCCURRENCES = 3      # below this it is an incident, not a pattern
LIFELONG_MIN_SPAN_DAYS = 90       # three occurrences in a week is a burst
#: When most of a pattern's occurrences fall in one year, say so rather than
#: implying it ran evenly throughout.
LIFELONG_CONCENTRATION_SHARE = 0.6

# --- Reading entries (agent/observations.py) --------------------------------
# A claim resting on one entry is an anecdote. Two entries is the floor for
# calling something recurrent, and the confidence levels below need more.
OBSERVATION_MIN_CITATIONS = 2
OBSERVATION_MIN_ENTRIES_CITED = 2
# Short enough to be a coincidence: "the gym" appears in half the archive and
# proves nothing about anything.
OBSERVATION_MIN_QUOTE_CHARS = 16
OBSERVATION_MAX_ENTRIES_READ = 60
# Distinct entries and days of span required before an observation is more than
# tentatively held.
OBSERVATION_HIGH_ENTRIES = 4
OBSERVATION_HIGH_SPAN_DAYS = 30
OBSERVATION_MEDIUM_ENTRIES = 3

# Reading the whole archive happens in chunks: one pass over ~110K tokens
# produces generalities, and the months are wildly uneven (two of them hold 50
# of 135 entries while four hold one each), so chunks accumulate to a token
# budget rather than a fixed entry count.
OBSERVATION_CHUNK_TOKENS = 20_000
#: Rough chars-per-token, good enough for deciding where to cut a chunk.
OBSERVATION_CHARS_PER_TOKEN = 4
# A staged recording below this is a near-empty clip, not writing. The real
# batch has six at 22-165 characters and the next one up is 1,108: a clean
# cliff, and nothing that short can carry a quote worth citing.
OBSERVATION_MIN_STAGED_CHARS = 200

# How much two findings must have in common before they are one finding.
# Measured as Jaccard over cited entries, not "any entry in common": the
# transcripts run to 22,000 characters and several unrelated findings quote the
# same one, so a single shared citation joined claims about three unrelated
# subjects. Complete linkage does not help here — every pair in such
# a group genuinely shares the bridge, so its condition is satisfied — which is
# why the ratio is the rule and not the linkage strategy.
OBSERVATION_MERGE_OVERLAP = 0.5

# A reasoning model spends this budget on thinking first and emits nothing if it
# runs out — the call succeeds, returns empty, and the pass is lost. At 1,500 a
# real archive read produced finish_reason=length with 1,500 reasoning tokens
# and no output, twice. Reading a chunk and citing it needs room for both.
OBSERVATION_MAX_TOKENS = 16_000

# Conflict Suppression Configuration
CONFLICT_MIN_CONFIDENCE = "medium"

# Priority order (higher index = higher priority)
ENGINE_PRIORITY = [
    # First, which is the lowest priority: a finding about a two-year span
    # should yield to one about this fortnight when both describe the same theme
    # and only one can be shown. It is the wider context, not the news. It sat
    # last, under a comment saying it yielded — and since a higher index wins,
    # it won every tie it was meant to lose.
    "lifelong",
    "tension",
    "leverage",
    "decision_impact",
    "trajectory",
    "resolution",
]

# Every engine the owner may switch on or off. Not the same list as the one
# above: ENGINE_PRIORITY is an *ordering*, used to break ties during conflict
# suppression and ranking, and observations take part in neither — they are
# reviewed and confirmed rather than ranked against other findings.
#
# Settings built its allow-list out of ENGINE_PRIORITY, so "observations" was
# never a valid value. The moment the owner customised their engines at all,
# apply_preferences dropped every observation, and nothing in Settings could
# put it back.
SELECTABLE_ENGINES = set(ENGINE_PRIORITY) | {"observations"}

# Insight Prioritization Engine Configuration
# 1. Scoring Weights
# In seventeenths: these were 0.35 / 0.20 / 0.20 / 0.10 beside a 15% "novelty"
# term that no engine ever set, so it added the same 0.075 to every finding and
# decided nothing. Dropping it and scaling the rest by 1/0.85 keeps every ratio.
# The ranker sorts on the total rounded to three places, so two findings within
# a thousandth of each other can now fall to the tie-breakers the other way; on
# the live archive that swapped two adjacent pairs below the tenth place.
PRIORITY_CONFIDENCE_WEIGHT = 7 / 17
PRIORITY_RECENCY_WEIGHT = 4 / 17
PRIORITY_MAGNITUDE_WEIGHT = 4 / 17
PRIORITY_ENGINE_WEIGHT = 2 / 17

# 2. Engine Base Weights (Multiplier bounded 0.6 - 1.0)
ENGINE_BASE_WEIGHTS = {
    "resolution": 1.0,
    "trajectory": 0.9,
    "decision_impact": 0.85,
    "leverage": 0.8,
    "tension": 0.7,
    # The lowest, for the reason ENGINE_PRIORITY puts it first. Absent, it took
    # the 0.6 default — the weight of persistence, which is not a finding any
    # more: lifelong reports the same counts over the span they belong to.
    "lifelong": 0.5,
}

PRIORITY_RECENT_DECAY_DAYS = 30

# Note: Weights must sum to 1.0
_priority_weights_sum = (
    PRIORITY_CONFIDENCE_WEIGHT +
    PRIORITY_RECENCY_WEIGHT +
    PRIORITY_MAGNITUDE_WEIGHT +
    PRIORITY_ENGINE_WEIGHT
)
assert abs(_priority_weights_sum - 1.0) < 1e-6, f"Priority weights must sum to 1.0, got {_priority_weights_sum}"

# Note: Rates are normalized per-day counts over their respective windows
