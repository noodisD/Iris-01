-- 0004_drop_theme_trajectories.sql
--
-- theme_trajectories was written on every trajectory analysis and read by
-- nothing. ADR-0005 ("cache only where there is a reader, and never without
-- expiry") stopped the writes and recorded that the table would stay until
-- there was a migration tool to drop it. There is one now.
--
-- Confirmed unreferenced before dropping: the engine no longer writes it, and
-- its two accessors (get_theme_trajectory, get_all_theme_trajectories) were
-- reachable only through repository wrappers that nothing called.
--
-- Trajectory recomputes on demand, so there is nothing here to preserve — the
-- table is empty of anything the product would read.

DROP TABLE IF EXISTS theme_trajectories;
