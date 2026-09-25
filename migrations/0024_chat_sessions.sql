-- A chat open is its own session. Messages stay stored and queued for
-- embedding; the screen shows only the session that was just opened.
CREATE TABLE chat_sessions (
    id VARCHAR(50) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX chat_sessions_user_created_idx
    ON chat_sessions (user_id, created_at DESC, id DESC);

CREATE INDEX conversation_messages_user_session_created_idx
    ON conversation_messages (user_id, session_id, created_at, id);
