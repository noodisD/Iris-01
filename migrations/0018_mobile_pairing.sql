-- 0018_mobile_pairing.sql
--
-- The mobile pairing row: a single record per IRIS installation,
-- storing the SHA-256 hash of the bearer token and the LAN bind
-- enable flag. Default values mean a fresh install is unpaired and
-- the LAN bind is off. The /api/mobile/pair route is the only writer.

CREATE TABLE mobile_pairing (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    bearer_hash     TEXT,
    lan_bind_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    paired_at       TIMESTAMPTZ,
    paired_device   TEXT
);
INSERT INTO mobile_pairing (id) VALUES (1);
