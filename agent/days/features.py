"""One day's measured facts, from confirmed readings only.

No coordinates leave this function's result. A comparison is not a cause.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from zoneinfo import ZoneInfo

WINDOW_START = 6
WINDOW_HOURS = 18
FIX_COVER = timedelta(minutes=5)
POOR_ACCURACY_M = 200
OFFICE_MINUTES = 180
HOME_SHARE = 0.8
UNKNOWN_COVERAGE = 0.5


@dataclass(frozen=True)
class Place:
    kind: str
    lat: float
    lon: float
    radius_m: float = 150


@dataclass(frozen=True)
class Fix:
    at: datetime
    lat: float
    lon: float
    accuracy_m: float | None = None


@dataclass(frozen=True)
class Visit:
    start: datetime
    end: datetime
    lat: float | None
    lon: float | None
    semantic: str | None = None


@dataclass(frozen=True)
class Activity:
    start: datetime
    end: datetime
    mode: str
    start_lat: float | None = None
    start_lon: float | None = None
    end_lat: float | None = None
    end_lon: float | None = None


@dataclass(frozen=True)
class Usage:
    package: str
    seconds: int
    category: str | None = None


@dataclass(frozen=True)
class Sleep:
    start: datetime
    end: datetime
    minutes: int | None = None

@dataclass(frozen=True)
class Steps:
    count: int
    full_day: bool


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * radius * asin(sqrt(a))


def _place_kind(lat: float | None, lon: float | None, places: list[Place]) -> str | None:
    if lat is None or lon is None:
        return None
    nearest: tuple[float, str] | None = None
    for place in places:
        distance = haversine_m(lat, lon, place.lat, place.lon)
        if distance <= place.radius_m and (nearest is None or distance < nearest[0]):
            nearest = (distance, place.kind)
    return nearest[1] if nearest else None


def _window(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, WINDOW_START, tzinfo=zone)
    return start, start + timedelta(hours=WINDOW_HOURS)


def _clip(start: datetime, end: datetime, window: tuple[datetime, datetime]) -> tuple[datetime, datetime] | None:
    start, end = _aware(start), _aware(end)
    clipped = (max(start, window[0]), min(end, window[1]))
    return clipped if clipped[1] > clipped[0] else None


def _paint(spans: list[tuple[datetime, datetime, str, str | None]],
           start: datetime, end: datetime, label: str, mode: str | None) -> list[tuple[datetime, datetime, str, str | None]]:
    """Replace whatever a higher-priority span covers."""
    out: list[tuple[datetime, datetime, str, str | None]] = []
    for span_start, span_end, span_label, span_mode in spans:
        if end <= span_start or start >= span_end:
            out.append((span_start, span_end, span_label, span_mode))
            continue
        if span_start < start:
            out.append((span_start, start, span_label, span_mode))
        if span_end > end:
            out.append((end, span_end, span_label, span_mode))
    out.append((start, end, label, mode))
    out.sort(key=lambda item: item[0])
    return out


def _minutes(spans: list[tuple[datetime, datetime, str, str | None]], label: str) -> int:
    seconds = sum((end - start).total_seconds() for start, end, kind, _mode in spans if kind == label)
    return int(seconds // 60)


def category_for(package: str, override: str | None, android: str | None) -> str:
    """Owner override, then the phone's category, then other."""
    if override:
        return override
    if android:
        return android
    return "other"


def compute_day(
    *,
    day: date,
    zone: ZoneInfo,
    places: list[Place],
    fixes: list[Fix],
    visits: list[Visit],
    activities: list[Activity],
    usage: list[Usage],
    sleep: list[Sleep],
    steps: list[Steps],
    overrides: dict[str, str] | None = None,
) -> dict:
    """Measured facts for one calendar day. The result has no coordinates."""
    window = _window(day, zone)
    spans: list[tuple[datetime, datetime, str, str | None]] = [(window[0], window[1], "unknown", None)]
    ordered = sorted(fixes, key=lambda fix: _aware(fix.at))
    for index, fix in enumerate(ordered):
        if fix.accuracy_m is not None and fix.accuracy_m > POOR_ACCURACY_M:
            continue
        start = _aware(fix.at)
        if index + 1 < len(ordered):
            end = min(_aware(ordered[index + 1].at), start + FIX_COVER)
        else:
            end = start + FIX_COVER
        clipped = _clip(start, end, window)
        if clipped is None:
            continue
        kind = _place_kind(fix.lat, fix.lon, places) or "away"
        spans = _paint(spans, clipped[0], clipped[1], kind, None)
    for visit in visits:
        clipped = _clip(visit.start, visit.end, window)
        if clipped is None:
            continue
        kind = _place_kind(visit.lat, visit.lon, places) or "away"
        spans = _paint(spans, clipped[0], clipped[1], kind, None)
    commute_modes: list[tuple[int, str]] = []
    for activity in activities:
        start_kind = _place_kind(activity.start_lat, activity.start_lon, places)
        end_kind = _place_kind(activity.end_lat, activity.end_lon, places)
        ends = {start_kind, end_kind}
        if ends != {"home", "office"}:
            continue
        clipped = _clip(activity.start, activity.end, window)
        if clipped is None:
            continue
        spans = _paint(spans, clipped[0], clipped[1], "commute", activity.mode)
        commute_modes.append((int((clipped[1] - clipped[0]).total_seconds() // 60), activity.mode))
    known = sum((end - start).total_seconds() for start, end, kind, _mode in spans if kind != "unknown")
    window_seconds = WINDOW_HOURS * 3600
    coverage = known / window_seconds if window_seconds else 0.0
    home = _minutes(spans, "home")
    office = _minutes(spans, "office")
    commute = _minutes(spans, "commute")
    if coverage < UNKNOWN_COVERAGE:
        day_kind = "unknown"
    elif office >= OFFICE_MINUTES:
        day_kind = "office"
    elif known and home / (known / 60) >= HOME_SHARE:
        day_kind = "home"
    else:
        day_kind = "other"
    category_seconds: dict[str, int] = {}
    screen_seconds = 0
    for item in usage:
        if item.seconds <= 0:
            continue
        screen_seconds += item.seconds
        label = category_for(item.package, (overrides or {}).get(item.package), item.category)
        category_seconds[label] = category_seconds.get(label, 0) + item.seconds
    by_category = {label: seconds // 60 for label, seconds in category_seconds.items()}
    sleep_minutes = 0
    saw_sleep = False
    for item in sleep:
        end = _aware(item.end)
        if end.astimezone(zone).date() != day:
            continue
        saw_sleep = True
        sleep_minutes += max(0, item.minutes if item.minutes is not None else int((end - _aware(item.start)).total_seconds() // 60))
    step_count = sum(item.count for item in steps)
    full_day = bool(steps) and all(item.full_day for item in steps)
    mode = max(commute_modes, key=lambda item: item[0])[1] if commute_modes else None
    return {
        "day": day.isoformat(),
        "day_kind": day_kind,
        "home_minutes": home,
        "office_minutes": office,
        "commute_minutes": commute,
        "commute_mode": mode,
        "steps": step_count if steps else None,
        "steps_full_day": full_day,
        "screen_minutes": screen_seconds // 60,
        "screen_by_category": by_category,
        "sleep_minutes": sleep_minutes if saw_sleep else None,
        "location_coverage": round(coverage, 4),
    }
