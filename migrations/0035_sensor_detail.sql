-- 0035_sensor_detail.sql
--
-- A location fix can say how accurate it was, and a visit or a sleep interval
-- has an end as well as a start. `detail` holds source-specific fields that
-- are not coordinates: an app category, a trip mode. Coordinates stay in
-- lat/lon, which day features never copy.

ALTER TABLE sensor_observations
    ADD COLUMN accuracy_m DOUBLE PRECISION,
    ADD COLUMN ended_at TIMESTAMPTZ,
    ADD COLUMN detail JSONB;
