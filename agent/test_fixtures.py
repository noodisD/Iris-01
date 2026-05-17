"""
Test Fixtures - Scoped Time Control and Database Isolation

This module provides modern test fixtures that replace the global freeze_time
pattern with per-test scoped fixtures. Each test gets its own isolated time
context that doesn't bleed into other tests.

Benefits:
- Tests are truly isolated (no shared mutable state)
- Time control is explicit and scoped
- Auto-patching of datetime in modules
- Clear fixture dependencies
- Easy to understand in tests
- Pytest's standard fixture patterns
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import sys
import importlib
import pytest
import logging

logger = logging.getLogger(__name__)


class FixtureContext:
    """Per-test context for managing time and database state.

    This is used by pytest fixtures to provide isolated test environments.
    Each test gets its own FixtureContext that controls the "current time"
    and cleans up after itself.
    """

    def __init__(self, test_name: str):
        """Initialize a test context.

        Args:
            test_name: Name of the test using this context
        """
        self.test_name = test_name
        self.start_time = datetime.now()
        self.frozen_time: Optional[datetime] = None
        self.time_offset = timedelta(0)
        self.original_datetime = datetime  # Save original for restoration
        self._patched_modules: set = set()

    def freeze_time(self, frozen_at: datetime) -> None:
        """Freeze time at a specific moment.

        Args:
            frozen_at: The moment to freeze at
        """
        self.frozen_time = frozen_at
        self._apply_patches()

    def set_time(self, new_time: datetime) -> None:
        """Move to a different time.

        Args:
            new_time: The new "current" time
        """
        self.frozen_time = new_time
        self._apply_patches()

    def advance_time(self, delta: timedelta) -> None:
        """Advance time by a duration.

        Args:
            delta: How much time to advance
        """
        if self.frozen_time is None:
            return

        self.frozen_time += delta
        self._apply_patches()

    def _apply_patches(self) -> None:
        """Apply datetime patches to all relevant modules.

        This auto-discovers modules that import datetime and patches them.
        """
        # List of common modules that use datetime
        modules_to_patch = [
            'agent.database',
            'agent.persistence',
            'agent.trajectory',
            'agent.tension',
            'agent.resolution',
            'agent.leverage',
            'agent.decision_impact',
            'agent.core',
            'agent.pipeline',
            'agent.memory',
        ]

        for module_name in modules_to_patch:
            if module_name not in sys.modules:
                try:
                    importlib.import_module(module_name)
                except ImportError:
                    continue

            try:
                module = sys.modules[module_name]
                if hasattr(module, 'datetime'):
                    # Patch the datetime module reference
                    module.datetime = MockDateTime(self.frozen_time)
                    self._patched_modules.add(module_name)
            except Exception as e:
                logger.debug(f"Could not patch {module_name}: {e}")

    def cleanup(self) -> None:
        """Restore all patches and clean up."""
        # Restore original datetime to all patched modules
        for module_name in self._patched_modules:
            try:
                module = sys.modules.get(module_name)
                if module:
                    module.datetime = self.original_datetime
            except Exception as e:
                logger.debug(f"Could not restore {module_name}: {e}")

        self._patched_modules.clear()
        self.frozen_time = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.cleanup()


class MockDateTime:
    """Mock datetime class that returns frozen time."""

    def __init__(self, frozen_time: Optional[datetime]):
        """Initialize mock.

        Args:
            frozen_time: The frozen time to return (or None for real time)
        """
        self.frozen_time = frozen_time
        self._real_datetime = datetime

    def now(self, tz=None):
        """Return frozen time or real time."""
        if self.frozen_time is None:
            return self._real_datetime.now(tz)
        return self.frozen_time.replace(tzinfo=tz) if tz else self.frozen_time

    def utcnow(self):
        """Return frozen UTC time."""
        if self.frozen_time is None:
            return self._real_datetime.utcnow()
        return self.frozen_time

    def fromtimestamp(self, timestamp, tz=None):
        """Convert timestamp."""
        return self._real_datetime.fromtimestamp(timestamp, tz)

    def strptime(self, date_string, format):
        """Parse datetime string."""
        return self._real_datetime.strptime(date_string, format)

    def fromisoformat(self, date_string):
        """Parse ISO format datetime."""
        return self._real_datetime.fromisoformat(date_string)

    def combine(self, date, time, tzinfo=None):
        """Combine date and time."""
        return self._real_datetime.combine(date, time, tzinfo)

    def __getattr__(self, name):
        """Delegate other attributes to real datetime."""
        return getattr(self._real_datetime, name)


@pytest.fixture
def fixture_context(request) -> FixtureContext:
    """Provide an isolated test context with frozen time.

    Usage in tests:
        def test_something(fixture_context):
            fixture_context.freeze_time(datetime(2026, 1, 1))
            # Test code here
            # Time is frozen at 2026-01-01

    Args:
        request: Pytest request fixture

    Yields:
        FixtureContext for this test
    """
    context = FixtureContext(request.node.name)

    yield context

    # Cleanup after test
    context.cleanup()


@pytest.fixture
def frozen_time(fixture_context) -> FixtureContext:
    """Convenience fixture that is an alias for fixture_context.

    Usage:
        def test_something(frozen_time):
            frozen_time.freeze_time(datetime(2026, 1, 1))
    """
    return fixture_context


def with_frozen_time(frozen_at: datetime):
    """Decorator to freeze time for a test.

    Usage:
        @with_frozen_time(datetime(2026, 1, 1))
        def test_something(fixture_context):
            # Time is already frozen at 2026-01-01
    """
    def decorator(test_func):
        def wrapper(fixture_context, *args, **kwargs):
            fixture_context.freeze_time(frozen_at)
            return test_func(fixture_context, *args, **kwargs)
        wrapper.__name__ = test_func.__name__
        return wrapper
    return decorator
