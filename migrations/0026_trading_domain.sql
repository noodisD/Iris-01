-- Trading patterns are their own domain. Economics is how an economy works.
ALTER TABLE ideas DROP CONSTRAINT ideas_domain_check;
ALTER TABLE ideas ADD CONSTRAINT ideas_domain_check
    CHECK (domain IN ('philosophy', 'economics', 'trading', 'politics', 'ethics', 'other'));
