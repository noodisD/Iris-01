"""Rebuild the day cache after a confirmation, a rejection, or a place change."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from psycopg2.extras import Json

from agent.database import db

from .features import Activity, Fix, Place, Sleep, Steps, Usage, Visit, compute_day
from .places import list_categories, list_places


def recompute(user_id: int, days: list[date] | None = None) -> list[date]:
    """Rewrite day features for these days, or every day with a confirmed reading.

    A day with nothing confirmed left is removed, so a rejected batch cannot
    keep a label it no longer supports.
    """
    zone = _zone(user_id)
    wanted = set(days) if days is not None else None
    places = [
        Place(kind=row["kind"], lat=row["lat"], lon=row["lon"], radius_m=row["radiusM"])
        for row in list_places(user_id)
    ]
    overrides = {row["package"]: row["category"] for row in list_categories(user_id)}
    rows = _confirmed(user_id)
    by_day = _group(rows, zone, wanted)
    if wanted is None:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT day FROM day_features WHERE user_id = %s", (user_id,))
            for (day,) in cur.fetchall():
                by_day.setdefault(day, [])
    if wanted is not None:
        for day in wanted:
            by_day.setdefault(day, [])
    written: list[date] = []
    with db.connection() as conn, conn.cursor() as cur:
        for day, items in sorted(by_day.items()):
            if not items:
                cur.execute(
                    "DELETE FROM day_features WHERE user_id = %s AND day = %s",
                    (user_id, day),
                )
                continue
            features = compute_day(
                day=day, zone=zone, places=places,
                fixes=_fixes(items), visits=_visits(items), activities=_activities(items),
                usage=_usage(items, day, zone), sleep=_sleep(items),
                steps=_steps(items, day, zone), overrides=overrides,
            )
            _upsert(cur, user_id, day, features)
            written.append(day)
        conn.commit()
    return written




def list_days(user_id: int) -> list[dict]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT day, day_kind, home_minutes, office_minutes, commute_minutes,
                      commute_mode, steps, steps_full_day, screen_minutes,
                      screen_by_category, sleep_minutes, location_coverage
                 FROM day_features WHERE user_id = %s ORDER BY day DESC""",
            (user_id,),
        )
        return [_day(row) for row in cur.fetchall()]


def _host_zone() -> ZoneInfo:
    """Resolve the host's IANA name, not its current fixed-offset tzinfo."""
    candidates = [os.environ.get("TZ", "").lstrip(":")]
    localtime = Path("/etc/localtime").resolve()
    marker = "/zoneinfo/"
    if marker in str(localtime):
        candidates.append(str(localtime).split(marker, 1)[1])
    try:
        candidates.append(Path("/etc/timezone").read_text(encoding="utf-8").strip())
    except OSError:
        pass
    for name in candidates:
        try:
            return ZoneInfo(name)
        except (KeyError, ValueError):
            continue
    return ZoneInfo("UTC")


def _zone(user_id: int) -> ZoneInfo:
    settings = db.get_app_settings(user_id) or {}
    name = settings.get("timezone")
    if name and name != "UTC":
        try:
            return ZoneInfo(name)
        except (KeyError, ValueError):
            pass
    return _host_zone()


