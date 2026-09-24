"""A log of risky commitments, written when one is made.

Kept out of `agent/database.py` for the same reason the import staging is: it
is one small feature with one table, which nothing else reads, and it should be
possible to read, and later remove, in one place.

It is deliberately not a journal entry. A reflection is writing that the
engines read for themes; this is a handful of facts recorded against a form.
Mixing the two would put structured answers into the text the theme engines
embed, and put a free-text journal line where a number was needed. Nothing
here is sent to a model or embedded.

The fields are the ones looking back through the archive could not recover:
how much was at stake as a share of what the owner had, whether any of it was
borrowed, what the days before held, money needed soon, sleep and energy, and
the plan, then later what happened and whether the plan was kept.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .database import db

LAST_DAYS = ("big_loss", "big_win", "neither")
FOLLOWED = ("yes", "partly", "no")

_COLUMNS = ("id", "decided_on", "created_at", "what", "share_pct", "borrowed",
            "last_days", "money_needed_for", "money_needed_by", "sleep_hours",
            "energy", "plan", "outcome", "followed_plan", "closed_at")
_SELECT = ", ".join(_COLUMNS)


def _row(values: tuple) -> dict[str, Any]:
    return dict(zip(_COLUMNS, values, strict=True))


def create(user_id: int, *, what: str, decided_on: date | None = None,
           share_pct: float | None = None, borrowed: bool = False,
           last_days: str | None = None, money_needed_for: str | None = None,
           money_needed_by: date | None = None, sleep_hours: float | None = None,
           energy: int | None = None, plan: str | None = None) -> dict[str, Any]:
    """Record one commitment as it is made. The table's checks are the last word
    on what is allowed; the API validates first so a bad value is a 422 with a
    reason rather than a database error."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO decisions
                  (user_id, decided_on, what, share_pct, borrowed, last_days,
                   money_needed_for, money_needed_by, sleep_hours, energy, plan)
                VALUES (%s, COALESCE(%s, CURRENT_DATE), %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING {_SELECT};""",
            (user_id, decided_on, what.strip(), share_pct, borrowed, last_days,
             _blank_to_none(money_needed_for), money_needed_by, sleep_hours,
             energy, _blank_to_none(plan)),
        )
        row = _row(cur.fetchone())
        conn.commit()
        return row


def list_for(user_id: int, limit: int = 200) -> list[dict[str, Any]]:
    """Newest first: by the day the commitment was made, then as entered."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""SELECT {_SELECT} FROM decisions WHERE user_id = %s
                ORDER BY decided_on DESC, id DESC LIMIT %s;""",
            (user_id, limit),
        )
        return [_row(r) for r in cur.fetchall()]


def record_outcome(user_id: int, decision_id: int, *, outcome: str,
                   followed_plan: str | None) -> dict[str, Any] | None:
    """What happened, and whether the plan was kept. None if there is no such
    decision for this user. Recording it again corrects it; the first closing
    time is kept, so a correction does not move the day it ended."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""UPDATE decisions
                   SET outcome = %s, followed_plan = %s,
                       closed_at = COALESCE(closed_at, now())
                 WHERE id = %s AND user_id = %s
             RETURNING {_SELECT};""",
            (outcome.strip(), followed_plan, decision_id, user_id),
        )
        found = cur.fetchone()
        conn.commit()
        return _row(found) if found else None


def _blank_to_none(text: str | None) -> str | None:
    if text is None:
        return None
    return text.strip() or None
