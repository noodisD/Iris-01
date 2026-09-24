"""A decision journal, written when a decision is made.

Kept out of `agent/database.py` for the same reason the import staging is: it
is one small feature with one table, which nothing else reads, and it should be
possible to read, and later remove, in one place.

It is deliberately not a journal entry. A reflection is writing that the
engines read for themes; this is a handful of answers to a form. Mixing the two
would put structured answers into the text the theme engines embed, and put a
free-text line where a choice was needed. Nothing here is sent to a model or
embedded.

The questions are the ones looking back through the archive could not answer,
asked of any kind of decision: what is at stake and whether it can be undone,
how sure the owner is, what the days before held, what is pushing for a
decision now, sleep, energy and feeling, and what would make them stop. Later:
how it went, whether the plan was kept, and whether they would decide the same
again — which is not the same question as whether it went well.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .database import db

STAKES = ("little", "fair", "a_lot", "beyond_means")
REVERSIBLE = ("easily", "at_a_cost", "not_at_all")
LAST_DAYS = ("setback", "success", "neither")
PRESSURES = ("deadline", "money", "people", "urge")
FEELINGS = ("calm", "excited", "anxious", "frustrated")
FOLLOWED = ("yes", "partly", "no")
WOULD_REPEAT = ("yes", "no", "unsure")

_COLUMNS = ("id", "decided_on", "created_at", "what", "stake", "reversible",
            "confidence", "last_days", "pressures", "sleep_hours", "energy",
            "feeling", "plan", "outcome", "followed_plan", "would_repeat", "closed_at")
_SELECT = ", ".join(_COLUMNS)


def _row(values: tuple) -> dict[str, Any]:
    return dict(zip(_COLUMNS, values, strict=True))


def create(user_id: int, *, what: str, decided_on: date | None = None,
           stake: str | None = None, reversible: str | None = None,
           confidence: int | None = None, last_days: str | None = None,
           pressures: list[str] | None = None, sleep_hours: float | None = None,
           energy: int | None = None, feeling: str | None = None,
           plan: str | None = None) -> dict[str, Any]:
    """Record one decision as it is made. The table's checks are the last word
    on what is allowed; the API validates first so a bad value is a 422 with a
    reason rather than a database error."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO decisions
                  (user_id, decided_on, what, stake, reversible, confidence, last_days,
                   pressures, sleep_hours, energy, feeling, plan)
                VALUES (%s, COALESCE(%s, CURRENT_DATE), %s, %s, %s, %s, %s,
                        %s::TEXT[], %s, %s, %s, %s)
                RETURNING {_SELECT};""",
            (user_id, decided_on, what.strip(), stake, reversible, confidence, last_days,
             sorted(set(pressures or [])), sleep_hours, energy, feeling, _blank_to_none(plan)),
        )
        row = _row(cur.fetchone())
        conn.commit()
        return row


def list_for(user_id: int, limit: int = 200) -> list[dict[str, Any]]:
    """Newest first: by the day the decision was made, then as entered."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""SELECT {_SELECT} FROM decisions WHERE user_id = %s
                ORDER BY decided_on DESC, id DESC LIMIT %s;""",
            (user_id, limit),
        )
        return [_row(r) for r in cur.fetchall()]


def record_outcome(user_id: int, decision_id: int, *, outcome: str,
                   followed_plan: str | None,
                   would_repeat: str | None) -> dict[str, Any] | None:
    """How it went, whether the plan was kept, and whether the owner would
    decide the same again. None if there is no such decision for this user.
    Recording it again corrects it; the first closing time is kept, so a
    correction does not move the day it ended."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""UPDATE decisions
                   SET outcome = %s, followed_plan = %s, would_repeat = %s,
                       closed_at = COALESCE(closed_at, now())
                 WHERE id = %s AND user_id = %s
             RETURNING {_SELECT};""",
            (outcome.strip(), followed_plan, would_repeat, decision_id, user_id),
        )
        found = cur.fetchone()
        conn.commit()
        return _row(found) if found else None


def _blank_to_none(text: str | None) -> str | None:
    if text is None:
        return None
    return text.strip() or None
