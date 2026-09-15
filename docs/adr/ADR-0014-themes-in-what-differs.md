# ADR-0014: Themes are found in what differs between entries

## Status
Accepted — 2026-09-15

## Context
The first real import (156 entries from four journaling tools, 2023–2026)
formed three themes, and one of them held 121 of the 132 entries that grouped
at all. The Insights screen had one thing to say.

No threshold was individually wrong. One person's writing shares a voice: a
single direction carried two-thirds of the variance across those embeddings,
and the typical entry scored 0.84 against the average of all of them. Measured
raw, a theme's centroid — fixed when the theme forms, averaged from its founding
entries — is mostly that shared voice, so almost every entry cleared the 0.70
match bar against it. Matching took the first theme past the bar, and themes
are listed largest first, so the biggest theme took every borderline entry and
kept growing.

A replay of the real process over the stored embeddings reproduced the result
exactly, which is what made it possible to compare alternatives rather than
guess.

Two other effects were visible once the collapse was gone: entries from the
earlier IRIS journal grouped by *format*, because every one began with the same
prompts ("What went well:", "Key insight:"); and dates assigned without direct
evidence (a template's creation minute, a parent page's date) piled entries onto
single days and produced themes that were really artefacts of dating.

## Decision

**Similarity is measured with the user's shared voice removed.** Once a user
has `PERSISTENCE_STYLE_MIN_ENTRIES` (30) evidence embeddings, their average is
subtracted from both the entry and the centroid before comparing. Thresholds
in that space are 0.40 to join a theme and 0.50 to form one; the raw thresholds
(0.70 / 0.78) still apply below 30 entries, where the average is mostly the
entries themselves. The values were chosen by replaying the real data: they
gave themes that each span several months and several sources with no
near-duplicate members.

**An entry joins the closest theme, not the first above the bar.**

**A theme forms only where every pair of its founding entries is similar.**
Clustering is complete linkage at the creation threshold. DBSCAN, used before,
linked A to B and B to C, and the cohesion check then rejected the whole chain:
after three entries were re-embedded, one entry bridged two good themes into a
chain of 21 that was thrown away, and the rebuild grouped 25 of 138 entries.
Removing any single entry changed how many themes formed in 75 of 138 runs with
DBSCAN and in 18 with complete linkage, which grouped 74 of 138 into six themes.

**The prompts a tool wrote are not embedded.** The stored entry keeps its
labels so each answer still says what it answered; the embedded text leaves out
the labels listed in `agent/prompt_labels.py`, and a test holds the importer to
that list.

**Themes are rebuildable.** They are derived: occurrences point at entries that
do not move. `rebuild_themes(user_id)` deletes a user's themes and every cached
analysis keyed by their ids, clusters all evidence in one pass, offers each
ungrouped entry to the result oldest first, and refreshes the cross-theme
analyses.

## Consequences
Fewer entries belong to a theme. On the owner's journal about half did (74 of
138), against 85% before; that is the point — an entry that resembles nothing in particular is
not evidence of a recurring pattern — but the product has less to say early on.

The average moves as evidence accumulates, so a theme formed from early data is
compared in a slightly different space later. It does not invalidate the theme,
but after a large import the honest move is a rebuild.

A rebuild changes theme ids. Anything keyed by theme id outside the pattern
caches — a dismissed or snoozed insight — does not carry over.

Crossing 30 entries changes how new entries are matched, without regrouping
what came before. A rebuild at that point is cheap and gives a consistent
starting set; it is not automatic.
