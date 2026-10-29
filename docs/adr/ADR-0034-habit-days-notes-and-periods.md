# ADR-0034: Any habit day can be fixed, each day can carry a note, and habits can be weekly or monthly

## Status
Accepted — 2026-10-22

## Context
The owner sometimes did a habit but forgot to tick it that day, and nothing on screen
could fix it: the server accepted any date, but the page only ever sent today. A
habit day had a note field nobody could write. Habits had a weekly frequency type,
but streaks were only ever counted day by day, and a monthly habit was impossible.
Unticking a day deleted the row, so a note on it would have been lost, and ticking
overwrote an existing note.

## Decision
The owner chose each of these in conversation.
- **Days are fixed, streaks follow.** Any day up to today can be marked done, skipped
  (a deliberate rest) or neither, on the habit's own page (a month calendar). The
  streak is always counted from the days (`agent/trackers/streaks.py`) and is never a
  number to set: a fixed day fixes it. A skipped day pauses a daily streak; a period in
  progress does not break one.
- **A note belongs to a day,** whatever the day's status. Chat recalls it as what the
  day was ("Did …", "Skipped …", "Note on …"). Notes are not read for patterns.
- **Only a done day is evidence.** A note on a skipped or unmarked day is embedded for
  recall and never counted as an occurrence or a written day.
- **Daily, weekly and monthly habits** (migration 0055), each with a target per period
  (`frequency_target`: "3 times a week"). A weekly or monthly streak counts consecutive
  weeks (Monday to Sunday) or calendar months that met the target. The Habits page has
  a tab for each (`/habits/daily`, `/habits/weekly`, `/habits/monthly`).
- **A habit can be edited, archived (history kept) or deleted (history removed, with
  everything derived from it), after a confirmation.**
- **Web first, then the phone.** The phone app's Habits screen followed on 2026-10-26
  with the same tabs, day notes, past days and order, on the same API.

## Consequences
- Forgotten days are no longer lost, and streaks always agree with the days.
- A habit day can hold the owner's reflection, which chat can bring back.
- Clustering, occurrences and "days written" count only done days.
