# ADR-0023: An insight is a difference in outcome

## Status
Accepted — 2026-09-25 · Threshold and reading lifecycle amended by [ADR-0027](ADR-0027-source-backed-patterns-and-selected-evidence.md)

## Context
The Insights screen showed the old analytical engine's findings: theme
trajectories, tensions, resolutions and the like. The owner judged them to be
from the old method. Replacing that screen with Patterns (library patterns and
the occasions that are instances of them) answered "what keeps coming up",
which the owner called recurring themes: worth keeping, but not insights.

Discovery already computes something closer to an insight. For each pattern it
compares the occasions that went better with those that went worse, by which
other patterns were also present on each side (`agent/alternatives.distinctive`).
On the owner's data that gives 12 differences across 7 patterns.

## Decision
An **insight** is one such difference: pattern A, another pattern B, and B's
count on each side of A's occasions ("when A came up, B was there 5 of 6 times
it went worse, and 1 of 7 times it went better"). It is listed only when:

- A has at least three accepted occasions on each of the better and worse sides;
- B's counts differ by two or more and its shares of the two sides differ by
  at least 25 percentage points (ADR-0027).

The Insights screen, on web and phone, shows these denominator-aware
differences with inspectable source accounts. The owner says whether each
rings true. That verdict is stored per pair in `difference_verdicts` (migration
0032). The differences themselves are arithmetic over current
`pattern_labels` and are not stored, so a verdict survives a difference that
later disappears. Separate exploratory outcome pairs show one better and one
worse occasion from different entries, without claiming a trend.

Patterns stays as its own screen for what keeps coming up. The old engine's
findings leave both clients. Its `/api/insights` routes and data stay on the
server, and chat still reads through admission. Computing a difference calls
no model; an owner-selected conversation can send its current bounded evidence
context to chat after preview and snapshot verification (ADR-0027).

## Consequences
An insight is only as good as the labels under it. Labellers err in both
directions, and the counts are small, so every insight is shown with both
sides' counts and called a difference, never a cause or advice. The owner's
verdicts on occasions change the counts, and can dissolve an insight.

With few occasions, few insights qualify. Lowering the threshold would show
more, but mostly coincidences. Revisit it when the reading covers more of the
archive, not to fill the screen.
