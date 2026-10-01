-- 0046_discovery_memo.sql
--
-- Model verdicts discovery has already paid for. A pattern checked against an
-- unchanged account, or two unchanged accounts compared for being the same
-- event, has the same answer next time; asking again only costs money. Each
-- row is keyed by a hash of exactly what was asked (prompt version, model,
-- definition wording, account fingerprints), so any change asks afresh.
-- Values are the model's validated decisions and replies, kept on this machine
-- like the drafts and views built from them.
CREATE TABLE discovery_memo (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key        CHAR(64) NOT NULL,
    kind       TEXT NOT NULL,
    value      JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    used_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, key)
);
CREATE INDEX discovery_memo_used ON discovery_memo (user_id, used_at);
