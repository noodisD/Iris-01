-- 0019_sensor_review.sql
--
-- Store parsed payloads for review, and the theme links the owner confirms.

ALTER TABLE sensor_batches
    ADD COLUMN parsed_payload JSONB,
    ADD COLUMN theme_links JSONB;
