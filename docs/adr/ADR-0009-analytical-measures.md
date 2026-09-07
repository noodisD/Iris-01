# ADR-0009: Analytical measures must mean what they are named

## Status
Accepted — 2026-09-07

## Context
Four measures did not compute the quantity their name and narrative promised.

- Trajectory regressed *cumulative count* against time. A cumulative count only
  rises, so the slope was positive for every real series — a constant cadence of
  one entry a day scored +1.0. Since the classifier falls through to the slope
  precisely when the frequency is steady, "stable" was unreachable and a habit
  kept at the same rate for two months was reported as increasing.
- Leverage counted (source, target) *pairs* and divided by the number of *source
  events*, so a value documented as `P(target | source)` reached 3.4.
- Decision impact divided by the full 14-day follow-up window however little of
  it had elapsed, so three anchors one to three days old over a perfectly steady
  target produced "decrease" with a delta of −0.76.
- Leverage's confidence came from the source's occurrences alone and never
  depended on the target, so a coincidental relation scored exactly as
  confidently as a reliable one.

## Decision
A measure computes the quantity it is named for, within stated bounds:

- A trend is a change in *rate* — the weighted count per week regressed against
  the week — not an accumulation.
- A conditional probability counts *events*, is bounded in [0, 1], and a lift as
  a difference of two of them is bounded in [−1, 1].
- Right-censored evidence is excluded rather than estimated: an anchor whose
  follow-up window has not elapsed cannot be judged.
- Confidence in a relation is computed from the relation's own evidence.
- Time windows compare durations, never `timedelta.days`, whose truncation made
  eight days minus a microsecond register as seven.

## Consequences
Classifications changed. "Stable" is now reachable, "decreasing" is now
reachable, and recent decisions no longer appear to have reduced whatever
followed them.

New measures need fixtures where the correct answer is known by construction —
constant, accelerating, decelerating, time-reversed — written before the
implementation. Four existing tests were found to be asserting the old, wrong
behaviour or using data that did not express what they claimed; each was
corrected in place with the arithmetic recorded.
