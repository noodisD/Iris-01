"""
Journal Entry Service Layer

This module provides a high-level interface for interacting with journal entries.
It acts as a service layer, delegating persistence to the database layer and
orchestrating post-processing via the pipeline layer.
"""

import logging
from typing import Dict, List, Optional

# Import the new architecture's components
from .database import db, journals
from .pipeline import run_processing_pipeline

logger = logging.getLogger(__name__)

class JournalEntry:
    """Manages the business logic for journal entries."""

    def __init__(self, user_id: int):
        """
        Initialize the journal entry service.

        Args:
            user_id: The ID of the user this service is for.
        """
        if user_id is None:
            raise ValueError("JournalEntry service requires a valid user_id.")
        self.user_id = user_id

    def create_entry(
        self,
        wellbeing: Dict,
        ideas: List[str],
        goals: List[str],
        execution: List[str],
        reflections: Optional[str] = None
    ) -> str:
        """
        Creates a new journal entry, saves it to the database,
        and triggers the processing pipeline.

        Args:
            wellbeing: Dict with mood, energy, sleep, etc.
            ideas: List of insights and ideas.
            goals: List of goal-related items.
            execution: List of accomplishments.
            reflections: Optional open-ended reflection.

        Returns:
            A confirmation message with the new entry's ID.
        """
        logger.info(f"Creating new journal entry for user {self.user_id}")

        # 1. Construct the raw text for embedding and future NLP
        raw_text = self._format_raw_text(wellbeing, ideas, goals, execution, reflections)

        try:
            # 2. Save the raw data to PostgreSQL (Source of Truth)
            entry_id = journals.create_entry(
                user_id=self.user_id,
                raw_text=raw_text,
                wellbeing_data=wellbeing
            )
            logger.info(f"Journal entry {entry_id} saved to database for user {self.user_id}.")

            # 3. Trigger the asynchronous processing pipeline
            # In a production app, this would be a message queue (e.g., Celery, RQ)
            # For this project, we'll call it synchronously for simplicity.
            run_processing_pipeline(source_type='journal_entry', source_id=entry_id)
            
            # 4. Return a success message to the user
            return f"✓ Journal Entry Created (ID: {entry_id}). Processing has started."

        except Exception as e:
            logger.error(f"Failed to create journal entry for user {self.user_id}: {e}")
            # In a real app, you'd have more specific error handling
            return "✗ Failed to create journal entry. Please check the logs."

    def _format_raw_text(
        self,
        wellbeing: Dict,
        ideas: List[str],
        goals: List[str],
        execution: List[str],
        reflections: Optional[str]
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

    # NOTE: Read methods (get_entry, get_daily_summary, etc.) would be added here.
    # They would query the PostgreSQL database via the `db` object.
    # For now, we are focusing on the write path.
