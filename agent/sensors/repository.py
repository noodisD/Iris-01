"""DB layer for sensor_batches and sensor_observations.

This is a thin wrapper; the analytical engines never read through here —
they read through get_sensor_occurrences. The repository's only job is
to stage, confirm, and write.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.database import db


class SensorRepository:
    def stage_batch(self, batch: dict[str, Any], payload_path: str | Path,
                    device_clock: datetime | None = None) -> int:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO sensor_batches
                       (source, payload_path, device_clock, host_clock,
                        clock_skew_seconds, observation_count, raw_payload_hash)
                   VALUES (%s, %s, %s, now(),
                           EXTRACT(EPOCH FROM (now() - COALESCE(%s, now())))::int,
                           %s, %s)
                   RETURNING id""",
                (batch["source"], str(payload_path), device_clock,
                 device_clock, len(batch.get("observations", [])),
                 batch.get("raw_payload_hash")),
            )
            batch_id = cur.fetchone()
            if batch_id is None:
                raise RuntimeError("INSERT into sensor_batches returned no id")
            conn.commit()
            return batch_id[0]

    def confirm_batch(self, batch_id: int) -> None:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE sensor_batches SET confirmed_at = now(), "
                "status = 'confirmed' WHERE id = %s AND status = 'pending'",
                (batch_id,))
            conn.commit()

    def reject_batch(self, batch_id: int) -> None:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE sensor_batches SET status = 'rejected' WHERE id = %s",
                (batch_id,))
            conn.commit()

    def insert_observations(self, batch_id: int,
                            observations: list[dict[str, Any]]) -> list[int]:
        ids: list[int] = []
        with db.connection() as conn, conn.cursor() as cur:
            for obs in observations:
                cur.execute(
                    """INSERT INTO sensor_observations
                           (batch_id, source_type, occurred_at, occurred_date,
                            value_num, value_text, lat, lon, payload_hash)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (batch_id, payload_hash) DO NOTHING
                       RETURNING id""",
                    (batch_id, obs["source_type"], obs.get("occurred_at"),
                     _to_date(obs.get("occurred_at")),
                     obs.get("value_num"), obs.get("value_text"),
                     obs.get("lat"), obs.get("lon"),
                     obs["payload_hash"]),
                )
                row = cur.fetchone()
                if row is not None:
                    ids.append(row[0])
            conn.commit()
        return ids

    def is_confirmed(self, batch_id: int) -> bool:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT status FROM sensor_batches WHERE id = %s",
                        (batch_id,))
            row = cur.fetchone()
            return bool(row) and row[0] == "confirmed"


def _to_date(occurred_at: str | datetime | None):
    if occurred_at is None:
        return None
    if isinstance(occurred_at, str):
        # Accept both 'Z' and explicit offsets.
        normalised = occurred_at.replace("Z", "+00:00")
        return datetime.fromisoformat(normalised).astimezone(timezone.utc).date()
    return occurred_at.astimezone(timezone.utc).date()
