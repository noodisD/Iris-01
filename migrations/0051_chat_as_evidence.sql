-- 0051_chat_as_evidence.sql
--
-- A chat conversation can be added to IRIS at the owner's click (ADR-0032).
-- It becomes a reflection in the session format (source 'chat', kind 'chat'):
-- the owner's turns are evidence, IRIS's turns are what was asked, context.
-- chat_sessions remembers which reflection holds it and how many messages it
-- had then, so a conversation that went on can be added again, replacing it.

ALTER TABLE reflections DROP CONSTRAINT reflections_source_check;
ALTER TABLE reflections
    ADD CONSTRAINT reflections_source_check
        CHECK (source IN ('app', 'cli', 'import', 'voice', 'session', 'questionnaire', 'chat'));

ALTER TABLE chat_sessions
    ADD COLUMN reflection_id  INTEGER REFERENCES reflections(id) ON DELETE SET NULL,
    ADD COLUMN added_messages INTEGER,
    ADD COLUMN added_at       TIMESTAMPTZ;
