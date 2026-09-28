-- 0039_observatory.sql
--
-- Full-content traces, logs and probe samples for the Observatory, plus the
-- trace that enqueued a job so a queue span can link back to its cause.
-- Raw telemetry is deleted by retention (OBS_RETENTION_DAYS).

ALTER TABLE processing_queue ADD COLUMN origin_traceparent TEXT;

CREATE TABLE obs_spans (
    trace_id CHAR(32) NOT NULL, span_id CHAR(16) NOT NULL, parent_span_id CHAR(16),
    name TEXT NOT NULL, component VARCHAR(16) NOT NULL, kind VARCHAR(8) NOT NULL,
    is_entry BOOLEAN NOT NULL, started_at TIMESTAMPTZ NOT NULL,
    duration_ms DOUBLE PRECISION NOT NULL, self_ms DOUBLE PRECISION NOT NULL,
    status VARCHAR(5) NOT NULL CHECK (status IN ('ok', 'error')), status_message TEXT,
    db_fingerprint CHAR(16),
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb, events JSONB NOT NULL DEFAULT '[]'::jsonb,
    links JSONB NOT NULL DEFAULT '[]'::jsonb,
    PRIMARY KEY (trace_id, span_id));
CREATE INDEX idx_obs_spans_started ON obs_spans (started_at);
CREATE INDEX idx_obs_spans_component_started ON obs_spans (component, started_at);
CREATE INDEX idx_obs_spans_entry_started ON obs_spans (started_at) WHERE is_entry;
CREATE INDEX idx_obs_spans_fingerprint ON obs_spans (db_fingerprint, started_at) WHERE db_fingerprint IS NOT NULL;

CREATE TABLE obs_logs (
    id BIGSERIAL PRIMARY KEY, at TIMESTAMPTZ NOT NULL,
    source VARCHAR(8) NOT NULL CHECK (source IN ('server', 'web', 'android')),
    level VARCHAR(8) NOT NULL, logger TEXT NOT NULL, message TEXT NOT NULL, exception TEXT,
    trace_id CHAR(32), span_id CHAR(16), attributes JSONB NOT NULL DEFAULT '{}'::jsonb);
CREATE INDEX idx_obs_logs_at ON obs_logs (at);
CREATE INDEX idx_obs_logs_trace ON obs_logs (trace_id) WHERE trace_id IS NOT NULL;

CREATE TABLE obs_samples (at TIMESTAMPTZ NOT NULL, name TEXT NOT NULL, value DOUBLE PRECISION NOT NULL);
CREATE INDEX idx_obs_samples_name_at ON obs_samples (name, at);

CREATE TABLE obs_client_state (
    source VARCHAR(8) PRIMARY KEY CHECK (source IN ('web', 'android')),
    received_at TIMESTAMPTZ NOT NULL, state JSONB NOT NULL);
