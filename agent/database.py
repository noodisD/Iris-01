"""
Database Layer - PostgreSQL Source of Truth

This module is the only part of the application that should interact directly with PostgreSQL.
It enforces the single source of truth principle. All data, including embeddings,
is stored here canonically.
"""

import logging
import os
from contextlib import contextmanager
from typing import Any

import psycopg2

# Use pgvector extension
from pgvector.psycopg2 import register_vector
from psycopg2 import pool as psycopg2_pool
from psycopg2.extras import Json

from .config import settings

logger = logging.getLogger(__name__)

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

    # The schema is owned by migrations/ (ADR-0012). create_schema() used to
    # live here and build it with CREATE TABLE IF NOT EXISTS; migrations/
    # 0001_initial_schema.sql was generated from its statements, so the DDL is
    # unchanged — it simply has one owner now, and one that can express a
    # change rather than only an addition.

    # ============================================================================
    # User Methods
    # ============================================================================

    def create_user(self, username: str) -> int:
        """Creates a user and returns its id. There is no password: IRIS has one
        local user and no login (ADR-0001, migration 0014)."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO users (username) VALUES (%s) RETURNING id;",
                    (username,)
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
                cur.execute("SELECT id, username FROM users WHERE username = %s;", (username,))
                user_data = cur.fetchone()
                if user_data:
                    return {"id": user_data[0], "username": user_data[1]}
                return None
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to get user {username}: {e}")
                raise

    def local_user_id(self, username: str | None = None) -> int:
        """The one local user's id, created on first use.

        The HTTP app and the CLI both resolve the owner through this, so the two
        front doors cannot disagree about who is using IRIS — the CLI used to
        have its own login and its own users.
        """
        username = username or os.getenv("IRIS_DEFAULT_USER", "local")
        user = self.get_user(username)
        return user["id"] if user else self.create_user(username)

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
                # Embedded for recall, never clustered (ADR-0003); queued here so
                # the message and its job commit together.
                self._queue(cur, user_id, 'message', message_id)
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
                    (query_vector, user_id, user_id, user_id, n_results)
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
        """Updates the processing status of an item (e.g., a reflection)."""
        table_map = {
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

    def is_still_processing(self, source_type: str, source_id: int) -> bool:
        """Whether a source is still in the state the running job put it in.

        An edit resets a reflection to 'pending'. A run that read the old text
        checks this before writing anything derived from it, so it stops
        instead of storing an embedding of words that no longer exist.
        """
        table, id_col = {
            'message': ('conversation_messages', 'id'),
            'reflection': ('reflections', 'id'),
            'habit': ('habits', 'id'),
            'habit_completion': ('habit_completions', 'id'),
        }[source_type]
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT processing_status FROM {table} WHERE {id_col} = %s;",
                        (source_id,))
            row = cur.fetchone()
            return bool(row) and row[0] == 'processing'

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
            if source_type == 'message':
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
                    first_seen_at: str, last_seen_at: str, occurrence_count: int = 1,
                    origin: str = "clustered", definition: str = None,
                    status: str = "active", claim_kind: str = "mention",
                    span_is_undated: bool = False) -> int:
        """Creates a new theme and returns its ID.

        The defaults describe a cluster, which is what every existing caller
        creates. A construct passes origin='observed' and status='candidate':
        a row that exists and can be reviewed, but that no engine measures
        until the owner confirms it.
        """
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO themes (user_id, centroid_embedding, summary, first_seen_at,
                                        last_seen_at, occurrence_count, origin, definition,
                                        status, claim_kind, span_is_undated)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
                    """,
                    (user_id, centroid_embedding, summary, first_seen_at, last_seen_at,
                     occurrence_count, origin, definition, status, claim_kind,
                     span_is_undated)
                )
                theme_id = cur.fetchone()[0]
                conn.commit()
                logger.info(f"Created theme ID {theme_id} for user {user_id}")
                return theme_id
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to create theme: {e}")
                raise

    #: What a theme row looks like to the engines, in one place so the active
    #: list and a status listing cannot drift apart.
    _THEME_COLUMNS = """id, centroid_embedding, summary, first_seen_at, last_seen_at,
                        occurrence_count, origin, definition, status, claim_kind,
                        span_is_undated, undated_occurrence_count"""

    @staticmethod
    def _theme_row(row) -> dict:
        return {
            "id": row[0],
            "centroid_embedding": row[1],
            "summary": row[2],
            "first_seen_at": row[3],
            "last_seen_at": row[4],
            "occurrence_count": row[5],
            "origin": row[6],
            "definition": row[7],
            "status": row[8],
            "claim_kind": row[9],
            "span_is_undated": row[10],
            # Occurrences in writing that carries no date. Kept apart from
            # occurrence_count rather than added to it: every window engine
            # gates on that number, and an undated occurrence cannot sit in a
            # window (ADR-0009).
            "undated_occurrence_count": row[11],
        }

    def get_themes(self, user_id: int) -> list:
        """The themes the engines may measure.

        Only `active` ones. A construct the owner has not confirmed yet exists
        as a row, has prototypes, and is visible for review — but measuring it
        would be counting a pattern nobody vouched for, which is the failure
        this status column exists to prevent.
        """
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {self._THEME_COLUMNS} FROM themes
                WHERE user_id = %s AND status = 'active'
                ORDER BY occurrence_count DESC;
                """,
                (user_id,)
            )
            return [self._theme_row(row) for row in cur.fetchall()]

    def create_observation_run(self, user_id: int, model: str, prompt_version: str,
                               entries_read: int, passes_planned: int) -> int:
        """Open a record of a reading run before any of it happens.

        Written first, so a run that dies partway still leaves a trace. A read
        that produced nothing and a read that never finished look identical from
        the outside, and telling them apart is the whole point.
        """
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO observation_runs
                    (user_id, model, prompt_version, entries_read, passes_planned, status)
                VALUES (%s, %s, %s, %s, %s, 'running') RETURNING id;
                """,
                (user_id, model, prompt_version, entries_read, passes_planned))
            run_id = cur.fetchone()[0]
            conn.commit()
            return run_id

    def finish_observation_run(self, run_id: int, status: str, passes_completed: int,
                               raw_observations, candidates_staged: int = 0,
                               error: str = None, dropped: dict | None = None) -> None:
        """Close the record with what actually happened.

        `raw_observations` is the pre-merge output: the claims and verified
        citations exactly as they came back, before anything was joined. Keeping
        it means a change to consolidation can be replayed offline instead of
        re-reading the owner's archive, which costs money and sends private
        writing out again.
        """
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE observation_runs
                   SET status = %s, passes_completed = %s, raw_observations = %s,
                       candidates_staged = %s, error = %s, dropped = %s,
                       finished_at = NOW()
                 WHERE id = %s;
                """,
                (status, passes_completed, Json(raw_observations) if raw_observations is not None else None,
                 candidates_staged, error, Json(dropped) if dropped is not None else None, run_id))
            conn.commit()

    def record_run_candidates(self, run_id: int, staged: int, already_decided: int = 0,
                              not_embedded: int = 0) -> None:
        """How many proposals a finished run put in front of the owner, and how
        many of its findings were held back at that last step.

        Separate from closing the run because staging happens afterwards: the
        reading is done and recorded before anything is promoted, so that a
        failure while promoting cannot make a completed read look like it never
        happened.
        """
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """UPDATE observation_runs
                      SET candidates_staged = %s,
                          dropped = COALESCE(dropped, '{}'::jsonb)
                                    || jsonb_build_object('already_decided', %s::int,
                                                          'not_embedded', %s::int)
                    WHERE id = %s;""",
                (staged, already_decided, not_embedded, run_id))
            conn.commit()

    def get_latest_observation_run(self, user_id: int) -> dict | None:
        """The most recent discovery run, as counts. Never a claim or a quote."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT id, status, started_at, finished_at, entries_read,
                          passes_planned, passes_completed,
                          COALESCE(jsonb_array_length(raw_observations), 0),
                          candidates_staged, COALESCE(dropped, '{}'::jsonb)
                     FROM observation_runs WHERE user_id = %s
                    ORDER BY started_at DESC, id DESC LIMIT 1;""",
                (user_id,))
            row = cur.fetchone()
        if row is None:
            return None
        keys = ("id", "status", "started_at", "finished_at", "entries_read", "passes_planned",
                "passes_completed", "raw_findings", "candidates_staged", "dropped")
        return dict(zip(keys, row, strict=True))

    def get_decided_proposal_keys(self, user_id: int) -> set:
        """Proposals the owner has already seen, whatever they decided.

        Re-reading unchanged writing produces the same findings again. Without
        this, a rerun would offer back a proposal already rejected, and quietly
        duplicate one already confirmed.
        """
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT proposal_key FROM themes
                    WHERE user_id = %s AND proposal_key IS NOT NULL;""",
                (user_id,))
            return {r[0] for r in cur.fetchall()}

    def set_theme_proposal(self, theme_id: int, proposal_key: str, run_id: int = None) -> None:
        """Tie a candidate to what proposed it, and to its stable identity."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """UPDATE themes SET proposal_key = %s, observation_run_id = %s
                    WHERE id = %s;""",
                (proposal_key, run_id, theme_id))
            conn.commit()

    def get_themes_by_origin(self, user_id: int, origin: str) -> list:
        """Active themes of one origin.

        Clustering and constructs answer different questions, so they must not
        compete for the same slot. An entry belongs to at most one cluster —
        topical grouping is exclusive by design — but to as many constructs as
        describe it, because "went all in" and "slept badly" are not rivals.
        Mixing them meant a confirmed construct could lose an entry to a cluster
        on ingestion while winning it during replay, so confirming a construct
        changed measured frequency for reasons that were routing, not writing.
        """
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {self._THEME_COLUMNS} FROM themes
                WHERE user_id = %s AND status = 'active' AND origin = %s
                ORDER BY occurrence_count DESC;
                """,
                (user_id, origin)
            )
            return [self._theme_row(row) for row in cur.fetchall()]

    def get_themes_by_status(self, user_id: int, status: str) -> list:
        """Themes in one state, newest first — the review surface's query."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {self._THEME_COLUMNS} FROM themes
                WHERE user_id = %s AND status = %s
                ORDER BY id DESC;
                """,
                (user_id, status)
            )
            return [self._theme_row(row) for row in cur.fetchall()]

    def get_theme_by_id(self, theme_id: int) -> dict:
        """Retrieves a specific theme by ID."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, centroid_embedding, summary, first_seen_at, last_seen_at,
                       occurrence_count, user_id, origin, definition, status, confirmed_at,
                       claim_kind, span_is_undated, undated_occurrence_count
                  FROM themes WHERE id = %s;
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
                    "user_id": row[6],
                    "origin": row[7],
                    "definition": row[8],
                    "status": row[9],
                    "confirmed_at": row[10],
                    "claim_kind": row[11],
                    "span_is_undated": row[12],
                    "undated_occurrence_count": row[13],
                }
            return None

    @staticmethod
    def _queue(cur, user_id: int, source_type: str, source_id: int) -> None:
        """Queue a source for processing inside the caller's transaction.

        The row that says "turn this into evidence" used to be written on a
        second connection after the entry had committed, with its failure
        logged and swallowed — so a crash or a dropped connection between the
        two left an entry the journal showed and every engine was blind to, and
        nothing in the queue to say so. Written in the same commit, the entry
        and its job exist together or not at all (ADR-0011).

        Queueing a source that is already queued bumps its generation: a run in
        flight for the old version must not retire the row (migration 0013).
        """
        cur.execute(
            """INSERT INTO processing_queue (user_id, source_type, source_id)
               VALUES (%s, %s, %s)
               ON CONFLICT (source_type, source_id) DO UPDATE
                  SET generation = processing_queue.generation + 1,
                      attempts = 0, last_error = NULL;""",
            (user_id, source_type, source_id))

    @staticmethod
    def _recompute_theme_stats(cur, theme_id: int) -> None:
        """A theme's counts and span, derived from the occurrences it has.

        The dated count, the undated count beside it, and a span taken from
        dated occurrences only; when none are dated the stored span keeps its
        value and `span_is_undated` says that value means nothing. A theme with
        no occurrences left counts zero — a deletion is reflected, not
        remembered — and keeps whatever span flag it had, so an unconfirmed
        construct's review span is not rewritten by an empty recount.
        """
        cur.execute(
            """UPDATE themes t
                  SET occurrence_count = agg.dated,
                      undated_occurrence_count = agg.undated,
                      first_seen_at = COALESCE(agg.min_at, t.first_seen_at),
                      last_seen_at = COALESCE(agg.max_at, t.last_seen_at),
                      span_is_undated = CASE WHEN agg.n = 0 THEN t.span_is_undated
                                             ELSE agg.min_at IS NULL END
                 FROM (SELECT COUNT(*) n,
                              COUNT(*) FILTER (WHERE occurred_at IS NOT NULL) dated,
                              COUNT(*) FILTER (WHERE occurred_at IS NULL) undated,
                              MIN(occurred_at) min_at, MAX(occurred_at) max_at
                         FROM theme_occurrences WHERE theme_id = %s) agg
                WHERE t.id = %s;""",
            (theme_id, theme_id))

    def update_theme_stats(self, theme_id: int, last_seen_at: str = None):
        """Recompute a theme's aggregates from the occurrences it actually has.

        This used to increment the stored counter unconditionally and overwrite
        last_seen_at with whatever timestamp the caller passed. Neither is
        safe, because add_theme_occurrence is an upsert:

        - A source delivered twice — a queue retry, a replay — wrote one
          occurrence and incremented the count twice, so a theme's count drifted
          above the number of occurrences supporting it, and every confidence
          and rate derived from that count inherited the drift.
        - The overwrite moved last_seen_at *backwards* whenever a historical
          entry was backfilled, because the newest occurrence and the most
          recently written one are not the same thing.

        Deriving both from theme_occurrences makes redelivery a no-op and lets a
        correction or deletion be reflected instead of accumulated. The
        `last_seen_at` argument is retained for callers but no longer trusted
        over the stored evidence.

        The two counts stay apart. `occurrence_count` is the dated occurrences,
        because every engine that gates on it measures something per day;
        `undated_occurrence_count` is the rest. When nothing is dated the span
        columns keep their previous value and `span_is_undated` says that value
        means nothing — the same flag ADR-0013 already uses for constructs
        promoted from undated writing.
        """
        with self.connection() as conn, conn.cursor() as cur:
            try:
                self._recompute_theme_stats(cur, theme_id)
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

    def delete_user_themes(self, user_id: int) -> int:
        """Delete a user's *clustered* themes, and every cached analysis of them.

        Occurrences and tensions cascade. The pattern caches are keyed by theme
        id with no foreign key, so they are cleared here explicitly: ids are not
        reused, and a stale row would otherwise describe a theme that no longer
        exists.

        Constructs are exempt. Clustering output is disposable — it is derived
        from entries that stay where they are, and can be thrown away and found
        again whenever the way it is found changes. A construct is not derived:
        it holds the owner's own sentences as prototypes, a claim they read, and
        a decision they made about it. Rebuilding clusters used to delete all of
        that, including rejections, with no way to recover the decision.
        """
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    "SELECT id FROM themes WHERE user_id = %s AND origin = 'clustered';",
                    (user_id,))
                ids = [row[0] for row in cur.fetchall()]
                if ids:
                    cur.execute("DELETE FROM pattern_evidence WHERE pattern_type = 'theme' AND (pattern_id = ANY(%s) OR related_pattern_id = ANY(%s));", (ids, ids))
                    # Every pattern_type an engine files under, not just
                    # 'theme': resolution writes 'resolution' and trajectory
                    # writes 'trajectory', so deleting one type left rows
                    # describing themes that no longer exist.
                    cur.execute(
                        """DELETE FROM pattern_confidence
                            WHERE pattern_id = ANY(%s)
                              AND pattern_type IN ('theme', 'resolution', 'trajectory',
                                                   'tension', 'leverage', 'decision_impact');""",
                        (ids,))
                    cur.execute("DELETE FROM pattern_resolutions WHERE pattern_type = 'theme' AND pattern_id = ANY(%s);", (ids,))
                    cur.execute("DELETE FROM pattern_leverage WHERE (source_type = 'theme' AND source_id = ANY(%s)) OR (target_type = 'theme' AND target_id = ANY(%s));", (ids, ids))
                    cur.execute("DELETE FROM decision_impacts WHERE (anchor_type = 'theme' AND anchor_id = ANY(%s)) OR (target_type = 'theme' AND target_id = ANY(%s));", (ids, ids))
                    cur.execute("DELETE FROM themes WHERE id = ANY(%s);", (ids,))
                conn.commit()
                return len(ids)
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to delete themes for user {user_id}: {e}")
                raise

    def create_theme_with_occurrences(self, user_id: int, centroid_embedding: list, summary: str,
                                      occurrences: list[dict], span_is_undated: bool = False) -> int:
        """A new cluster and the evidence it was made of, in one transaction.

        Discovery used to write the theme, then add each occurrence in its own
        transaction. A failure partway left a theme carrying some of its
        members and the caller returning None, so the worker retired the job
        and the half-built cluster stayed — counted by every reader, and with
        no record that anything had gone wrong.

        Each occurrence is {source_type, source_id, snippet, similarity_score,
        occurred_at}. The counts and span are derived from what was actually
        written, not from the caller's expectation of it.
        """
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO themes (user_id, centroid_embedding, summary, first_seen_at,
                                        last_seen_at, occurrence_count, span_is_undated)
                    VALUES (%s, %s, %s, NOW(), NOW(), 0, %s) RETURNING id;
                    """,
                    (user_id, centroid_embedding, summary, span_is_undated),
                )
                theme_id = cur.fetchone()[0]
                for occ in occurrences:
                    cur.execute(
                        """
                        INSERT INTO theme_occurrences
                        (theme_id, source_type, source_id, snippet, similarity_score,
                         occurred_at, admission_basis)
                        VALUES (%s, %s, %s, %s, %s, %s, 'similarity')
                        ON CONFLICT (theme_id, source_type, source_id) DO UPDATE
                        SET snippet = EXCLUDED.snippet,
                            similarity_score = EXCLUDED.similarity_score;
                        """,
                        (theme_id, occ["source_type"], occ["source_id"], occ.get("snippet"),
                         occ.get("similarity_score"), occ.get("occurred_at")),
                    )
                self._recompute_theme_stats(cur, theme_id)
                conn.commit()
                return theme_id
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to create theme with its occurrences: {e}")
                raise

    def add_theme_occurrence(self, theme_id: int, source_type: str, source_id: int,
                            snippet: str, similarity_score: float, occurred_at: str | None,
                            admission_basis: str = "similarity"):
        """Records that a theme occurred at a specific entry.

        `admission_basis` says why: 'citation' for a sentence the owner read
        while reviewing, 'similarity' for a match a detector proposed and they
        never saw. Clustering only ever produces the latter, which is why that
        is the default.

        `occurred_at` may be None, for an occurrence in writing that carries no
        date. Such a row is real evidence and is counted, but no reader that
        measures in days will see it: get_theme_occurrences excludes it unless
        asked for it.
        """
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO theme_occurrences
                    (theme_id, source_type, source_id, snippet, similarity_score, occurred_at,
                     admission_basis)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (theme_id, source_type, source_id) DO UPDATE
                    SET snippet = EXCLUDED.snippet,
                        similarity_score = EXCLUDED.similarity_score,
                        admission_basis = EXCLUDED.admission_basis;
                    """,
                    (theme_id, source_type, source_id, snippet, similarity_score, occurred_at,
                     admission_basis)
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

    def remove_theme_occurrences_except(self, theme_id: int, keep: set) -> int:
        """Remove a theme's occurrences other than `keep`, a set of
        (source_type, source_id). Returns how many went."""
        keys = [f"{t}:{i}" for t, i in keep]
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """DELETE FROM theme_occurrences
                        WHERE theme_id = %s
                          AND NOT (source_type || ':' || source_id = ANY(%s));""",
                    (theme_id, keys))
                removed = cur.rowcount
                conn.commit()
                return removed
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to prune occurrences of theme {theme_id}: {e}")
                raise

    def set_theme_status(self, theme_id: int, status: str) -> None:
        """Confirm or reject a construct.

        Confirming stamps the moment, because when the owner vouched for a
        pattern is part of its provenance: the occurrences written afterwards
        rest on that decision.
        """
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE themes SET status = %s,
                       confirmed_at = CASE WHEN %s = 'active' THEN NOW() ELSE confirmed_at END
                 WHERE id = %s;
                """,
                (status, status, theme_id)
            )
            conn.commit()

    def retract_construct(self, theme_id: int) -> None:
        """Mark a construct rejected and remove the evidence it produced.

        Status alone was not a retraction. Occurrences survived, and the leverage
        and decision-impact caches join themes without filtering on status, so a
        withdrawn construct could still reach chat through a cached reader.
        Prototypes are kept: they are the owner's own sentences and the record of
        what was proposed.
        """
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute("DELETE FROM theme_occurrences WHERE theme_id = %s;", (theme_id,))
                cur.execute(
                    """DELETE FROM pattern_confidence WHERE pattern_id = %s
                        AND pattern_type IN ('theme', 'resolution', 'trajectory',
                                             'tension', 'leverage', 'decision_impact');""",
                    (theme_id,))
                cur.execute(
                    "DELETE FROM pattern_resolutions WHERE pattern_type = 'theme' AND pattern_id = %s;",
                    (theme_id,))
                cur.execute(
                    """DELETE FROM pattern_leverage
                        WHERE (source_type = 'theme' AND source_id = %s)
                           OR (target_type = 'theme' AND target_id = %s);""",
                    (theme_id, theme_id))
                cur.execute(
                    """DELETE FROM decision_impacts
                        WHERE (anchor_type = 'theme' AND anchor_id = %s)
                           OR (target_type = 'theme' AND target_id = %s);""",
                    (theme_id, theme_id))
                cur.execute(
                    """UPDATE themes SET status = 'rejected', occurrence_count = 0
                        WHERE id = %s;""",
                    (theme_id,))
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to retract construct {theme_id}: {e}")
                raise

    def publish_construct(self, theme_id: int, occurrences: list) -> int:
        """Make a construct active and record its evidence, together or not at all.

        Confirmation used to commit `active` first and then write occurrences
        through a second connection. A failure in between left an active
        construct with no evidence — and because the review surface only lists
        candidates, it had also vanished from the one screen that could show the
        owner what happened.

        The transition is guarded here rather than trusted from the caller: only
        a candidate may become active, and only one the reader proposed, so a
        stale request cannot revive something already rejected.

        Returns the number of occurrences written, or -1 if the row was not in a
        state that may be confirmed.
        """
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """SELECT status FROM themes
                        WHERE id = %s AND origin = 'observed' FOR UPDATE;""",
                    (theme_id,))
                row = cur.fetchone()
                if row is None or row[0] != 'candidate':
                    conn.rollback()
                    logger.info(f"Construct {theme_id} is not a candidate; nothing published")
                    return -1

                for occ in occurrences:
                    cur.execute(
                        """
                        INSERT INTO theme_occurrences
                            (theme_id, source_type, source_id, snippet, similarity_score,
                             occurred_at, admission_basis)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (theme_id, source_type, source_id) DO UPDATE
                            SET similarity_score = EXCLUDED.similarity_score,
                                snippet = EXCLUDED.snippet,
                                admission_basis = EXCLUDED.admission_basis;
                        """,
                        (theme_id, occ["source_type"], occ["source_id"], occ["snippet"],
                         occ["similarity_score"], occ["occurred_at"],
                         occ.get("admission_basis", "similarity")))

                cur.execute(
                    """UPDATE themes SET status = 'active', confirmed_at = NOW()
                        WHERE id = %s;""",
                    (theme_id,))
                self._recompute_theme_stats(cur, theme_id)
                conn.commit()
                return len(occurrences)
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to publish construct {theme_id}: {e}")
                raise

    def add_theme_prototype(self, theme_id: int, source_type: str, source_id,
                            quote: str, vector: list) -> int:
        """Store one of the owner's own sentences as an anchor for a construct.

        A prototype is a quote already verified verbatim against a stored entry,
        so a construct cannot drift away from text that exists.
        """
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO theme_prototypes (theme_id, source_type, source_id, quote, vector)
                VALUES (%s, %s, %s, %s, %s) RETURNING id;
                """,
                (theme_id, source_type, source_id, quote, vector)
            )
            prototype_id = cur.fetchone()[0]
            conn.commit()
            return prototype_id

    def create_candidate_construct(self, user_id: int, centroid_embedding: list, summary: str,
                                   definition: str, first_seen_at: str, last_seen_at: str,
                                   span_is_undated: bool, claim_kind: str,
                                   prototypes: list[dict], proposal_key: str,
                                   run_id: int = None) -> int:
        """A proposal, its quotes and its identity, written together.

        These were three transactions. A failure between them left a candidate
        on the review screen with some of the sentences it rests on, or with no
        proposal key — so a decision the owner made about it could not be
        matched on the next run, and the promise that a rejection sticks was
        quietly void. Nothing here is measured until the owner confirms.
        """
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO themes (user_id, centroid_embedding, summary, first_seen_at,
                                        last_seen_at, occurrence_count, origin, definition,
                                        status, claim_kind, span_is_undated, proposal_key,
                                        observation_run_id)
                    VALUES (%s, %s, %s, %s, %s, 0, 'observed', %s, 'candidate', %s, %s, %s, %s)
                    RETURNING id;
                    """,
                    (user_id, centroid_embedding, summary, first_seen_at, last_seen_at,
                     definition, claim_kind, span_is_undated, proposal_key, run_id),
                )
                theme_id = cur.fetchone()[0]
                for proto in prototypes:
                    cur.execute(
                        """
                        INSERT INTO theme_prototypes (theme_id, source_type, source_id, quote, vector)
                        VALUES (%s, %s, %s, %s, %s);
                        """,
                        (theme_id, proto["source_type"], proto["source_id"], proto["quote"],
                         proto["vector"]),
                    )
                conn.commit()
                return theme_id
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to store a candidate construct: {e}")
                raise

    def get_theme_prototypes(self, theme_id: int) -> list:
        """The sentences a construct is anchored in, oldest first."""
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, source_type, source_id, quote, vector
                  FROM theme_prototypes WHERE theme_id = %s ORDER BY id;
                """,
                (theme_id,)
            )
            return [
                {"id": r[0], "source_type": r[1], "source_id": r[2],
                 "quote": r[3], "vector": r[4]}
                for r in cur.fetchall()
            ]

    def get_theme_occurrences(self, theme_id: int, include_undated: bool = False) -> list:
        """The occurrences of a theme; by default only those with a date.

        Every window engine measures rates, gaps, trends and co-occurrence in
        days, so an occurrence with no date has no place in any of their
        arithmetic. Defaulting to dated-only makes that the property of one
        query rather than a null check repeated in six engines, any one of
        which could be missed.

        `include_undated` is for the reader that genuinely counts over the
        whole record without placing anything in time — currently the lifelong
        scale, which reports the two counts separately.
        """
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_type, source_id, snippet, similarity_score, occurred_at
                FROM theme_occurrences
                WHERE theme_id = %s AND (%s OR occurred_at IS NOT NULL)
                ORDER BY occurred_at DESC NULLS LAST;
                """,
                (theme_id, include_undated)
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

    def last_observed_day(self, user_id: int):
        """The most recent day the user deliberately logged anything, or None.

        Same definition of evidence as count_observed_days (ADR-0003), so the
        two agree about what counts as being observed.
        """
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT MAX(d) FROM (
                    SELECT MAX(reflection_date) AS d FROM reflections
                     WHERE user_id = %s AND evidence_eligible
                    UNION ALL
                    SELECT MAX(hc.completion_date) FROM habit_completions hc
                      JOIN habits h ON hc.habit_id = h.id
                     WHERE h.user_id = %s AND hc.is_skipped IS NOT TRUE
                ) days;
                """,
                (user_id, user_id),
            )
            return cur.fetchone()[0]

    def count_observed_days(self, user_id: int, start, end) -> int:
        """Distinct days in [start, end) on which the user deliberately logged.

        "Deliberately logged" is ADR-0003's definition of evidence: a journal
        entry, a reflection, or a completed habit. Chat is excluded here for the
        same reason it is excluded from occurrences — it is not a record the user
        chose to keep.

        This exists to tell an *observed* silence from an unobserved one. A theme
        going quiet while someone keeps writing every day is evidence that it
        stopped; the same silence while they stop opening the app at all is
        evidence of nothing, and the two must not be scored alike.

        Deliberately reads only the source tables. Unioning theme_occurrences in
        as well looks equivalent — every occurrence derives from one of these
        rows — but it joins two tables that add_theme_occurrence writes inside a
        transaction while opening further pooled connections to invalidate
        caches. Adding this read to that pattern produced deadlocks and a test
        suite that hung instead of finishing in half a minute.
        """
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(DISTINCT d) FROM (
                    -- Exclusive start, inclusive end, on every source: two
                    -- touching windows share their boundary day, and it must
                    -- count in one of them, not both. With the start inclusive,
                    -- the day of a theme's last occurrence counted as observed
                    -- *before* the silence and again *during* it, which is how
                    -- an unobserved gap earned continuity credit. The end stays
                    -- inclusive so what was written earlier today still counts.
                    SELECT reflection_date AS d FROM reflections
                     WHERE user_id = %s AND evidence_eligible
                       AND reflection_date > %s::date
                       AND reflection_date <= %s::date
                    UNION
                    SELECT hc.completion_date AS d
                      FROM habit_completions hc JOIN habits h ON hc.habit_id = h.id
                     WHERE h.user_id = %s AND hc.is_skipped IS NOT TRUE
                       AND hc.completion_date > %s::date
                       AND hc.completion_date <= %s::date
                ) days;
                """,
                (user_id, start, end, user_id, start, end),
            )
            return int(cur.fetchone()[0])

    def get_unassigned_embeddings(self, user_id: int) -> list:
        """
        Retrieves embeddings that haven't been assigned to any theme.
        An embedding is assigned if it appears in theme_occurrences.
        """
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.id, e.source_type, e.source_id, e.vector, e.created_at,
                       -- When the thing happened, not when we got round to
                       -- embedding it. Discovery used e.created_at for a theme's
                       -- first_seen/last_seen *and* for every occurrence it
                       -- wrote, so an entry backdated to March, or one embedded
                       -- late after a provider outage, was recorded as having
                       -- happened at embedding time. The matching path already
                       -- uses the source's own date, so the same entry landed on
                       -- a different date depending on whether it joined an
                       -- existing theme or founded one.
                       CASE e.source_type
                           WHEN 'reflection' THEN
                               (SELECT r.reflection_date::timestamp AT TIME ZONE 'UTC'
                                  FROM reflections r WHERE r.id = e.source_id)
                           WHEN 'habit_completion' THEN
                               (SELECT hc.completion_date::timestamp AT TIME ZONE 'UTC'
                                  FROM habit_completions hc WHERE hc.id = e.source_id)
                       END AS occurred_at
                FROM embeddings e
                WHERE NOT EXISTS (
                    SELECT 1 FROM theme_occurrences occ
                    WHERE occ.source_type = e.source_type AND occ.source_id = e.source_id
                )
                -- Eligibility here must match the online path in pipeline.py
                -- and ADR-0003: evidence is what the user deliberately logged.
                -- 'habit' is the habit *definition* -- an intention, not
                -- behaviour -- and admitting it here let a habit someone created
                -- and never did found a theme and count as an occurrence of it.
                -- Completions still qualify; skipped ones already do not.
                AND (
                    -- evidence_eligible is false for copied setup text and
                    -- placeholders: still searchable, no longer proof that
                    -- anything recurred (ADR-0003).
                    (e.source_type = 'reflection' AND e.source_id IN (
                        SELECT id FROM reflections WHERE user_id = %s AND evidence_eligible)) OR
                    (e.source_type = 'habit_completion' AND e.source_id IN (
                        SELECT hc.id FROM habit_completions hc JOIN habits h ON hc.habit_id = h.id
                        WHERE h.user_id = %s AND hc.is_skipped IS NOT TRUE))
                )
                ORDER BY e.created_at DESC;
                """,
                (user_id, user_id)
            )
            rows = cur.fetchall()
            return [
                {
                    "embedding_id": row[0],
                    "source_type": row[1],
                    "source_id": row[2],
                    "vector": row[3],
                    # Kept distinct on purpose: created_at is when this row was
                    # embedded, occurred_at is when the user's entry happened.
                    #
                    # No fallback between them. This used to read `row[5] or
                    # row[4]`, which was harmless only while every entry had a
                    # date: the moment an undated one exists, that `or` dates it
                    # to the minute it was embedded and nothing downstream can
                    # tell the difference — the precise substitution ADR-0013
                    # forbids, arriving as a default rather than a guess. None
                    # stays None, and the readers decide what they can measure.
                    "created_at": row[4],
                    "occurred_at": row[5],
                }
                for row in rows
            ]

    def get_evidence_style(self, user_id: int) -> tuple:
        """How many evidence embeddings a user has, and their average.

        The average is the voice every entry shares. Themes are compared with it
        removed once there is enough evidence for it to mean that (ADR-0014).
        Eligibility is the same as get_unassigned_embeddings: evidence only.

        That last sentence was a claim the SQL did not honour. Copied setup text
        and placeholders — excluded from matching, excluded from occurrences —
        were still shaping the space everything is matched *in*. Worse, they
        counted toward PERSISTENCE_STYLE_MIN_ENTRIES, so a user could be moved
        into style space by rows that are not evidence.
        """
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*), AVG(e.vector) FROM embeddings e
                WHERE (e.source_type = 'reflection' AND e.source_id IN (
                        SELECT id FROM reflections WHERE user_id = %s AND evidence_eligible))
                   OR (e.source_type = 'habit_completion' AND e.source_id IN (
                        SELECT hc.id FROM habit_completions hc JOIN habits h ON hc.habit_id = h.id
                        WHERE h.user_id = %s AND hc.is_skipped IS NOT TRUE));
                """,
                (user_id, user_id)
            )
            count, mean = cur.fetchone()
            return int(count), mean

    def get_latest_reflections(self, user_id: int, limit: int = 5) -> list:
        """The most recently *written* reflections, newest first.

        get_reflections pages by id, which is insertion order. Since importing
        that is not writing order: a batch of 2024 entries committed today has
        the newest ids, so the chat's "recent entries" meant "last imported".
        """
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT id, reflection_date, content, mood, energy_level, clarity_level
                   FROM reflections WHERE user_id = %s
                   -- NULLS LAST, explicitly: DESC puts them first in Postgres,
                   -- so "the most recent entries" began with the writing whose
                   -- day is unknown and the dated ones fell off the end.
                   ORDER BY reflection_date DESC NULLS LAST, id DESC LIMIT %s;""",
                (user_id, limit),
            )
            keys = ("id", "reflection_date", "content", "mood", "energy_level", "clarity_level")
            return [dict(zip(keys, row)) for row in cur.fetchall()]

    def get_memory_item(self, source_type: str, source_id: int) -> dict | None:
        """What a retrieved memory is, when it happened, and its own words.

        get_content_for_source returns the text that was embedded, which wraps a
        reflection in a header ("Anchor: Self-Reflection | ... | Content: ...")
        with placeholder scores and no date: right for the embedding, wrong for
        the model reading the chat context.
        """
        queries = {
            "reflection": ("journal", "SELECT content, reflection_date FROM reflections WHERE id = %s;"),
            "message": ("said in chat", "SELECT content, created_at::date FROM conversation_messages WHERE id = %s;"),
            "habit_completion": ("habit", """SELECT CASE WHEN hc.is_skipped
                                                     THEN 'Skipped ' || h.name || COALESCE(': ' || hc.skip_reason, '')
                                                     ELSE 'Did ' || h.name || COALESCE(': ' || hc.notes, '') END,
                                                hc.completion_date
                                         FROM habit_completions hc JOIN habits h ON h.id = hc.habit_id
                                         WHERE hc.id = %s;"""),
        }
        if source_type not in queries:
            return None
        kind, sql = queries[source_type]
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (source_id,))
            row = cur.fetchone()
        if not row or not (row[0] or "").strip():
            return None
        return {"kind": kind, "date": row[1], "text": row[0]}

    def is_evidence_eligible(self, source_type: str, source_id: int) -> bool:
        """Whether this source may form or reinforce a theme.

        False for copied setup text and placeholders: they stay stored,
        embedded and searchable, and stop counting as proof that something
        recurred (ADR-0003). Only reflections carry the flag; anything else is
        eligible by definition of its own table.
        """
        if source_type != 'reflection':
            return True
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT evidence_eligible FROM reflections WHERE id = %s;", (source_id,))
            row = cur.fetchone()
        return bool(row[0]) if row else True

    def get_journal_page(self, user_id: int, limit: int = 50, before=None) -> list:
        """A page of reflections ordered by when they were *written*.

        get_reflections pages by id, which is insertion order: after an import
        that is the order files were committed, so a 2024 entry can sit at the
        top of "newest first". The cursor is (date, id) because dates repeat.

        Undated entries sort after every dated one and are ordered among
        themselves by the sequence their source recorded. They need their own
        cursor arm: a NULL date makes `(reflection_date, id) < (...)` evaluate
        to NULL, so under the previous single condition they dropped out of
        every page after the first — and a page that ended inside them handed
        back a NULL cursor, which the first arm reads as "no cursor" and serves
        page one again, forever. `before_id` is what distinguishes the two,
        since it is set for any real cursor and never for the first page.
        """
        before_date, before_id = (before or (None, None))
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, reflection_date, content, mood, energy_level, clarity_level,
                       tags, created_at, updated_at, audio_path, entry_sequence
                  FROM reflections
                 WHERE user_id = %s
                   AND (%s::int IS NULL
                        OR (%s::date IS NOT NULL
                            AND (reflection_date IS NULL
                                 OR (reflection_date, id) < (%s::date, %s::int)))
                        OR (%s::date IS NULL
                            AND reflection_date IS NULL
                            AND (COALESCE(entry_sequence, -1), id)
                                < (COALESCE((SELECT entry_sequence FROM reflections
                                              WHERE id = %s), -1), %s::int)))
                 ORDER BY (reflection_date IS NULL),
                          reflection_date DESC,
                          entry_sequence DESC NULLS LAST,
                          id DESC
                 LIMIT %s;
                """,
                (user_id, before_id, before_date, before_date, before_id,
                 before_date, before_id, before_id, limit),
            )
            keys = ("id", "reflection_date", "content", "mood", "energy_level",
                    "clarity_level", "tags", "created_at", "updated_at", "audio_path",
                    "entry_sequence")
            return [dict(zip(keys, row)) for row in cur.fetchall()]

    def get_staged_for_reading(self, user_id: int, min_chars: int, batch_id: int = None) -> list:
        """Staged import items long enough to be worth reading.

        The voice transcripts sit here rather than in reflections because they
        carry no date, and ImportService.commit refuses a batch with undated
        entries (ADR-0013): a date is read or it is absent, never invented. They
        can still be *read* — a quote from one is as real as any other — so they
        supply citations for discovery while never becoming an occurrence, which
        would need a day they happened on.

        `min_chars` drops the near-empty clips: the real batch has six between
        22 and 165 characters and the next one up is 1,108.
        """
        clause = "AND batch_id = %s" if batch_id else ""
        params = [user_id, min_chars] + ([batch_id] if batch_id else [])
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, entry_date, content, source_name
                  FROM import_items
                 WHERE user_id = %s AND status = 'staged'
                   AND content IS NOT NULL AND length(trim(content)) >= %s
                   {clause}
                 ORDER BY id;
                """,
                params,
            )
            return [
                {"id": r[0], "date": r[1], "content": r[2],
                 "source_name": r[3], "source_type": "import_item"}
                for r in cur.fetchall()
            ]

    def get_entries_with_vectors(self, user_id: int) -> list:
        """Every evidence-eligible entry with its embedding, for matching.

        Same definition of evidence as get_unassigned_embeddings (ADR-0003):
        what the owner deliberately logged, minus anything marked memory-only.
        A construct is a statement about the person, so a placeholder or a
        duplicated paragraph must not be able to become one of its occurrences.

        All three source types ingestion admits, so replaying the archive and
        classifying a new entry read the same population. This read reflections
        alone while ingestion also admitted journal entries and completed habits,
        which would have made a construct's history disagree with its future.
        The owner's archive is currently all reflections, so the gap had no
        present effect — it was waiting for the first habit tick.

        Undated entries are included, and come back with a null date. Excluding
        them was right while a reflection could not be undated; once it can,
        excluding them here would mean replay saw a smaller archive than
        ingestion, and confirming a construct would move its measured frequency
        for reasons that are routing rather than writing — the one divergence
        this query was rewritten to close.
        """
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT e.source_type, e.source_id, e.vector, r.content, r.reflection_date
                  FROM embeddings e
                  JOIN reflections r ON r.id = e.source_id
                 WHERE e.source_type = 'reflection'
                   AND r.user_id = %s AND r.evidence_eligible


                UNION ALL

                SELECT e.source_type, e.source_id, e.vector,
                       CASE WHEN hc.is_skipped THEN 'Skipped ' || h.name
                            ELSE 'Did ' || h.name END,
                       hc.completion_date
                  FROM embeddings e
                  JOIN habit_completions hc ON hc.id = e.source_id
                  JOIN habits h ON h.id = hc.habit_id
                 WHERE e.source_type = 'habit_completion'
                   AND h.user_id = %s AND hc.is_skipped IS NOT TRUE

                 ORDER BY 5;
                """,
                (user_id, user_id)
            )
            return [
                {"source_type": r[0], "source_id": r[1], "vector": r[2],
                 "content": r[3], "occurred_at": r[4]}
                for r in cur.fetchall()
            ]

    def get_entries_for_reading(self, user_id: int, limit: int = 60, since=None) -> list:
        """Entries an engine may read and quote from, newest first.

        Only what the owner deliberately logged, and only what still counts as
        evidence (ADR-0003). Copied setup text and placeholders marked
        memory-only stay searchable and stay visible in the journal, but must
        never become the citation under an observation about the person — a
        quote is meant to be the thing that convinces them, so it has to come
        from something they actually sat down and wrote.
        """
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, reflection_date, content
                  FROM reflections
                 WHERE user_id = %s AND evidence_eligible
                   AND (%s::date IS NULL OR reflection_date >= %s::date)
                   AND content IS NOT NULL AND length(trim(content)) > 0
                 ORDER BY reflection_date DESC, id DESC
                 LIMIT %s;
                """,
                (user_id, since, since, limit),
            )
            return [{"id": r[0], "date": r[1], "content": r[2],
                     "source_type": "reflection"} for r in cur.fetchall()]

    def get_content_for_source(self, source_type: str, source_id: int) -> str:
        """Retrieves text content for any source type."""
        with self.connection() as conn, conn.cursor() as cur:
            if source_type == 'reflection':
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
        (computation_id, pattern_type, pattern_id, related_pattern_id,
         engine_name, evidence_type, evidence_key, evidence_value)
        """
        if not records:
            return

        with self.connection() as conn, conn.cursor() as cur:
            try:
                # evidence_value is stored as JSONB
                from psycopg2.extras import execute_values
                execute_values(cur, """
                    INSERT INTO pattern_evidence
                    (computation_id, pattern_type, pattern_id, related_pattern_id,
                     engine_name, evidence_type, evidence_key, evidence_value)
                    VALUES %s
                """, records)
                conn.commit()
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to batch insert evidence: {e}")
                raise

    def get_latest_evidence_bundle(self, pattern_type: str, pattern_id: int,
                                   engine_name: str = None,
                                   related_pattern_id: int = None) -> list:
        """
        Retrieves evidence records for a pattern.
        If engine_name is provided, gets the latest snapshot for THAT engine.
        If NO engine_name provided, gets the latest snapshots for ALL engines
        associated with this pattern.

        `related_pattern_id` addresses one side of a pairwise relation. It is
        matched with IS NOT DISTINCT FROM so that passing None selects the
        single-pattern engines' bundles (where the column is NULL) rather than
        matching nothing, which is what `= NULL` would have done.
        """
        with self.connection() as conn, conn.cursor() as cur:
            if engine_name:
                # 1. Find latest computation for specific engine
                cur.execute("""
                    SELECT computation_id FROM pattern_evidence
                    WHERE pattern_type = %s AND pattern_id = %s AND engine_name = %s
                      AND related_pattern_id IS NOT DISTINCT FROM %s
                    ORDER BY created_at DESC LIMIT 1
                """, (pattern_type, pattern_id, engine_name, related_pattern_id))
                row = cur.fetchone()
                if not row: return []
                comp_ids = [row[0]]
            else:
                # 2. Find the latest computation_id for EACH engine associated with this pattern
                # DISTINCT ON includes related_pattern_id, so a source theme
                # with several targets contributes each relation's latest bundle
                # instead of one of them standing in for all.
                cur.execute("""
                    SELECT DISTINCT ON (engine_name, related_pattern_id) computation_id
                    FROM pattern_evidence
                    WHERE pattern_type = %s AND pattern_id = %s
                    ORDER BY engine_name, related_pattern_id, created_at DESC
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

    def retire_insight_priorities(self, keep_insight_ids: list) -> int:
        """Drop priority rows outside the current selection.

        The writer upserts by insight_id, so a shorter selection left the
        previous, longer one in place: five rows described a ranking that no
        longer existed and read as current. A selection is a snapshot — what is
        not in it is not ranked.
        """
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    "DELETE FROM insight_priorities WHERE NOT (insight_id = ANY(%s));",
                    (list(keep_insight_ids),),
                )
                retired = cur.rowcount
                conn.commit()
                return retired
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to retire insight priorities: {e}")
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
                    SELECT min_confidence, max_items, enabled_engines
                    FROM user_preferences WHERE user_id = %s;
                """, (user_id,))
                row = cur.fetchone()
                if row:
                    return {
                        "min_confidence": row[0],
                        "max_items": row[1],
                        "enabled_engines": row[2], # list or None
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
        "min_confidence", "max_items", "enabled_engines",
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
                self._queue(cur, user_id, 'habit', habit_id)
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
                cur.execute("SELECT user_id FROM habits WHERE id = %s;", (habit_id,))
                self._queue(cur, cur.fetchone()[0], 'habit_completion', completion_id)
                conn.commit()
                return completion_id
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to log habit completion: {e}")
                raise

    @staticmethod
    def _retract_source(cur, source_type: str, source_id: int) -> None:
        """Take back everything derived from one source, in the caller's
        transaction: its evidence, its embedding and any queued work for it.

        A correction that reaches only the row the owner edited leaves the
        thing they took back still being counted — and a queued job pointing at
        a source that no longer exists, which the worker then retries until it
        parks.
        """
        cur.execute("""SELECT DISTINCT theme_id FROM theme_occurrences
                        WHERE source_type = %s AND source_id = %s;""",
                    (source_type, source_id))
        theme_ids = [r[0] for r in cur.fetchall()]
        cur.execute("DELETE FROM theme_occurrences WHERE source_type = %s AND source_id = %s;",
                    (source_type, source_id))
        cur.execute("DELETE FROM embeddings WHERE source_type = %s AND source_id = %s;",
                    (source_type, source_id))
        cur.execute("DELETE FROM processing_queue WHERE source_type = %s AND source_id = %s;",
                    (source_type, source_id))
        for theme_id in theme_ids:
            # The stored counts and span are what the readers use; leaving them
            # is how two surfaces come to disagree about the same theme.
            Database._recompute_theme_stats(cur, theme_id)
            cur.execute("UPDATE pattern_resolutions SET last_computed_at = NULL "
                        "WHERE pattern_type = 'theme' AND pattern_id = %s;", (theme_id,))
            cur.execute("UPDATE theme_tensions SET last_computed_at = NULL "
                        "WHERE theme_a_id = %s OR theme_b_id = %s;", (theme_id, theme_id))
            cur.execute("UPDATE pattern_confidence SET last_computed_at = NULL "
                        "WHERE pattern_type = 'theme' AND pattern_id = %s;", (theme_id,))

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
                    self._retract_source(cur, 'habit_completion', row[0])
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
                # A day the owner says did not happen stops being evidence that
                # it did. Turning a completion into a skip used to update this
                # row alone, leaving the embedding, the theme occurrences and
                # the queued job it had already produced.
                self._retract_source(cur, 'habit_completion', skip_id)
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
                         mood: str = None, energy_level: int = None, clarity_level: int = None,
                         tags: list = None, source: str = 'app',
                         content_hash: str = None, audio_path: str = None,
                         metrics: dict = None, date_source: str = None,
                         date_confidence: str = None, evidence_eligible: bool = True,
                         undated: bool = False, entry_sequence: int = None,
                         import_item_id: int = None) -> int:
        """Creates a new reflection and returns its ID.

        `source`, `content_hash` and `audio_path` carry provenance for entries
        that did not originate in the app. They default so the existing callers
        are unaffected — in particular content_hash stays NULL for anything
        typed here, which keeps those rows outside the de-duplication index.
        """
        with self.connection() as conn, conn.cursor() as cur:
            try:
                from datetime import date
                # No date supplied means "written now", which is true for an
                # entry typed in the app. `undated=True` is the different
                # statement that the day is not known, and it is the only way
                # to store an absence — so a caller can never arrive at NULL by
                # forgetting an argument.
                if undated:
                    reflection_date = None
                elif reflection_date is None:
                    reflection_date = date.today()

                cur.execute(
                    """
                    INSERT INTO reflections (user_id, reflection_date, content, mood,
                                             energy_level, clarity_level, tags,
                                             source, content_hash, audio_path,
                                             metrics, date_source, date_confidence,
                                             evidence_eligible, entry_sequence)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
                    """,
                    (user_id, reflection_date, content, mood, energy_level, clarity_level,
                     Json(tags) if tags else None, source, content_hash, audio_path,
                     Json(metrics) if metrics else None, date_source, date_confidence,
                     evidence_eligible, entry_sequence)
                )
                reflection_id = cur.fetchone()[0]
                self._queue(cur, user_id, 'reflection', reflection_id)
                if import_item_id is not None:
                    # The staging row learns its reflection in the same commit.
                    # It used to be linked afterwards, so a failure in between
                    # left an entry that was safely stored and no longer
                    # attributable to the batch that made it — and the retry
                    # hit the duplicate index and recorded no id at all, which
                    # is how undo came to miss what it had created.
                    cur.execute(
                        """UPDATE import_items
                              SET status = 'imported', reflection_id = %s, error = NULL
                            WHERE id = %s AND user_id = %s;""",
                        (reflection_id, import_item_id, user_id))
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
                    SELECT id, reflection_date, content, mood, energy_level, clarity_level, tags, created_at, updated_at, audio_path
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
                        "updated_at": row[8],
                        "audio_path": row[9],
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
                           processing_status, created_at, updated_at, audio_path, clarity_level
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
                        "updated_at": row[9],
                        "audio_path": row[10],
                        "clarity_level": row[11],
                    }
                return None
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to get reflection {reflection_id}: {e}")
                raise

    def set_reflection_date(self, reflection_id: int, user_id: int, on) -> int:
        """Give an undated entry the day it was written, and carry that through.

        The reason an absence is storable at all is that it can be resolved
        later. Resolving it has to reach further than the one row: the entry's
        occurrences were admitted with no date, so until they are dated too the
        entry stays invisible to every window engine and the owner has supplied
        a date that changed nothing they can see.

        Returns the number of occurrences that became dated. Only fills a date
        that is genuinely absent — this never overwrites a date already read
        from the writing, which would be the invention ADR-0013 forbids, just
        arriving by a different door.
        """
        with self.connection() as conn, conn.cursor() as cur:
            try:
                cur.execute(
                    """UPDATE reflections SET reflection_date = %s,
                              date_source = 'user', date_confidence = 'certain',
                              updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s AND user_id = %s AND reflection_date IS NULL;""",
                    (on, reflection_id, user_id))
                if cur.rowcount == 0:
                    conn.rollback()
                    return 0

                cur.execute(
                    """UPDATE theme_occurrences SET occurred_at = %s
                        WHERE source_type = 'reflection' AND source_id = %s
                          AND occurred_at IS NULL
                     RETURNING theme_id;""",
                    (on, reflection_id))
                touched = {row[0] for row in cur.fetchall()}

                for theme_id in touched:
                    self._recompute_theme_stats(cur, theme_id)
                conn.commit()
                return len(touched)
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to date reflection {reflection_id}: {e}")
                raise

    def update_reflection(self, reflection_id: int, **updates) -> bool:
        """Updates a reflection's fields."""
        with self.connection() as conn, conn.cursor() as cur:
            try:
                # clarity_level was accepted and validated by the API and the
                # service, then dropped here — saved on create, silently lost on
                # edit.
                allowed_fields = {'content', 'mood', 'energy_level', 'clarity_level', 'tags'}
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
                    f"UPDATE reflections SET {set_clause}, updated_at = CURRENT_TIMESTAMP "
                    f"WHERE id = %s RETURNING user_id;",
                    values
                )
                row = cur.fetchone()
                if row and 'content' in updates:
                    # What was derived from the old words goes in the same commit
                    # as the new words, and the entry is queued again. Done as
                    # separate steps after the edit, a crash in between left the
                    # new text beside the old embedding with nothing queued.
                    # Resetting the status is how a run already in flight learns
                    # that the text it read is no longer the text (pipeline.py).
                    cur.execute(
                        """DELETE FROM theme_occurrences
                            WHERE source_type = 'reflection' AND source_id = %s
                        RETURNING theme_id;""", (reflection_id,))
                    touched = {r[0] for r in cur.fetchall()}
                    cur.execute(
                        "DELETE FROM embeddings WHERE source_type = 'reflection' AND source_id = %s;",
                        (reflection_id,))
                    cur.execute(
                        "UPDATE reflections SET processing_status = 'pending' WHERE id = %s;",
                        (reflection_id,))
                    for theme_id in touched:
                        self._recompute_theme_stats(cur, theme_id)
                    self._queue(cur, row[0], 'reflection', reflection_id)
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
                    """DELETE FROM theme_occurrences
                        WHERE source_type = 'reflection' AND source_id = %s
                    RETURNING theme_id;""",
                    (reflection_id,)
                )
                touched = {r[0] for r in cur.fetchall()}
                cur.execute(
                    "DELETE FROM embeddings WHERE source_type = 'reflection' AND source_id = %s;",
                    (reflection_id,)
                )
                # Its job goes too. A queued entry deleted before the worker
                # reached it is not a failure to process, and must not be left
                # to retry and park as one.
                cur.execute(
                    "DELETE FROM processing_queue WHERE source_type = 'reflection' AND source_id = %s;",
                    (reflection_id,)
                )
                cur.execute("DELETE FROM reflections WHERE id = %s;", (reflection_id,))
                # Counts reflect the deletion rather than remembering the entry.
                for theme_id in touched:
                    self._recompute_theme_stats(cur, theme_id)
                conn.commit()
                return True
            except psycopg2.Error as e:
                conn.rollback()
                logger.error(f"Failed to delete reflection {reflection_id}: {e}")
                raise









# Create a global instance for easy access throughout the application
db = Database()
