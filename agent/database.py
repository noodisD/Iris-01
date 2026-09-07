"""
Database Layer - PostgreSQL Source of Truth

This module is the only part of the application that should interact directly with PostgreSQL.
It enforces the single source of truth principle. All data, including embeddings,
is stored here canonically.
"""

import hashlib
import logging
from contextlib import contextmanager
from typing import Any

import psycopg2

# Use pgvector extension
from pgvector.psycopg2 import register_vector
from psycopg2 import pool as psycopg2_pool
from psycopg2.extras import Json

from .config import settings

logger = logging.getLogger(__name__)

def hash_password(password: str) -> str:
    """Hashes a password for secure storage."""
    return hashlib.sha256(password.encode()).hexdigest()


class Database:
    """Manages the PostgreSQL connection pool and all data persistence."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._pool = None
            cls._instance._legacy_conn = None
        return cls._instance

    # The pool is created lazily on first use, not here: constructing this
    # singleton happens at import time, and connecting there made an unreachable
    # database an import error for the whole app rather than a runtime one.

    def _init_pool(self):
        """Create the ThreadedConnectionPool and ensure pgvector is installed."""
        if self._pool is not None and not self._pool.closed:
            return

        logger.info(
            f"Creating PostgreSQL connection pool at "
            f"{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT} (min=1, max=5)..."
        )
        try:
            self._pool = psycopg2_pool.ThreadedConnectionPool(
                minconn=1,
                # Blocking handlers run in FastAPI's threadpool (40 workers by
                # default), and a single ingest can hold one connection while
                # its cache invalidations check out others — so a ceiling of 5
                # exhausted the pool under very little concurrency.
                maxconn=20,
                dbname=settings.POSTGRES_DB,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT,
            )
            # Install pgvector on a raw pooled connection, NOT through
            # self.connection(): that helper calls register_vector(), which
            # needs the vector type to already exist. Going through it here
            # meant a brand-new database could never be bootstrapped — the
            # statement that creates the extension required the extension.
            conn = self._pool.getconn()
            try:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                conn.commit()
            finally:
                self._pool.putconn(conn)
            logger.info("PostgreSQL connection pool ready.")
        except psycopg2.OperationalError as e:
            logger.error(f"Failed to create PostgreSQL pool: {e}")
            self._pool = None
            raise

    @contextmanager
    def connection(self):
        """Check out a connection from the pool; return it on exit.

        Rolls back any uncommitted transaction on exception to keep pooled
        connections clean for the next caller.
        """
        if self._pool is None or self._pool.closed:
            self._init_pool()
        conn = self._pool.getconn()
        try:
            register_vector(conn)
            yield conn
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            self._pool.putconn(conn)

    def get_connection(self):
        """Legacy API: returns a long-lived shared connection for CLI/test callers.

        New internal code uses the pool via `with self.connection() as conn:`.
        This dedicated connection is kept separate so legacy callers (companion.py
        CLI, test fixtures, graph rebuild) never exhaust the pool.
        """
        if self._legacy_conn is None or self._legacy_conn.closed:
            self._legacy_conn = psycopg2.connect(
                dbname=settings.POSTGRES_DB,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                host=settings.POSTGRES_HOST,
                port=settings.POSTGRES_PORT,
            )
            register_vector(self._legacy_conn)
        return self._legacy_conn

    def close_connection(self):
        """Close all connections in the pool and the legacy connection."""
        if self._pool and not self._pool.closed:
            self._pool.closeall()
            logger.info("PostgreSQL connection pool closed.")
        if self._legacy_conn and not self._legacy_conn.closed:
            self._legacy_conn.close()
            self._legacy_conn = None

    def ping(self) -> bool:
        """Cheap liveness probe: check out a connection and round-trip a SELECT."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1;")
            return cur.fetchone()[0] == 1

    def create_schema(self):
        """
        Creates the necessary tables and extensions in the database.
        This method is idempotent and safe to run multiple times.
        """
        with self.connection() as conn, conn.cursor() as cur:
            try:
                # Enable pgvector extension
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                register_vector(conn) # Register vector type for psycopg2
                logger.info("Ensured vector extension is enabled and registered.")

                # Users table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(50) UNIQUE NOT NULL,
                        password_hash VARCHAR(256) NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                logger.info("Ensured users table exists.")

                # Journal entries table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS journal_entries (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        raw_text TEXT NOT NULL,
                        wellbeing_data JSONB,
                        processing_status VARCHAR(20) DEFAULT 'pending', -- pending, processing, complete, failed
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                logger.info("Ensured journal_entries table exists.")

                # Conversation messages table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_messages (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        session_id VARCHAR(50) NOT NULL,
                        role VARCHAR(20) NOT NULL, -- user, assistant
                        content TEXT NOT NULL,
                        processing_status VARCHAR(20) DEFAULT 'pending',
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                logger.info("Ensured conversation_messages table exists.")

                # Embeddings table (canonical store)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS embeddings (
                        id SERIAL PRIMARY KEY,
                        source_type VARCHAR(50) NOT NULL, -- e.g., 'journal_entry', 'message'
                        source_id INTEGER NOT NULL,
                        model_name VARCHAR(100) NOT NULL,
                        vector VECTOR(1536) NOT NULL, -- Assuming OpenAI's ada-002 dimension
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(source_type, source_id, model_name)
                    );
                """)
                logger.info("Ensured embeddings table exists.")

                # IVFFlat index on cosine distance for fast vector search.
                # lists=100 is appropriate for tables up to ~1M rows.
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_embeddings_vector_cosine
                    ON embeddings USING ivfflat (vector vector_cosine_ops)
                    WITH (lists = 100);
                """)
                logger.info("Ensured IVFFlat index on embeddings.vector exists.")

                # Themes table (discovered semantic themes)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS themes (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        centroid_embedding VECTOR(1536) NOT NULL,
                        summary TEXT,
                        first_seen_at TIMESTAMPTZ NOT NULL,
                        last_seen_at TIMESTAMPTZ NOT NULL,
                        occurrence_count INTEGER DEFAULT 1,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                logger.info("Ensured themes table exists.")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_themes_user ON themes(user_id);")
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_themes_centroid_cosine
                    ON themes USING ivfflat (centroid_embedding vector_cosine_ops)
                    WITH (lists = 50);
                """)
                logger.info("Ensured IVFFlat index on themes.centroid_embedding exists.")

                # Theme occurrences table (evidence)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS theme_occurrences (
                        id SERIAL PRIMARY KEY,
                        theme_id INTEGER NOT NULL REFERENCES themes(id) ON DELETE CASCADE,
                        source_type VARCHAR(50) NOT NULL,
                        source_id INTEGER NOT NULL,
                        snippet TEXT,
                        similarity_score FLOAT NOT NULL,
                        occurred_at TIMESTAMPTZ NOT NULL,
                        UNIQUE(theme_id, source_type, source_id)
                    );
                """)
                logger.info("Ensured theme_occurrences table exists.")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_occurrences_theme ON theme_occurrences(theme_id, occurred_at DESC);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_occurrences_source ON theme_occurrences(source_type, source_id);")

                # Theme trajectories table (cache for computed trends)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS theme_trajectories (
                        theme_id INTEGER PRIMARY KEY REFERENCES themes(id) ON DELETE CASCADE,
                        trajectory_label VARCHAR(50),  -- 'emerging', 'increasing', 'stable', 'fading'
                        trend_score FLOAT,             -- signed slope
                        recent_count INTEGER,
                        past_count INTEGER,
                        confidence_level VARCHAR(20),  -- 'low', 'medium', 'high'
                        data_points_count INTEGER,     -- number of occurrences used in calculation
                        last_computed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                logger.info("Ensured theme_trajectories table exists.")

                # Theme tensions table (cache for computed tensions between theme pairs)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS theme_tensions (
                        id SERIAL PRIMARY KEY,
                        theme_a_id INTEGER REFERENCES themes(id) ON DELETE CASCADE,
                        theme_b_id INTEGER REFERENCES themes(id) ON DELETE CASCADE,

                        cooccurrence_count INTEGER,
                        recent_cooccurrence_count INTEGER,
                        past_cooccurrence_count INTEGER,

                        divergence_score FLOAT,          -- difference in trajectory or frequency
                        stability_score FLOAT,           -- how consistently this pair appears
                        tension_label VARCHAR(50),       -- 'persistent', 'emerging', 'fading', 'intermittent'
                        confidence_level VARCHAR(20),    -- 'low', 'medium', 'high'

                        last_computed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

                        UNIQUE(theme_a_id, theme_b_id)
                    );
                """)
                logger.info("Ensured theme_tensions table exists.")

                # Pattern resolutions table (cache for resolution status)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS pattern_resolutions (
                        id SERIAL PRIMARY KEY,
                        pattern_type VARCHAR(20) NOT NULL,   -- 'theme' | 'tension'
                        pattern_id INTEGER NOT NULL,

                        resolution_label VARCHAR(50),        -- 'dissipated' | 'stabilized' | 'persisting' | 'reappearing'
                        attenuation_score FLOAT,             -- 1.0 = dissipated, 0.0 = stable
                        confidence_level VARCHAR(20),        -- 'low' | 'medium' | 'high'

                        recent_count INTEGER,
                        past_count INTEGER,

                        -- Cache Invariant: NULL means invalid/stale. NOT NULL means valid snapshot.
                        last_computed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

                        UNIQUE(pattern_type, pattern_id)
                    );
                """)
                logger.info("Ensured pattern_resolutions table exists.")

                # Pattern leverage table (cache for influence relationships)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS pattern_leverage (
                        id SERIAL PRIMARY KEY,
                        source_type VARCHAR(20) NOT NULL,   -- 'theme' | 'tension'
                        source_id INTEGER NOT NULL,
                        target_type VARCHAR(20) NOT NULL,
                        target_id INTEGER NOT NULL,

                        influence_score FLOAT,              -- normalized 0–1
                        directional_lift FLOAT,             -- asymmetry metric (-1 to 1)
                        cooccurrence_count INTEGER,
                        confidence_level VARCHAR(20),        -- 'low' | 'medium' | 'high'

                        last_computed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

                        UNIQUE(source_type, source_id, target_type, target_id)
                    );
                """)
                logger.info("Ensured pattern_leverage table exists.")

                # Decision impacts table (cache for post-hoc sequence analysis)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS decision_impacts (
                        id SERIAL PRIMARY KEY,

                        anchor_type VARCHAR(20) NOT NULL,     -- 'theme' | 'tension'
                        anchor_id INTEGER NOT NULL,

                        target_type VARCHAR(20) NOT NULL,     -- 'theme' | 'tension'
                        target_id INTEGER NOT NULL,

                        effect_direction VARCHAR(20),         -- 'increase' | 'decrease' | 'emergence' | 'fade'
                        delta_score FLOAT,                    -- signed relative change
                        anchor_count INTEGER,                 -- number of anchor events analyzed
                        target_count INTEGER,                 -- total target observations

                        confidence_level VARCHAR(20),         -- 'low' | 'medium' | 'high'

                        last_computed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

                        UNIQUE(anchor_type, anchor_id, target_type, target_id)
                    );
                """)
                logger.info("Ensured decision_impacts table exists.")

                # Pattern confidence table (central registry for reliability audit)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS pattern_confidence (
                        id SERIAL PRIMARY KEY,

                        pattern_type VARCHAR(30) NOT NULL,   -- 'theme', 'trajectory', 'tension', 'leverage', 'impact'
                        pattern_id INTEGER NOT NULL,

                        confidence_level VARCHAR(20),        -- 'low', 'medium', 'high'
                        confidence_score FLOAT,              -- 0.0–1.0 (weighted aggregate)
                        
                        data_points_count INTEGER,
                        time_coverage_days INTEGER,
                        consistency_score FLOAT,
                        recency_score FLOAT,

                        last_computed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

                        UNIQUE(pattern_type, pattern_id)
                    );
                """)
                logger.info("Ensured pattern_confidence table exists.")

                # Pattern evidence table (immutable audit trail)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS pattern_evidence (
                        id SERIAL PRIMARY KEY,
                        computation_id UUID NOT NULL,        -- Groups evidence from a single run
                        pattern_type VARCHAR(30) NOT NULL,   -- 'theme', 'trajectory', etc.
                        pattern_id INTEGER NOT NULL,
                        engine_name VARCHAR(50) NOT NULL,    -- 'resolution', 'leverage', etc.
                        
                        evidence_type VARCHAR(50) NOT NULL,  -- 'count', 'rate', 'delta', 'window'
                        evidence_key VARCHAR(100) NOT NULL,  -- machine label
                        evidence_value JSONB NOT NULL,       -- raw data
                        
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_evidence_pattern ON pattern_evidence(pattern_type, pattern_id, created_at DESC);")
                logger.info("Ensured pattern_evidence table exists.")

                # Insight priorities table (cache for ranking audit)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS insight_priorities (
                        id SERIAL PRIMARY KEY,
                        insight_id TEXT NOT NULL,        -- engine:type:id
                        engine_name VARCHAR(50),
                        pattern_type VARCHAR(20),
                        pattern_id INTEGER,

                        priority_score FLOAT,
                        rank INTEGER,

                        computed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(insight_id)
                    );
                """)
                logger.info("Ensured insight_priorities table exists.")

                # User preferences table (gates and thresholds)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS user_preferences (
                        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                        min_confidence VARCHAR(20) DEFAULT 'medium' 
                            CHECK (min_confidence IN ('low', 'medium', 'high')),
                        max_items INTEGER DEFAULT 5,
                        enabled_engines JSONB, -- NULL means all enabled
                        show_suppressed BOOLEAN DEFAULT FALSE,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                logger.info("Ensured user_preferences table exists.")

                # Preference audit table (traceability)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS preference_audit (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        setting_key VARCHAR(50) NOT NULL,
                        old_value TEXT,
                        new_value TEXT,
                        changed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                logger.info("Ensured preference_audit table exists.")

                # App-level settings (frontend User/UserPreferences + onboarding +
                # connector toggles). Kept separate from user_preferences, which is
                # analytical engine config, not app/UI preferences.
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS user_app_settings (
                        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                        name TEXT,
                        timezone TEXT DEFAULT 'UTC',
                        tone TEXT DEFAULT 'warm',
                        density TEXT DEFAULT 'balanced',
                        daily_checkin_time TEXT,
                        weekly_review_time TEXT,
                        max_nudges_per_day INTEGER DEFAULT 3,
                        threads JSONB DEFAULT '[]',
                        connectors JSONB DEFAULT '{}',
                        onboarding_completed BOOLEAN DEFAULT FALSE,
                        onboarding_answers JSONB DEFAULT '{}',
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                logger.info("Ensured user_app_settings table exists.")

                # Insight status — persists snooze/resolve/seen over engine-derived
                # insight IDs (insights are recomputed on the fly, not stored).
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS insight_status (
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        insight_id TEXT NOT NULL,
                        status TEXT,
                        snoozed_until TIMESTAMPTZ,
                        seen BOOLEAN DEFAULT FALSE,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (user_id, insight_id)
                    );
                """)
                logger.info("Ensured insight_status table exists.")

                # Habits table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS habits (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        name VARCHAR(255) NOT NULL,
                        description TEXT,
                        frequency_type VARCHAR(20) NOT NULL DEFAULT 'daily'
                            CHECK (frequency_type IN ('daily', 'weekly', 'specific_days')),
                        habit_type VARCHAR(20) NOT NULL DEFAULT 'completion'
                            CHECK (habit_type IN ('completion', 'duration', 'count')),
                        weekly_target FLOAT DEFAULT 0,
                        tracking_metric VARCHAR(50) DEFAULT 'completion',
                        frequency_target INTEGER DEFAULT 1,
                        specific_days SMALLINT[],
                        category VARCHAR(50) DEFAULT 'general',
                        is_active BOOLEAN DEFAULT TRUE,
                        current_streak INTEGER DEFAULT 0,
                        longest_streak INTEGER DEFAULT 0,
                        total_completions INTEGER DEFAULT 0,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                # Migrations for existing habits table
                cur.execute("ALTER TABLE habits ADD COLUMN IF NOT EXISTS habit_type VARCHAR(20) DEFAULT 'completion';")
                cur.execute("ALTER TABLE habits ADD COLUMN IF NOT EXISTS weekly_target FLOAT DEFAULT 0;")
                cur.execute("ALTER TABLE habits ADD COLUMN IF NOT EXISTS tracking_metric VARCHAR(50) DEFAULT 'completion';")
                cur.execute("ALTER TABLE habits ADD COLUMN IF NOT EXISTS processing_status VARCHAR(20) DEFAULT 'pending';")

                logger.info("Ensured habits table exists.")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_habits_user_active ON habits(user_id, is_active);")
                # Optimization 1: Composite index for pipeline processing
                cur.execute("CREATE INDEX IF NOT EXISTS idx_habits_status_date ON habits(processing_status, created_at);")

                # Habit completions table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS habit_completions (
                        id SERIAL PRIMARY KEY,
                        habit_id INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
                        completion_date DATE NOT NULL,
                        is_completed BOOLEAN DEFAULT TRUE,
                        is_skipped BOOLEAN DEFAULT FALSE,
                        skip_reason TEXT,
                        value FLOAT DEFAULT 1.0,
                        notes TEXT,
                        processing_status VARCHAR(20) DEFAULT 'pending',
                        completed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(habit_id, completion_date)
                    );
                """)
                cur.execute("ALTER TABLE habit_completions ADD COLUMN IF NOT EXISTS value FLOAT DEFAULT 1.0;")
                cur.execute("ALTER TABLE habit_completions ADD COLUMN IF NOT EXISTS processing_status VARCHAR(20) DEFAULT 'pending';")
                logger.info("Ensured habit_completions table exists.")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_completions_habit_date ON habit_completions(habit_id, completion_date DESC);")
                # Optimization 1: Composite index for pipeline processing
                cur.execute("CREATE INDEX IF NOT EXISTS idx_completions_status_date ON habit_completions(processing_status, completed_at);")

                # Reflections table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS reflections (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        reflection_date DATE NOT NULL,
                        content TEXT NOT NULL,
                        mood VARCHAR(20),
                        energy_level SMALLINT CHECK (energy_level BETWEEN 1 AND 10),
                        clarity_level SMALLINT CHECK (clarity_level BETWEEN 1 AND 10),
                        tags JSONB,
                        processing_status VARCHAR(20) DEFAULT 'pending',
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                logger.info("Ensured reflections table exists.")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_reflections_user_date ON reflections(user_id, reflection_date DESC);")
                # Optimization 1: Composite index for pipeline processing
                cur.execute("CREATE INDEX IF NOT EXISTS idx_reflections_status_date ON reflections(processing_status, reflection_date);")

                conn.commit()
                logger.info("Database schema is up to date.")
            except psycopg2.Error as e:
                logger.error(f"Error creating schema: {e}")
                conn.rollback()
                raise

    # ============================================================================
    # User Methods
    # ============================================================================

    def create_user(self, username: str, password: str) -> int:
        """Creates a new user and returns the user ID."""
        password_hash = hash_password(password)
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id;",
                    (username, password_hash)
                )
                user_id = cur.fetchone()[0]
                conn.commit()
                logger.info(f"Created new user '{username}' with ID {user_id}.")
                return user_id
            except psycopg2.IntegrityError as e:
                conn.rollback()
                logger.warning(f"Attempted to create a user that already exists: {username}")
                raise ValueError("Username already exists.") from e

    def get_user(self, username: str) -> dict:
        """Retrieves a user by username."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute("SELECT id, username, password_hash FROM users WHERE username = %s;", (username,))
                user_data = cur.fetchone()
                if user_data:
                    return {"id": user_data[0], "username": user_data[1], "password_hash": user_data[2]}
                return None
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to get user {username}: {e}")
                raise

    def verify_user(self, username: str, password: str) -> dict:
        """Verifies a user's password and returns user data if valid."""
        user = self.get_user(username)
        if user and user["password_hash"] == hash_password(password):
            logger.info(f"Successfully verified user '{username}'.")
            return user
        logger.warning(f"Failed verification attempt for user '{username}'.")
        return None

    # ============================================================================
    # Journal Entry Methods
    # ============================================================================

    def create_journal_entry(self, user_id: int, raw_text: str, wellbeing_data: dict) -> int:
        """Creates a new journal entry and returns its ID."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO journal_entries (user_id, raw_text, wellbeing_data)
                    VALUES (%s, %s, %s) RETURNING id;
                    """,
                    (user_id, raw_text, Json(wellbeing_data))
                )
                entry_id = cur.fetchone()[0]
                conn.commit()
                return entry_id
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to create journal entry for user {user_id}: {e}")
                raise

    # ============================================================================
    # Conversation Message Methods
    # ============================================================================

    def create_conversation_message(self, user_id: int, session_id: str, role: str, content: str) -> int:
        """Creates a new conversation message and returns its ID."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO conversation_messages (user_id, session_id, role, content)
                    VALUES (%s, %s, %s, %s) RETURNING id;
                    """,
                    (user_id, session_id, role, content)
                )
                message_id = cur.fetchone()[0]
                conn.commit()
                return message_id
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to create conversation message for user {user_id}: {e}")
                raise

    def get_chat_history(self, user_id: int, limit: int = 50) -> list:
        """Retrieves the most recent chat history for a user, returned in chronological order.

        Pulls the latest `limit` messages (DESC), then reverses so callers get
        them oldest-first — the order the LLM expects for conversation context.
        """
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT role, content, created_at FROM (
                        SELECT role, content, created_at
                        FROM conversation_messages
                        WHERE user_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                    ) recent
                    ORDER BY created_at ASC;
                    """,
                    (user_id, limit)
                )
                rows = cur.fetchall()
                return [{"role": r[0], "content": r[1], "created_at": r[2]} for r in rows]
            except Exception as e:
                logger.error(f"Failed to get chat history for user {user_id}: {e}")
                return []

    # ============================================================================
    # Embedding Methods
    # ============================================================================

    def add_embedding(self, source_type: str, source_id: int, model_name: str, vector: list):
        """Stores a vector embedding for a source item."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO embeddings (source_type, source_id, model_name, vector)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (source_type, source_id, model_name) DO UPDATE
                    SET vector = EXCLUDED.vector;
                    """,
                    (source_type, source_id, model_name, vector)
                )
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to add embedding for {source_type} ID {source_id}: {e}")
                raise

    def search_similar_embeddings(self, user_id: int, query_vector: list, n_results: int = 5) -> list:
        """Searches for semantically similar embeddings using pgvector cosine distance."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT e.source_type, e.source_id, e.vector <=> %s::vector AS distance
                    FROM embeddings e
                    WHERE (
                        (e.source_type = 'journal_entry' AND e.source_id IN (
                            SELECT id FROM journal_entries WHERE user_id = %s)) OR
                        (e.source_type = 'reflection' AND e.source_id IN (
                            SELECT id FROM reflections WHERE user_id = %s)) OR
                        (e.source_type = 'message' AND e.source_id IN (
                            SELECT id FROM conversation_messages WHERE user_id = %s AND role = 'user')) OR
                        (e.source_type = 'habit_completion' AND e.source_id IN (
                            SELECT hc.id FROM habit_completions hc
                            JOIN habits h ON hc.habit_id = h.id WHERE h.user_id = %s))
                    )
                    ORDER BY distance ASC
                    LIMIT %s;
                    """,
                    (query_vector, user_id, user_id, user_id, user_id, n_results)
                )
                rows = cur.fetchall()
                return [
                    {"source_type": row[0], "source_id": row[1], "distance": row[2]}
                    for row in rows
                ]
            except Exception as e:
                logger.error(f"Failed to search similar embeddings for user {user_id}: {e}")
                return []

    # ============================================================================
    # Processing Status Methods
    # ============================================================================

    def update_processing_status(self, source_type: str, source_id: int, status: str):
        """Updates the processing status of an item (e.g., a journal entry)."""
        table_map = {
            'journal_entry': 'journal_entries',
            'message': 'conversation_messages',
            'reflection': 'reflections',
            'habit': 'habits',
            'habit_completion': 'habit_completions'
        }
        if source_type not in table_map:
            raise ValueError(f"Invalid source_type: {source_type}")

        table_name = table_map[source_type]
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    f"UPDATE {table_name} SET processing_status = %s WHERE id = %s;",
                    (status, source_id)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to update processing status for {source_type} ID {source_id}: {e}")
                raise

    def get_items_to_process(self, source_type: str, status: str = 'pending', limit: int = 10,
                             source_id: int = None) -> list:
        """Retrieves items in a processing status, optionally narrowed to one id.

        `source_id` is not cosmetic. The pipeline marks one row 'processing' and
        then reads it back; filtering on status alone let it pick up a different
        row that happened to share that status (a concurrent write, or one left
        behind by a crashed run) and embed that row's text — and its user_id —
        under the caller's id.
        """
        table_map = {
            'journal_entry': 'journal_entries',
            'message': 'conversation_messages',
            'reflection': 'reflections',
            'habit': 'habits',
            'habit_completion': 'habit_completions'
        }
        if source_type not in table_map:
            raise ValueError(f"Invalid source_type: {source_type}")

        table_name = table_map[source_type]
        # Optional narrowing to a single row (see the docstring).
        id_col = 'hc.id' if source_type == 'habit_completion' else 'id'
        scope = f" AND {id_col} = %s" if source_id is not None else ""
        params = (status, source_id, limit) if source_id is not None else (status, limit)
        with self.connection() as conn, conn.cursor() as cur:
            if source_type == 'journal_entry':
                cur.execute(
                    f"SELECT id, user_id, raw_text as content, created_at FROM {table_name} WHERE processing_status = %s{scope} LIMIT %s;",
                    params
                )
                items = cur.fetchall()
                return [
                    {
                        "id": row[0],
                        "user_id": row[1],
                        "content": row[2],
                        "created_at": row[3],
                        "occurred_at": row[3]
                    }
                    for row in items
                ]

            elif source_type == 'message':
                cur.execute(
                    f"SELECT id, user_id, content, created_at, role FROM {table_name} WHERE processing_status = %s{scope} LIMIT %s;",
                    params
                )
                items = cur.fetchall()
                return [
                    {
                        "id": row[0],
                        "user_id": row[1],
                        "content": row[2],
                        "created_at": row[3],
                        "occurred_at": row[3],
                        "role": row[4]
                    }
                    for row in items
                ]

            elif source_type == 'reflection':
                cur.execute(
                    f"SELECT id, user_id, content, created_at, mood, energy_level, clarity_level, reflection_date FROM {table_name} WHERE processing_status = %s{scope} LIMIT %s;",
                    params
                )
                items = cur.fetchall()
                return [
                    {
                        "id": row[0],
                        "user_id": row[1],
                        "content": f"Anchor: Self-Reflection | Source: Reflection | Mood: {row[4] or 'okay'} (Energy: {row[5] or '?'}/10, Clarity: {row[6] or '?'}/10) | Content: {row[2]}",
                        "created_at": row[3],
                        "occurred_at": row[7]
                    }
                    for row in items
                ]

            elif source_type == 'habit':
                cur.execute(
                    f"SELECT id, user_id, name, description, created_at, category FROM {table_name} WHERE processing_status = %s{scope} LIMIT %s;",
                    params
                )
                items = cur.fetchall()
                return [
                    {
                        "id": row[0],
                        "user_id": row[1],
                        "content": f"Anchor: {row[2]} | Source: Habit Definition | Category: {row[5] or 'General'} | Intent: {row[3] or 'No description'}",
                        "created_at": row[4],
                        "occurred_at": row[4],
                        "name": row[2]
                    }
                    for row in items
                ]

            elif source_type == 'habit_completion':
                # Join with habits to get user_id and habit name
                query = f"""
                    SELECT hc.id, h.user_id, h.name, hc.is_completed, hc.is_skipped, hc.skip_reason, hc.notes, hc.completed_at, hc.habit_id, h.description, hc.completion_date
                    FROM habit_completions hc
                    JOIN habits h ON hc.habit_id = h.id
                    WHERE hc.processing_status = %s{scope} LIMIT %s;
                """
                cur.execute(query, params)
                items = cur.fetchall()

                results = []
                for row in items:
                    hc_id, user_id, name, is_completed, is_skipped, skip_reason, notes, completed_at, habit_id, description, completion_date = row

                    if is_skipped:
                        action = "Skipped"
                        details = f"Reason: {skip_reason}"
                    else:
                        action = "Completed"
                        details = f"Notes: {notes}"

                    text = f"Anchor: {name} | Source: Habit Completion | Intent: {description or 'None'} | Action: {action} | {details}"

                    results.append({
                        "id": hc_id,
                        "user_id": user_id,
                        "content": text,
                        "created_at": completed_at,
                        "occurred_at": completion_date,
                        "habit_id": habit_id
                    })
                return results

    # ============================================================================
    # Theme Methods (Persistence Engine)
    # ============================================================================

    def create_theme(self, user_id: int, centroid_embedding: list, summary: str,
                    first_seen_at: str, last_seen_at: str, occurrence_count: int = 1) -> int:
        """Creates a new theme and returns its ID."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO themes (user_id, centroid_embedding, summary, first_seen_at, last_seen_at, occurrence_count)
                    VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;
                    """,
                    (user_id, centroid_embedding, summary, first_seen_at, last_seen_at, occurrence_count)
                )
                theme_id = cur.fetchone()[0]
                conn.commit()
                logger.info(f"Created theme ID {theme_id} for user {user_id}")
                return theme_id
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to create theme: {e}")
                raise

    def get_themes(self, user_id: int) -> list:
        """Retrieves all themes for a user."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, centroid_embedding, summary, first_seen_at, last_seen_at,
                       occurrence_count FROM themes WHERE user_id = %s ORDER BY occurrence_count DESC;
                """,
                (user_id,)
            )
            rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "centroid_embedding": row[1],
                    "summary": row[2],
                    "first_seen_at": row[3],
                    "last_seen_at": row[4],
                    "occurrence_count": row[5]
                }
                for row in rows
            ]

    def get_theme_by_id(self, theme_id: int) -> dict:
        """Retrieves a specific theme by ID."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, centroid_embedding, summary, first_seen_at, last_seen_at,
                       occurrence_count, user_id FROM themes WHERE id = %s;
                """,
                (theme_id,)
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row[0],
                    "centroid_embedding": row[1],
                    "summary": row[2],
                    "first_seen_at": row[3],
                    "last_seen_at": row[4],
                    "occurrence_count": row[5],
                    "user_id": row[6]
                }
            return None

    def update_theme_stats(self, theme_id: int, last_seen_at: str):
        """Updates theme's last_seen_at and increments occurrence_count."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    UPDATE themes SET last_seen_at = %s, occurrence_count = occurrence_count + 1
                    WHERE id = %s;
                    """,
                    (last_seen_at, theme_id)
                )
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to update theme stats: {e}")
                raise

    def delete_theme(self, theme_id: int) -> bool:
        """Deletes a theme. Occurrences/trajectories/tensions cascade automatically."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute("DELETE FROM themes WHERE id = %s;", (theme_id,))
                deleted = cur.rowcount > 0
                conn.commit()
                return deleted
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to delete theme {theme_id}: {e}")
                raise

    def add_theme_occurrence(self, theme_id: int, source_type: str, source_id: int,
                            snippet: str, similarity_score: float, occurred_at: str):
        """Records that a theme occurred at a specific entry."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO theme_occurrences
                    (theme_id, source_type, source_id, snippet, similarity_score, occurred_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (theme_id, source_type, source_id) DO UPDATE
                    SET snippet = EXCLUDED.snippet, similarity_score = EXCLUDED.similarity_score;
                    """,
                    (theme_id, source_type, source_id, snippet, similarity_score, occurred_at)
                )

                # Invalidate caches
                cur.execute("UPDATE pattern_resolutions SET last_computed_at = NULL WHERE pattern_type = 'theme' AND pattern_id = %s;", (theme_id,))
                cur.execute("UPDATE theme_tensions SET last_computed_at = NULL WHERE theme_a_id = %s OR theme_b_id = %s;", (theme_id, theme_id))
                self.invalidate_leverage_for_source('theme', theme_id)
                self.invalidate_decision_impacts('theme', theme_id)
                self.invalidate_pattern_confidence('theme', theme_id)

                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to add theme occurrence: {e}")
                raise

    def get_theme_occurrences(self, theme_id: int) -> list:
        """Retrieves all occurrences of a theme."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_type, source_id, snippet, similarity_score, occurred_at
                FROM theme_occurrences WHERE theme_id = %s ORDER BY occurred_at DESC;
                """,
                (theme_id,)
            )
            rows = cur.fetchall()
            return [
                {
                    "source_type": row[0],
                    "source_id": row[1],
                    "snippet": row[2],
                    "similarity_score": row[3],
                    "occurred_at": row[4]
                }
                for row in rows
            ]

    def get_unassigned_embeddings(self, user_id: int) -> list:
        """
        Retrieves embeddings that haven't been assigned to any theme.
        An embedding is assigned if it appears in theme_occurrences.
        """
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.id, e.source_type, e.source_id, e.vector, e.created_at
                FROM embeddings e
                WHERE NOT EXISTS (
                    SELECT 1 FROM theme_occurrences occ
                    WHERE occ.source_type = e.source_type AND occ.source_id = e.source_id
                )
                AND (
                    (e.source_type = 'journal_entry' AND e.source_id IN (SELECT id FROM journal_entries WHERE user_id = %s)) OR
                    (e.source_type = 'reflection' AND e.source_id IN (SELECT id FROM reflections WHERE user_id = %s)) OR
                    (e.source_type = 'habit' AND e.source_id IN (SELECT id FROM habits WHERE user_id = %s)) OR
                    (e.source_type = 'habit_completion' AND e.source_id IN (
                        SELECT hc.id FROM habit_completions hc JOIN habits h ON hc.habit_id = h.id
                        WHERE h.user_id = %s AND hc.is_skipped IS NOT TRUE))
                )
                ORDER BY e.created_at DESC;
                """,
                (user_id, user_id, user_id, user_id)
            )
            rows = cur.fetchall()
            return [
                {
                    "embedding_id": row[0],
                    "source_type": row[1],
                    "source_id": row[2],
                    "vector": row[3],
                    "created_at": row[4]
                }
                for row in rows
            ]

    def get_entry_count(self, user_id: int) -> int:
        """Returns the number of journal entries for a user."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM journal_entries WHERE user_id = %s;", (user_id,))
            return cur.fetchone()[0]

    def get_journal_entry_content(self, entry_id: int) -> str:
        """Retrieves the raw text of a journal entry."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT raw_text FROM journal_entries WHERE id = %s;", (entry_id,))
            result = cur.fetchone()
            return result[0] if result else None

    def get_recent_journal_entries(self, user_id: int, limit: int = 3) -> list:
        """Retrieves the most recent journal entries for a user, newest first."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, raw_text, wellbeing_data, created_at
                FROM journal_entries
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (user_id, limit)
            )
            rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "raw_text": row[1],
                    "wellbeing_data": row[2],
                    "created_at": row[3],
                }
                for row in rows
            ]

    def get_content_for_source(self, source_type: str, source_id: int) -> str:
        """Retrieves text content for any source type."""
        with self.connection() as conn, conn.cursor() as cur:
            if source_type == 'journal_entry':
                cur.execute("SELECT raw_text FROM journal_entries WHERE id = %s;", (source_id,))
                res = cur.fetchone()
                return res[0] if res else ""
            elif source_type == 'reflection':
                cur.execute("SELECT content, mood, energy_level, clarity_level FROM reflections WHERE id = %s;", (source_id,))
                res = cur.fetchone()
                if not res: return ""
                return f"Anchor: Self-Reflection | Source: Reflection | Mood: {res[1] or 'okay'} (Energy: {res[2] or '?'}/10, Clarity: {res[3] or '?'}/10) | Content: {res[0]}"
            elif source_type == 'habit':
                cur.execute("SELECT name, description, category FROM habits WHERE id = %s;", (source_id,))
                res = cur.fetchone()
                if not res: return ""
                return f"Anchor: {res[0]} | Source: Habit Definition | Category: {res[2] or 'General'} | Intent: {res[1] or 'No description'}"
            elif source_type == 'habit_completion':
                # Join to get habit name and description
                cur.execute("""
                    SELECT h.name, hc.notes, hc.skip_reason, hc.is_skipped, h.description 
                    FROM habit_completions hc 
                    JOIN habits h ON hc.habit_id = h.id 
                    WHERE hc.id = %s;
                """, (source_id,))
                res = cur.fetchone()
                if not res: return ""
                name, notes, reason, skipped, description = res
                action = "Skipped" if skipped else "Completed"
                details = f"Reason: {reason}" if skipped else f"Notes: {notes}"
                return f"Anchor: {name} | Source: Habit Completion | Intent: {description or 'None'} | Action: {action} | {details}"
            elif source_type == 'message':
                cur.execute("SELECT content FROM conversation_messages WHERE id = %s;", (source_id,))
                res = cur.fetchone()
                return res[0] if res else ""

            return ""

    # ============================================================================
    # Trajectory Methods (Trajectory Engine)
    # ============================================================================

    def create_theme_trajectory(self, theme_id: int, trajectory_label: str,
                               trend_score: float, recent_count: int, past_count: int,
                               confidence_level: str, data_points_count: int) -> None:
        """Creates or updates a theme trajectory record."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute("""
                    INSERT INTO theme_trajectories
                    (theme_id, trajectory_label, trend_score, recent_count, past_count,
                     confidence_level, data_points_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (theme_id) DO UPDATE
                    SET trajectory_label = EXCLUDED.trajectory_label,
                        trend_score = EXCLUDED.trend_score,
                        recent_count = EXCLUDED.recent_count,
                        past_count = EXCLUDED.past_count,
                        confidence_level = EXCLUDED.confidence_level,
                        data_points_count = EXCLUDED.data_points_count,
                        last_computed_at = CURRENT_TIMESTAMP;
                """, (theme_id, trajectory_label, trend_score, recent_count, past_count,
                      confidence_level, data_points_count))
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to create/update theme trajectory: {e}")
                raise

    def get_theme_trajectory(self, theme_id: int) -> dict:
        """Retrieves trajectory information for a specific theme."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT trajectory_label, trend_score, recent_count, past_count,
                       confidence_level, data_points_count, last_computed_at
                FROM theme_trajectories WHERE theme_id = %s;
            """, (theme_id,))
            row = cur.fetchone()
            if row:
                return {
                    "trajectory_label": row[0],
                    "trend_score": row[1],
                    "recent_count": row[2],
                    "past_count": row[3],
                    "confidence_level": row[4],
                    "data_points_count": row[5],
                    "last_computed_at": row[6]
                }
            return None

    def update_theme_trajectory(self, theme_id: int, trajectory_label: str,
                               trend_score: float, recent_count: int, past_count: int,
                               confidence_level: str, data_points_count: int) -> None:
        """Updates a theme trajectory record."""
        self.create_theme_trajectory(theme_id, trajectory_label, trend_score,
                                   recent_count, past_count, confidence_level, data_points_count)

    def get_all_theme_trajectories(self, user_id: int) -> list:
        """Retrieves all theme trajectories for a user."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT tt.theme_id, tt.trajectory_label, tt.trend_score, tt.recent_count,
                       tt.past_count, tt.confidence_level, tt.data_points_count,
                       tt.last_computed_at, t.summary
                FROM theme_trajectories tt
                JOIN themes t ON tt.theme_id = t.id
                WHERE t.user_id = %s
                ORDER BY ABS(tt.trend_score) DESC;
            """, (user_id,))
            rows = cur.fetchall()
            return [
                {
                    "theme_id": row[0],
                    "trajectory_label": row[1],
                    "trend_score": row[2],
                    "recent_count": row[3],
                    "past_count": row[4],
                    "confidence_level": row[5],
                    "data_points_count": row[6],
                    "last_computed_at": row[7],
                    "theme_summary": row[8]
                }
                for row in rows
            ]

    # ============================================================================
    # Tension Methods (Tension Engine)
    # ============================================================================

    def get_theme_pairs(self, user_id: int) -> list:
        """Retrieves all theme pairs for a user."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT t1.id, t1.summary, t2.id, t2.summary
                FROM themes t1
                JOIN themes t2 ON t1.id < t2.id
                WHERE t1.user_id = %s AND t2.user_id = %s
                ORDER BY t1.id, t2.id;
            """, (user_id, user_id))
            rows = cur.fetchall()
            return [
                {
                    "theme_a_id": row[0],
                    "theme_a_summary": row[1],
                    "theme_b_id": row[2],
                    "theme_b_summary": row[3]
                }
                for row in rows
            ]

    def get_theme_pair_occurrences(self, theme_a_id: int, theme_b_id: int) -> list:
        """Retrieves occurrences where both themes appear together."""
        with self.connection() as conn, conn.cursor() as cur:
            # Get occurrences of theme A
            cur.execute("""
                SELECT occurred_at, source_type, source_id
                FROM theme_occurrences
                WHERE theme_id = %s
            """, (theme_a_id,))
            theme_a_occurrences = cur.fetchall()

            # Get occurrences of theme B
            cur.execute("""
                SELECT occurred_at, source_type, source_id
                FROM theme_occurrences
                WHERE theme_id = %s
            """, (theme_b_id,))
            theme_b_occurrences = cur.fetchall()

            # Find co-occurrences (same source_id and close in time)
            cooccurrences = []
            for a_occ in theme_a_occurrences:
                for b_occ in theme_b_occurrences:
                    if a_occ[1] == b_occ[1] and a_occ[2] == b_occ[2]:  # Same source_type and source_id
                        # Same entry, so they co-occur
                        cooccurrences.append({
                            "occurred_at": a_occ[0],
                            "source_type": a_occ[1],
                            "source_id": a_occ[2]
                        })

            return cooccurrences

    def create_or_update_tension(self, theme_a_id: int, theme_b_id: int, cooccurrence_count: int,
                                recent_cooccurrence_count: int, past_cooccurrence_count: int,
                                divergence_score: float, stability_score: float,
                                tension_label: str, confidence_level: str) -> None:
        """Creates or updates a tension record between two themes."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                # Ensure theme_a_id < theme_b_id for consistent ordering
                if theme_a_id > theme_b_id:
                    theme_a_id, theme_b_id = theme_b_id, theme_a_id

                cur.execute("""
                    INSERT INTO theme_tensions
                    (theme_a_id, theme_b_id, cooccurrence_count, recent_cooccurrence_count,
                     past_cooccurrence_count, divergence_score, stability_score,
                     tension_label, confidence_level)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (theme_a_id, theme_b_id) DO UPDATE
                    SET cooccurrence_count = EXCLUDED.cooccurrence_count,
                        recent_cooccurrence_count = EXCLUDED.recent_cooccurrence_count,
                        past_cooccurrence_count = EXCLUDED.past_cooccurrence_count,
                        divergence_score = EXCLUDED.divergence_score,
                        stability_score = EXCLUDED.stability_score,
                        tension_label = EXCLUDED.tension_label,
                        confidence_level = EXCLUDED.confidence_level,
                        last_computed_at = CURRENT_TIMESTAMP;
                """, (theme_a_id, theme_b_id, cooccurrence_count, recent_cooccurrence_count,
                      past_cooccurrence_count, divergence_score, stability_score,
                      tension_label, confidence_level))
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to create/update theme tension: {e}")
                raise

    def get_all_tensions(self, user_id: int) -> list:
        """Retrieves all tensions for a user."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT tt.id, tt.theme_a_id, t1.summary as theme_a_summary,
                       tt.theme_b_id, t2.summary as theme_b_summary,
                       tt.cooccurrence_count, tt.recent_cooccurrence_count,
                       tt.past_cooccurrence_count, tt.divergence_score,
                       tt.stability_score, tt.tension_label, tt.confidence_level,
                       tt.last_computed_at
                FROM theme_tensions tt
                JOIN themes t1 ON tt.theme_a_id = t1.id
                JOIN themes t2 ON tt.theme_b_id = t2.id
                WHERE t1.user_id = %s OR t2.user_id = %s
                ORDER BY tt.stability_score DESC, tt.cooccurrence_count DESC;
            """, (user_id, user_id))
            rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "theme_a_id": row[1],
                    "theme_a_summary": row[2],
                    "theme_b_id": row[3],
                    "theme_b_summary": row[4],
                    "cooccurrence_count": row[5],
                    "recent_cooccurrence_count": row[6],
                    "past_cooccurrence_count": row[7],
                    "divergence_score": row[8],
                    "stability_score": row[9],
                    "tension_label": row[10],
                    "confidence_level": row[11],
                    "last_computed_at": row[12]
                }
                for row in rows
            ]

    def get_significant_tensions(self, user_id: int) -> list:
        """Retrieves significant tensions (high confidence) for a user."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT tt.id, tt.theme_a_id, t1.summary as theme_a_summary,
                       tt.theme_b_id, t2.summary as theme_b_summary,
                       tt.cooccurrence_count, tt.recent_cooccurrence_count,
                       tt.past_cooccurrence_count, tt.divergence_score,
                       tt.stability_score, tt.tension_label, tt.confidence_level,
                       tt.last_computed_at
                FROM theme_tensions tt
                JOIN themes t1 ON tt.theme_a_id = t1.id
                JOIN themes t2 ON tt.theme_b_id = t2.id
                WHERE (t1.user_id = %s OR t2.user_id = %s)
                  AND tt.confidence_level = 'high'
                ORDER BY tt.stability_score DESC, tt.cooccurrence_count DESC;
            """, (user_id, user_id))
            rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "theme_a_id": row[1],
                    "theme_a_summary": row[2],
                    "theme_b_id": row[3],
                    "theme_b_summary": row[4],
                    "cooccurrence_count": row[5],
                    "recent_cooccurrence_count": row[6],
                    "past_cooccurrence_count": row[7],
                    "divergence_score": row[8],
                    "stability_score": row[9],
                    "tension_label": row[10],
                    "confidence_level": row[11],
                    "last_computed_at": row[12]
                }
                for row in rows
            ]

    def invalidate_tension(self, theme_id: int) -> None:
        """Mark all tensions involving this theme as stale (set last_computed_at = NULL)."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute("""
                    UPDATE theme_tensions
                    SET last_computed_at = NULL
                    WHERE theme_a_id = %s OR theme_b_id = %s;
                """, (theme_id, theme_id))
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to invalidate tensions for theme {theme_id}: {e}")
                raise

    # ============================================================================
    # Resolution Methods (Resolution Engine)
    # ============================================================================

    def create_or_update_resolution(self, pattern_type: str, pattern_id: int,
                                  resolution_label: str, attenuation_score: float,
                                  confidence_level: str, recent_count: int,
                                  past_count: int) -> None:
        """Creates or updates a resolution record."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute("""
                    INSERT INTO pattern_resolutions
                    (pattern_type, pattern_id, resolution_label, attenuation_score,
                     confidence_level, recent_count, past_count, last_computed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (pattern_type, pattern_id) DO UPDATE
                    SET resolution_label = EXCLUDED.resolution_label,
                        attenuation_score = EXCLUDED.attenuation_score,
                        confidence_level = EXCLUDED.confidence_level,
                        recent_count = EXCLUDED.recent_count,
                        past_count = EXCLUDED.past_count,
                        last_computed_at = CURRENT_TIMESTAMP;
                """, (pattern_type, pattern_id, resolution_label, attenuation_score,
                      confidence_level, recent_count, past_count))
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to create/update resolution: {e}")
                raise

    def get_resolution(self, pattern_type: str, pattern_id: int) -> dict:
        """Retrieves resolution info for a specific pattern."""
        with self.connection() as conn, conn.cursor() as cur:
            # Get the most recent resolution, preferring ones with last_computed_at set
            cur.execute("""
                SELECT resolution_label, attenuation_score, confidence_level,
                       recent_count, past_count, last_computed_at
                FROM pattern_resolutions
                WHERE pattern_type = %s AND pattern_id = %s
                ORDER BY (last_computed_at IS NOT NULL) DESC, last_computed_at DESC, id DESC
                LIMIT 1;
            """, (pattern_type, pattern_id))
            row = cur.fetchone()
            if row:
                return {
                    "resolution_label": row[0],
                    "attenuation_score": row[1],
                    "confidence_level": row[2],
                    "recent_count": row[3],
                    "past_count": row[4],
                    "last_computed_at": row[5]
                }
            return None

    def get_all_resolutions(self, user_id: int) -> list:
        """Retrieves all resolutions for a user's themes."""
        with self.connection() as conn, conn.cursor() as cur:
            # Join with themes to get summary and filter by user
            cur.execute("""
                SELECT pr.pattern_type, pr.pattern_id, pr.resolution_label,
                       pr.attenuation_score, pr.confidence_level,
                       pr.recent_count, pr.past_count, pr.last_computed_at,
                       t.summary
                FROM pattern_resolutions pr
                JOIN themes t ON pr.pattern_id = t.id
                WHERE pr.pattern_type = 'theme' AND t.user_id = %s
                ORDER BY pr.attenuation_score DESC;
            """, (user_id,))
            rows = cur.fetchall()
            return [
                {
                    "pattern_type": row[0],
                    "pattern_id": row[1],
                    "resolution_label": row[2],
                    "attenuation_score": row[3],
                    "confidence_level": row[4],
                    "recent_count": row[5],
                    "past_count": row[6],
                    "last_computed_at": row[7],
                    "summary": row[8]
                }
                for row in rows
            ]

    def invalidate_resolution(self, pattern_type: str, pattern_id: int) -> None:
        """Mark resolution as stale (last_computed_at = NULL)."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute("""
                    UPDATE pattern_resolutions
                    SET last_computed_at = NULL
                    WHERE pattern_type = %s AND pattern_id = %s;
                """, (pattern_type, pattern_id))
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to invalidate resolution: {e}")
                raise

    # ============================================================================
    # Leverage Methods (Leverage Engine)
    # ============================================================================

    def create_or_update_leverage_pair(self, source_type: str, source_id: int,
                                    target_type: str, target_id: int,
                                    influence_score: float, directional_lift: float,
                                    cooccurrence_count: int, confidence_level: str) -> None:
        """Creates or updates a leverage relationship between two patterns."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute("""
                    INSERT INTO pattern_leverage
                    (source_type, source_id, target_type, target_id,
                     influence_score, directional_lift, cooccurrence_count, confidence_level)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_type, source_id, target_type, target_id) DO UPDATE
                    SET influence_score = EXCLUDED.influence_score,
                        directional_lift = EXCLUDED.directional_lift,
                        cooccurrence_count = EXCLUDED.cooccurrence_count,
                        confidence_level = EXCLUDED.confidence_level,
                        last_computed_at = CURRENT_TIMESTAMP;
                """, (source_type, source_id, target_type, target_id,
                      influence_score, directional_lift, cooccurrence_count, confidence_level))
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to create/update leverage pair: {e}")
                raise

    def get_leverage_targets(self, source_type: str, source_id: int) -> list:
        """Retrieves all patterns influenced by a specific source."""
        with self.connection() as conn, conn.cursor() as cur:
            # We assume themes for target for now
            cur.execute("""
                SELECT pl.target_type, pl.target_id, pl.influence_score, 
                       pl.directional_lift, pl.cooccurrence_count, t.summary
                FROM pattern_leverage pl
                JOIN themes t ON pl.target_id = t.id
                WHERE pl.source_type = %s AND pl.source_id = %s
                  AND pl.target_type = 'theme'
                  AND pl.last_computed_at IS NOT NULL
                ORDER BY pl.influence_score DESC;
            """, (source_type, source_id))
            rows = cur.fetchall()
            return [
                {
                    "target_type": row[0],
                    "target_id": row[1],
                    "influence_score": row[2],
                    "directional_lift": row[3],
                    "cooccurrence_count": row[4],
                    "summary": row[5]
                }
                for row in rows
            ]

    def get_high_leverage_sources(self, user_id: int, min_confidence: str = 'medium') -> list:
        """
        Retrieves top influential patterns for a user.
        Groups by source to see which patterns have the most collective outbound influence.
        """
        conf_map = {'low': 0, 'medium': 1, 'high': 2}
        min_val = conf_map.get(min_confidence, 1)

        with self.connection() as conn, conn.cursor() as cur:
            # We aggregate influence across targets
            cur.execute("""
                SELECT pl.source_type, pl.source_id, AVG(pl.influence_score) as avg_influence,
                       COUNT(pl.target_id) as targets_count, t.summary
                FROM pattern_leverage pl
                JOIN themes t ON pl.source_id = t.id
                WHERE pl.source_type = 'theme' AND t.user_id = %s
                  AND pl.last_computed_at IS NOT NULL
                  AND (CASE WHEN pl.confidence_level = 'high' THEN 2 
                            WHEN pl.confidence_level = 'medium' THEN 1 
                            ELSE 0 END) >= %s
                GROUP BY pl.source_type, pl.source_id, t.summary
                HAVING AVG(pl.influence_score) > 0.1
                ORDER BY avg_influence DESC, targets_count DESC;
            """, (user_id, min_val))
            rows = cur.fetchall()
            return [
                {
                    "source_type": row[0],
                    "source_id": row[1],
                    "avg_influence": row[2],
                    "targets_count": row[3],
                    "summary": row[4]
                }
                for row in rows
            ]

    def invalidate_leverage_for_source(self, source_type: str, source_id: int) -> None:
        """Mark leverage records as stale (last_computed_at = NULL)."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                # Invalidate where it is source OR target
                cur.execute("""
                    UPDATE pattern_leverage
                    SET last_computed_at = NULL
                    WHERE (source_type = %s AND source_id = %s)
                       OR (target_type = %s AND target_id = %s);
                """, (source_type, source_id, source_type, source_id))
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to invalidate leverage: {e}")
                raise

    # ============================================================================
    # Decision Impact Methods (Decision Impact Engine)
    # ============================================================================

    def create_or_update_decision_impact(self, anchor_type: str, anchor_id: int,
                                       target_type: str, target_id: int,
                                       effect_direction: str, delta_score: float,
                                       anchor_count: int, target_count: int,
                                       confidence_level: str) -> None:
        """Creates or updates a decision impact record."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute("""
                    INSERT INTO decision_impacts
                    (anchor_type, anchor_id, target_type, target_id,
                     effect_direction, delta_score, anchor_count, target_count, confidence_level)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (anchor_type, anchor_id, target_type, target_id) DO UPDATE
                    SET effect_direction = EXCLUDED.effect_direction,
                        delta_score = EXCLUDED.delta_score,
                        anchor_count = EXCLUDED.anchor_count,
                        target_count = EXCLUDED.target_count,
                        confidence_level = EXCLUDED.confidence_level,
                        last_computed_at = CURRENT_TIMESTAMP;
                """, (anchor_type, anchor_id, target_type, target_id,
                      effect_direction, delta_score, anchor_count, target_count, confidence_level))
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to create/update decision impact: {e}")
                raise

    def get_decision_impacts_for_anchor(self, anchor_type: str, anchor_id: int) -> list:
        """Retrieves all significant impacts for a specific anchor."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT di.target_type, di.target_id, di.effect_direction,
                       di.delta_score, di.anchor_count, di.target_count,
                       di.confidence_level, t.summary as target_summary
                FROM decision_impacts di
                JOIN themes t ON di.target_id = t.id
                WHERE di.anchor_type = %s AND di.anchor_id = %s
                  AND di.target_type = 'theme'
                  AND di.last_computed_at IS NOT NULL
                ORDER BY ABS(di.delta_score) DESC;
            """, (anchor_type, anchor_id))
            rows = cur.fetchall()
            return [
                {
                    "target_type": row[0],
                    "target_id": row[1],
                    "effect_direction": row[2],
                    "delta_score": row[3],
                    "anchor_count": row[4],
                    "target_count": row[5],
                    "confidence_level": row[6],
                    "target_summary": row[7]
                }
                for row in rows
            ]

    def get_significant_decision_impacts(self, user_id: int, min_confidence: str = 'medium') -> list:
        """Retrieves top significant decision impacts for a user."""
        conf_map = {'low': 0, 'medium': 1, 'high': 2}
        min_val = conf_map.get(min_confidence, 1)

        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT di.anchor_type, di.anchor_id, t1.summary as anchor_summary,
                       di.target_type, di.target_id, t2.summary as target_summary,
                       di.effect_direction, di.delta_score, di.confidence_level
                FROM decision_impacts di
                JOIN themes t1 ON di.anchor_id = t1.id
                JOIN themes t2 ON di.target_id = t2.id
                WHERE t1.user_id = %s AND di.last_computed_at IS NOT NULL
                  AND (CASE WHEN di.confidence_level = 'high' THEN 2 
                            WHEN di.confidence_level = 'medium' THEN 1 
                            ELSE 0 END) >= %s
                ORDER BY ABS(di.delta_score) DESC;
            """, (user_id, min_val))
            rows = cur.fetchall()
            return [
                {
                    "anchor_type": row[0],
                    "anchor_id": row[1],
                    "anchor_summary": row[2],
                    "target_type": row[3],
                    "target_id": row[4],
                    "target_summary": row[5],
                    "effect_direction": row[6],
                    "delta_score": row[7],
                    "confidence_level": row[8]
                }
                for row in rows
            ]

    def invalidate_decision_impacts(self, pattern_type: str, pattern_id: int) -> None:
        """Mark decision impact records as stale (last_computed_at = NULL)."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                # Invalidate where it is anchor OR target
                cur.execute("""
                    UPDATE decision_impacts
                    SET last_computed_at = NULL
                    WHERE (anchor_type = %s AND anchor_id = %s)
                       OR (target_type = %s AND target_id = %s);
                """, (pattern_type, pattern_id, pattern_type, pattern_id))
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to invalidate decision impact: {e}")
                raise

    # ============================================================================
    # Confidence Methods (Confidence Engine)
    # ============================================================================

    def create_or_update_confidence(self, pattern_type: str, pattern_id: int,
                                  confidence_level: str, confidence_score: float,
                                  data_points_count: int, time_coverage_days: int,
                                  consistency_score: float, recency_score: float) -> None:
        """Stores a standard confidence assessment for any pattern."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute("""
                    INSERT INTO pattern_confidence
                    (pattern_type, pattern_id, confidence_level, confidence_score,
                     data_points_count, time_coverage_days, consistency_score, recency_score)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (pattern_type, pattern_id) DO UPDATE
                    SET confidence_level = EXCLUDED.confidence_level,
                        confidence_score = EXCLUDED.confidence_score,
                        data_points_count = EXCLUDED.data_points_count,
                        time_coverage_days = EXCLUDED.time_coverage_days,
                        consistency_score = EXCLUDED.consistency_score,
                        recency_score = EXCLUDED.recency_score,
                        last_computed_at = CURRENT_TIMESTAMP;
                """, (pattern_type, pattern_id, confidence_level, confidence_score,
                      data_points_count, time_coverage_days, consistency_score, recency_score))
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to create/update pattern confidence: {e}")
                raise

    def get_confidence(self, pattern_type: str, pattern_id: int) -> dict:
        """Retrieves the central confidence assessment for a pattern."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT confidence_level, confidence_score, data_points_count,
                       time_coverage_days, consistency_score, recency_score,
                       last_computed_at
                FROM pattern_confidence
                WHERE pattern_type = %s AND pattern_id = %s;
            """, (pattern_type, pattern_id))
            row = cur.fetchone()
            if row:
                return {
                    "confidence_level": row[0],
                    "confidence_score": row[1],
                    "data_points_count": row[2],
                    "time_coverage_days": row[3],
                    "consistency_score": row[4],
                    "recency_score": row[5],
                    "last_computed_at": row[6]
                }
            return None

    def invalidate_pattern_confidence(self, pattern_type: str, pattern_id: int) -> None:
        """Mark central confidence record as stale."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute("""
                    UPDATE pattern_confidence
                    SET last_computed_at = NULL
                    WHERE pattern_type = %s AND pattern_id = %s;
                """, (pattern_type, pattern_id))
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to invalidate pattern confidence: {e}")
                raise

    # ============================================================================
    # Evidence Methods (Evidence Engine)
    # ============================================================================

    def add_evidence_records(self, records: list) -> None:
        """
        Batch inserts evidence records.
        Each record should be a tuple/dict containing:
        (computation_id, pattern_type, pattern_id, engine_name, evidence_type, evidence_key, evidence_value)
        """
        if not records:
            return

        with self.connection() as conn, conn.cursor() as cur:
            try:
                # evidence_value is stored as JSONB
                from psycopg2.extras import execute_values
                execute_values(cur, """
                    INSERT INTO pattern_evidence 
                    (computation_id, pattern_type, pattern_id, engine_name, evidence_type, evidence_key, evidence_value)
                    VALUES %s
                """, records)
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to batch insert evidence: {e}")
                raise

    def get_latest_evidence_bundle(self, pattern_type: str, pattern_id: int, engine_name: str = None) -> list:
        """
        Retrieves evidence records for a pattern.
        If engine_name is provided, gets the latest snapshot for THAT engine.
        If NO engine_name provided, gets the latest snapshots for ALL engines 
        associated with this pattern.
        """
        with self.connection() as conn, conn.cursor() as cur:
            if engine_name:
                # 1. Find latest computation for specific engine
                cur.execute("""
                    SELECT computation_id FROM pattern_evidence 
                    WHERE pattern_type = %s AND pattern_id = %s AND engine_name = %s
                    ORDER BY created_at DESC LIMIT 1
                """, (pattern_type, pattern_id, engine_name))
                row = cur.fetchone()
                if not row: return []
                comp_ids = [row[0]]
            else:
                # 2. Find the latest computation_id for EACH engine associated with this pattern
                cur.execute("""
                    SELECT DISTINCT ON (engine_name) computation_id
                    FROM pattern_evidence
                    WHERE pattern_type = %s AND pattern_id = %s
                    ORDER BY engine_name, created_at DESC
                """, (pattern_type, pattern_id))
                rows = cur.fetchall()
                if not rows: return []
                comp_ids = [r[0] for r in rows]

            # 3. Fetch all records for these computation IDs
            cur.execute("""
                SELECT engine_name, evidence_type, evidence_key, evidence_value, created_at
                FROM pattern_evidence
                WHERE computation_id IN %s
                ORDER BY created_at DESC, engine_name, evidence_type, evidence_key
            """, (tuple(comp_ids),))

            rows = cur.fetchall()
            return [
                {
                    "engine_name": r[0],
                    "evidence_type": r[1],
                    "evidence_key": r[2],
                    "evidence_value": r[3],
                    "created_at": r[4]
                }
                for r in rows
            ]

    # ============================================================================
    # Prioritization Methods (Prioritization Engine)
    # ============================================================================

    def create_or_update_insight_priority(self, insight_id: str, engine_name: str,
                                        pattern_type: str, pattern_id: int,
                                        priority_score: float, rank: int) -> None:
        """Stores or updates the priority score and rank for an insight."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute("""
                    INSERT INTO insight_priorities 
                    (insight_id, engine_name, pattern_type, pattern_id, priority_score, rank)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (insight_id) DO UPDATE
                    SET priority_score = EXCLUDED.priority_score,
                        rank = EXCLUDED.rank,
                        computed_at = CURRENT_TIMESTAMP;
                """, (insight_id, engine_name, pattern_type, pattern_id, priority_score, rank))
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to create/update insight priority: {e}")
                raise

    def get_insight_priority(self, engine_name: str, pattern_type: str, pattern_id: int) -> dict:
        """Retrieves the priority assessment for a specific insight."""
        insight_id = f"{engine_name}:{pattern_type}:{pattern_id}"
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT priority_score, rank, computed_at
                FROM insight_priorities
                WHERE insight_id = %s;
            """, (insight_id,))
            row = cur.fetchone()
            if row:
                return {
                    "priority_score": row[0],
                    "rank": row[1],
                    "computed_at": row[2]
                }
            return None

    # ============================================================================
    # User Preferences Methods (Control & Transparency)
    # ============================================================================

    def get_preferences(self, user_id: int) -> dict:
        """Retrieves user preferences or returns default structure if not found."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute("""
                    SELECT min_confidence, max_items, enabled_engines, show_suppressed
                    FROM user_preferences WHERE user_id = %s;
                """, (user_id,))
                row = cur.fetchone()
                if row:
                    return {
                        "min_confidence": row[0],
                        "max_items": row[1],
                        "enabled_engines": row[2], # list or None
                        "show_suppressed": row[3]
                    }
                return None
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to get preferences for user {user_id}: {e}")
                raise

    # The only columns update_preference may write. `key` reaches SQL as an
    # identifier, which cannot be parameterised, so it is checked against this
    # set rather than trusted. Nothing user-facing calls this today; the check
    # is here so that adding a preferences endpoint later cannot turn it into
    # an injection.
    _PREFERENCE_COLS = frozenset({
        "min_confidence", "max_items", "enabled_engines", "show_suppressed",
    })

    def update_preference(self, user_id: int, key: str, value: Any) -> None:
        """
        Updates a specific user preference and logs the change.
        Note: value must be JSON serializable if updating enabled_engines.
        """
        if key not in self._PREFERENCE_COLS:
            raise ValueError(f"Unknown preference: {key!r}")

        with self.connection() as conn, conn.cursor() as cur:
            try:
                # 1. Fetch old value for audit
                cur.execute(f"SELECT {key} FROM user_preferences WHERE user_id = %s;", (user_id,))
                row = cur.fetchone()
                old_val = str(row[0]) if row else None

                # 2. Upsert preference
                cur.execute(f"""
                    INSERT INTO user_preferences (user_id, {key}, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id) DO UPDATE
                    SET {key} = EXCLUDED.{key}, updated_at = CURRENT_TIMESTAMP;
                """, (user_id, value if not isinstance(value, list) else Json(value)))

                # 3. Log audit
                cur.execute("""
                    INSERT INTO preference_audit (user_id, setting_key, old_value, new_value)
                    VALUES (%s, %s, %s, %s);
                """, (user_id, key, old_val, str(value)))

                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to update preference '{key}': {e}")
                raise

    def reset_preferences(self, user_id: int) -> None:
        """Deletes user preference row to restore system defaults."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute("DELETE FROM user_preferences WHERE user_id = %s;", (user_id,))
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to reset preferences: {e}")
                raise

    # ============================================================================
    # App Settings Methods (frontend User/UserPreferences + onboarding)
    # ============================================================================

    # Columns stored as JSONB — values are wrapped in Json() on write.
    _APP_SETTINGS_JSON_COLS = {"threads", "connectors", "onboarding_answers"}
    _APP_SETTINGS_COLS = [
        "name", "timezone", "tone", "density", "daily_checkin_time",
        "weekly_review_time", "max_nudges_per_day", "threads", "connectors",
        "onboarding_completed", "onboarding_answers",
    ]

    def get_app_settings(self, user_id: int) -> dict:
        """Returns the user's app settings row (incl. users.created_at), or None."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute("""
                    SELECT s.name, s.timezone, s.tone, s.density, s.daily_checkin_time,
                           s.weekly_review_time, s.max_nudges_per_day, s.threads,
                           s.connectors, s.onboarding_completed, s.onboarding_answers,
                           u.created_at
                    FROM users u
                    LEFT JOIN user_app_settings s ON s.user_id = u.id
                    WHERE u.id = %s;
                """, (user_id,))
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "name": row[0],
                    "timezone": row[1] or "UTC",
                    "tone": row[2] or "warm",
                    "density": row[3] or "balanced",
                    "daily_checkin_time": row[4],
                    "weekly_review_time": row[5],
                    "max_nudges_per_day": row[6] if row[6] is not None else 3,
                    "threads": row[7] if row[7] is not None else [],
                    "connectors": row[8] if row[8] is not None else {},
                    "onboarding_completed": bool(row[9]),
                    "onboarding_answers": row[10] if row[10] is not None else {},
                    "created_at": row[11],
                }
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to get app settings for user {user_id}: {e}")
                raise

    def upsert_app_settings(self, user_id: int, **fields) -> None:
        """Upserts the given app-settings columns for the user."""
        cols = [c for c in fields if c in self._APP_SETTINGS_COLS]
        if not cols:
            return
        values = [
            Json(fields[c]) if c in self._APP_SETTINGS_JSON_COLS else fields[c]
            for c in cols
        ]
        insert_cols = ", ".join(["user_id"] + cols)
        placeholders = ", ".join(["%s"] * (len(cols) + 1))
        updates = ", ".join([f"{c} = EXCLUDED.{c}" for c in cols])
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(f"""
                    INSERT INTO user_app_settings ({insert_cols}, updated_at)
                    VALUES ({placeholders}, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id) DO UPDATE
                    SET {updates}, updated_at = CURRENT_TIMESTAMP;
                """, [user_id] + values)
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to upsert app settings for user {user_id}: {e}")
                raise

    # ============================================================================
    # Insight Status Methods (snooze/resolve/seen for engine-derived insights)
    # ============================================================================

    def get_insight_statuses(self, user_id: int) -> dict:
        """Returns {insight_id: {status, snoozed_until, seen}} for the user."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute("""
                    SELECT insight_id, status, snoozed_until, seen
                    FROM insight_status WHERE user_id = %s;
                """, (user_id,))
                return {
                    r[0]: {"status": r[1], "snoozed_until": r[2], "seen": bool(r[3])}
                    for r in cur.fetchall()
                }
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to get insight statuses for user {user_id}: {e}")
                raise

    def set_insight_status(self, user_id: int, insight_id: str, status: str,
                           snoozed_until=None) -> None:
        """Upserts the status (and optional snooze expiry) for one insight."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute("""
                    INSERT INTO insight_status (user_id, insight_id, status, snoozed_until, updated_at)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id, insight_id) DO UPDATE
                    SET status = EXCLUDED.status, snoozed_until = EXCLUDED.snoozed_until,
                        updated_at = CURRENT_TIMESTAMP;
                """, (user_id, insight_id, status, snoozed_until))
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to set insight status for user {user_id}: {e}")
                raise

    def mark_insight_seen(self, user_id: int, insight_id: str) -> None:
        """Marks one insight as seen for the user."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute("""
                    INSERT INTO insight_status (user_id, insight_id, seen, updated_at)
                    VALUES (%s, %s, TRUE, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id, insight_id) DO UPDATE
                    SET seen = TRUE, updated_at = CURRENT_TIMESTAMP;
                """, (user_id, insight_id))
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to mark insight seen for user {user_id}: {e}")
                raise

    # ============================================================================
    # Habits Methods
    # ============================================================================

    def create_habit(self, user_id: int, name: str, description: str = None,
                    frequency_type: str = 'daily', habit_type: str = 'completion',
                    weekly_target: float = 0, tracking_metric: str = 'completion',
                    category: str = 'general') -> int:
        """Creates a new habit and returns its ID."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO habits (user_id, name, description, frequency_type, habit_type, weekly_target, tracking_metric, category)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
                    """,
                    (user_id, name, description, frequency_type, habit_type, weekly_target, tracking_metric, category)
                )
                habit_id = cur.fetchone()[0]
                conn.commit()
                logger.info(f"Created habit ID {habit_id} for user {user_id}")
                return habit_id
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to create habit: {e}")
                raise

    def get_habits(self, user_id: int, active_only: bool = True) -> list:
        """Retrieves habits for a user."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                if active_only:
                    cur.execute(
                        """
                        SELECT id, name, description, frequency_type, habit_type, weekly_target, tracking_metric, category, is_active,
                               current_streak, longest_streak, total_completions, created_at
                        FROM habits WHERE user_id = %s AND is_active = TRUE
                        ORDER BY created_at DESC;
                        """,
                        (user_id,)
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, name, description, frequency_type, habit_type, weekly_target, tracking_metric, category, is_active,
                               current_streak, longest_streak, total_completions, created_at
                        FROM habits WHERE user_id = %s
                        ORDER BY created_at DESC;
                        """,
                        (user_id,)
                    )
                rows = cur.fetchall()
                return [
                    {
                        "id": row[0],
                        "name": row[1],
                        "description": row[2],
                        "frequency_type": row[3],
                        "habit_type": row[4],
                        "weekly_target": row[5],
                        "tracking_metric": row[6],
                        "category": row[7],
                        "is_active": row[8],
                        "current_streak": row[9],
                        "longest_streak": row[10],
                        "total_completions": row[11],
                        "created_at": row[12]
                    }
                    for row in rows
                ]
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to get habits for user {user_id}: {e}")
                raise

    def get_habit(self, habit_id: int) -> dict:
        """Retrieves a specific habit by ID."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT id, user_id, name, description, frequency_type, habit_type, weekly_target, tracking_metric, category, is_active,
                           current_streak, longest_streak, total_completions, created_at, updated_at
                    FROM habits WHERE id = %s;
                    """,
                    (habit_id,)
                )
                row = cur.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "user_id": row[1],
                        "name": row[2],
                        "description": row[3],
                        "frequency_type": row[4],
                        "habit_type": row[5],
                        "weekly_target": row[6],
                        "tracking_metric": row[7],
                        "category": row[8],
                        "is_active": row[9],
                        "current_streak": row[10],
                        "longest_streak": row[11],
                        "total_completions": row[12],
                        "created_at": row[13],
                        "updated_at": row[14]
                    }
                return None
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to get habit {habit_id}: {e}")
                raise

    def update_habit(self, habit_id: int, **updates) -> bool:
        """Updates a habit's fields."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                allowed_fields = {'name', 'description', 'is_active', 'current_streak', 'longest_streak', 'total_completions', 'habit_type', 'weekly_target', 'tracking_metric'}
                update_pairs = [(k, v) for k, v in updates.items() if k in allowed_fields]

                if not update_pairs:
                    return True

                set_clause = ", ".join([f"{k} = %s" for k, v in update_pairs])
                values = [v for k, v in update_pairs] + [habit_id]

                cur.execute(
                    f"UPDATE habits SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = %s;",
                    values
                )
                conn.commit()
                return True
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to update habit {habit_id}: {e}")
                raise

    def delete_habit(self, habit_id: int) -> bool:
        """Soft-deletes a habit by marking it as inactive."""
        return self.update_habit(habit_id, is_active=False)

    def log_habit_completion(self, habit_id: int, completion_date, value: float = 1.0, notes: str = None) -> int:
        """Logs a habit completion."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO habit_completions (habit_id, completion_date, is_completed, value, notes)
                    VALUES (%s, %s, TRUE, %s, %s)
                    ON CONFLICT (habit_id, completion_date) DO UPDATE
                    SET is_completed = TRUE, is_skipped = FALSE, value = EXCLUDED.value, notes = EXCLUDED.notes
                    RETURNING id;
                    """,
                    (habit_id, completion_date, value, notes)
                )
                completion_id = cur.fetchone()[0]
                conn.commit()
                return completion_id
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to log habit completion: {e}")
                raise

    def uncomplete_habit(self, habit_id: int, completion_date=None) -> bool:
        """Removes a habit's completion for a date, and everything derived from it.

        embeddings and theme_occurrences reference their source by
        (source_type, source_id) rather than by foreign key, so deleting the
        completion alone left a day the user had taken back still counting as
        evidence for the theme, and still reachable by semantic search.
        """
        if completion_date is None:
            from datetime import date
            completion_date = date.today()
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    "SELECT id FROM habit_completions WHERE habit_id = %s AND completion_date = %s;",
                    (habit_id, completion_date)
                )
                row = cur.fetchone()
                if row:
                    completion_id = row[0]
                    cur.execute(
                        "DELETE FROM theme_occurrences WHERE source_type = 'habit_completion' AND source_id = %s;",
                        (completion_id,)
                    )
                    cur.execute(
                        "DELETE FROM embeddings WHERE source_type = 'habit_completion' AND source_id = %s;",
                        (completion_id,)
                    )
                cur.execute(
                    "DELETE FROM habit_completions WHERE habit_id = %s AND completion_date = %s;",
                    (habit_id, completion_date)
                )
                deleted = cur.rowcount > 0
                conn.commit()
                return deleted
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to uncomplete habit {habit_id} on {completion_date}: {e}")
                raise

    def log_habit_skip(self, habit_id: int, skip_date, reason: str = None) -> int:
        """Logs a habit skip."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO habit_completions
                        (habit_id, completion_date, is_completed, is_skipped, skip_reason,
                         processing_status)
                    -- is_completed must be set explicitly: the column defaults to
                    -- TRUE, so a first skip used to be stored as completed *and*
                    -- skipped, and everything counting completions counted it.
                    -- Only the ON CONFLICT branch below ever corrected it.
                    VALUES (%s, %s, FALSE, TRUE, %s, 'skipped')
                    ON CONFLICT (habit_id, completion_date) DO UPDATE
                    SET is_skipped = TRUE, is_completed = FALSE,
                        skip_reason = EXCLUDED.skip_reason, processing_status = 'skipped'
                    RETURNING id;
                    """,
                    (habit_id, skip_date, reason)
                )
                skip_id = cur.fetchone()[0]
                conn.commit()
                return skip_id
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to log habit skip: {e}")
                raise

    def get_habit_completions(self, habit_id: int, start_date = None, end_date = None) -> list:
        """Retrieves completions for a habit in a date range."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                if start_date and end_date:
                    cur.execute(
                        """
                        SELECT id, completion_date, is_completed, is_skipped, skip_reason, value, notes, completed_at
                        FROM habit_completions
                        WHERE habit_id = %s AND completion_date BETWEEN %s AND %s
                        ORDER BY completion_date DESC;
                        """,
                        (habit_id, start_date, end_date)
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, completion_date, is_completed, is_skipped, skip_reason, value, notes, completed_at
                        FROM habit_completions
                        WHERE habit_id = %s
                        ORDER BY completion_date DESC LIMIT 30;
                        """,
                        (habit_id,)
                    )
                rows = cur.fetchall()
                return [
                    {
                        "id": row[0],
                        "completion_date": row[1],
                        "is_completed": row[2],
                        "is_skipped": row[3],
                        "skip_reason": row[4],
                        "value": row[5],
                        "notes": row[6],
                        "completed_at": row[7]
                    }
                    for row in rows
                ]
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to get habit completions for habit {habit_id}: {e}")
                raise

    # ============================================================================
    # Reflections Methods
    # ============================================================================

    def create_reflection(self, user_id: int, content: str, reflection_date = None,
                         mood: str = None, energy_level: int = None, clarity_level: int = None, tags: list = None) -> int:
        """Creates a new reflection and returns its ID."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                from datetime import date
                if reflection_date is None:
                    reflection_date = date.today()

                cur.execute(
                    """
                    INSERT INTO reflections (user_id, reflection_date, content, mood, energy_level, clarity_level, tags)
                    VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;
                    """,
                    (user_id, reflection_date, content, mood, energy_level, clarity_level, Json(tags) if tags else None)
                )
                reflection_id = cur.fetchone()[0]
                conn.commit()
                logger.info(f"Created reflection ID {reflection_id} for user {user_id}")
                return reflection_id
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to create reflection: {e}")
                raise

    def get_reflections(self, user_id: int, limit: int = 30, before_id: int = None,
                        start_date=None, end_date=None) -> list:
        """Retrieves a user's reflections, newest first.

        `before_id` is a keyset cursor: pass the id of the last row you saw to
        get the page after it. Ordering is by id rather than reflection_date so
        the cursor stays stable when several entries share a date.

        `start_date`/`end_date` are applied in SQL. They used to be filtered in
        Python *after* fetching only the most recent `limit` rows, so a date
        range that fell outside those rows silently came back empty — which is
        why the weekly review compared a week against nothing once a user had
        more than `limit` entries.
        """
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT id, reflection_date, content, mood, energy_level, clarity_level, tags, created_at, updated_at
                    FROM reflections
                    WHERE user_id = %s
                      AND (%s::int IS NULL OR id < %s)
                      AND (%s::date IS NULL OR reflection_date >= %s)
                      AND (%s::date IS NULL OR reflection_date <= %s)
                    ORDER BY id DESC
                    LIMIT %s;
                    """,
                    (user_id, before_id, before_id, start_date, start_date,
                     end_date, end_date, limit)
                )
                rows = cur.fetchall()
                return [
                    {
                        "id": row[0],
                        "reflection_date": row[1],
                        "content": row[2],
                        "mood": row[3],
                        "energy_level": row[4],
                        "clarity_level": row[5],
                        "tags": row[6],
                        "created_at": row[7],
                        "updated_at": row[8]
                    }
                    for row in rows
                ]
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to get reflections for user {user_id}: {e}")
                raise

    def get_reflection(self, reflection_id: int) -> dict:
        """Retrieves a specific reflection by ID."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT id, user_id, reflection_date, content, mood, energy_level, tags,
                           processing_status, created_at, updated_at
                    FROM reflections WHERE id = %s;
                    """,
                    (reflection_id,)
                )
                row = cur.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "user_id": row[1],
                        "reflection_date": row[2],
                        "content": row[3],
                        "mood": row[4],
                        "energy_level": row[5],
                        "tags": row[6],
                        "processing_status": row[7],
                        "created_at": row[8],
                        "updated_at": row[9]
                    }
                return None
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to get reflection {reflection_id}: {e}")
                raise

    def update_reflection(self, reflection_id: int, **updates) -> bool:
        """Updates a reflection's fields."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                allowed_fields = {'content', 'mood', 'energy_level', 'tags'}
                update_pairs = [(k, v) for k, v in updates.items() if k in allowed_fields]

                if not update_pairs:
                    return True

                set_clause = ", ".join([f"{k} = %s" for k, v in update_pairs])
                values = []
                for k, v in update_pairs:
                    if k == 'tags':
                        values.append(Json(v) if v else None)
                    else:
                        values.append(v)
                values.append(reflection_id)

                cur.execute(
                    f"UPDATE reflections SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = %s;",
                    values
                )
                conn.commit()
                return True
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to update reflection {reflection_id}: {e}")
                raise

    def delete_reflection(self, reflection_id: int) -> bool:
        """Deletes a reflection and everything derived from it.

        embeddings and theme_occurrences reference sources by
        (source_type, source_id) rather than by foreign key, so deleting the
        row alone left an embedding that still matched semantic searches and an
        occurrence that still counted as evidence for a theme.
        """
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    "DELETE FROM theme_occurrences WHERE source_type = 'reflection' AND source_id = %s;",
                    (reflection_id,)
                )
                cur.execute(
                    "DELETE FROM embeddings WHERE source_type = 'reflection' AND source_id = %s;",
                    (reflection_id,)
                )
                cur.execute("DELETE FROM reflections WHERE id = %s;", (reflection_id,))
                conn.commit()
                return True
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to delete reflection {reflection_id}: {e}")
                raise









# Create a global instance for easy access throughout the application
db = Database()

# Initialize repositories for clean domain-specific access
from .repositories import initialize_repositories

_repos = initialize_repositories(db)

# Export repositories for use by engines and other modules
users = _repos['users']
journals = _repos['journals']
habits = _repos['habits']
embeddings = _repos['embeddings']
themes = _repos['themes']
trajectories = _repos['trajectories']
tensions = _repos['tensions']
resolutions = _repos['resolutions']
leverage = _repos['leverage']
decision_impacts = _repos['decision_impacts']
confidence = _repos['confidence']
evidence = _repos['evidence']
priorities = _repos['priorities']
preferences = _repos['preferences']
