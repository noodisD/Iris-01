-- 0049_questionnaire_suggestions.sql
--
-- A questionnaire answer can be suggested from the owner's own writing: their
-- sentences, quoted word for word from journal entries, sessions or chat, for
-- the owner to keep, edit or discard (ADR-0029). A suggestion kept unchanged is
-- added as memory, not evidence: its sentences already count once in the
-- entries they came from.

ALTER TABLE questionnaire_answers DROP CONSTRAINT questionnaire_answers_source_check;
ALTER TABLE questionnaire_answers
    ADD CONSTRAINT questionnaire_answers_source_check
        CHECK (source IN ('form', 'interview', 'suggested'));
