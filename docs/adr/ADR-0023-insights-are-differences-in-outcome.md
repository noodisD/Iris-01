# ADR-0023: An insight is a difference in outcome

## Status
Accepted — 2026-09-25

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

- A has occasions on both sides, since a side with none compares nothing;
- B's counts on the two sides differ by two or more, the same threshold the
  Patterns screen uses.

The Insights screen, on web and phone, lists every such difference across the
library, largest first, with those still waiting for a verdict at the top. The
owner says whether each rings true. That verdict is stored per pair in
`difference_verdicts` (migration 0032). The differences themselves are
arithmetic over `pattern_labels` and are not stored, so a verdict survives a
difference that later disappears.

Patterns stays as its own screen for what keeps coming up. The old engine's
findings leave both clients. Its `/api/insights` routes and data stay on the
server, and chat still reads through admission.

Nothing here is sent to a model.

## Consequences
An insight is only as good as the labels under it. Labellers err in both
directions, and the counts are small, so every insight is shown with both
sides' counts and called a difference, never a cause or advice. The owner's
verdicts on occasions change the counts, and can dissolve an insight.

With few occasions, few insights qualify. Lowering the threshold would show
more, but mostly coincidences. Revisit it when the reading covers more of the
archive, not to fill the screen.
