-- 0056_habit_order.sql
--
-- The owner orders habits so the most important stay on top. `position` is
-- that order (lower first), the same on the Habits list, Today and the phone.
-- Existing habits keep the order they were shown in: newest first.

ALTER TABLE habits ADD COLUMN position INTEGER;

UPDATE habits h SET position = ranked.n
  FROM (SELECT id, row_number() OVER (PARTITION BY user_id ORDER BY created_at DESC, id DESC) AS n
          FROM habits) ranked
 WHERE ranked.id = h.id;
