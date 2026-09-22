"""Adapters that turn a sensor export into a ParsedSensorBatch."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REGISTRY: dict[str, type] = {}


def register(source_name: str):
    def decorator(cls):
        REGISTRY[source_name] = cls
        return cls
    return decorator


def detect(payload_path) -> str | None:
    """Best-effort guess of which adapter owns this payload."""
    try:
        data = json.loads(Path(payload_path).read_text())
    except (OSError, json.JSONDecodeError):
        return None
    device = str(data.get("device", ""))
    if device.startswith("Pixel"):
        return "pixel"
    if device.lower().startswith("fitbit"):
        return "fitbit"
    return None


def _payload_hash(source_type: str, ts: str, raw: dict[str, Any]) -> str:
    """Short stable hash for dedup within a batch."""
    return hashlib.sha1(
        f"{source_type}|{ts}|{json.dumps(raw, sort_keys=True)}"
        .encode()).hexdigest()[:16]


def _read_payload(path) -> tuple[dict[str, Any], bytes]:
    raw = Path(path).read_bytes()
    return json.loads(raw), raw


@register("pixel")
class PixelAdapter:
    """Parses a manual export from a Pixel 10a.

    Three tiers are honoured: location, app_usage, steps. Anything
    else in the export is ignored — a future tier becomes a future
    adapter change, not a silent widening here.
    """

    SOURCE_TYPE = {
        "location": "pixel_location",
        "app_usage": "pixel_app_usage",
        "steps": "pixel_steps",
    }

    def parse(self, payload_path) -> dict[str, Any]:
        data, raw_bytes = _read_payload(payload_path)
        observations: list[dict[str, Any]] = []
        dropped = 0
        for tier, source_type in self.SOURCE_TYPE.items():
            for raw in data.get("tiers", {}).get(tier, []):
                obs = self._to_observation(tier, source_type, raw)
                if obs is None:
                    dropped += 1
                else:
                    observations.append(obs)
        return {
            "source": "pixel",
            "raw_payload_hash": hashlib.sha256(raw_bytes).hexdigest(),
            "observations": observations,
            "dropped_count": dropped,
        }

    @staticmethod
    def _to_observation(tier: str, source_type: str,
                        raw: dict[str, Any]) -> dict[str, Any] | None:
        # ADR-0013: a date is read or absent; refuse to invent one.
        ts = raw.get("ts") or raw.get("date")
        if not ts:
            return None
        obs: dict[str, Any] = {
            "source_type": source_type,
            "occurred_at": ts,
            "payload_hash": _payload_hash(source_type, str(ts), raw),
        }
        if tier == "location":
            obs["lat"] = raw.get("lat"); obs["lon"] = raw.get("lon")
        elif tier == "app_usage":
            obs["value_text"] = raw.get("package")
            obs["value_num"] = raw.get("foreground_seconds")
        elif tier == "steps":
            obs["value_num"] = raw.get("count")
        return obs


@register("fitbit")
class FitbitAdapter:
    """Parses a manual export from a Fitbit Air.

    Three tiers: heart_rate, sleep, spo2. Same shape as PixelAdapter —
    this duplication is the test that the seam is honest.
    """

    SOURCE_TYPE = {
        "heart_rate": "fitbit_heart_rate",
        "sleep": "fitbit_sleep",
        "spo2": "fitbit_spo2",
    }

    def parse(self, payload_path) -> dict[str, Any]:
        data, raw_bytes = _read_payload(payload_path)
        observations: list[dict[str, Any]] = []
        dropped = 0
        for tier, source_type in self.SOURCE_TYPE.items():
            for raw in data.get("tiers", {}).get(tier, []):
                obs = self._to_observation(tier, source_type, raw)
                if obs is None:
                    dropped += 1
                else:
                    observations.append(obs)
        return {
            "source": "fitbit",
            "raw_payload_hash": hashlib.sha256(raw_bytes).hexdigest(),
            "observations": observations,
            "dropped_count": dropped,
        }

    @staticmethod
    def _to_observation(tier: str, source_type: str,
                        raw: dict[str, Any]) -> dict[str, Any] | None:
        ts = raw.get("ts") or raw.get("date")
        if not ts:
            return None
        obs: dict[str, Any] = {
            "source_type": source_type,
            "occurred_at": ts,
            "payload_hash": _payload_hash(source_type, str(ts), raw),
        }
        if tier == "heart_rate":
            obs["value_num"] = raw.get("bpm")
            obs["value_text"] = raw.get("context")
        elif tier == "sleep":
            obs["value_num"] = raw.get("total_minutes")
            obs["value_text"] = raw.get("stage_summary")
        elif tier == "spo2":
            obs["value_num"] = raw.get("percent")
        return obs
