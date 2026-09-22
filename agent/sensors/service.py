"""The seam that turns a confirmed batch into sensor_observations.

Mirrors ReflectionService.create_reflection in shape — staged review
first, a single write method that takes the confirmed batch. Nothing
else in IRIS writes sensor_observations.
"""
from __future__ import annotations

from typing import Any


class SensorService:
    """One method: confirm a staged batch and write its observations.

    The class is deliberately minimal in this first cut; repository
    wiring lands in Task 3 once the schema exists.
    """

    @staticmethod
    def create_sensor_observation(batch: dict[str, Any]) -> list[int]:
        """Return the ids of the written sensor_observations.

        ``batch`` is the confirmed payload: {source, observations: [...]}.
        Raises ValueError if the batch is unconfirmed or its observations
        are missing the date invariant (ADR-0013: a date is read or absent,
        never invented).
        """
        raise NotImplementedError
