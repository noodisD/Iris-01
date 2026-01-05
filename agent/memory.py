"""
Conversation Memory Service Layer

This module provides a high-level interface for managing conversation history.
It uses the database layer for persistence and triggers the processing pipeline
for new messages. It also maintains an in-memory history for the current
session to provide immediate context for the LLM.
"""

import logging
from datetime import datetime
from typing import List, Dict

# Import the new architecture's components
from .database import db
from .pipeline import run_processing_pipeline

logger = logging.getLogger(__name__)

class ConversationMemory:
    """Manages the business logic for conversation history."""

    def __init__(self, user_id: int, session_id: str):
        """
        Initializes the memory service for a specific user and session.

        Args:
            user_id: The ID of the current user.
            session_id: The ID for the current conversation session.
        """
        if user_id is None or session_id is None:
            raise ValueError("ConversationMemory requires a valid user_id and session_id.")
        
        self.user_id = user_id
        self.session_id = session_id
        
        # In-memory history for the current session's immediate context
        self.history: List[Dict[str, str]] = []
        self._load_history_from_db()

    def add_message(self, role: str, content: str):
        """
        Adds a message to the conversation, saves it to the database,
        and triggers the processing pipeline.

        Args:
            role: "user" or "assistant".
            content: The message content.
        """
        logger.info(f"Adding message for user {self.user_id} in session {self.session_id}.")

        # Add to in-memory history for immediate context
        self.history.append({"role": role, "content": content})

        try:
            # 1. Save the message to PostgreSQL
            message_id = db.create_conversation_message(
                user_id=self.user_id,
                session_id=self.session_id,
                role=role,
                content=content
            )
            logger.info(f"Message {message_id} saved to database.")

            # 2. Trigger the processing pipeline
            run_processing_pipeline(source_type='message', source_id=message_id)

        except Exception as e:
            logger.error(f"Failed to save or process message for user {self.user_id}: {e}")
            # The message is in memory, so the conversation can continue.
            # A background job could retry saving later.

    def get_context(self, max_messages: int = 10) -> List[Dict[str, str]]:
        """
        Gets the recent conversation context from the in-memory history.

        Args:
            max_messages: The maximum number of messages to return.

        Returns:
            A list of messages suitable for the LLM API.
        """
        return self.history[-max_messages:]

    def get_full_history(self) -> List[Dict[str, str]]:
        """Gets the full in-memory history for the current session."""
        return self.history.copy()

    def _load_history_from_db(self):
        """Loads the history for the current session from the database."""
        logger.info(f"Loading history for session {self.session_id} from database.")
        # NOTE: This requires a new method in the Database class, e.g.,
        # `get_messages_by_session(user_id, session_id)`.
        # For now, we'll start with an empty history.
        # self.history = db.get_messages_by_session(self.user_id, self.session_id)
        self.history = []

    def clear(self):
        """Clears the in-memory history."""
        self.history = []
        logger.info(f"In-memory history cleared for session {self.session_id}.")
