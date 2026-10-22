"""The doctor: checkable promises IRIS makes about itself, for an agent to read.

The Observatory answers "is something failing right now?". What actually went
wrong in practice failed quietly: memory search compared one memory in a
hundred, a pattern update restarted three times without anyone seeing it, a
read failed on every retry under a generic name. None of that raised an error.
Each check here states what should be true, measures it, and says what to do
when it is not, in a form an agent coming in cold can act on.

A check returns counts, timings and ids, never what anyone wrote: the report is
read by agents and may be pasted anywhere.

    uv run python -m agent.doctor            # run, store, and show what changed
    uv run python -m agent.doctor --json     # the whole report, for tools
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)

Status = Literal["ok", "warn", "fail", "waiting", "unknown"]
#: What an agent may do about it without asking (see docs/runbooks/README.md).
Action = Literal["read-only", "safe-auto", "needs-owner", "guarded"]
ORDER = {"fail": 0, "warn": 1, "waiting": 2, "unknown": 3, "ok": 4}


@dataclass
class Result:
    id: str
    status: Status
    summary: str
    value: float | None = None
    expected: str | None = None
    #: The query that reproduces it, returning counts or ids only.
    evidence: str | None = None
    causes: list[str] = field(default_factory=list)
    action: str | None = None
    action_class: Action = "read-only"
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def runbook(self) -> str:
        return f"docs/runbooks/{self.id}.md"


@dataclass
class Check:
    id: str
    area: str
    run: Callable[[], Result]


CHECKS: list[Check] = []


def check(id: str, area: str):
    """Register a check. Its function takes nothing and returns a Result."""
    def register(fn: Callable[[], Result]) -> Callable[[], Result]:
        CHECKS.append(Check(id, area, fn))
        return fn
    return register


def _load() -> None:
    # Imported for their registrations.
    from . import (checks_data, checks_docs, checks_moving, checks_owner,  # noqa: F401
                   checks_quality, checks_resources)


def run(only: set[str] | None = None) -> list[dict]:
    """Every check, worst first. A check that raises is reported, not hidden."""
    _load()
    results = []
    for item in CHECKS:
        if only and item.area not in only and item.id not in only:
            continue
        began = time.monotonic()
        try:
            result = item.run()
        except Exception as exc:
            result = Result(item.id, "unknown", f"The check itself failed: {type(exc).__name__}.",
                            causes=["A bug in the check, or the database is unreachable."])
            logger.warning(f"Doctor check {item.id} raised {type(exc).__name__}: {exc}")
        row = asdict(result)
        row["area"] = item.area
        row["runbook"] = result.runbook
        row["ms"] = round((time.monotonic() - began) * 1000)
        results.append(row)
    results.sort(key=lambda r: (ORDER[r["status"]], r["id"]))
    return results


def store(results: list[dict]) -> str:
    """Keep this run, so the next one can say what changed."""
    from psycopg2.extras import Json

    from ..database import db

    run_id = str(uuid.uuid4())
    with db.connection() as conn, conn.cursor() as cur:
        for r in results:
            cur.execute("""INSERT INTO health_checks (run_id, check_id, status, value, details)
                           VALUES (%s, %s, %s, %s, %s)""",
                        (run_id, r["id"], r["status"], r["value"],
                         Json({"summary": r["summary"], "expected": r["expected"]})))
        conn.commit()
    return run_id


def changes(results: list[dict], run_id: str | None = None) -> list[dict]:
    """What is different from the run before: new failures first, then the rest."""
    import psycopg2

    from ..database import db

    try:
        return _changes(results, run_id, db)
    except psycopg2.errors.UndefinedTable:
        return []  # Before migration 0053: nothing to compare with.


def _changes(results: list[dict], run_id: str | None, db) -> list[dict]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT DISTINCT ON (check_id) check_id, status, value, run_at
                         FROM health_checks
                        WHERE run_id IS DISTINCT FROM %s::uuid
                        ORDER BY check_id, run_at DESC""", (run_id,))
        before = {row[0]: {"status": row[1], "value": row[2], "at": row[3]} for row in cur.fetchall()}
    out = []
    for r in results:
        last = before.get(r["id"])
        bad = r["status"] in ("fail", "warn")
        if last is None:
            if bad:
                out.append({"change": "NEW", **_brief(r)})
            continue
        was_bad = last["status"] in ("fail", "warn")
        if bad and not was_bad:
            out.append({"change": "NEW " + r["status"].upper(), **_brief(r)})
        elif was_bad and not bad:
            out.append({"change": "RESOLVED", **_brief(r)})
        elif r["status"] == "fail" and last["status"] == "warn":
            out.append({"change": "WORSE", **_brief(r)})
        elif bad and r["value"] is not None and last["value"] is not None and r["value"] != last["value"]:
            out.append({"change": "CHANGED", "was": last["value"], **_brief(r)})
    order = {"NEW FAIL": 0, "NEW": 1, "WORSE": 2, "NEW WARN": 3, "CHANGED": 4, "RESOLVED": 5}
    return sorted(out, key=lambda c: order.get(c["change"], 9))


