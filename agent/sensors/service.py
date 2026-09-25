"""Review and commit sensor batches through a single atomic write seam."""
from __future__ import annotations

from datetime import date
from typing import Any

from .repository import SensorRepository


class SensorService:
    """Stage observations for review, then commit them with owner-approved links."""

    def __init__(self) -> None:
        self._repo = SensorRepository()

    def stage_delivery(self, batch: dict[str, Any], *, delivery_key: str,
                       review_day: date, clock_skew_seconds: int | None) -> int:
        """Stage one phone delivery without admitting analytical evidence."""
        return self._repo.stage_delivery(
            batch, delivery_key=delivery_key, review_day=review_day,
            clock_skew_seconds=clock_skew_seconds,
        )

    def commit_batch(self, batch_id: int, *, links: dict[str, int | None],
                     user_id: int, expected_observation_count: int | None = None) -> list[int]:
        """Atomically commit the batch, its linked evidence and theme aggregates.

        Retrying with the same links returns the existing observation IDs;
        changing a confirmed batch requires deleting and staging a new one.
        """
        return self._repo.commit_batch(
            batch_id, links=links, user_id=user_id,
            expected_observation_count=expected_observation_count,
        )
