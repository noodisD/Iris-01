-- 0055_habit_periods.sql
--
-- Habits can be daily, weekly or monthly, with a target per period in
-- frequency_target ("3 times a week"). A habit day can now also be neither
-- done nor skipped but carry a note: the owner's reflection on that day. Only
-- done days are evidence; a note on any day is recalled by chat as what it is.

ALTER TABLE habits DROP CONSTRAINT IF EXISTS habits_frequency_type_check;
ALTER TABLE habits
    ADD CONSTRAINT habits_frequency_type_check
        CHECK (frequency_type IN ('daily', 'weekly', 'monthly', 'specific_days'));
