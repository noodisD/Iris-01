"""Persistence for staged sensor batches and their reviewed evidence."""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from agent.constants import MAX_SENSOR_OCCURRENCES_PER_DAY_PER_THEME
from agent.database import db

from .adapters import describe_observation, has_essential_measurement, to_timestamp


class SensorBatchChanged(ValueError):
    """The pending batch grew after the owner opened it."""


class SensorRepository:
    def stage_delivery(self, batch: dict[str, Any], *, delivery_key: str,
                       review_day: date, clock_skew_seconds: int | None) -> int:
        """Merge a phone delivery into the day's pending review, exactly once."""
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",
                        ("sensor-intake:" + batch["source"],))
            cur.execute("SELECT batch_id FROM sensor_deliveries WHERE delivery_key = %s",
                        (delivery_key,))
            existing = cur.fetchone()
            if existing is not None:
                conn.commit()
                return int(existing[0])
            cur.execute(
                """INSERT INTO sensor_batches
                       (source, payload_path, device_clock, host_clock,
                        clock_skew_seconds, observation_count, dropped_count,
                        raw_payload_hash, parsed_payload, review_day)
                   VALUES (%s, %s, %s, now(), %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (source, review_day)
                       WHERE status = 'pending' AND review_day IS NOT NULL
                   DO UPDATE SET
                       parsed_payload = jsonb_set(
                           sensor_batches.parsed_payload, '{observations}',
                           COALESCE(sensor_batches.parsed_payload -> 'observations', '[]'::jsonb)
                             || (EXCLUDED.parsed_payload -> 'observations')),
                       observation_count = sensor_batches.observation_count + EXCLUDED.observation_count,
                       dropped_count = sensor_batches.dropped_count + EXCLUDED.dropped_count,
                       device_clock = EXCLUDED.device_clock,
                       host_clock = EXCLUDED.host_clock,
                       clock_skew_seconds = EXCLUDED.clock_skew_seconds,
                       raw_payload_hash = EXCLUDED.raw_payload_hash
                   RETURNING id""",
                (batch["source"], "intake:" + batch["source"],
                 to_timestamp(batch.get("device_clock")), clock_skew_seconds,
                 len(batch.get("observations", [])), batch.get("dropped_count", 0),
                 batch.get("raw_payload_hash"), json.dumps(batch), review_day),
            )
            batch_id = int(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO sensor_deliveries (delivery_key, batch_id) VALUES (%s, %s)",
                (delivery_key, batch_id),
            )
            conn.commit()
            return batch_id

    def commit_batch(self, batch_id: int, *, links: dict[str, int | None],
                     user_id: int, expected_observation_count: int | None = None) -> list[int]:
        """Lock the batch and linked themes; all derived writes share this transaction."""
        if not isinstance(links, dict):
            raise ValueError("links must be a mapping of source types to theme IDs")
        # Explicit null and omitted links mean the same thing: keep the raw
        # reading, without admitting it as evidence.
        if any(not isinstance(source, str) or
               (theme_id is not None and type(theme_id) is not int)
               for source, theme_id in links.items()):
            raise ValueError("links must map source types to theme IDs or null")
        selected = {source: theme_id for source, theme_id in links.items()
                    if theme_id is not None}
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT status, parsed_payload, theme_links, observation_count
                   FROM sensor_batches WHERE id = %s FOR UPDATE""", (batch_id,))
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"batch {batch_id} not found")
            status, parsed, saved_links, observation_count = row
            if status == "confirmed":
                if selected != {source: theme_id
                                for source, theme_id in (saved_links or {}).items()
                                if theme_id is not None}:
                    raise ValueError(f"batch {batch_id} already confirmed with different links")
                self._lock_active_themes(cur, selected.values(), user_id)
                cur.execute("SELECT id FROM sensor_observations WHERE batch_id = %s ORDER BY id",
                            (batch_id,))
                ids = [r[0] for r in cur.fetchall()]
                conn.commit()
                return ids
            if status != "pending":
                raise ValueError(f"batch {batch_id} is not pending")
            if (expected_observation_count is not None
                    and expected_observation_count != observation_count):
                raise SensorBatchChanged(
                    "New readings arrived after this batch was opened. "
                    "Review it again before confirming."
                )

            ids = self._commit_pending(cur, batch_id, parsed, links, selected, user_id)
            conn.commit()
            return ids

    @staticmethod
    def _validated_observations(batch_id: int, parsed: Any, links: dict[str, int | None],
                                selected: dict[str, int]) -> list[dict[str, Any]]:
        if not isinstance(parsed, dict) or not isinstance(parsed.get("observations"), list):
            raise ValueError(f"batch {batch_id} has no parsed observations to commit")
        observations = parsed["observations"]
        source_types = {obs["source_type"] for obs in observations}
        unknown = links.keys() - source_types
        if unknown:
            raise ValueError(f"source type not in batch: {', '.join(sorted(unknown))}")
        if any(obs["source_type"] in selected and not has_essential_measurement(obs)
               for obs in observations):
            raise ValueError("linked sensor reading has no essential measurement")
        return observations

    def _commit_pending(self, cur: Any, batch_id: int, parsed: Any,
                        links: dict[str, int | None], selected: dict[str, int],
                        user_id: int) -> list[int]:
        observations = self._validated_observations(batch_id, parsed, links, selected)
        self._lock_active_themes(cur, selected.values(), user_id)

        by_hash: dict[str, int] = {}
        dated_by_source: dict[str, set[date]] = {}
        undated_by_source: dict[str, list[tuple[dict[str, Any], int]]] = {}
        for obs in observations:
            occurred_at = to_timestamp(obs.get("occurred_at"))
            cur.execute(
                """INSERT INTO sensor_observations
                       (batch_id, source_type, occurred_at, occurred_date,
                        value_num, value_text, lat, lon, payload_hash)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (batch_id, payload_hash) DO NOTHING
                   RETURNING id""",
                (batch_id, obs["source_type"], occurred_at,
                 occurred_at.date() if occurred_at else None,
                 obs.get("value_num"), obs.get("value_text"),
                 obs.get("lat"), obs.get("lon"), obs["payload_hash"]),
            )
            inserted = cur.fetchone()
            if inserted is None:
                continue
            obs_id = inserted[0]
            by_hash[obs["payload_hash"]] = obs_id
            if obs["source_type"] not in selected:
                continue
            if occurred_at is None:
                undated_by_source.setdefault(obs["source_type"], []).append((obs, obs_id))
            else:
                dated_by_source.setdefault(obs["source_type"], set()).add(
                    occurred_at.date())

        cur.execute(
            """UPDATE sensor_batches SET status = 'confirmed',
                      confirmed_at = clock_timestamp(), theme_links = %s
               WHERE id = %s""", (json.dumps(selected), batch_id))
        touched: set[int] = set()
        for source_type, theme_id in sorted(selected.items()):
            for day in sorted(dated_by_source.get(source_type, ())):
                if self._reconcile_daily_occurrences(cur, theme_id, source_type, day):
                    touched.add(theme_id)
            if self._admit_undated(cur, theme_id, source_type,
                                  undated_by_source.get(source_type, [])):
                touched.add(theme_id)

        self._refresh_themes(cur, touched)
        return list(by_hash.values())

    @staticmethod
    def _admit_undated(cur: Any, theme_id: int, source_type: str,
                       readings: list[tuple[dict[str, Any], int]]) -> bool:
        # Undated evidence cannot occupy a UTC day; cap it separately.
        cur.execute(
            """SELECT COUNT(*) FROM theme_occurrences
               WHERE theme_id = %s AND source_type = %s
                 AND occurred_at IS NULL""", (theme_id, source_type))
        room = max(0, MAX_SENSOR_OCCURRENCES_PER_DAY_PER_THEME - cur.fetchone()[0])
        admitted = readings[:room]
        for obs, obs_id in admitted:
            cur.execute(
                """INSERT INTO theme_occurrences
                       (theme_id, source_type, source_id, snippet,
                        similarity_score, occurred_at, admission_basis)
                   VALUES (%s, %s, %s, %s, 1.0, NULL, 'citation')""",
                (theme_id, source_type, obs_id, describe_observation(obs)))
        return bool(admitted)

    @staticmethod
    def _lock_active_themes(cur: Any, theme_ids: Any, user_id: int) -> None:
        ids = sorted(set(theme_ids))
        if not ids:
            return
        # Serialize admissions to each theme across batches, and validate
        # ownership/status under the same locks used for evidence insertion.
        cur.execute(
            """SELECT id FROM themes
               WHERE id = ANY(%s) AND user_id = %s AND status = 'active'
               ORDER BY id FOR UPDATE""", (ids, user_id))
        if {r[0] for r in cur.fetchall()} != set(ids):
            raise ValueError("linked theme must be active and belong to the user")

    @staticmethod
    def _reconcile_daily_occurrences(cur: Any, theme_id: int, source_type: str,
                                     day: date) -> bool:
        """Keep the newest confirmed measured readings within this UTC-day cap.

        The raw rows outlive their capped occurrences, so deleting a newer
        batch can restore the previous owner's approved reading.
        Call only while holding the theme row lock.
        """
        cur.execute(
            """SELECT s.id, s.occurred_at, s.value_num, s.value_text, s.lat, s.lon
               FROM sensor_observations s
               JOIN sensor_batches b ON b.id = s.batch_id
               WHERE b.status = 'confirmed'
                 AND b.theme_links ->> s.source_type = %s
                 AND s.source_type = %s AND s.occurred_date = %s
               ORDER BY s.occurred_at DESC, b.received_at DESC, s.id DESC
               LIMIT %s""",
            (str(theme_id), source_type, day, MAX_SENSOR_OCCURRENCES_PER_DAY_PER_THEME))
        winners = cur.fetchall()
        wanted = {row[0] for row in winners}
        cur.execute(
            """SELECT id, source_id FROM theme_occurrences
               WHERE theme_id = %s AND source_type = %s
                 AND (occurred_at AT TIME ZONE 'UTC')::date = %s""",
            (theme_id, source_type, day))
        existing = {source_id: occurrence_id for occurrence_id, source_id in cur.fetchall()}
        if wanted == existing.keys():
            return False
        stale = [occurrence_id for source_id, occurrence_id in existing.items()
                 if source_id not in wanted]
        if stale:
            cur.execute("DELETE FROM theme_occurrences WHERE id = ANY(%s)", (stale,))
        for obs_id, occurred_at, value_num, value_text, lat, lon in winners:
            if obs_id in existing:
                continue
            snippet = describe_observation({
                "source_type": source_type, "value_num": value_num,
                "value_text": value_text, "lat": lat, "lon": lon,
            })
            cur.execute(
                """INSERT INTO theme_occurrences
                       (theme_id, source_type, source_id, snippet,
                        similarity_score, occurred_at, admission_basis)
                   VALUES (%s, %s, %s, %s, 1.0, %s, 'citation')""",
                (theme_id, source_type, obs_id, snippet, occurred_at))
        return True

    def reject_batch(self, batch_id: int) -> None:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT status FROM sensor_batches WHERE id = %s FOR UPDATE",
                        (batch_id,))
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"batch {batch_id} not found")
            if row[0] != "pending":
                raise ValueError(f"batch {batch_id} is not pending")
            cur.execute("UPDATE sensor_batches SET status = 'rejected' WHERE id = %s",
                        (batch_id,))
            conn.commit()

    def get_batch(self, batch_id: int) -> dict[str, Any] | None:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT b.id, b.source, b.received_at, b.status, b.observation_count,
                          b.dropped_count, b.clock_skew_seconds, b.parsed_payload,
                          b.theme_links, b.review_day,
                          (SELECT max(d.received_at) FROM sensor_deliveries d
                           WHERE d.batch_id = b.id)
                   FROM sensor_batches b WHERE b.id = %s""", (batch_id,))
            row = cur.fetchone()
            return self._batch_dict(row) if row else None

    def list_batches(self, limit: int = 50) -> list[dict[str, Any]]:
        """List review metadata without loading every parsed reading."""
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT b.id, b.source, b.received_at, b.status, b.observation_count,
                          b.dropped_count, b.clock_skew_seconds, b.theme_links,
                          b.review_day,
                          (SELECT max(d.received_at) FROM sensor_deliveries d
                           WHERE d.batch_id = b.id)
                   FROM sensor_batches b
                   WHERE b.status = 'pending' OR b.id IN (
                       SELECT id FROM sensor_batches WHERE status <> 'pending'
                       ORDER BY received_at DESC LIMIT %s
                   )
                   ORDER BY (b.status = 'pending') DESC, b.received_at DESC""", (limit,))
            return [
                {"id": row[0], "source": row[1], "received_at": row[2],
                 "status": row[3], "observation_count": row[4],
                 "dropped_count": row[5], "clock_skew_seconds": row[6],
                 "theme_links": row[7] or {}, "review_day": row[8],
                 "last_delivery_at": row[9]}
                for row in cur.fetchall()
            ]

    @staticmethod
    def _batch_dict(row: tuple[Any, ...]) -> dict[str, Any]:
        return {
            "id": row[0], "source": row[1], "received_at": row[2],
            "status": row[3], "observation_count": row[4],
            "dropped_count": row[5], "clock_skew_seconds": row[6],
            "parsed_payload": row[7], "theme_links": row[8] or {},
            "review_day": row[9], "last_delivery_at": row[10],
        }

    def delete_batch(self, batch_id: int) -> None:
        """Retract the batch's evidence and restore any capped previous readings."""
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT status, theme_links FROM sensor_batches WHERE id = %s FOR UPDATE",
                        (batch_id,))
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"batch {batch_id} not found")
            touched: set[int] = set()
            affected_days: list[tuple[int, str, date]] = []
            if row[0] == "confirmed":
                links = row[1] or {}
                theme_ids = sorted(set(links.values()))
                if theme_ids:
                    # Lock all linked themes, not just those with visible rows.
                    # An uncapped sample may still become the next fallback.
                    cur.execute(
                        "SELECT id FROM themes WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
                        (theme_ids,))
                    locked = {r[0] for r in cur.fetchall()}
                    cur.execute(
                        """SELECT DISTINCT source_type, occurred_date
                           FROM sensor_observations
                           WHERE batch_id = %s AND occurred_date IS NOT NULL""",
                        (batch_id,))
                    affected_days = [(links[source], source, day)
                                     for source, day in cur.fetchall()
                                     if source in links and links[source] in locked]
                cur.execute(
                    """SELECT DISTINCT t.theme_id FROM theme_occurrences t
                       JOIN sensor_observations s
                         ON s.id = t.source_id AND s.source_type = t.source_type
                       WHERE s.batch_id = %s ORDER BY t.theme_id""", (batch_id,))
                touched = {r[0] for r in cur.fetchall()}
                cur.execute(
                    """DELETE FROM theme_occurrences t
                       USING sensor_observations s
                       WHERE s.batch_id = %s AND s.id = t.source_id
                         AND s.source_type = t.source_type""", (batch_id,))
            cur.execute("DELETE FROM sensor_batches WHERE id = %s", (batch_id,))
            for theme_id, source_type, day in sorted(affected_days):
                if self._reconcile_daily_occurrences(cur, theme_id, source_type, day):
                    touched.add(theme_id)
            self._refresh_themes(cur, touched)
            conn.commit()

    @staticmethod
    def _refresh_themes(cur: Any, theme_ids: set[int]) -> None:
        for theme_id in sorted(theme_ids):
            db._recompute_theme_stats(cur, theme_id)
            cur.execute("UPDATE pattern_resolutions SET last_computed_at = NULL "
                        "WHERE pattern_type = 'theme' AND pattern_id = %s", (theme_id,))
            cur.execute("UPDATE theme_tensions SET last_computed_at = NULL "
                        "WHERE theme_a_id = %s OR theme_b_id = %s", (theme_id, theme_id))
            cur.execute("UPDATE pattern_leverage SET last_computed_at = NULL "
                        "WHERE (source_type = 'theme' AND source_id = %s) "
                        "OR (target_type = 'theme' AND target_id = %s)",
                        (theme_id, theme_id))
            cur.execute("UPDATE decision_impacts SET last_computed_at = NULL "
                        "WHERE (anchor_type = 'theme' AND anchor_id = %s) "
                        "OR (target_type = 'theme' AND target_id = %s)",
                        (theme_id, theme_id))
            cur.execute("UPDATE pattern_confidence SET last_computed_at = NULL "
                        "WHERE pattern_type = 'theme' AND pattern_id = %s", (theme_id,))



