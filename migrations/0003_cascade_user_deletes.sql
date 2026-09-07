-- 0003_cascade_user_deletes.sql
--
-- Twelve of the fifteen foreign keys to users(id) already cascade on delete.
-- Three did not: conversation_messages, journal_entries and themes. Deleting a
-- user therefore failed with a foreign key violation unless those three tables
-- were cleared by hand first — which is exactly what the test suite's
-- _purge_user does, in the right order, as a workaround for this.
--
-- The inconsistency is the defect. A user's data either goes with the user or
-- it does not, and having it depend on which table the row happens to live in
-- means "delete everything about me" cannot be implemented correctly without
-- someone remembering all three exceptions.
--
-- theme_occurrences already cascades from themes, so removing a user's themes
-- takes their occurrences with it.
--
-- This is the change ADR-0012 named as the thing CREATE/ALTER ... IF NOT EXISTS
-- could not express: altering an existing constraint is neither an addition nor
-- idempotent, so it had to wait for migrations.

ALTER TABLE conversation_messages
    DROP CONSTRAINT conversation_messages_user_id_fkey,
    ADD CONSTRAINT conversation_messages_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE journal_entries
    DROP CONSTRAINT journal_entries_user_id_fkey,
    ADD CONSTRAINT journal_entries_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE themes
    DROP CONSTRAINT themes_user_id_fkey,
    ADD CONSTRAINT themes_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
