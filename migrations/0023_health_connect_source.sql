-- Rename reviewed Fitbit-labelled Health Connect measurements without losing their
-- observation IDs, theme links, occurrence references, or delivery retry keys.
-- Two pending daily batches can already exist under the old/new source names;
-- consolidate them before changing the indexed source (source, review_day).
WITH collisions AS (
    SELECT old.id AS old_id, current.id AS current_id
    FROM sensor_batches old
    JOIN sensor_batches current
      ON current.source = 'health_connect'
     AND current.status = 'pending'
     AND current.review_day = old.review_day
    WHERE old.source = 'fitbit'
      AND old.status = 'pending'
      AND old.review_day IS NOT NULL
)
UPDATE sensor_batches current
SET parsed_payload = CASE
        WHEN jsonb_typeof(current.parsed_payload -> 'observations') = 'array'
         AND jsonb_typeof(old.parsed_payload -> 'observations') = 'array'
        THEN jsonb_set(current.parsed_payload, '{observations}',
             (old.parsed_payload -> 'observations') ||
             (current.parsed_payload -> 'observations'))
        WHEN jsonb_typeof(current.parsed_payload -> 'observations') = 'array'
        THEN current.parsed_payload
        ELSE COALESCE(old.parsed_payload, current.parsed_payload)
    END,
    observation_count = old.observation_count + current.observation_count,
    dropped_count = old.dropped_count + current.dropped_count
FROM collisions c, sensor_batches old
WHERE current.id = c.current_id AND old.id = c.old_id;

WITH collisions AS (
    SELECT old.id AS old_id, current.id AS current_id
    FROM sensor_batches old
    JOIN sensor_batches current
      ON current.source = 'health_connect'
     AND current.status = 'pending'
     AND current.review_day = old.review_day
    WHERE old.source = 'fitbit'
      AND old.status = 'pending'
      AND old.review_day IS NOT NULL
)
UPDATE sensor_deliveries d
SET batch_id = c.current_id
FROM collisions c
WHERE d.batch_id = c.old_id;

DELETE FROM sensor_batches old
USING sensor_batches current
WHERE old.source = 'fitbit'
  AND old.status = 'pending'
  AND old.review_day IS NOT NULL
  AND current.source = 'health_connect'
  AND current.status = 'pending'
  AND current.review_day = old.review_day;

UPDATE sensor_batches
SET source = 'health_connect',
    payload_path = CASE WHEN payload_path = 'intake:fitbit'
                        THEN 'intake:health_connect' ELSE payload_path END
WHERE source = 'fitbit';

UPDATE sensor_batches
SET parsed_payload = jsonb_set(parsed_payload, '{source}', '"health_connect"'::jsonb)
WHERE parsed_payload ->> 'source' = 'fitbit';

UPDATE sensor_batches b
SET parsed_payload = jsonb_set(b.parsed_payload, '{observations}', (
    SELECT COALESCE(jsonb_agg(
        CASE WHEN reading.value ->> 'source_type' IN
                   ('fitbit_heart_rate', 'fitbit_sleep', 'fitbit_spo2')
             THEN jsonb_set(reading.value, '{source_type}',
                            to_jsonb('health_connect_' || substr(reading.value ->> 'source_type', 8)))
             ELSE reading.value END
        ORDER BY reading.ordinality), '[]'::jsonb)
    FROM jsonb_array_elements(b.parsed_payload -> 'observations')
         WITH ORDINALITY AS reading(value, ordinality)
))
WHERE jsonb_typeof(b.parsed_payload -> 'observations') = 'array'
  AND b.parsed_payload::text LIKE '%fitbit_%';

UPDATE sensor_batches b
SET theme_links = (
    SELECT jsonb_object_agg(
        CASE WHEN link.key IN ('fitbit_heart_rate', 'fitbit_sleep', 'fitbit_spo2')
             THEN 'health_connect_' || substr(link.key, 8)
             ELSE link.key END,
        link.value)
    FROM jsonb_each(b.theme_links) AS link(key, value)
)
WHERE jsonb_typeof(b.theme_links) = 'object'
  AND b.theme_links::text LIKE '%fitbit_%';

UPDATE sensor_observations
SET source_type = 'health_connect_' || substr(source_type, 8)
WHERE source_type IN ('fitbit_heart_rate', 'fitbit_sleep', 'fitbit_spo2');

UPDATE theme_occurrences
SET source_type = 'health_connect_' || substr(source_type, 8)
WHERE source_type IN ('fitbit_heart_rate', 'fitbit_sleep', 'fitbit_spo2');
