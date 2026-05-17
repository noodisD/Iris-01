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
from .database import db, journals
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

        # DB is the source of truth: persist first, then append to in-memory
        # context only on success. This prevents ghost messages that exist in
        # the LLM context but not in the database.
        try:
            message_id = journals.create_conversation_message(
                user_id=self.user_id,
                session_id=self.session_id,
                role=role,
                content=content,
            )
            logger.info(f"Message {message_id} saved to database.")

            self.history.append({"role": role, "content": content})

            # Pipeline failures are logged but do not roll back the message.
            # The message is durable; embedding/theme processing can retry later.
            try:
                run_processing_pipeline(source_type='message', source_id=message_id)
            except Exception as pipeline_err:
                logger.error(
                    f"Pipeline failed for message {message_id} (message persisted): {pipeline_err}"
                )

        except Exception as e:
            logger.error(f"Failed to save message for user {self.user_id}: {e}")
            raise

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
        """Loads recent conversation history from the database to seed session context."""
        logger.info(f"Loading recent history for user {self.user_id} from database.")
        try:
            recent_messages = journals.get_chat_history(self.user_id, limit=20)
            self.history = [
                {"role": msg["role"], "content": msg["content"]}
                for msg in recent_messages
            ]
            logger.info(f"Loaded {len(self.history)} messages from database.")
        except Exception as e:
            logger.error(f"Failed to load history from database: {e}")
            self.history = []

    def clear(self):
        """Clears the in-memory history."""
        self.history = []
        logger.info(f"In-memory history cleared for session {self.session_id}.")
