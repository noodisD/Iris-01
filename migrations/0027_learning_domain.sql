-- Skill and mastery are learning, not an unlabelled other.
ALTER TABLE ideas DROP CONSTRAINT ideas_domain_check;
ALTER TABLE ideas ADD CONSTRAINT ideas_domain_check
    CHECK (domain IN (
        'philosophy', 'economics', 'trading', 'politics', 'ethics', 'learning', 'other'
    ));
