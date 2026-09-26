"""Parse live Pixel and Health Connect measurements into reviewable batches."""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from datetime import UTC, date, datetime, time
from typing import Any, ClassVar

REGISTRY: dict[str, type] = {}


def to_timestamp(occurred_at: str | date | datetime | None) -> datetime | None:
    """Interpret date-only readings as UTC calendar days, never local time."""
    if occurred_at is None:
        return None
    if isinstance(occurred_at, datetime):
        value = occurred_at
    elif isinstance(occurred_at, date):
        value = datetime.combine(occurred_at, time.min, tzinfo=UTC)
    elif isinstance(occurred_at, str):
        value = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
    else:
        raise ValueError(f"invalid observation date: {occurred_at!r}")
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def register(source_name: str) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        REGISTRY[source_name] = cls
        return cls
    return decorator


def describe_observation(obs: dict[str, Any]) -> str:
    """Format an observation into a factual snippet."""
    source_type = obs.get("source_type", "")
    if source_type.startswith("timeline_"):
        from .timeline import describe_timeline
        return describe_timeline(obs) or "Timeline reading"
    if source_type.startswith("pixel_"):
        return PixelAdapter.describe_observation(obs)
    if source_type.startswith("health_connect_"):
        return HealthConnectAdapter.describe_observation(obs)
    return "Unknown reading"

def has_essential_measurement(obs: dict[str, Any]) -> bool:
    """Whether a reading carries the actual measurement its source claims."""
    source_type = obs.get("source_type")
    value = obs.get("value_num")
    numeric = (isinstance(value, (int, float)) and not isinstance(value, bool)
               and (not isinstance(value, float) or math.isfinite(value)))
    if source_type == "pixel_location":
        lat, lon = obs.get("lat"), obs.get("lon")
        return all(isinstance(coord, (int, float)) and not isinstance(coord, bool)
                   and (not isinstance(coord, float) or math.isfinite(coord))
                   for coord in (lat, lon))
    if source_type == "pixel_app_usage":
        package = obs.get("value_text")
        return numeric and isinstance(package, str) and bool(package.strip())
    if source_type in ("pixel_steps", "health_connect_heart_rate",
                       "health_connect_sleep", "health_connect_spo2"):
        return numeric
    if source_type in ("timeline_visit", "timeline_activity"):
        return bool(obs.get("occurred_at"))
    return False


def _payload_hash(source_type: str, ts: str, raw: dict[str, Any]) -> str:
    """Short stable hash for dedup within a batch."""
    return hashlib.sha1(
        f"{source_type}|{ts}|{json.dumps(raw, sort_keys=True)}"
        .encode()).hexdigest()[:16]



def _build_batch(source: str, data: dict[str, Any],
                 raw_bytes: bytes) -> dict[str, Any]:
    """Shared batch-construction logic across all adapters."""
    source_type_map: dict[str, str]
    adapter_cls: type
    if source == "pixel":
        source_type_map = PixelAdapter.SOURCE_TYPE
        adapter_cls = PixelAdapter
    elif source == "health_connect":
        source_type_map = HealthConnectAdapter.SOURCE_TYPE
        adapter_cls = HealthConnectAdapter
    else:
        raise ValueError(f"unknown source {source!r}")
    tiers = data.get("tiers", {})
    if not isinstance(tiers, dict):
        raise ValueError("tiers must be an object")
    observations: list[dict[str, Any]] = []
    dropped = 0
    for tier, source_type in source_type_map.items():
        rows = tiers.get(tier, [])
        if not isinstance(rows, list):
            raise ValueError(f"{tier} must be a list")
        for raw in rows:
            obs = adapter_cls._to_observation(tier, source_type, raw) if isinstance(raw, dict) else None
            if obs is None:
                dropped += 1
            else:
                observations.append(obs)
    try:
        device_clock = to_timestamp(data.get("exported_at"))
    except (TypeError, ValueError):
        device_clock = None
    return {
        "source": source,
        "raw_payload_hash": hashlib.sha256(raw_bytes).hexdigest(),
        "device_clock": device_clock.isoformat() if device_clock else None,
        "observations": observations,
        "dropped_count": dropped,
    }


