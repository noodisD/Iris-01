-- Phone deliveries merge into one pending batch per source and review day;
-- each delivery's body hash keeps retries idempotent.
CREATE TABLE sensor_deliveries (
    delivery_key TEXT PRIMARY KEY,
    batch_id     BIGINT NOT NULL REFERENCES sensor_batches(id) ON DELETE CASCADE,
    received_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX sensor_deliveries_batch_idx ON sensor_deliveries (batch_id);
INSERT INTO sensor_deliveries (delivery_key, batch_id, received_at)
    SELECT delivery_key, id, received_at FROM sensor_batches WHERE delivery_key IS NOT NULL;
ALTER TABLE sensor_batches DROP COLUMN delivery_key;
ALTER TABLE sensor_batches ADD COLUMN review_day DATE;
CREATE UNIQUE INDEX sensor_batches_open_review_day
    ON sensor_batches (source, review_day)
    WHERE status = 'pending' AND review_day IS NOT NULL;
