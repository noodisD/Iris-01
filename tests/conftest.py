"""
Pytest configuration and fixtures.
"""

import os

# The suite writes and deletes rows, so it must never touch the application
# database. pydantic-settings resolves environment variables ahead of .env, so
# setting POSTGRES_DB here — before agent.config is imported below — redirects
# every connection in the process. Override with IRIS_TEST_POSTGRES_DB.
os.environ["POSTGRES_DB"] = os.environ.get("IRIS_TEST_POSTGRES_DB", "iris_test_db")

import datetime
import hashlib
import logging
import random

import psycopg2
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from agent.config import settings
from agent.database import db
from agent.logging_config import configure_logging


def _ensure_test_database() -> None:
    """Create the test database (and pgvector) if it does not exist yet."""
    conn = psycopg2.connect(
        dbname="postgres",
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (settings.POSTGRES_DB,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{settings.POSTGRES_DB}";')
    finally:
        conn.close()

    conn = psycopg2.connect(
        dbname=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    finally:
        conn.close()

def _offline_embedding(text: str, model: str = None) -> list:
    """A deterministic stand-in for OpenAI embeddings.

    Same text in, same vector out, so repeated entries still cluster and
    unrelated ones stay apart. Tests that need particular semantic
    relationships override this with mock_pipeline_logic.
    """
    seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(seed)
    return [rng.uniform(-1.0, 1.0) for _ in range(1536)]


@pytest.fixture(autouse=True)
def offline_embeddings(monkeypatch):
    """Keep the suite free, deterministic and runnable with no network.

    Several tests reach the embedding call through the ingest pipeline, so
    without this the suite silently required a funded OPENAI_API_KEY: with a
    dummy key the embeddings 401, no themes form, and
    test_system_health_invariant failed with `assert 0 == 1`. A green run was
    therefore not an offline fact. Set IRIS_TEST_LIVE_OPENAI=1 to exercise the
    real API deliberately.
    """
    if os.environ.get("IRIS_TEST_LIVE_OPENAI") == "1":
        yield
        return

    def fake_create(input, model=None, **kwargs):  # noqa: A002 - matches the SDK
        text = input[0] if isinstance(input, (list, tuple)) else input
        return SimpleNamespace(data=[SimpleNamespace(embedding=_offline_embedding(text))])

    # Patched at the SDK boundary rather than at generate_embedding, so the
    # retry/backoff logic above it still runs and tests that drive failures
    # through this same call can override it.
    monkeypatch.setattr("agent.pipeline.openai.embeddings.create", fake_create)
    # Theme discovery names its clusters with the LLM. That call fails soft,
    # but it is still a real request made from a test.
    monkeypatch.setattr(
        "agent.persistence.PersistenceEngine._generate_theme_summary",
        lambda self, entries: "Offline Theme",
    )
    yield


@pytest.fixture(scope="session", autouse=True)
def logging_setup(tmp_path_factory):
    """
    Set up centralized logging for the entire test session.
    Logs are written to a temporary directory and console output is suppressed.
    """
    log_dir = tmp_path_factory.mktemp("logs")
    configure_logging(log_dir=str(log_dir))

    # Suppress console output during tests (set console handler to CRITICAL)
    agent_logger = logging.getLogger("agent")
    for handler in agent_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setLevel(logging.CRITICAL)

    yield
    # Cleanup: handlers remain until session ends (pytest handles cleanup)

@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create the dedicated test database and its schema for the session."""
    # Refuse to run against anything that is not clearly a test database, so a
    # misconfigured environment cannot quietly point the suite at real data.
    if "test" not in settings.POSTGRES_DB:
        raise RuntimeError(
            f"Refusing to run tests against database {settings.POSTGRES_DB!r}: "
            "the name must contain 'test'. Set IRIS_TEST_POSTGRES_DB."
        )
    _ensure_test_database()
    db.create_schema()
    _truncate_all()
    yield
    logging.getLogger(__name__).info("Test session finished.")

def _truncate_all() -> None:
    """Empty every table before the session runs.

    Per-test cleanup only covers users created through the test_user fixture;
    tests that call db.create_user() directly left rows behind, and they
    accumulated across runs (16 users / 54 reflections / 41 embeddings were
    found in iris_test_db during the independent audit). Leftovers are not just
    untidy: stale rows in a pending state used to change what the ingest
    pipeline picked up, so runs influenced each other.
    """
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT string_agg(quote_ident(tablename), ', ')
            FROM pg_tables WHERE schemaname = 'public';
        """)
        tables = cur.fetchone()[0]
        if tables:
            cur.execute(f"TRUNCATE {tables} RESTART IDENTITY CASCADE;")
        conn.commit()


def _purge_user(user_id: int) -> None:
    """Remove every row a test user can create.

    Only habits, reflections, user_preferences, user_app_settings,
    preference_audit and insight_status cascade from users; journal entries,
    messages and themes do not, and embeddings and the pattern_* caches are
    keyed by (source_type, source_id) / (pattern_type, pattern_id) rather than
    by user, so they have to be matched explicitly and deleted first.
    """
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM themes WHERE user_id = %s;", (user_id,))
        theme_ids = [r[0] for r in cur.fetchall()]

        # Embeddings, keyed by source rather than by user.
        cur.execute(
            """
            DELETE FROM embeddings WHERE
                (source_type = 'journal_entry' AND source_id IN (SELECT id FROM journal_entries WHERE user_id = %s))
             OR (source_type = 'reflection'    AND source_id IN (SELECT id FROM reflections WHERE user_id = %s))
             OR (source_type = 'message'       AND source_id IN (SELECT id FROM conversation_messages WHERE user_id = %s))
             OR (source_type IN ('habit', 'habit_completion') AND source_id IN (
                    SELECT c.id FROM habit_completions c
                    JOIN habits h ON h.id = c.habit_id WHERE h.user_id = %s));
            """,
            (user_id, user_id, user_id, user_id),
        )

        # Analytical caches keyed by pattern, not by user.
        if theme_ids:
            for table, col in (
                ("pattern_resolutions", "pattern_id"),
                ("pattern_confidence", "pattern_id"),
                ("pattern_evidence", "pattern_id"),
                ("insight_priorities", "pattern_id"),
            ):
                cur.execute(f"DELETE FROM {table} WHERE pattern_type = 'theme' AND {col} = ANY(%s);", (theme_ids,))
            cur.execute("DELETE FROM pattern_leverage WHERE source_id = ANY(%s) OR target_id = ANY(%s);", (theme_ids, theme_ids))
            cur.execute("DELETE FROM decision_impacts WHERE anchor_id = ANY(%s) OR target_id = ANY(%s);", (theme_ids, theme_ids))

        # Rows that do not cascade from users.
        cur.execute("DELETE FROM theme_occurrences WHERE theme_id = ANY(%s);", (theme_ids,))
        cur.execute("DELETE FROM themes WHERE user_id = %s;", (user_id,))
        cur.execute("DELETE FROM journal_entries WHERE user_id = %s;", (user_id,))
        cur.execute("DELETE FROM conversation_messages WHERE user_id = %s;", (user_id,))
        # habits -> habit_completions and reflections cascade with the user.
        cur.execute("DELETE FROM users WHERE id = %s;", (user_id,))
        conn.commit()


@pytest.fixture
def mock_pipeline_logic(monkeypatch):
    """Deterministic embeddings keyed by keyword, shared by the stress tests.

    Lived in test_final_system_stress_test.py, which meant
    test_stress_theme_resolution_debug.py requested a fixture it could not
    see and errored at setup on every run.
    """
    import random

    def mock_embed(text, model=None):
        if "Stress" in text: return [0.1] * 1536
        if "Sleep" in text: return [0.2] * 1536
        if "Yoga" in text: return [0.3] * 1536
        if "Meditation" in text: return [0.4] * 1536
        if "Habit" in text: return [0.5] * 1536
        return [random.random() for _ in range(1536)]

    monkeypatch.setattr("agent.pipeline.generate_embedding", mock_embed)
    monkeypatch.setattr("agent.core.generate_embedding", mock_embed)
    monkeypatch.setattr("agent.persistence.PersistenceEngine._generate_theme_summary", lambda s, e: "Dynamic Theme")


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
    _purge_user(user["id"])

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