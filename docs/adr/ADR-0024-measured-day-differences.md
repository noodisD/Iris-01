# ADR-0024: Day differences are measured, not written

## Status
Accepted — 2026-09-26

## Context
ADR-0017 admits confirmed phone readings as sensor evidence, not journal
entries. The owner also records five 1–10 check-in outcomes. A day feature
built from confirmed Pixel, Health Connect or Timeline readings can be compared
with a check-in on the same calendar day. It must not masquerade as something
the owner wrote, or turn a difference between days into an explanation.

## Decision
`agent/day_differences.py` compares day-level check-ins against the
coordinate-free `day_features` cache. An outcome has one value per day; when
several check-ins share a day, their values are averaged. Energy uses the
journal's `energy_level`; mood, sleep quality, stress and focus use only
metrics explicitly sourced from a check-in. Missing values never become zero.

The fixed splits are office versus home days, and above versus below the
owner's own median for commute time, full-day steps, screen time, the share of
screen time in social/video/game apps, and sleep time. Median ties are omitted.
Office/home and commute use only days with at least 50% location coverage.
A comparison appears only with at least five days on **each** side, a gap of
at least 1.0 on the 1–10 outcome scale, and a two-sided p-value at most 0.01
from 2,000 seeded plain-Python permutation shuffles. These thresholds are not
loosened to fill the screen.

Every displayed sentence states both means and both day counts. The Insights
section labels these as measurements from the phone or Timeline, not causes.
Comparisons are computed, not quoted, embedded, or written into reflections.
`day_difference_verdicts` stores the owner's answer per outcome and split; a
verdict survives a comparison disappearing after more data or a reclassification.
Only comparisons currently qualifying **and** marked `rings_true` enter the
approved chat block, labelled "measured by the phone and Timeline; never
causes". Chat still sends that block only when the owner asks it a question.
No model is called to compute or judge a day difference.

## Consequences
A small or uneven sample shows no comparison. A small p-value is a threshold
for showing a difference, not evidence of causation; self-reports, collection
coverage and unmeasured circumstances can differ between the two sides. The
owner's verdict is preserved, but does not override the fixed display gate.
Named place coordinates remain on the laptop; the comparison API and phone
screen receive only derived minutes, counts, means and verdicts.
