-- 0040_observatory_modules.sql
--
-- Stable module ids for the system map. Existing rows get identities from the
-- recorded name, component, and attributes. Generic input/output is not invented
-- for spans captured before this migration.

ALTER TABLE obs_spans ADD COLUMN module_id TEXT;
ALTER TABLE obs_spans ADD COLUMN parent_module_id TEXT;

UPDATE obs_spans
   SET module_id = CASE
       WHEN name = 'db.connection' THEN 'db.connection'
       WHEN name LIKE 'http:%' THEN name
       WHEN component = 'web' AND name = 'page.load' THEN 'web.page_load'
       WHEN component = 'android' AND name IN ('collector.state', 'android.collector.state')
           THEN 'android.collector.state'
       WHEN component IN ('web', 'android')
            AND split_part(name, ' ', 1) IN ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS')
           THEN component || '.request'
       WHEN component IN ('web', 'android') THEN component || '.other'
       WHEN component = 'http' THEN
           CASE
               WHEN COALESCE(attributes->>'http.route', '') <> ''
                    AND attributes->>'http.route' <> '<unmatched>'
                   THEN 'http:' || upper(COALESCE(attributes->>'http.request.method', split_part(name, ' ', 1)))
                        || ' ' || (attributes->>'http.route')
               ELSE 'http:' || upper(COALESCE(attributes->>'http.request.method', split_part(name, ' ', 1)))
                    || ' <unmatched>'
           END
       WHEN component = 'db' OR name LIKE 'db.fetch%' THEN
           CASE
               WHEN COALESCE(attributes->>'db.collection.name', '') <> ''
                   THEN 'db:' || (attributes->>'db.collection.name')
               WHEN name = 'db.fetch' THEN 'db:<statement>'
               WHEN name LIKE 'db.fetch %' THEN 'db:' || btrim(substring(name FROM 10))
               WHEN position(' ' IN name) > 0 AND name NOT LIKE 'db.%'
                   THEN 'db:' || split_part(name, ' ', 2)
               ELSE 'db:' || name
           END
       ELSE name
   END
 WHERE module_id IS NULL;

WITH RECURSIVE ancestors AS (
    SELECT child.trace_id,
           child.span_id,
           parent.span_id AS anc_span,
           parent.parent_span_id AS anc_parent,
           parent.name AS anc_name,
           parent.module_id AS anc_module,
           1 AS depth,
           ARRAY[child.span_id]::text[] AS seen
      FROM obs_spans AS child
      JOIN obs_spans AS parent
        ON parent.trace_id = child.trace_id
       AND parent.span_id = child.parent_span_id
    UNION ALL
    SELECT ancestors.trace_id,
           ancestors.span_id,
           parent.span_id,
           parent.parent_span_id,
           parent.name,
           parent.module_id,
           ancestors.depth + 1,
           ancestors.seen || ancestors.anc_span::text
      FROM ancestors
      JOIN obs_spans AS parent
        ON parent.trace_id = ancestors.trace_id
       AND parent.span_id = ancestors.anc_parent
     WHERE ancestors.anc_name = 'db.connection'
       AND ancestors.depth < 64
       AND ancestors.anc_parent IS NOT NULL
       AND NOT (ancestors.anc_parent::text = ANY (ancestors.seen))
)
UPDATE obs_spans AS child
   SET parent_module_id = picked.anc_module
  FROM (
      SELECT DISTINCT ON (trace_id, span_id)
             trace_id, span_id, anc_module
        FROM ancestors
       WHERE anc_name IS DISTINCT FROM 'db.connection'
       ORDER BY trace_id, span_id, depth
  ) AS picked
 WHERE child.trace_id = picked.trace_id
   AND child.span_id = picked.span_id;

UPDATE obs_spans SET module_id = name WHERE module_id IS NULL;

ALTER TABLE obs_spans ALTER COLUMN module_id SET NOT NULL;

CREATE INDEX idx_obs_spans_module_started ON obs_spans (module_id, started_at DESC);
