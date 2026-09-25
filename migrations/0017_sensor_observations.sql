-- 0017_sensor_observations.sql
--
-- Staged sensor batches and the observations they commit into.
-- Mirrors import_items / reflections in shape (ADR-0017).
--
-- Sensor observations are NEVER written by anything other than
-- SensorService.create_sensor_observation. See tests/test_context_guards.py
-- and the guard test added in Task 8.

CREATE TABLE sensor_batches (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,            -- 'pixel' or 'fitbit'
    payload_path    TEXT NOT NULL,            -- where the bytes came from
    received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at    TIMESTAMPTZ,              -- null until owner confirms
    device_clock    TIMESTAMPTZ,              -- the device's own timestamp
    host_clock      TIMESTAMPTZ,              -- when IRIS first saw the file
    clock_skew_seconds INTEGER,               -- host_clock - device_clock
    observation_count INTEGER NOT NULL DEFAULT 0,
    dropped_count   INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','confirmed','rejected','errored')),
    raw_payload_hash TEXT                     -- sha256 of the source bytes
);

CREATE INDEX sensor_batches_status_idx ON sensor_batches (status, received_at DESC);

CREATE TABLE sensor_observations (
    id              BIGSERIAL PRIMARY KEY,
    batch_id        BIGINT NOT NULL REFERENCES sensor_batches(id) ON DELETE CASCADE,
    source_type     TEXT NOT NULL,            -- pixel_location, fitbit_heart_rate, ...
    occurred_at     TIMESTAMPTZ,              -- nullable per ADR-0013
    occurred_date   DATE,                     -- the local calendar day
    value_num       DOUBLE PRECISION,         -- steps, bpm, seconds, metres, ...
    value_text      TEXT,                     -- app name, location label, sleep stage
    lat             DOUBLE PRECISION,
    lon             DOUBLE PRECISION,
    payload_hash    TEXT NOT NULL,            -- for dedup within a batch
    UNIQUE (batch_id, payload_hash)           -- one row per reading
);

CREATE INDEX sensor_observations_source_occurred_idx
    ON sensor_observations (source_type, occurred_at DESC NULLS LAST);
CREATE INDEX sensor_observations_occurred_date_idx
    ON sensor_observations (occurred_date);
