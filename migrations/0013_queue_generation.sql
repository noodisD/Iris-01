-- 0013_queue_generation.sql
--
-- Which version of a source a queued job is for.
--
-- Editing an entry re-queues it. If the entry was already queued — or already
-- being processed — the re-queue used to be `ON CONFLICT DO NOTHING`, and the
-- run in flight then finished with the *old* text and deleted the row as done.
-- The edit was never processed: the journal showed the new words while every
-- engine held the old ones, with nothing left in the queue to say so.
--
-- A re-queue now bumps this counter. A run records the generation it claimed
-- and may only retire the row if it is still that generation; if the source
-- changed underneath it, the row is re-armed and the new text is processed.
ALTER TABLE processing_queue
    ADD COLUMN IF NOT EXISTS generation INTEGER NOT NULL DEFAULT 0;
