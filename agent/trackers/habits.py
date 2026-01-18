"""
Habit Tracker Service Layer

Provides business logic for managing habits, completions, and streaks.
"""

from datetime import date, timedelta
from typing import Dict, List, Optional
from ..database import db

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
        description: Optional[str] = None,
        frequency_type: str = "daily",
        habit_type: str = "completion",
        weekly_target: float = 0,
        tracking_metric: str = "completion",
        category: str = "general"
    ) -> int:
        """Create a new habit. Returns habit ID."""
        return db.create_habit(
            self.user_id, name, description, frequency_type,
            habit_type, weekly_target, tracking_metric, category
        )

    def get_habits(self, active_only: bool = True) -> List[Dict]:
        """Get all habits for this user."""
        return db.get_habits(self.user_id, active_only)

    def get_habit(self, habit_id: int) -> Optional[Dict]:
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
        completion_date: Optional[date] = None,
        value: float = 1.0,
        notes: Optional[str] = None
    ) -> int:
        """Log a habit completion."""
        if completion_date is None:
            completion_date = date.today()
        return db.log_habit_completion(habit_id, completion_date, value, notes)

    def log_skip(
        self,
        habit_id: int,
        skip_date: Optional[date] = None,
        reason: Optional[str] = None
    ) -> int:
        """Log an intentional skip."""
        if skip_date is None:
            skip_date = date.today()
        return db.log_habit_skip(habit_id, skip_date, reason)

    # ========== Streak Management ==========

    def update_streaks(self, habit_id: int) -> Dict:
        """
        Recalculate and update streak counters for a habit.
        Returns dict with current_streak, longest_streak, total_completions.
        """
        habit = self.get_habit(habit_id)
        if not habit:
            return {"current_streak": 0, "longest_streak": 0, "total_completions": 0}

        completions = db.get_habit_completions(habit_id)

        if not completions:
            return {"current_streak": 0, "longest_streak": 0, "total_completions": 0}

        # Sort completions by date (newest first)
        sorted_completions = sorted(
            completions,
            key=lambda x: x["completion_date"],
            reverse=True
        )

        # Count total completions
        total_completions = sum(1 for c in completions if c["is_completed"])

        # Calculate current streak (consecutive days from today backwards)
        # Note: For weekly habits, streak calculation could be different,
        # but for now we keep daily consecutive completion streak.
        current_streak = 0
        current_date = date.today()
        
        # Check if completed today or yesterday (to maintain streak)
        # If not completed today, streak might still be active if completed yesterday
        for completion in sorted_completions:
            if completion["is_completed"]:
                if completion["completion_date"] == current_date:
                    current_streak += 1
                    current_date -= timedelta(days=1)
                elif completion["completion_date"] == current_date - timedelta(days=1):
                    # We missed today but yesterday was done
                    if current_date == date.today():
                        current_date -= timedelta(days=1)
                        current_streak += 1
                        current_date -= timedelta(days=1)
                    else:
                        break
                else:
                    break
            else:
                break

        # Calculate longest streak
        longest_streak = 0
        temp_streak = 0
        prev_date = None

        for completion in sorted(completions, key=lambda x: x["completion_date"]):
            if completion["is_completed"]:
                if prev_date is None or (prev_date + timedelta(days=1) == completion["completion_date"]):
                    temp_streak += 1
                else:
                    longest_streak = max(longest_streak, temp_streak)
                    temp_streak = 1
                prev_date = completion["completion_date"]
            else:
                longest_streak = max(longest_streak, temp_streak)
                temp_streak = 0
                prev_date = None

        longest_streak = max(longest_streak, temp_streak)

        # Update habit record
        db.update_habit(
            habit_id,
            current_streak=current_streak,
            longest_streak=longest_streak,
            total_completions=total_completions
        )

        return {
            "current_streak": current_streak,
            "longest_streak": longest_streak,
            "total_completions": total_completions
        }

    def get_streak_info(self, habit_id: int) -> Dict:
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

    def get_today_status(self) -> List[Dict]:
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

    def get_weekly_progress(self, habit_id: int) -> Dict:
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

    def get_weekly_summary(self) -> Dict:
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
    ) -> List[Dict]:
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

    def get_consistency_report(self, days: int = 30) -> Dict:
        """Generate a consistency report across all habits."""
        habits = self.get_habits(active_only=True)
        start_date = date.today() - timedelta(days=days - 1)
        end_date = date.today()

        report = {
            "period_days": days,
            "start_date": start_date,
            "end_date": end_date,
            "habits": []
        }

        for habit in habits:
            completions = db.get_habit_completions(habit["id"], start_date, end_date)
            completed = sum(1 for c in completions if c["is_completed"])
            completion_rate = (completed / days * 100) if days > 0 else 0

            report["habits"].append({
                "id": habit["id"],
                "name": habit["name"],
                "completed": completed,
                "total_days": days,
                "completion_rate": f"{completion_rate:.1f}%"
            })

        return report
