-- 0028_markets_domain.sql
--
-- One of the ideas framework's areas is renamed to `markets`: patterns,
-- methods and practices for buying and selling in markets, kept apart from
-- economics, which is how an economy works. The owner draws that line and it
-- stays; only the name changes, so the public code describes the area without
-- naming a private subject.
--
-- 0026 and 0027 created the area under its old name and are left untouched:
-- both are already applied, and editing an applied migration is refused. So the
-- rename happens here, moving the ideas already filed there before the rule
-- changes, so no existing row can fall outside the new one.
--
-- The rows are found without naming the old area. 0027's rule admits exactly
-- seven areas, so an idea in none of the six that keep their names is in the
-- one being renamed.
UPDATE ideas SET domain = 'markets'
 WHERE domain NOT IN ('philosophy', 'economics', 'politics', 'ethics', 'learning', 'other');

ALTER TABLE ideas DROP CONSTRAINT ideas_domain_check;
ALTER TABLE ideas ADD CONSTRAINT ideas_domain_check
    CHECK (domain IN (
        'philosophy', 'economics', 'markets', 'politics', 'ethics', 'learning', 'other'
    ));
