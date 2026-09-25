-- Retry-identical live deliveries reuse their staged batch; manual uploads remain independent.
ALTER TABLE sensor_batches
    ADD COLUMN delivery_key TEXT UNIQUE;
