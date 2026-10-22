"""Streaks for daily, weekly and monthly habits, worked out from the days alone.

A streak is never stored as something to edit: it is counted from the days the
owner marked, so fixing a forgotten day fixes the streak, and the number can
never disagree with the history it claims to count.

- **Daily:** consecutive days done. A skipped day (a deliberate rest) pauses the
  streak: it neither adds nor breaks.
- **Weekly / monthly:** consecutive weeks (Monday to Sunday) or calendar months in
  which the habit was done at least `target` times.
- **The current period** counts once it is met, and does not break the streak
  while it is still in progress.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

PERIODS = ("daily", "weekly", "monthly")


@dataclass(frozen=True)
class Streak:
    current: int
    longest: int
    #: Times done in the current period (today, this week, this month).
    period_done: int


def period_start(day: date, frequency: str) -> date:
    if frequency == "weekly":
        return day - timedelta(days=day.weekday())
    if frequency == "monthly":
        return day.replace(day=1)
    return day


def previous_period(start: date, frequency: str) -> date:
    if frequency == "weekly":
        return start - timedelta(days=7)
    if frequency == "monthly":
        last = start - timedelta(days=1)
        return last.replace(day=1)
    return start - timedelta(days=1)


def compute(frequency: str, target: int, done: set[date], skipped: set[date], today: date) -> Streak:
    """The current and longest streak, and how far the current period has got."""
    frequency = frequency if frequency in PERIODS else "daily"
    target = max(1, int(target or 1)) if frequency != "daily" else 1
    counts: dict[date, int] = {}
    for day in done:
        if day <= today:
            start = period_start(day, frequency)
            counts[start] = counts.get(start, 0) + 1
    paused = {d for d in skipped if d <= today} if frequency == "daily" else set()
    now = period_start(today, frequency)
    period_done = counts.get(now, 0)

    def met(start: date) -> bool:
        return counts.get(start, 0) >= target

    # Current: walk back from now; the period in progress may be unmet.
    current, start = 0, now
    if not met(start):
        start = previous_period(start, frequency)
    while start in paused or met(start):
        if met(start):
            current += 1
        start = previous_period(start, frequency)

    # Longest: every run of met periods, pauses bridging, from the first done day.
    longest = run = 0
    if counts:
        start = period_start(min(counts), frequency)
        while start <= now:
            if met(start):
                run += 1
                longest = max(longest, run)
            elif start not in paused and start != now:
                run = 0
            start = _next_period(start, frequency)
    return Streak(current=current, longest=max(longest, current), period_done=period_done)


def _next_period(start: date, frequency: str) -> date:
    if frequency == "weekly":
        return start + timedelta(days=7)
    if frequency == "monthly":
        return (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start + timedelta(days=1)
