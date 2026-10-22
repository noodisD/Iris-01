"""
Habit Tracker Service Layer

Provides business logic for managing habits, completions, and streaks.
"""

import logging
from datetime import date, datetime, timedelta

from ..database import db
from ..work_queue import notify

logger = logging.getLogger(__name__)

class HabitTracker:
    """Manages habits for a user with streak tracking and completion logging."""

    def __init__(self, user_id: int):
        if not user_id:
            raise ValueError("user_id is required")
        self.user_id = user_id

    # ========== CRUD Operations ==========

    def create_habit(
        self,
        name: str,
        description: str | None = None,
        frequency_type: str = "daily",
        habit_type: str = "completion",
        weekly_target: float = 0,
        tracking_metric: str = "completion",
        category: str = "general",
        frequency_target: int = 1,
    ) -> int:
        """Create a new habit. Returns habit ID."""
        habit_id = db.create_habit(
            self.user_id, name, description, frequency_type,
            habit_type, weekly_target, tracking_metric, category, frequency_target
        )
        notify()  # queued in the same commit as the habit
        return habit_id

    def get_habits(self, active_only: bool = True) -> list[dict]:
        """Get all habits for this user."""
        return db.get_habits(self.user_id, active_only)

    def get_habit(self, habit_id: int) -> dict | None:
        """Get a specific habit by ID."""
        habit = db.get_habit(habit_id)
        if habit and habit["user_id"] != self.user_id:
            return None  # User can only access their own habits
        return habit

    def update_habit(self, habit_id: int, **updates) -> bool:
        """Update a habit's properties."""
        habit = self.get_habit(habit_id)
        if not habit:
            return False
        return db.update_habit(habit_id, **updates)

    def delete_habit(self, habit_id: int) -> bool:
        """Soft-delete a habit (mark as inactive)."""
        habit = self.get_habit(habit_id)
        if not habit:
            return False
        return db.delete_habit(habit_id)

    # ========== Completion & Skip Logging ==========

    def log_completion(
        self,
        habit_id: int,
        completion_date: date | None = None,
        value: float = 1.0,
        notes: str | None = None
    ) -> int:
        """Log a habit completion."""
        if completion_date is None:
            completion_date = date.today()
        completion_id = db.log_habit_completion(habit_id, completion_date, value, notes)

        notify()  # queued in the same commit as the completion

        return completion_id

    def log_skip(
        self,
        habit_id: int,
        skip_date: date | None = None,
        reason: str | None = None
    ) -> int:
        """Log an intentional skip."""
        if skip_date is None:
            skip_date = date.today()
        skip_id = db.log_habit_skip(habit_id, skip_date, reason)

        # A skip is evidence the pattern did NOT occur, so it is deliberately
        # not sent through the analytical pipeline. It used to be embedded as
        # "Anchor: Yoga | ... | Action: Skipped", a vector dominated by the
        # habit's own name, so skipping a habit reinforced its theme and could
        # make trajectory report it as increasing while it was being abandoned.
        return skip_id

    # ========== Streak Management ==========

    def update_streaks(self, habit_id: int) -> dict:
        """Recount a habit's streaks from its days (agent/trackers/streaks.py) and store them.

        The counters are written back even when nothing is left, or undoing a
        habit's only tick would leave its old streak on show.
        """
        from .streaks import compute

        habit = self.get_habit(habit_id)
        if not habit:
            return {"current_streak": 0, "longest_streak": 0, "total_completions": 0}
        days = db.get_habit_days(habit_id)
        done = {d["date"] for d in days if d["status"] == "done"}
        skipped = {d["date"] for d in days if d["status"] == "skipped"}
        streak = compute(habit.get("frequency_type") or "daily", habit.get("frequency_target") or 1,
                         done, skipped, date.today())
        db.update_habit(habit_id, current_streak=streak.current, longest_streak=streak.longest,
                        total_completions=len(done))
        return {"current_streak": streak.current, "longest_streak": streak.longest,
                "total_completions": len(done), "period_done": streak.period_done}

    def set_day(self, habit_id: int, day: date, status: str, note: str | None) -> dict:
        """Mark one day done, skipped or neither, with a note; then recount the streaks."""
        if day > date.today():
            raise ValueError("A day that has not happened yet cannot be marked.")
        result = db.set_habit_day(habit_id, day, status, note)
        if result is not None:
            notify()
        self.update_streaks(habit_id)
        return {"date": day.isoformat(), "status": status if result else "none",
                "note": (result or {}).get("note")}

    def get_streak_info(self, habit_id: int) -> dict:
        """Get streak information for a habit."""
        habit = self.get_habit(habit_id)
        if not habit:
            return {}
        return {
            "current_streak": habit["current_streak"],
            "longest_streak": habit["longest_streak"],
            "total_completions": habit["total_completions"]
        }

    # ========== Queries & Analytics ==========

    def get_today_status(self) -> list[dict]:
        """Get all habits with today's completion status."""
        habits = self.get_habits(active_only=True)
        today = date.today()

        for habit in habits:
            completions = db.get_habit_completions(habit["id"])
            today_completion = next(
                (c for c in completions if c["completion_date"] == today),
                None
            )
            habit["completed_today"] = bool(today_completion and today_completion["is_completed"])
            habit["skipped_today"] = bool(today_completion and today_completion["is_skipped"])
            habit["today_value"] = today_completion["value"] if today_completion else 0

            # Add weekly progress info
            habit["weekly_progress"] = self.get_weekly_progress(habit["id"])

        return habits

    def get_weekly_progress(self, habit_id: int) -> dict:
        """Calculate progress towards weekly target."""
        habit = db.get_habit(habit_id)
        if not habit or habit["weekly_target"] <= 0:
            return {"current": 0, "target": 0, "percent": 0}

        today = date.today()
        # Assume week starts on Monday (0)
        start_of_week = today - timedelta(days=today.weekday())

        completions = db.get_habit_completions(habit_id, start_of_week, today)
        current_total = sum(c["value"] for c in completions if c["is_completed"])

        percent = (current_total / habit["weekly_target"] * 100) if habit["weekly_target"] > 0 else 0

        return {
            "current": current_total,
            "target": habit["weekly_target"],
            "metric": habit["tracking_metric"],
            "percent": round(min(percent, 100), 1),
            "is_met": current_total >= habit["weekly_target"]
        }

    def get_weekly_summary(self) -> dict:
        """Get completion statistics for the past 7 days."""
        habits = self.get_habits(active_only=True)
        today = date.today()
        week_start = today - timedelta(days=6)

        summary = {
            "period": f"{week_start} to {today}",
            "habits": []
        }

        for habit in habits:
            completions = db.get_habit_completions(habit["id"], week_start, today)
            completed = sum(1 for c in completions if c["is_completed"])
            skipped = sum(1 for c in completions if c["is_skipped"])
            total_value = sum(c["value"] for c in completions if c["is_completed"])

            summary["habits"].append({
                "id": habit["id"],
                "name": habit["name"],
                "completed": completed,
                "skipped": skipped,
                "total_value": total_value,
                "weekly_target": habit["weekly_target"],
                "metric": habit["tracking_metric"],
                "total_days": len(completions),
                "completion_rate": f"{(completed / 7 * 100):.0f}%" if completed > 0 else "0%"
            })

        return summary

    def get_calendar(
        self,
        habit_id: int,
        start_date: date,
        end_date: date
    ) -> list[dict]:
        """Get completion calendar for a habit in a date range."""
        completions = db.get_habit_completions(habit_id, start_date, end_date)

        calendar = []
        current_date = start_date
        completion_map = {c["completion_date"]: c for c in completions}

        while current_date <= end_date:
            completion = completion_map.get(current_date)
            if completion:
                calendar.append({
                    "date": current_date,
                    "completed": completion["is_completed"],
                    "skipped": completion["is_skipped"],
                    "notes": completion["notes"]
                })
            else:
                calendar.append({
                    "date": current_date,
                    "completed": False,
                    "skipped": False,
                    "notes": None
                })
            current_date += timedelta(days=1)

        return calendar

    def get_consistency_report(self, days: int = 30) -> dict:
        """Generate a consistency report across all habits."""
        habits = self.get_habits(active_only=True)
        today = date.today()
        start_period = today - timedelta(days=days - 1)

        report = {
            "period_days": days,
            "start_date": start_period,
            "end_date": today,
            "habits": []
        }

        for habit in habits:
            # Improved: Calculate relative consistency
            # Divisor is the MINIMUM of (requested days) and (days since creation)
            creation_date = habit['created_at'].date() if hasattr(habit['created_at'], 'date') else datetime.fromisoformat(str(habit['created_at'])).date()
            days_since_creation = (today - creation_date).days + 1
            effective_days = min(days, days_since_creation)

            completions = db.get_habit_completions(habit["id"], start_period, today)
            completed = sum(1 for c in completions if c["is_completed"])

            # Prevent division by zero
            completion_rate = (completed / effective_days * 100) if effective_days > 0 else 0

            report["habits"].append({
                "id": habit["id"],
                "name": habit["name"],
                "completed": completed,
                "total_days": effective_days,
                "completion_rate": f"{completion_rate:.1f}%"
            })

        return report
