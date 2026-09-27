-- 0038_idea_link_applies.sql
--
-- `applies`: the from-idea is a specific application of the to-idea's more
-- general principle. "Water the garden in the evening" applies "act when
-- losses are smallest". Related ideas were proposed as `same_meaning` when one
-- was only an application of the other; this names that relation instead.
-- It has a direction, so it is not in the lower-id-first constraint.
ALTER TABLE idea_links DROP CONSTRAINT idea_links_kind_check;
ALTER TABLE idea_links ADD CONSTRAINT idea_links_kind_check
    CHECK (kind IN ('supports', 'contradicts', 'refines', 'depends_on', 'same_meaning', 'applies'));
