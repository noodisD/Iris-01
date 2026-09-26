"""The on-device Google Maps Timeline export.

Visits become ``timeline_visit``. Trips become ``timeline_activity``.
Coordinate strings are parsed strictly: a degree pair or a ``geo:`` URI, or
nothing. A bad segment is dropped, not repaired.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from .adapters import _payload_hash, register, to_timestamp

_DEGREE = re.compile(r"^(-?\d+(?:\.\d+)?)°,\s*(-?\d+(?:\.\d+)?)°$")
_GEO = re.compile(r"^geo:(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)$")


def parse_latlng(value: object) -> tuple[float, float] | None:
    """A coordinate pair, or None. Never a guess."""
    if isinstance(value, dict):
        value = value.get("latLng")
    if not isinstance(value, str):
        return None
    text = value.strip()
    match = _DEGREE.fullmatch(text) or _GEO.fullmatch(text)
    if match is None:
        return None
    lat, lon = float(match.group(1)), float(match.group(2))
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return lat, lon


def semantic_type(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    token = value.strip().upper().removeprefix("TYPE_")
    if token in {"HOME", "WORK"}:
        return token
    return "OTHER"


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value == value else None
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if parsed == parsed else None
    return None


def _candidate(block: dict[str, Any]) -> dict[str, Any]:
    top = block.get("topCandidate")
    return top if isinstance(top, dict) else block


def _segment(segment: object) -> dict[str, Any] | None:
    if not isinstance(segment, dict):
        return None
    start = segment.get("startTime") or segment.get("start_time")
    end = segment.get("endTime") or segment.get("end_time")
    if not start:
        return None
    try:
        started = to_timestamp(str(start))
        ended = to_timestamp(str(end)) if end else None
        if ended is not None and started is not None and ended <= started:
            return None
    except (TypeError, ValueError):
        return None
    visit = segment.get("visit")
    activity = segment.get("activity")
    if isinstance(visit, dict):
        return _visit(str(start), str(end) if end else None, visit)
    if isinstance(activity, dict):
        return _activity(str(start), str(end) if end else None, activity)
    return None


def _visit(start: str, end: str | None, visit: dict[str, Any]) -> dict[str, Any] | None:
    candidate = _candidate(visit)
    kind = semantic_type(candidate.get("semanticType") or candidate.get("semantic_type"))
    location = candidate.get("placeLocation") or candidate.get("location")
    coords = parse_latlng(location)
    if location is not None and coords is None:
        return None
    if kind is None and coords is None:
        return None
    raw = {"start": start, "end": end, "semantic": kind, "coords": coords}
    obs: dict[str, Any] = {
        "source_type": "timeline_visit",
        "occurred_at": start,
        "ended_at": end,
        "value_text": kind,
        "payload_hash": _payload_hash("timeline_visit", start, {"raw": raw}),
        "detail": {"semantic_type": kind} if kind else {},
    }
    if coords is not None:
        obs["lat"], obs["lon"] = coords
    return obs


def _activity(start: str, end: str | None, activity: dict[str, Any]) -> dict[str, Any] | None:
    candidate = _candidate(activity)
    mode = candidate.get("type") or activity.get("activityType") or activity.get("type")
    if not isinstance(mode, str) or not mode.strip():
        return None
    distance = _number(activity.get("distanceMeters") or activity.get("distance"))
    if ((activity.get("start") is not None and parse_latlng(activity["start"]) is None) or
            (activity.get("end") is not None and parse_latlng(activity["end"]) is None)):
        return None
    start_point = parse_latlng(activity.get("start"))
    end_point = parse_latlng(activity.get("end"))
    raw = {"start": start, "end": end, "mode": mode, "distance": distance}
    detail: dict[str, Any] = {"mode": mode.strip().upper()}
    if start_point:
        detail["start_lat"], detail["start_lon"] = start_point
    if end_point:
        detail["end_lat"], detail["end_lon"] = end_point
    return {
        "source_type": "timeline_activity",
        "occurred_at": start,
        "ended_at": end,
        "value_text": mode.strip().upper(),
        "value_num": distance,
        "payload_hash": _payload_hash("timeline_activity", start, {"raw": raw}),
        "detail": detail,
    }


def segments_of(data: object) -> list[object] | None:
    """The segment list, or None when this document is not a Timeline export."""
    if isinstance(data, dict) and isinstance(data.get("semanticSegments"), list):
        return data["semanticSegments"]
    if isinstance(data, list):
        return data
    return None


def parse_timeline(data: object) -> dict[str, Any]:
    segments = segments_of(data)
    if segments is None:
        raise ValueError("not a Timeline export")
    observations: list[dict[str, Any]] = []
    dropped = 0
    for segment in segments:
        obs = _segment(segment)
        if obs is None:
            dropped += 1
        else:
            observations.append(obs)
    raw = json.dumps(data, sort_keys=True, default=str).encode()
    return {
        "source": "google_timeline",
        "raw_payload_hash": hashlib.sha256(raw).hexdigest(),
        "device_clock": None,
        "observations": observations,
        "dropped_count": dropped,
    }


@register("google_timeline")
class GoogleTimelineAdapter:
    """Registered so a staged Timeline batch is described like any other source."""

    def parse_from_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        return parse_timeline(data)


def describe_timeline(obs: dict[str, Any]) -> str | None:
    source = obs.get("source_type")
    if source == "timeline_visit":
        kind = obs.get("value_text") or "visit"
        return f"Visit: {kind}"
    if source == "timeline_activity":
        mode = obs.get("value_text") or "trip"
        distance = obs.get("value_num")
        if isinstance(distance, (int, float)):
            return f"Trip: {mode}, {int(distance)} m"
        return f"Trip: {mode}"
    return None


def day_of(value: object) -> datetime | None:
    try:
        return to_timestamp(value) if value else None
    except (TypeError, ValueError):
        return None


def stage_export(raw: bytes) -> dict:
    """Stage a Timeline file, one pending batch per day it covers."""
    import json
    from collections import defaultdict

    from agent.sensors.repository import SensorRepository

    if not raw:
        raise ValueError("empty timeline export")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("timeline export is not JSON") from exc
    parsed = parse_timeline(data)
    by_day: dict = defaultdict(list)
    for obs in parsed["observations"]:
        started = day_of(obs.get("occurred_at"))
        if started is None:
            parsed["dropped_count"] += 1
            continue
        by_day[started.date()].append(obs)
    repo = SensorRepository()
    digest = parsed["raw_payload_hash"]
    batch_ids = []
    for day, observations in sorted(by_day.items()):
        batch = {**parsed, "observations": observations, "dropped_count": 0}
        batch_ids.append(repo.stage_delivery(
            batch,
            delivery_key=f"timeline:{digest}:{day.isoformat()}",
            review_day=day,
            clock_skew_seconds=None,
        ))
    return {
        "batches": batch_ids,
        "observations": sum(len(items) for items in by_day.values()),
        "dropped": parsed["dropped_count"],
    }
