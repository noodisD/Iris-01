"""
Preferences Guard - Centralized User Preference Enforcement

This module validates and enforces user preferences at module boundaries.
Instead of scattering preference checks throughout the codebase, all validation
happens here, creating a single source of truth.

Benefits:
- Preferences are validated at boot time (fail fast)
- Gates don't need to know about preferences (PreferencesGuard checks for them)
- Changes to preference rules propagate automatically
- Clear error messages when preferences are invalid
- Tests can mock the guard for different preference scenarios
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PreferencesGuard:
    """Validates and enforces user preferences across the system.

    The guard provides:
    - Boot-time validation of preference state
    - Runtime checks for individual preference decisions
    - Clear error messages for invalid states
    - A cache of validated preferences
    """

    # Valid values for each preference
    VALID_PREFERENCES = {
        'min_confidence': {'low', 'medium', 'high'},
        'max_items': {n for n in range(1, 21)},  # 1-20 items
        'show_suppressed': {True, False},
        'enabled_engines': None,  # None = all enabled, or a set of engine names
    }

    # Defaults if preference not set
    DEFAULTS = {
        'min_confidence': 'medium',
        'max_items': 5,
        'show_suppressed': False,
        'enabled_engines': None,  # All engines enabled by default
    }

    def __init__(self, user_id: int, prefs_dict: dict[str, Any] | None = None):
        """Initialize guard for a user.

        Args:
            user_id: The user ID
            prefs_dict: User's preferences dict (from database)
        """
        self.user_id = user_id
        self.prefs = self.DEFAULTS.copy()

        if prefs_dict:
            self.prefs.update(prefs_dict)

        # Validate at initialization
        self.is_valid, self.validation_errors = self._validate()
        if not self.is_valid:
            logger.warning(f"User {user_id} has invalid preferences: {self.validation_errors}")

    def _validate(self) -> tuple[bool, list[str]]:
        """Validate the preference state.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Check min_confidence
        min_conf = self.prefs.get('min_confidence')
        if min_conf not in self.VALID_PREFERENCES['min_confidence']:
            errors.append(f"Invalid min_confidence: {min_conf}")

        # Check max_items
        max_items = self.prefs.get('max_items')
        if not isinstance(max_items, int) or max_items < 1 or max_items > 20:
            errors.append(f"Invalid max_items: {max_items}")

        # Check show_suppressed
        show_supp = self.prefs.get('show_suppressed')
        if not isinstance(show_supp, bool):
            errors.append(f"Invalid show_suppressed: {show_supp}")

        # Check enabled_engines (if set)
        enabled = self.prefs.get('enabled_engines')
        if enabled is not None:
            if not isinstance(enabled, (list, set)):
                errors.append(f"enabled_engines must be a list or set, got {type(enabled)}")
            elif len(enabled) == 0:
                errors.append("At least one engine must be enabled")

        return len(errors) == 0, errors

    def check(self, gate_name: str, value: Any) -> bool:
        """Check if a value passes a preference gate.

        This is the main method called by gates to enforce preferences.

        Args:
            gate_name: Name of the gate ('enablement', 'confidence', 'budget')
            value: Value to check (varies by gate)

        Returns:
            True if value passes the gate, False otherwise

        Example:
            if not guard.check('confidence', 'low'):
                # Filter out this low-confidence insight
        """
        if not self.is_valid:
            logger.warning("Guard has validation errors, allowing by default")
            return True  # Conservative: allow if guard is broken

        if gate_name == 'enablement':
            return self._check_engine_enablement(value)
        elif gate_name == 'confidence':
            return self._check_confidence(value)
        elif gate_name == 'budget':
            return self._check_budget(value)
        else:
            logger.warning(f"Unknown gate: {gate_name}")
            return True

    def _check_engine_enablement(self, engine_name: str) -> bool:
        """Check if an engine is enabled.

        Args:
            engine_name: Name of the engine

        Returns:
            True if engine is enabled
        """
        enabled = self.prefs.get('enabled_engines')

        # If None, all engines are enabled
        if enabled is None:
            return True

        # Otherwise, only listed engines are enabled
        return engine_name in enabled

    def _check_confidence(self, confidence_level: str) -> bool:
        """Check if a confidence level meets the minimum threshold.

        Args:
            confidence_level: 'low', 'medium', or 'high'

        Returns:
            True if confidence meets minimum
        """
        levels = {'low': 0, 'medium': 1, 'high': 2}
        min_level = levels.get(self.prefs.get('min_confidence', 'medium'), 0)
        actual_level = levels.get(confidence_level, 0)

        return actual_level >= min_level

    def _check_budget(self, current_count: int) -> bool:
        """Check if we're within the items budget.

        Args:
            current_count: Number of items collected so far

        Returns:
            True if count is within max_items
        """
        max_items = self.prefs.get('max_items', 5)
        return current_count < max_items

    def get_min_confidence(self) -> str:
        """Get the minimum confidence level allowed."""
        return self.prefs.get('min_confidence', 'medium')

    def get_max_items(self) -> int:
        """Get the maximum number of items to return."""
        return self.prefs.get('max_items', 5)

    def get_enabled_engines(self) -> set[str] | None:
        """Get the set of enabled engines, or None if all are enabled."""
        enabled = self.prefs.get('enabled_engines')
        return set(enabled) if enabled else None

    def show_suppressed(self) -> bool:
        """Check if user wants to see suppressed insights."""
        return self.prefs.get('show_suppressed', False)

    def get_validation_errors(self) -> list[str]:
        """Get list of validation errors (empty if valid)."""
        return self.validation_errors.copy()

    def enable_engine(self, engine_name: str) -> None:
        """Enable a specific engine."""
        if self.prefs.get('enabled_engines') is None:
            return  # Already all enabled

        enabled = set(self.prefs['enabled_engines'])
        enabled.add(engine_name)
        self.prefs['enabled_engines'] = list(enabled)

    def disable_engine(self, engine_name: str) -> None:
        """Disable a specific engine (if not the last one)."""
        if self.prefs.get('enabled_engines') is None:
            # Convert from "all enabled" to explicit list
            self.prefs['enabled_engines'] = [
                'persistence', 'trajectory', 'tension', 'resolution', 'leverage', 'decision_impact'
            ]

        enabled = set(self.prefs['enabled_engines'])
        if len(enabled) <= 1:
            logger.warning("Cannot disable the last enabled engine")
            return

        enabled.discard(engine_name)
        self.prefs['enabled_engines'] = list(enabled)

    def __repr__(self) -> str:
        """String representation for debugging."""
        status = "valid" if self.is_valid else f"invalid: {self.validation_errors}"
        return f"PreferencesGuard(user={self.user_id}, {status})"


