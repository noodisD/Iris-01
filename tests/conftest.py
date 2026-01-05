"""
Pytest configuration and fixtures.
"""

import pytest
import datetime
from unittest.mock import MagicMock
from agent.database import db

@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """
    Fixture to set up and tear down a test database for the session.
    """
    # For simplicity, we're using the same database as the main app,
    # but in a real-world scenario, you'd use a dedicated test database.
    # We ensure schema is up to date.
    db.create_schema()
    yield
    # Cleanup: In a real app we might drop the test schema/db.
    print("Test session finished.")

@pytest.fixture
def test_user():
    """
    Creates a unique test user for each test to ensure isolation.
    """
    import uuid
    username = f"testuser_{uuid.uuid4().hex[:8]}"
    user_id = db.create_user(username, "testpassword")
    user = {"id": user_id, "username": username}
    yield user
    # Cleanup user data
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM theme_occurrences WHERE theme_id IN (SELECT id FROM themes WHERE user_id = %s);", (user['id'],))
        cur.execute("DELETE FROM themes WHERE user_id = %s;", (user['id'],))
        cur.execute("DELETE FROM journal_entries WHERE user_id = %s;", (user['id'],))
        cur.execute("DELETE FROM conversation_messages WHERE user_id = %s;", (user['id'],))
        cur.execute("DELETE FROM users WHERE id = %s;", (user['id'],))
        conn.commit()

@pytest.fixture
def freeze_time(monkeypatch):
    """
    Provides a way to 'teleport' the system time for sliding window tests.
    Usage:
        def test_x(freeze_time):
            freeze_time.set_time(datetime.datetime(2026, 1, 1))
            ...
    """
    class TimeMachine:
        def __init__(self):
            self.now = datetime.datetime.now()
        
        def set_time(self, new_time):
            self.now = new_time
            
        def move_forward(self, days=0, hours=0):
            self.now += datetime.timedelta(days=days, hours=hours)

    machine = TimeMachine()
    
    # We must patch everywhere datetime.now is used
    # This is broad, but necessary for the IRIS analytical stack
    import agent.database
    import agent.persistence
    import agent.trajectory
    import agent.tension
    import agent.resolution
    import agent.leverage
    import agent.decision_impact
    import agent.confidence
    import agent.prioritization
    import agent.core

    modules = [
        agent.database, agent.persistence, agent.trajectory, 
        agent.tension, agent.resolution, agent.leverage, 
        agent.decision_impact, agent.confidence, 
        agent.prioritization, agent.core
    ]

    # Note: mocking datetime.datetime.now directly is hard because it's a built-in.
    # We patch the datetime reference in each module instead.
    
    class MockDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return machine.now

    for mod in modules:
        if hasattr(mod, 'datetime'):
            monkeypatch.setattr(mod, "datetime", MockDateTime)

    return machine

@pytest.fixture
def mock_llm(monkeypatch):
    """
    Standard mock for LLM to avoid real API costs and ensure determinism.
    """
    mock_intelligence = MagicMock()
    mock_intelligence.chat.return_value = "IRIS Mocked Response"
    
    monkeypatch.setattr("agent.core.Intelligence", lambda *args, **kwargs: mock_intelligence)
    return mock_intelligence