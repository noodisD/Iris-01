-- 0050_reading_copies_and_passages.sql
--
-- reading_copy: an entry dictated in one breath, with punctuation and capitals
-- put in and not a single word changed (agent/readable.py). The reader reads
-- this copy, and every quote it takes is resolved back to the entry's own text.
-- Cleared whenever the entry's words change; checked word for word before use.
--
-- entry_passages: a long journal entry cut into recall-sized runs of whole
-- sentences, each embedded on its own for chat, as a session is (0047). One
-- vector for four thousand words matches everything a little and nothing well.
-- Rebuilt whenever the entry is processed, so an edit re-cuts it.

ALTER TABLE reflections ADD COLUMN reading_copy TEXT;

CREATE TABLE entry_passages (
    id            SERIAL PRIMARY KEY,
    reflection_id INTEGER NOT NULL REFERENCES reflections(id) ON DELETE CASCADE,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    position      INTEGER NOT NULL,
    text          TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (reflection_id, position)
);
CREATE INDEX entry_passages_user ON entry_passages (user_id);
