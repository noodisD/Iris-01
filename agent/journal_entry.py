"""
Journal Entry Service Layer

A journal entry *is* a reflection. This module only formats the CLI's
structured prompts (wellbeing / ideas / goals / execution) into the text of one,
then hands it to ReflectionService — the same seam the HTTP API writes through.

It used to write its own `journal_entries` rows instead, so an entry made in the
CLI and an entry made in the UI lived in different tables under different source
types, and neither surface could see the other's. See ADR-0010.
"""

import logging

from .trackers.reflections import ReflectionService

logger = logging.getLogger(__name__)

class JournalEntry:
    """Formats structured journal input and stores it as a reflection."""

    def __init__(self, user_id: int):
        """
        Initialize the journal entry service.

        Args:
            user_id: The ID of the user this service is for.
        """
        if user_id is None:
            raise ValueError("JournalEntry service requires a valid user_id.")
        self.user_id = user_id
        self._reflections = ReflectionService(user_id)

    def create_entry(
        self,
        wellbeing: dict,
        ideas: list[str],
        goals: list[str],
        execution: list[str],
        reflections: str | None = None
    ) -> str:
        """
        Creates a journal entry as a reflection and triggers the pipeline.

        Args:
            wellbeing: Dict with notes, and optionally energy/clarity (1-10).
            ideas: List of insights and ideas.
            goals: List of goal-related items.
            execution: List of accomplishments.
            reflections: Optional open-ended reflection.

        Returns:
            A confirmation message with the new entry's ID.
        """
        logger.info(f"Creating new journal entry for user {self.user_id}")

        content = self._format_raw_text(wellbeing, ideas, goals, execution, reflections)

        try:
            # ReflectionService owns mood inference and the pipeline call, so a
            # CLI entry and a UI entry are indistinguishable downstream.
            entry_id = self._reflections.create_reflection(
                content=content,
                energy_level=wellbeing.get('energy'),
                clarity_level=wellbeing.get('clarity'),
                tags=wellbeing.get('tags'),
            )
            logger.info(f"Journal entry {entry_id} saved as a reflection for user {self.user_id}.")
            return f"✓ Journal Entry Created (ID: {entry_id}). Processing has started."

        except Exception as e:
            logger.error(f"Failed to create journal entry for user {self.user_id}: {e}")
            return "✗ Failed to create journal entry. Please check the logs."

    def _format_raw_text(
        self,
        wellbeing: dict,
        ideas: list[str],
        goals: list[str],
        execution: list[str],
        reflections: str | None
    ) -> str:
        """Formats the structured journal data into a single string."""

        parts = []

        wb_notes = wellbeing.get('notes', 'N/A')
        parts.append(f"Wellbeing Notes: {wb_notes}")

        if ideas:
            parts.append("\nIdeas:")
            for idea in ideas:
                parts.append(f"- {idea}")

        if goals:
            parts.append("\nGoals:")
            for goal in goals:
                parts.append(f"- {goal}")

        if execution:
            parts.append("\nExecution:")
            for item in execution:
                parts.append(f"- {item}")

        if reflections:
            parts.append(f"\nReflections:\n{reflections}")

        return "\n".join(parts)
