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
from types import SimpleNamespace
from unittest.mock import MagicMock

import psycopg2
import pytest

from agent.config import settings
from agent.database import db
from agent.logging_config import configure_logging


#: Written into any database this suite creates. The session truncates every
#: table before it runs, and a name check alone cannot tell our scratch database
#: from someone's important one that merely has "test" in its name — so we only
#: ever truncate a database carrying this marker.
_MARKER_TABLE = "_iris_test_database"


def _ensure_test_database() -> None:
    """Create the test database, its pgvector extension and its marker.

    Refuses to proceed against an existing database that we did not create.
    """
    conn = psycopg2.connect(
        dbname="postgres",
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    conn.autocommit = True
    created = False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (settings.POSTGRES_DB,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{settings.POSTGRES_DB}";')
                created = True
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
            cur.execute("SELECT to_regclass(%s);", (f"public.{_MARKER_TABLE}",))
            has_marker = cur.fetchone()[0] is not None

            if created or not has_marker:
                # A database that already had tables but no marker is not ours.
                cur.execute("""
                    SELECT count(*) FROM pg_tables WHERE schemaname = 'public';
                """)
                table_count = cur.fetchone()[0]
                if not created and table_count > 0:
                    raise RuntimeError(
                        f"Refusing to use database {settings.POSTGRES_DB!r}: it already "
                        f"contains {table_count} tables and was not created by this test "
                        f"suite (no {_MARKER_TABLE!r} marker). The suite truncates every "
                        "table before running. Point IRIS_TEST_POSTGRES_DB at a database "
                        "this suite may own, or drop that one first."
                    )
                cur.execute(
                    f"CREATE TABLE IF NOT EXISTS {_MARKER_TABLE} "
                    "(created_at TIMESTAMPTZ NOT NULL DEFAULT now());"
                )
                cur.execute(f"INSERT INTO {_MARKER_TABLE} DEFAULT VALUES;")
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

    def fake_create(input, model=None, **kwargs):
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

    return
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
    from agent import migrations
    migrations.upgrade()
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
        # schema_migrations is the migration ledger, not test data. Truncating
        # it would make an already-migrated database claim it had never been
        # migrated, and the next upgrade() would re-apply everything.
        cur.execute("""
            SELECT string_agg(quote_ident(tablename), ', ')
            FROM pg_tables
            WHERE schemaname = 'public' AND tablename <> 'schema_migrations';
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
        # Since migration 0003 these three cascade from users, so the
        # explicit deletes are belt-and-braces rather than load-bearing;
        # they also keep the ordering obvious for the caches below.
        cur.execute("DELETE FROM journal_entries WHERE user_id = %s;", (user_id,))
        cur.execute("DELETE FROM conversation_messages WHERE user_id = %s;", (user_id,))
        # habits -> habit_completions and reflections cascade with the user.
        cur.execute("DELETE FROM users WHERE id = %s;", (user_id,))
        conn.commit()


@pytest.fixture
def process_queue():
    """Run queued ingest work to completion, returning how many items ran.

    Writes only enqueue now (ADR-0011): embedding, theme matching and the
    cross-theme refresh happen in the background worker, not in the request. A
    test that asserts on derived state has to say where it waits for that, so
    this is deliberately explicit rather than an autouse fixture — the point of
    the queue is that the work is decoupled, and a test that hid the decoupling
    would stop testing it.
    """
    from agent.work_queue import drain
    return drain


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
        """Frozen clock for the sliding-window engines.

        Everything it hands out is timezone-aware UTC, matching what the
        database returns and what the engines now compare against. A naive
        datetime passed to set_time() is interpreted as UTC rather than
        silently producing a naive/aware comparison deep inside an engine.
        """

        def __init__(self):
            self.now = datetime.datetime.now(datetime.UTC)

        @staticmethod
        def _aware(value):
            if value.tzinfo is None:
                return value.replace(tzinfo=datetime.UTC)
            return value.astimezone(datetime.UTC)

        def set_time(self, new_time):
            self.now = self._aware(new_time)

        def move_forward(self, days=0, hours=0):
            self.now += datetime.timedelta(days=days, hours=hours)

    machine = TimeMachine()

    # We must patch everywhere datetime.now is used
    # This is broad, but necessary for the IRIS analytical stack
    import agent.confidence
    import agent.core
    import agent.database
    import agent.decision_impact
    import agent.leverage
    import agent.persistence
    import agent.prioritization
    import agent.resolution
    import agent.tension
    import agent.trajectory

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
            return machine.now.astimezone(tz) if tz else machine.now

    for mod in modules:
        if hasattr(mod, 'datetime'):
            monkeypatch.setattr(mod, "datetime", MockDateTime)

    # The engines take "now" from agent.timeutils.utc_now, not from their own
    # datetime reference, so the time machine has to move that too — otherwise
    # frozen tests would silently compare frozen occurrences against real time.
    monkeypatch.setattr("agent.timeutils.utc_now", lambda: machine.now)
    for mod in modules:
        if hasattr(mod, "utc_now"):
            monkeypatch.setattr(mod, "utc_now", lambda: machine.now)

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
