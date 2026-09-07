# ADR-0007: Chat and the Insights screen answer with one policy

## Status
Accepted — 2026-09-07

## Context
`InsightsService` called the analytical engines directly with no gating: no
confidence threshold, no conflict suppression, no user preferences. The chat
context applied all three. So a finding chat discarded as low-confidence, or
silenced because it contradicted another, was still presented on the Insights
screen as something IRIS believed. Two surfaces, one question, two answers.

## Decision
Both paths apply the same admission policy, using the same components and the
same user preferences: engine enablement, the user's confidence threshold, then
conflict suppression.

The budget is the one deliberate difference. A cap of five exists because that
is what fits usefully in an LLM prompt; it is not a claim about what is true,
and the screen is a list the user scrolls, so it is ordered by strength rather
than truncated.

Policy governs what is *surfaced*, not what is *addressable*: fetching one
insight by id still returns it, so a link keeps working and snooze/resolve
continue to act on an insight the list no longer shows.

## Consequences
A user cannot be shown a finding on one screen that IRIS refuses to say in
conversation.

Any new surface that presents insights must route through the same policy, and
any new gate must be added in one place rather than per-surface.
