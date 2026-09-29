-- Versioned, source-linked discovery reads. Legacy paraphrases remain non-current.
ALTER TABLE reflections ADD COLUMN discovery_revision BIGINT NOT NULL DEFAULT 1;
ALTER TABLE occasions ADD COLUMN extraction_version INTEGER NOT NULL DEFAULT 2;
ALTER TABLE occasions ADD COLUMN is_current BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE occasion_sources (
    occasion_id INTEGER NOT NULL REFERENCES occasions(id) ON DELETE CASCADE,
    reflection_id INTEGER NOT NULL REFERENCES reflections(id) ON DELETE CASCADE,
    source_revision BIGINT NOT NULL,
    PRIMARY KEY (occasion_id, reflection_id)
);
CREATE INDEX occasion_sources_reflection ON occasion_sources (reflection_id);

CREATE TABLE discovery_reads (
    reflection_id INTEGER PRIMARY KEY REFERENCES reflections(id) ON DELETE CASCADE,
    source_revision BIGINT NOT NULL,
    extraction_version INTEGER NOT NULL,
    library_hash CHAR(64) NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    omitted_accounts INTEGER NOT NULL DEFAULT 0
);

ALTER TABLE pattern_labels ADD COLUMN is_current BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE pattern_labels ADD COLUMN owner_tone VARCHAR(10)
    CHECK (owner_tone IN ('better', 'worse', 'mixed'));

ALTER TABLE pattern_verdicts ALTER COLUMN verdict DROP NOT NULL;
ALTER TABLE difference_verdicts ALTER COLUMN verdict DROP NOT NULL;
ALTER TABLE day_difference_verdicts ALTER COLUMN verdict DROP NOT NULL;

-- A legacy occasion can be linked only when every citation names a live
-- reflection belonging to its owner. Accounts with unresolved sources are
-- removed entirely so their copied excerpts cannot survive a source deletion.
WITH cited AS (
    SELECT o.id AS occasion_id, o.user_id, c.item,
           r.id AS reflection_id, r.discovery_revision
      FROM occasions o
      LEFT JOIN LATERAL jsonb_array_elements(
          CASE WHEN jsonb_typeof(o.citations) = 'array'
               THEN o.citations ELSE '[]'::jsonb END) c(item) ON TRUE
      LEFT JOIN reflections r
        ON c.item->>'sourceType' = 'reflection'
       AND c.item->>'entryId' = r.id::text
       AND r.user_id = o.user_id
), invalid AS (
    SELECT occasion_id
      FROM cited
     GROUP BY occasion_id
    HAVING count(*) FILTER (WHERE reflection_id IS NULL) > 0 OR count(reflection_id) = 0
)
DELETE FROM occasions o USING invalid i WHERE o.id = i.occasion_id;

INSERT INTO occasion_sources (occasion_id, reflection_id, source_revision)
SELECT DISTINCT o.id, r.id, r.discovery_revision
  FROM occasions o
 CROSS JOIN LATERAL jsonb_array_elements(o.citations) c(item)
 JOIN reflections r ON c.item->>'sourceType' = 'reflection'
                   AND c.item->>'entryId' = r.id::text
                   AND r.user_id = o.user_id;