def _confirmed(user_id: int) -> list[dict]:
    # Older, untagged batches belong to the single local owner. New reviews
    # record their owner so other users in the database never inherit a day.
    legacy_owner = user_id == db.local_user_id()
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT o.source_type, o.occurred_at, o.ended_at, o.value_num, o.value_text,
                      o.lat, o.lon, o.accuracy_m, o.detail, o.occurred_date
                 FROM sensor_observations o
                 JOIN sensor_batches b ON b.id = o.batch_id
                WHERE b.status = 'confirmed'
                  AND (b.parsed_payload ->> 'day_owner_user_id' = %s
                       OR (b.parsed_payload ->> 'day_owner_user_id' IS NULL AND %s))""",
            (str(user_id), legacy_owner),
        )
        keys = ("source_type", "occurred_at", "ended_at", "value_num", "value_text",
                "lat", "lon", "accuracy_m", "detail", "occurred_date")
        return [dict(zip(keys, row)) for row in cur.fetchall()]


def _local_day(value: datetime | None, zone: ZoneInfo) -> date | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(zone).date()


def _group(rows: list[dict], zone: ZoneInfo, wanted: set[date] | None) -> dict[date, list[dict]]:
    grouped: dict[date, list[dict]] = {}
    for row in rows:
        # The phone's step counter sends a calendar date, not an instant.
        if row["source_type"] == "pixel_steps" and row["occurred_date"]:
            day = row["occurred_date"]
            if wanted is None or day in wanted:
                grouped.setdefault(day, []).append(row)
            continue
        started = _local_day(row["occurred_at"], zone)
        ended = _local_day(row["ended_at"], zone)
        if started:
            last = ended if ended and ended >= started else started
            day = started
            while day <= last:
                if wanted is None or day in wanted:
                    grouped.setdefault(day, []).append(row)
                day += timedelta(days=1)
        elif row["occurred_date"]:
            day = row["occurred_date"]
            if wanted is None or day in wanted:
                grouped.setdefault(day, []).append(row)
    return grouped


def _fixes(items: list[dict]) -> list[Fix]:
    return [
        Fix(row["occurred_at"], row["lat"], row["lon"], row["accuracy_m"])
        for row in items
        if row["source_type"] == "pixel_location" and row["occurred_at"]
        and row["lat"] is not None and row["lon"] is not None
    ]


def _visits(items: list[dict]) -> list[Visit]:
    found = []
    for row in items:
        if row["source_type"] != "timeline_visit" or not row["occurred_at"]:
            continue
        end = row["ended_at"] or (row["occurred_at"] + timedelta(minutes=1))
        found.append(Visit(row["occurred_at"], end, row["lat"], row["lon"], row["value_text"]))
    return found


def _activities(items: list[dict]) -> list[Activity]:
    found = []
    for row in items:
        if row["source_type"] != "timeline_activity" or not row["occurred_at"] or not row["ended_at"]:
            continue
        detail = row["detail"] if isinstance(row["detail"], dict) else {}
        found.append(Activity(
            row["occurred_at"], row["ended_at"], row["value_text"] or "trip",
            detail.get("start_lat"), detail.get("start_lon"),
            detail.get("end_lat"), detail.get("end_lon"),
        ))
    return found


def _usage(items: list[dict], day: date, zone: ZoneInfo) -> list[Usage]:
    found = []
    for row in items:
        if row["source_type"] != "pixel_app_usage":
            continue
        if _local_day(row["occurred_at"], zone) != day and row["occurred_date"] != day:
            continue
        detail = row["detail"] if isinstance(row["detail"], dict) else {}
        found.append(Usage(
            row["value_text"] or "",
            int(row["value_num"] or 0),
            detail.get("category"),
        ))
    return found


def _sleep(items: list[dict]) -> list[Sleep]:
    found = []
    for row in items:
        if row["source_type"] != "health_connect_sleep" or not row["occurred_at"]:
            continue
        minutes = max(0, int(row["value_num"] or 0))
        end = row["ended_at"] or row["occurred_at"]
        start = row["occurred_at"] if row["ended_at"] else end - timedelta(minutes=minutes)
        found.append(Sleep(start, end, minutes))
    return found


def _steps(items: list[dict], day: date, zone: ZoneInfo) -> list[Steps]:
    found = []
    for row in items:
        if row["source_type"] != "pixel_steps":
            continue
        if _local_day(row["occurred_at"], zone) != day and row["occurred_date"] != day:
            continue
        partial = row["value_text"] == "recorded while IRIS was running"
        found.append(Steps(int(row["value_num"] or 0), not partial))
    return found


def _upsert(cur, user_id: int, day: date, features: dict) -> None:
    cur.execute(
        """INSERT INTO day_features (
               user_id, day, day_kind, home_minutes, office_minutes, commute_minutes,
               commute_mode, steps, steps_full_day, screen_minutes, screen_by_category,
               sleep_minutes, location_coverage)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (user_id, day) DO UPDATE SET
               day_kind = EXCLUDED.day_kind,
               home_minutes = EXCLUDED.home_minutes,
               office_minutes = EXCLUDED.office_minutes,
               commute_minutes = EXCLUDED.commute_minutes,
               commute_mode = EXCLUDED.commute_mode,
               steps = EXCLUDED.steps,
               steps_full_day = EXCLUDED.steps_full_day,
               screen_minutes = EXCLUDED.screen_minutes,
               screen_by_category = EXCLUDED.screen_by_category,
               sleep_minutes = EXCLUDED.sleep_minutes,
               location_coverage = EXCLUDED.location_coverage""",
        (user_id, day, features["day_kind"], features["home_minutes"], features["office_minutes"],
         features["commute_minutes"], features["commute_mode"], features["steps"],
         features["steps_full_day"], features["screen_minutes"], Json(features["screen_by_category"]),
         features["sleep_minutes"], features["location_coverage"]),
    )


def _day(row: tuple) -> dict:
    return {
        "day": row[0].isoformat(),
        "dayKind": row[1],
        "homeMinutes": row[2],
        "officeMinutes": row[3],
        "commuteMinutes": row[4],
        "commuteMode": row[5],
        "steps": row[6],
        "stepsFullDay": row[7],
        "screenMinutes": row[8],
        "screenByCategory": row[9] or {},
        "sleepMinutes": row[10],
        "locationCoverage": row[11],
    }
