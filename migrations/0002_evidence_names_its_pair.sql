-- 0002_evidence_names_its_pair.sql
--
-- pattern_evidence is keyed by (pattern_type, pattern_id), which cannot express
-- a pair. Leverage and decision impact are pairwise: they run once per
-- (source, target) and store the bundle under the source alone. So a source
-- theme with two targets had two bundles competing for one key, and
-- get_latest_evidence_bundle — which takes the most recent computation for that
-- pattern and engine — returned whichever pair happened to run last.
--
-- Asking "why does IRIS say A tends to precede B?" could therefore answer with
-- the evidence for A and C. The engines already emit target_id as an evidence
-- row, which lets a reader notice the mismatch afterwards but does nothing
-- about which bundle is selected.
--
-- related_pattern_id is NULL for the single-pattern engines (persistence,
-- trajectory, tension, resolution) and carries the target for the pairwise
-- ones, so a bundle is addressed by the relation it actually describes.
--
-- This is the first migration that could not have been an IF NOT EXISTS
-- statement: replacing the index is a change, not an addition.

ALTER TABLE pattern_evidence
    ADD COLUMN IF NOT EXISTS related_pattern_id INTEGER;

DROP INDEX IF EXISTS idx_evidence_pattern;

CREATE INDEX idx_evidence_pattern
    ON pattern_evidence (pattern_type, pattern_id, related_pattern_id,
                         engine_name, created_at DESC);
