-- 0033_life_and_same_meaning.sql
--
-- Two additions to the ideas framework, both about ideas that hold beyond one
-- field.
--
-- * `life`, an area for a principle the owner states as holding across areas
--   of life, not within one field. The reader files an idea there only when
--   the owner's own words say so; it never generalises on their behalf.
-- * `same_meaning`, a link between two ideas that express the same essential
--   meaning in different words or fields. It has no direction, so like
--   `contradicts` it is stored once, lower id first.
--
-- `meaning` is the run that proposes those links across the accepted ideas.
ALTER TABLE ideas DROP CONSTRAINT ideas_domain_check;
ALTER TABLE ideas ADD CONSTRAINT ideas_domain_check
    CHECK (domain IN (
        'philosophy', 'economics', 'markets', 'politics', 'ethics', 'learning', 'life', 'other'
    ));

ALTER TABLE idea_links DROP CONSTRAINT idea_links_kind_check;
ALTER TABLE idea_links ADD CONSTRAINT idea_links_kind_check
    CHECK (kind IN ('supports', 'contradicts', 'refines', 'depends_on', 'same_meaning'));

ALTER TABLE idea_links DROP CONSTRAINT idea_links_contradicts_order;
ALTER TABLE idea_links ADD CONSTRAINT idea_links_contradicts_order
    CHECK (kind NOT IN ('contradicts', 'same_meaning') OR from_idea_id < to_idea_id);

ALTER TABLE idea_runs DROP CONSTRAINT idea_runs_kind_check;
ALTER TABLE idea_runs ADD CONSTRAINT idea_runs_kind_check
    CHECK (kind IN ('discovery', 'links', 'meaning'));