@register("pixel")
class PixelAdapter:
    """Parses the Pixel collector's location, app-use and step readings.

    The same payload shape can be used by the checked-in fixture. New tiers
    require an explicit adapter change; they are not silently widened.
    """

    SOURCE_TYPE: ClassVar[dict[str, str]] = {
        "location": "pixel_location",
        "app_usage": "pixel_app_usage",
        "steps": "pixel_steps",
    }

    def parse_from_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize the phone's decoded JSON without admitting evidence."""
        raw_bytes = json.dumps(data, sort_keys=True).encode()
        return _build_batch("pixel", data, raw_bytes)

    @staticmethod
    def _to_observation(tier: str, source_type: str,
                        raw: dict[str, Any]) -> dict[str, Any] | None:
        # ADR-0013: a date is read or absent; refuse to invent one.
        ts = raw.get("ts") or raw.get("date")
        if not ts:
            return None
        try:
            to_timestamp(ts)
        except (TypeError, ValueError):
            return None
        obs: dict[str, Any] = {
            "source_type": source_type,
            "occurred_at": ts,
            "payload_hash": _payload_hash(source_type, str(ts), raw),
        }
        if tier == "location":
            obs["lat"] = raw.get("lat")
            obs["lon"] = raw.get("lon")
            accuracy = raw.get("accuracy_m")
            if isinstance(accuracy, (int, float)) and not isinstance(accuracy, bool):
                obs["accuracy_m"] = float(accuracy)
        elif tier == "app_usage":
            obs["value_text"] = raw.get("package")
            obs["value_num"] = raw.get("foreground_seconds")
            category = raw.get("category")
            if isinstance(category, str) and category.strip():
                obs["detail"] = {"category": category.strip()}
        elif tier == "steps":
            obs["value_num"] = raw.get("count")
            if raw.get("count_kind") == "observed":
                obs["value_text"] = "recorded while IRIS was running"
        return obs if has_essential_measurement(obs) else None
    @staticmethod
    def describe_observation(obs: dict[str, Any]) -> str:
        """Factual, non-interpretive rendering of an observation for display."""
        st = obs["source_type"]
        v_num, v_text = obs.get("value_num"), obs.get("value_text")
        if st == "pixel_location":
            lat, lon = obs.get("lat"), obs.get("lon")
            return (f"Location: ({lat}, {lon})" if lat is not None and lon is not None
                    else "Location: no reported coordinates")
        if st == "pixel_app_usage":
            package = f"App: {v_text}" if v_text is not None else "App usage: no reported package"
            return package + (f" ({int(v_num)} s)" if v_num is not None else "")
        if st == "pixel_steps":
            if v_num is None:
                return "Steps: no reported count"
            return f"{int(v_num)} steps" + (f" ({v_text})" if v_text else "")
        return "Unknown reading"


@register("health_connect")
class HealthConnectAdapter:
    """Parse Health Connect readings regardless of their contributing app."""

    SOURCE_TYPE: ClassVar[dict[str, str]] = {
        "heart_rate": "health_connect_heart_rate",
        "sleep": "health_connect_sleep",
        "spo2": "health_connect_spo2",
    }

    def parse_from_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize the phone's decoded JSON without admitting evidence."""
        raw_bytes = json.dumps(data, sort_keys=True).encode()
        return _build_batch("health_connect", data, raw_bytes)

    @staticmethod
    def _to_observation(tier: str, source_type: str,
                        raw: dict[str, Any]) -> dict[str, Any] | None:
        ts = raw.get("ts") or raw.get("date")
        if not ts:
            return None
        try:
            to_timestamp(ts)
        except (TypeError, ValueError):
            return None
        obs: dict[str, Any] = {
            "source_type": source_type,
            "occurred_at": ts,
            "payload_hash": _payload_hash(source_type, str(ts), raw),
        }
        if isinstance(raw.get("origin_package"), str):
            obs["origin_package"] = raw["origin_package"]
        if tier == "heart_rate":
            obs["value_num"] = raw.get("bpm")
            obs["value_text"] = raw.get("context")
        elif tier == "sleep":
            obs["value_num"] = raw.get("total_minutes")
            obs["value_text"] = raw.get("stage_summary")
            start = raw.get("start_ts")
            if start:
                try:
                    to_timestamp(start)
                except (TypeError, ValueError):
                    return None
                obs["occurred_at"] = start
                obs["ended_at"] = ts
        elif tier == "spo2":
            obs["value_num"] = raw.get("percent")
        return obs if has_essential_measurement(obs) else None
    @staticmethod
    def describe_observation(obs: dict[str, Any]) -> str:
        st = obs["source_type"]
        v_num, v_text = obs.get("value_num"), obs.get("value_text")
        if st == "health_connect_heart_rate":
            rate = f"{int(v_num)} bpm" if v_num is not None else "Heart rate: no reported bpm"
            return rate + (f" ({v_text})" if v_text else "")
        if st == "health_connect_sleep":
            return f"Sleep: {int(v_num)} min" if v_num is not None else "Sleep: no reported duration"
        if st == "health_connect_spo2":
            return f"SpO2: {v_num}%" if v_num is not None else "SpO2: no reported percent"
        return "Unknown reading"
