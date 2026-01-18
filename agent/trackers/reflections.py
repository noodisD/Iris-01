"""
Reflection Service Layer

Provides business logic for managing reflections and mood tracking.
"""

from datetime import date, timedelta
from typing import Dict, List, Optional
from ..database import db

class ReflectionService:
    """Manages reflections and mood tracking for a user."""

    def __init__(self, user_id: int):
        if not user_id:
            raise ValueError("user_id is required")
        self.user_id = user_id

    # ========== CRUD Operations ==========

    def create_reflection(
        self,
        content: str,
        reflection_date: Optional[date] = None,
        mood: Optional[str] = None,
        energy_level: Optional[int] = None,
        tags: Optional[List[str]] = None
    ) -> int:
        """Create a new reflection. Returns reflection ID."""
        if not content or not content.strip():
            raise ValueError("Reflection content cannot be empty")

        if mood and mood not in ["great", "good", "okay", "bad", "terrible"]:
            raise ValueError("Invalid mood value")

        if energy_level and not (1 <= energy_level <= 5):
            raise ValueError("Energy level must be between 1 and 5")

        return db.create_reflection(
            self.user_id,
            content,
            reflection_date,
            mood,
            energy_level,
            tags
        )

    def get_reflections(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 30
    ) -> List[Dict]:
        """Get recent reflections for this user."""
        reflections = db.get_reflections(self.user_id, limit)

        # Filter by date range if provided
        if start_date or end_date:
            filtered = []
            for reflection in reflections:
                refl_date = reflection["reflection_date"]
                if start_date and refl_date < start_date:
                    continue
                if end_date and refl_date > end_date:
                    continue
                filtered.append(reflection)
            return filtered

        return reflections

    def get_reflection(self, reflection_id: int) -> Optional[Dict]:
        """Get a specific reflection by ID."""
        reflection = db.get_reflection(reflection_id)
        if reflection and reflection["user_id"] != self.user_id:
            return None  # User can only access their own reflections
        return reflection

    def update_reflection(self, reflection_id: int, **updates) -> bool:
        """Update a reflection's fields."""
        reflection = self.get_reflection(reflection_id)
        if not reflection:
            return False

        # Validate mood if being updated
        if "mood" in updates and updates["mood"]:
            if updates["mood"] not in ["great", "good", "okay", "bad", "terrible"]:
                raise ValueError("Invalid mood value")

        # Validate energy_level if being updated
        if "energy_level" in updates and updates["energy_level"]:
            if not (1 <= updates["energy_level"] <= 5):
                raise ValueError("Energy level must be between 1 and 5")

        return db.update_reflection(reflection_id, **updates)

    def delete_reflection(self, reflection_id: int) -> bool:
        """Delete a reflection."""
        reflection = self.get_reflection(reflection_id)
        if not reflection:
            return False
        return db.delete_reflection(reflection_id)

    # ========== Analytics ==========

    def get_recent_moods(self, days: int = 7) -> List[Dict]:
        """Get mood data for the past N days."""
        start_date = date.today() - timedelta(days=days - 1)
        reflections = self.get_reflections(start_date=start_date)

        moods = [
            {
                "date": r["reflection_date"],
                "mood": r["mood"],
                "energy_level": r["energy_level"]
            }
            for r in reflections
            if r["mood"] or r["energy_level"]
        ]

        return sorted(moods, key=lambda x: x["date"], reverse=True)

    def get_mood_trend(self, days: int = 30) -> Dict:
        """Analyze mood and energy trends over a period."""
        start_date = date.today() - timedelta(days=days - 1)
        end_date = date.today()
        reflections = self.get_reflections(start_date=start_date, end_date=end_date)

        # Count moods
        mood_counts = {
            "great": 0,
            "good": 0,
            "okay": 0,
            "bad": 0,
            "terrible": 0
        }

        energy_levels = []
        total_reflections = len(reflections)

        for reflection in reflections:
            if reflection["mood"]:
                mood_counts[reflection["mood"]] += 1
            if reflection["energy_level"]:
                energy_levels.append(reflection["energy_level"])

        # Calculate average energy level
        avg_energy = (
            sum(energy_levels) / len(energy_levels)
            if energy_levels
            else None
        )

        return {
            "period_days": days,
            "start_date": start_date,
            "end_date": end_date,
            "total_reflections": total_reflections,
            "mood_distribution": mood_counts,
            "average_energy_level": round(avg_energy, 2) if avg_energy else None,
            "most_common_mood": max(
                (k for k, v in mood_counts.items() if v > 0),
                default=None
            )
        }

    def get_tag_summary(self, days: int = 30) -> Dict:
        """Get a summary of tags used in reflections."""
        start_date = date.today() - timedelta(days=days - 1)
        reflections = self.get_reflections(start_date=start_date)

        tag_counts = {}
        for reflection in reflections:
            tags = reflection.get("tags", []) or []
            for tag in tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        # Sort by frequency
        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)

        return {
            "period_days": days,
            "total_tags": len(tag_counts),
            "tags": [{"tag": tag, "count": count} for tag, count in sorted_tags]
        }

    def get_reflection_summary(self, days: int = 30) -> Dict:
        """Get a comprehensive summary of reflections."""
        start_date = date.today() - timedelta(days=days - 1)
        reflections = self.get_reflections(start_date=start_date)

        return {
            "period_days": days,
            "total_reflections": len(reflections),
            "mood_trend": self.get_mood_trend(days),
            "tags": self.get_tag_summary(days),
            "recent": reflections[:5]
        }