def _brief(r: dict) -> dict:
    return {"id": r["id"], "status": r["status"], "value": r["value"], "summary": r["summary"]}


def report(results: list[dict], diff: list[dict]) -> str:
    """The text an agent reads first: what changed, then everything not fine."""
    counts = {s: sum(r["status"] == s for r in results) for s in ORDER}
    lines = [f"IRIS doctor: {counts['fail']} fail, {counts['warn']} warn, {counts['waiting']} waiting on owner, "
             f"{counts['unknown']} unknown, {counts['ok']} ok"]
    if diff:
        lines.append("\nSince the last run:")
        lines += [f"  {c['change']:<9} {c['id']}: {c['summary']}"
                  + (f" (was {c['was']:g})" if c.get("was") is not None else "") for c in diff]
    else:
        lines.append("\nNothing changed since the last run.")
    attention = [r for r in results if r["status"] != "ok"]
    if attention:
        lines.append("\nNeeds attention:")
        for r in attention:
            lines.append(f"  [{r['status']}] {r['id']}: {r['summary']}")
            if r["expected"]:
                lines.append(f"      expected {r['expected']}")
            if r["action"]:
                lines.append(f"      action ({r['action_class']}): {r['action']}")
            lines.append(f"      runbook: {r['runbook']}")
    return "\n".join(lines)


def latest() -> dict | None:
    """The last stored run, for the health banner: what is not fine, and when it was checked."""
    import psycopg2

    from ..database import db

    try:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT run_id, max(run_at) FROM health_checks
                            GROUP BY run_id ORDER BY max(run_at) DESC LIMIT 1""")
            row = cur.fetchone()
            if row is None:
                return None
            run_id, run_at = row
            cur.execute("""SELECT check_id, status, value, details FROM health_checks
                            WHERE run_id = %s ORDER BY check_id""", (run_id,))
            rows = cur.fetchall()
    except psycopg2.errors.UndefinedTable:
        return None
    counts = {s: sum(r[1] == s for r in rows) for s in ORDER}
    attention = sorted(({"id": cid, "status": status, "summary": (details or {}).get("summary", "")}
                        for cid, status, _, details in rows if status != "ok"),
                       key=lambda a: (ORDER[a["status"]], a["id"]))
    try:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT check_id, outcome, summary FROM health_fixes
                            WHERE fixed_at > %s - interval '1 day' ORDER BY fixed_at""", (run_at,))
            repaired = [{"id": cid, "outcome": outcome, "summary": summary}
                        for cid, outcome, summary in cur.fetchall()]
    except psycopg2.errors.UndefinedTable:
        repaired = []
    return {"runId": str(run_id), "runAt": run_at.isoformat(), "counts": counts, "attention": attention,
            "repaired": repaired}
