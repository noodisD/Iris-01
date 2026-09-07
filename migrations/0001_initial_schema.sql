-- 0001_initial_schema.sql
--
-- The schema as it stood when migrations were introduced (2026-09-07).
--
-- Generated from Database.create_schema() by extracting every literal passed to
-- cur.execute(), in source order, rather than by re-typing it — so this is the
-- same DDL that built every existing database, not a transcription of it.
-- Verified by applying it to an empty database and diffing the result against
-- tests/schema_snapshot.json.
--
-- Statements keep their IF NOT EXISTS clauses so this migration is safe to
-- apply to a database that create_schema() already built: such a database is
-- stamped at 0001 with no changes made.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(256) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    raw_text TEXT NOT NULL,
    wellbeing_data JSONB,
    processing_status VARCHAR(20) DEFAULT 'pending', -- pending, processing, complete, failed
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    session_id VARCHAR(50) NOT NULL,
    role VARCHAR(20) NOT NULL, -- user, assistant
    content TEXT NOT NULL,
    processing_status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS embeddings (
    id SERIAL PRIMARY KEY,
    source_type VARCHAR(50) NOT NULL, -- e.g., 'journal_entry', 'message'
    source_id INTEGER NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    vector VECTOR(1536) NOT NULL, -- Assuming OpenAI's ada-002 dimension
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_type, source_id, model_name)
);

CREATE INDEX IF NOT EXISTS idx_embeddings_vector_cosine
ON embeddings USING ivfflat (vector vector_cosine_ops)
WITH (lists = 100);

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

CREATE INDEX IF NOT EXISTS idx_themes_user ON themes(user_id);

CREATE INDEX IF NOT EXISTS idx_themes_centroid_cosine
ON themes USING ivfflat (centroid_embedding vector_cosine_ops)
WITH (lists = 50);

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

CREATE INDEX IF NOT EXISTS idx_occurrences_theme ON theme_occurrences(theme_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_occurrences_source ON theme_occurrences(source_type, source_id);

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

CREATE INDEX IF NOT EXISTS idx_evidence_pattern ON pattern_evidence(pattern_type, pattern_id, created_at DESC);

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

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    min_confidence VARCHAR(20) DEFAULT 'medium' 
        CHECK (min_confidence IN ('low', 'medium', 'high')),
    max_items INTEGER DEFAULT 5,
    enabled_engines JSONB, -- NULL means all enabled
    show_suppressed BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS preference_audit (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    setting_key VARCHAR(50) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

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

CREATE TABLE IF NOT EXISTS insight_status (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    insight_id TEXT NOT NULL,
    status TEXT,
    snoozed_until TIMESTAMPTZ,
    seen BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, insight_id)
);

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

ALTER TABLE habits ADD COLUMN IF NOT EXISTS habit_type VARCHAR(20) DEFAULT 'completion';

ALTER TABLE habits ADD COLUMN IF NOT EXISTS weekly_target FLOAT DEFAULT 0;

ALTER TABLE habits ADD COLUMN IF NOT EXISTS tracking_metric VARCHAR(50) DEFAULT 'completion';

ALTER TABLE habits ADD COLUMN IF NOT EXISTS processing_status VARCHAR(20) DEFAULT 'pending';

CREATE INDEX IF NOT EXISTS idx_habits_user_active ON habits(user_id, is_active);

CREATE INDEX IF NOT EXISTS idx_habits_status_date ON habits(processing_status, created_at);

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

ALTER TABLE habit_completions ADD COLUMN IF NOT EXISTS value FLOAT DEFAULT 1.0;

ALTER TABLE habit_completions ADD COLUMN IF NOT EXISTS processing_status VARCHAR(20) DEFAULT 'pending';

CREATE INDEX IF NOT EXISTS idx_completions_habit_date ON habit_completions(habit_id, completion_date DESC);

CREATE INDEX IF NOT EXISTS idx_completions_status_date ON habit_completions(processing_status, completed_at);

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

CREATE TABLE IF NOT EXISTS processing_queue (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_type VARCHAR(50) NOT NULL,
    source_id INTEGER NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_type, source_id)
);

CREATE INDEX IF NOT EXISTS idx_processing_queue_due
ON processing_queue (next_attempt_at);

CREATE INDEX IF NOT EXISTS idx_reflections_user_date ON reflections(user_id, reflection_date DESC);

CREATE INDEX IF NOT EXISTS idx_reflections_status_date ON reflections(processing_status, reflection_date);