class PreferencesGate:
    """Gate implementation that uses PreferencesGuard to enforce preferences.

    This can be registered with the AnalysisPipeline as a filtering gate.
    """

    def __init__(self, guard: PreferencesGuard):
        """Initialize gate with a preferences guard.

        Args:
            guard: PreferencesGuard instance
        """
        self.guard = guard

    def filter_insights(self, insights: list[dict[str, Any]],
                       context: dict[str, Any]) -> list[dict[str, Any]]:
        """Apply preferences-based filtering to insights.

        This gate combines multiple checks:
        - Engine enablement
        - Confidence threshold
        - Budget (max_items)

        Args:
            insights: List of insights to filter
            context: Gate context (unused here, preferences come from guard)

        Returns:
            Filtered list of insights
        """
        filtered = []
        suppression_log = context.get('suppression_log', {})

        for insight in insights:
            engine_name = insight.get('engine_name', 'unknown')
            confidence = insight.get('confidence_level', 'unknown')

            # Check enablement
            if not self.guard.check('enablement', engine_name):
                if 'engine_disabled' not in suppression_log:
                    suppression_log['engine_disabled'] = []
                suppression_log['engine_disabled'].append(
                    f"{engine_name}: {insight.get('label')}"
                )
                continue

            # Check confidence
            if not self.guard.check('confidence', confidence):
                if 'low_confidence' not in suppression_log:
                    suppression_log['low_confidence'] = []
                suppression_log['low_confidence'].append(
                    f"{engine_name}: {insight.get('label')} ({confidence})"
                )
                continue

            # Check budget
            if not self.guard.check('budget', len(filtered)):
                if 'budget_exceeded' not in suppression_log:
                    suppression_log['budget_exceeded'] = []
                suppression_log['budget_exceeded'].append(
                    f"{engine_name}: {insight.get('label')}"
                )
                continue

            filtered.append(insight)

        return filtered
