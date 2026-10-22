"""What is waiting on the owner? Not failures: decisions only they can make.

Twenty thousand phone readings waited two weeks for a confirmation nobody was
reminded of, and the phone had stopped sending without anyone noticing. These
checks report as "waiting", so they are seen without being mistaken for faults.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..database import db
from . import Result, check

#: The phone sends many times a day; this long without a delivery means it stopped.
PHONE_SILENT_DAYS = 2


def _one(sql: str, *args):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchone()


def _days_since(value) -> float | None:
    return None if value is None else (datetime.now(UTC) - value).total_seconds() / 86400


def _waiting(id: str, count: int, ok: str, waiting: str, action: str, **details) -> Result:
    if not count:
        return Result(id, "ok", ok, value=0, details=details)
    return Result(id, "waiting", waiting, value=count, action=action, action_class="needs-owner",
                  details=details)


@check("owner.sensor_batches", "owner")
def sensor_batches() -> Result:
    count, oldest, readings = _one("""SELECT count(*), min(received_at), coalesce(sum(observation_count), 0)
                                        FROM sensor_batches WHERE status = 'pending'""")
    days = _days_since(oldest)
    return _waiting("owner.sensor_batches", count, "No phone batches are waiting.",
                    f"{count} phone batch(es), {readings} readings, waiting for confirmation"
                    + (f"; the oldest {days:.0f} days" if days is not None else "") + ".",
                    "Review them on the Sensors screen; nothing counts until confirmed.",
                    oldest_days=round(days, 1) if days is not None else None)


@check("owner.phone_silent", "owner")
def phone_silent() -> Result:
    paired = _one("SELECT count(*) FROM mobile_pairing")[0]
    if not paired:
        return Result("owner.phone_silent", "ok", "No phone is paired.", value=0)
    last = _one("SELECT max(received_at) FROM sensor_deliveries")[0]
    days = _days_since(last)
    if days is None or days > PHONE_SILENT_DAYS:
        return Result("owner.phone_silent", "waiting",
                      "The paired phone has never sent readings." if days is None
                      else f"The paired phone has sent nothing for {days:.0f} days.",
                      value=round(days, 1) if days is not None else None,
                      expected=f"a delivery within {PHONE_SILENT_DAYS} days",
                      causes=["The app's collection was stopped by a reboot or update (it needs a tap).",
                              "The laptop's address changed, or the phone is off the home network or Tailscale."],
                      action="Open the IRIS app on the phone and resume collection; re-scan the address QR "
                             "if the laptop's address changed.", action_class="needs-owner")
    return Result("owner.phone_silent", "ok", f"The phone last sent {days * 24:.0f} h ago.", value=round(days, 1))


@check("owner.ideas_review", "owner")
def ideas_review() -> Result:
    ideas = _one("SELECT count(*) FROM ideas WHERE status = 'candidate'")[0]
    quotes = _one("""SELECT count(*) FROM idea_citations c JOIN ideas i ON i.id = c.idea_id
                      WHERE c.status = 'candidate' AND i.status = 'candidate'""")[0]
    return _waiting("owner.ideas_review", ideas, "No proposed ideas are waiting.",
                    f"{ideas} proposed idea(s) wait in Review.",
                    "Accept, reject or edit them on the Ideas screen (Review).", quotes=quotes)


@check("owner.questionnaire", "owner")
def questionnaire() -> Result:
    drafts = _one("SELECT count(*) FROM questionnaire_answers WHERE status = 'draft'")[0]
    return _waiting("owner.questionnaire", drafts, "No questionnaire drafts are waiting to be added.",
                    f"{drafts} questionnaire draft(s) are not yet added to IRIS.",
                    "Add their section on the Questionnaire screen, or discard them.")


@check("owner.sessions", "owner")
def sessions_staged() -> Result:
    staged = _one("""SELECT count(*) FROM session_imports
                      WHERE status = 'staged' AND reflection_id IS NULL""")[0]
    return _waiting("owner.sessions", staged, "No therapy session is waiting to be imported.",
                    f"{staged} therapy session(s) are staged but not imported.",
                    "Finish them on the Import screen (Therapy sessions), or discard them.")


@check("owner.constructs", "owner")
def constructs() -> Result:
    candidates = _one("SELECT count(*) FROM themes WHERE status = 'candidate'")[0]
    return _waiting("owner.constructs", candidates, "No noticed constructs are waiting.",
                    f"{candidates} construct(s) noticed by reading wait to be confirmed or rejected.",
                    "Review them on the Constructs screen.")
