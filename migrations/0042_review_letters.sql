-- 0042_review_letters.sql
--
-- The weekly letter, kept once written. Opening the week recomputed every
-- finding and asked the model again on each view: seconds of work and a paid
-- call to produce the letter the owner had already read. A letter is reused
-- while its inputs (the week's entries, the facts, the day) are the same.
CREATE TABLE review_letters (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    input_key  CHAR(64) NOT NULL,
    letter     TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, input_key)
);
