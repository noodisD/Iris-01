"""Named places. Coordinates stay in this table and never go to the phone."""

from __future__ import annotations

from math import isfinite
from typing import Any

from agent.database import db

KINDS = ("home", "office", "other")
SOURCES = ("owner", "timeline")


def list_places(user_id: int) -> list[dict[str, Any]]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id, name, kind, lat, lon, radius_m, source
                 FROM places WHERE user_id = %s ORDER BY name""",
            (user_id,),
        )
        return [_place(row) for row in cur.fetchall()]


def create_place(user_id: int, *, name: str, kind: str, lat: float, lon: float,
                 radius_m: int = 150, source: str = "owner") -> dict[str, Any]:
    _check(name, kind, lat, lon, radius_m, source)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO places (user_id, name, kind, lat, lon, radius_m, source)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id, name, kind, lat, lon, radius_m, source""",
            (user_id, name.strip(), kind, lat, lon, radius_m, source),
        )
        row = cur.fetchone()
        conn.commit()
    return _place(row)


def update_place(user_id: int, place_id: int, **fields: Any) -> dict[str, Any] | None:
    allowed = {"name", "kind", "lat", "lon", "radius_m"}
    changes = {key: value for key, value in fields.items() if key in allowed and value is not None}
    if not changes:
        return get_place(user_id, place_id)
    current = get_place(user_id, place_id)
    if current is None:
        return None
    merged = {**current, **changes}
    _check(merged["name"], merged["kind"], merged["lat"], merged["lon"], merged["radius_m"], merged["source"])
    assignments = ", ".join(f"{key} = %s" for key in changes)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""UPDATE places SET {assignments}
                 WHERE id = %s AND user_id = %s
                 RETURNING id, name, kind, lat, lon, radius_m, source""",
            (*changes.values(), place_id, user_id),
        )
        row = cur.fetchone()
        conn.commit()
    return _place(row) if row else None


def remove_place(user_id: int, place_id: int) -> bool:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM places WHERE id = %s AND user_id = %s", (place_id, user_id))
        removed = cur.rowcount > 0
        conn.commit()
    return removed


def get_place(user_id: int, place_id: int) -> dict[str, Any] | None:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id, name, kind, lat, lon, radius_m, source
                 FROM places WHERE id = %s AND user_id = %s""",
            (place_id, user_id),
        )
        row = cur.fetchone()
    return _place(row) if row else None


def suggest_from_timeline(user_id: int) -> dict[str, dict[str, float] | None]:
    """Time-weighted centre of confirmed HOME and WORK visits.

    The weight is the visit's duration. A visit with no end counts as one minute.
    """
    legacy_owner = user_id == db.local_user_id()
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT o.value_text, o.lat, o.lon,
                      EXTRACT(EPOCH FROM (COALESCE(o.ended_at, o.occurred_at + interval '1 minute')
                                          - o.occurred_at))
                 FROM sensor_observations o
                 JOIN sensor_batches b ON b.id = o.batch_id
                WHERE b.status = 'confirmed'
                  AND (b.parsed_payload ->> 'day_owner_user_id' = %s
                       OR (b.parsed_payload ->> 'day_owner_user_id' IS NULL AND %s))
                  AND o.source_type = 'timeline_visit'
                  AND o.value_text IN ('HOME', 'WORK')
                  AND o.lat IS NOT NULL AND o.lon IS NOT NULL
                  AND o.occurred_at IS NOT NULL""",
            (str(user_id), legacy_owner),
        )
        rows = cur.fetchall()
    return {
        "home": _centre(rows, "HOME"),
        "office": _centre(rows, "WORK"),
    }


def set_category(user_id: int, package: str, category: str) -> None:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO app_categories (user_id, package, category)
               VALUES (%s, %s, %s)
               ON CONFLICT (user_id, package) DO UPDATE SET category = EXCLUDED.category""",
            (user_id, package.strip(), category.strip()),
        )
        conn.commit()


def list_categories(user_id: int) -> list[dict[str, str]]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT package, category FROM app_categories
                WHERE user_id = %s ORDER BY package""",
            (user_id,),
        )
        return [{"package": row[0], "category": row[1]} for row in cur.fetchall()]


def _centre(rows: list[tuple], kind: str) -> dict[str, float] | None:
    chosen = [(lat, lon, max(float(weight or 0), 60.0)) for label, lat, lon, weight in rows if label == kind]
    total = sum(weight for _lat, _lon, weight in chosen)
    if not chosen or total <= 0:
        return None
    return {
        "lat": sum(lat * weight for lat, _lon, weight in chosen) / total,
        "lon": sum(lon * weight for _lat, lon, weight in chosen) / total,
    }


def _place(row: tuple) -> dict[str, Any]:
    return {
        "id": row[0], "name": row[1], "kind": row[2], "lat": row[3], "lon": row[4],
        "radiusM": row[5], "source": row[6],
    }


def _check(name: str, kind: str, lat: float, lon: float, radius_m: int, source: str) -> None:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("a place needs a name")
    if kind not in KINDS:
        raise ValueError("kind must be home, office, or other")
    if source not in SOURCES:
        raise ValueError("source must be owner or timeline")
    if not (isfinite(float(lat)) and isfinite(float(lon))
            and -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180):
        raise ValueError("coordinates are out of range")
    if int(radius_m) <= 0:
        raise ValueError("radius must be positive")
