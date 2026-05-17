"""
User Preferences Service - Control Layer Management

This module manages user-specific gates and thresholds.
It provides a single source of truth for the companion's analytical sensitivity.
"""

import logging
from typing import Dict, Any, List, Optional

# Import database and constants
from .database import db, preferences as pref_repo
from .constants import ENGINE_PRIORITY

logger = logging.getLogger(__name__)

class UserPreferencesService:
    """
    Handles retrieval, validation, and persistence of user analytical settings.
    """

    DEFAULT_PREFS = {
        "min_confidence": "medium",
        "max_items": 5,
        "enabled_engines": None, # All enabled
        "show_suppressed": False
    }

    def __init__(self, user_id: int):
        self.user_id = user_id

    def get_prefs(self) -> Dict[str, Any]:
        """
        Loads user preferences from DB, falling back to system defaults.
        """
        stored = pref_repo.get_preferences(self.user_id)
        if not stored:
            return self.DEFAULT_PREFS.copy()
        
        # Merge stored with defaults to ensure all keys exist
        prefs = self.DEFAULT_PREFS.copy()
        prefs.update(stored)
        return prefs

    def update_pref(self, key: str, value: Any) -> Dict[str, Any]:
        """
        Validates and updates a specific preference.
        """
        self._validate(key, value)
        pref_repo.update_preference(self.user_id, key, value)
        return self.get_prefs()

    def reset(self) -> Dict[str, Any]:
        """
        Restores system defaults for the user.
        """
        db.reset_preferences(self.user_id)
        return self.DEFAULT_PREFS.copy()

    def _validate(self, key: str, value: Any):
        """
        Strict validation bounds for user controls.
        """
        if key == "min_confidence":
            if value not in ["low", "medium", "high"]:
                raise ValueError("min_confidence must be 'low', 'medium', or 'high'")
        
        elif key == "max_items":
            try:
                v = int(value)
                if not (1 <= v <= 10):
                    raise ValueError("max_items must be between 1 and 10")
            except (TypeError, ValueError):
                raise ValueError("max_items must be an integer between 1 and 10")
        
        elif key == "enabled_engines":
            if value is not None:
                if not isinstance(value, list):
                    raise ValueError("enabled_engines must be a list of strings or null")
                # Cross-reference with existing engines
                all_engines = set(ENGINE_PRIORITY) | {"persistence"}
                for e in value:
                    if e not in all_engines:
                        raise ValueError(f"Invalid engine name: {e}")
        
        elif key == "show_suppressed":
            if not isinstance(value, bool):
                raise ValueError("show_suppressed must be a boolean")
        
        else:
            raise ValueError(f"Unknown setting: {key}")
