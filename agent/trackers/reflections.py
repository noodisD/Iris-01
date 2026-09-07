"""
Reflection Service Layer

Provides business logic for managing reflections and mood tracking.
"""

import logging
from datetime import date, timedelta

from ..database import db
from ..work_queue import enqueue

logger = logging.getLogger(__name__)

class ReflectionService:
    """Manages reflections and mood tracking for a user."""

    def __init__(self, user_id: int):
        if not user_id:
            raise ValueError("user_id is required")
        self.user_id = user_id

    # ========== CRUD Operations ==========

    def _infer_mood(self, tags: list[str]) -> str:
        """Infers a general mood from emotional tags."""
        if not tags:
            return "okay"

        # Normalize tags
        tags = [t.lower() for t in tags]

        positive = {"excited", "inspired", "proud", "content", "calm", "grateful", "hopeful", "great", "good"}
        negative = {"stressed", "anxious", "frustrated", "tired", "bad", "terrible", "sad"}

        pos_count = sum(1 for t in tags if t in positive)
        neg_count = sum(1 for t in tags if t in negative)

        if pos_count > 0 and neg_count == 0:
            return "great" if "excited" in tags or "inspired" in tags else "good"
        if neg_count > 0 and pos_count == 0:
            return "bad"
        return "okay"

    def create_reflection(
        self,
        content: str,
        reflection_date: date | None = None,
        energy_level: int | None = None,
        clarity_level: int | None = None,
        tags: list[str] | None = None
    ) -> int:
        """Create a new reflection. Returns reflection ID."""
        if not content or not content.strip():
            raise ValueError("Reflection content cannot be empty")

        if energy_level and not (1 <= energy_level <= 10):
            raise ValueError("Energy level must be between 1 and 10")

        if clarity_level and not (1 <= clarity_level <= 10):
            raise ValueError("Clarity level must be between 1 and 10")

        # Auto-infer mood
        mood = self._infer_mood(tags or [])

        reflection_id = db.create_reflection(
            self.user_id,
            content,
            reflection_date,
            mood,
            energy_level,
            clarity_level,
            tags
        )

        # The reflection is stored. Turning it into evidence is queued, so a
        # provider outage delays that work instead of losing it.
        enqueue('reflection', reflection_id, self.user_id)

        return reflection_id

    def get_reflections(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 30,
        before_id: int | None = None
    ) -> list[dict]:
        """Get this user's reflections, newest first, filtered in the database."""
        return db.get_reflections(
            self.user_id, limit, before_id, start_date=start_date, end_date=end_date
        )

    def get_reflection(self, reflection_id: int) -> dict | None:
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

        # Validate energy_level if being updated
        if updates.get("energy_level"):
            if not (1 <= updates["energy_level"] <= 10):
                raise ValueError("Energy level must be between 1 and 10")

        # Validate clarity_level if being updated
        if updates.get("clarity_level"):
            if not (1 <= updates["clarity_level"] <= 10):
                raise ValueError("Clarity level must be between 1 and 10")

        updated = db.update_reflection(reflection_id, **updates)

        # An edit to the text invalidates everything derived from it. Without
        # this, the embedding still described the original wording and the theme
        # occurrence still quoted it, so a sentence the user had removed stayed
        # searchable and could still be quoted back at them. Re-running the
        # pipeline recomputes both from the corrected text.
        if updated and "content" in updates:
            with db.connection() as conn, conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM theme_occurrences WHERE source_type = 'reflection' AND source_id = %s;",
                    (reflection_id,)
                )
                cur.execute(
                    "DELETE FROM embeddings WHERE source_type = 'reflection' AND source_id = %s;",
                    (reflection_id,)
                )
                conn.commit()
            # Derived rows for the old wording were just deleted; queue the
            # re-analysis of the new wording.
            enqueue('reflection', reflection_id, self.user_id)

        return updated

    def delete_reflection(self, reflection_id: int) -> bool:
        """Delete a reflection."""
        reflection = self.get_reflection(reflection_id)
        if not reflection:
            return False
        return db.delete_reflection(reflection_id)

    # ========== Analytics ==========

    def get_recent_moods(self, days: int = 7) -> list[dict]:
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

    def get_mood_trend(self, days: int = 30) -> dict:
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

    def get_tag_summary(self, days: int = 30) -> dict:
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

    def get_reflection_summary(self, days: int = 30) -> dict:
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
