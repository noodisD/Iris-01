"""Adapters that turn a sensor export into a ParsedSensorBatch.

The first two adapters (Pixel and Fitbit) land in Tasks 4 and 5.
This file is the registry.
"""
from __future__ import annotations

from typing import Any


REGISTRY: dict[str, type] = {}


def register(source_name: str) -> Any:
    def decorator(cls: type) -> type:
        REGISTRY[source_name] = cls
        return cls
    return decorator


def detect(payload_path) -> str | None:
    """Best-effort guess of which adapter owns this payload.

    Returns the registered source name, or None if nothing matches.
    """
    return None  # Replaced in Task 4 once adapters exist.
