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
-- rename happens here, in the only order that works: the old rule comes off,
-- the ideas filed under the old name move, and the new rule goes on. Moving
-- them first fails, because the old rule does not admit 'markets'. A rehearsal
-- against a copy of the real database found that; an empty test database
-- cannot, because there is nothing for the update to move.
--
-- The rows are found without naming the old area. 0027's rule admits exactly
-- seven areas, so an idea in none of the six that keep their names is in the
-- one being renamed. This runs in one transaction, so no row is ever outside a
-- rule except inside it.
ALTER TABLE ideas DROP CONSTRAINT ideas_domain_check;

UPDATE ideas SET domain = 'markets'
 WHERE domain NOT IN ('philosophy', 'economics', 'politics', 'ethics', 'learning', 'other');

ALTER TABLE ideas ADD CONSTRAINT ideas_domain_check
    CHECK (domain IN (
        'philosophy', 'economics', 'markets', 'politics', 'ethics', 'learning', 'other'
    ));
