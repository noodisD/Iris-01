"""Room and money: database size and growth, telemetry, backups, disk, model spend,
and failures new or wasteful enough to look at.

Telemetry once grew to nine tenths of the database and every backup with it,
and a pattern update once ran twenty-one hours before failing and starting
again. Neither raised anything a person would see.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from ..config import settings
from ..database import db
from . import Result, check

ROOT = Path(__file__).resolve().parents[2]
BACKUPS = ROOT / "data" / "backups"
DB_WARN_GB = 2.0
#: Growth beyond this per day is a leak, not writing.
GROWTH_WARN_MB_PER_DAY = 100
SPANS_WARN_PER_DAY = 150_000
TELEMETRY_WARN_GB = 1.0
BACKUP_MAX_AGE_DAYS = 7
BACKUPS_WARN_GB = 5.0
DISK_WARN_GB, DISK_FAIL_GB = 10, 2
#: Model time thrown away by failed attempts before it is worth a look, in minutes per week.
WASTED_WARN_MIN = 60


def _rows(sql: str, *args) -> list[tuple]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def _value_days_ago(check_id: str, days: int) -> tuple[float, float] | None:
    """A check's stored value from about `days` ago, and how many days back it really is."""
    rows = _rows("""SELECT value, EXTRACT(EPOCH FROM (NOW() - run_at)) / 86400 FROM health_checks
                     WHERE check_id = %s AND value IS NOT NULL AND run_at < NOW() - make_interval(days => %s)
                     ORDER BY run_at DESC LIMIT 1""", check_id, max(1, days // 2))
    return (rows[0][0], rows[0][1]) if rows else None


@check("resources.db_size", "resources")
def db_size() -> Result:
    total = _rows("SELECT pg_database_size(current_database())")[0][0] / 1e6
    top = [(name, round(size / 1e6)) for name, size in _rows(
        """SELECT relname, pg_total_relation_size(relid) FROM pg_statio_user_tables
            ORDER BY 2 DESC LIMIT 5""")]
    earlier = _value_days_ago("resources.db_size", 7)
    growth = (total - earlier[0]) / earlier[1] if earlier and earlier[1] > 0 else None
    details = {"largest_tables_mb": top, "growth_mb_per_day": round(growth, 1) if growth is not None else None}
    summary = f"The database is {total:.0f} MB" + (f", growing {growth:+.0f} MB a day." if growth is not None else ".")
    if total / 1000 > DB_WARN_GB or (growth is not None and growth > GROWTH_WARN_MB_PER_DAY):
        return Result("resources.db_size", "warn", summary, value=round(total), details=details,
                      expected=f"under {DB_WARN_GB:g} GB, growing under {GROWTH_WARN_MB_PER_DAY} MB a day",
                      causes=["Telemetry retention or volume (see resources.telemetry).",
                              "A cache table that is never pruned."],
                      action="Find the growing table in details and its writer.", action_class="read-only")
    return Result("resources.db_size", "ok", summary, value=round(total), details=details,
                  expected=f"under {DB_WARN_GB:g} GB")


@check("resources.telemetry", "resources")
def telemetry() -> Result:
    per_day = _rows("SELECT count(*) FROM obs_spans WHERE started_at > NOW() - interval '1 day'")[0][0]
    size_gb = _rows("SELECT pg_total_relation_size('obs_spans')")[0][0] / 1e9
    summary = f"{per_day:,} spans in the last day; the span table is {size_gb * 1000:.0f} MB."
    if per_day > SPANS_WARN_PER_DAY or size_gb > TELEMETRY_WARN_GB:
        return Result("resources.telemetry", "warn", summary, value=per_day,
                      expected=f"under {SPANS_WARN_PER_DAY:,} a day and {TELEMETRY_WARN_GB:g} GB",
                      causes=["A new code path traced in a tight loop.", "Pruning stopped (OBS_RETENTION_DAYS)."],
                      action="Prune and VACUUM obs_spans; find the span name that grew.",
                      action_class="safe-auto")
    return Result("resources.telemetry", "ok", summary, value=per_day)


@check("resources.backups", "resources")
def backups() -> Result:
    dumps = sorted(BACKUPS.glob("*.dump"), key=lambda p: p.stat().st_mtime) if BACKUPS.exists() else []
    total_gb = sum(p.stat().st_size for p in BACKUPS.iterdir()) / 1e9 if BACKUPS.exists() else 0
    if not dumps:
        return Result("resources.backups", "warn", "There is no database backup.", value=None,
                      action="uv run python scripts/backup_db.py manual", action_class="safe-auto")
    age = (datetime.now().timestamp() - dumps[-1].stat().st_mtime) / 86400
    details = {"count": len(dumps), "newest": dumps[-1].name, "total_gb": round(total_gb, 2)}
    summary = f"Newest backup {age:.1f} days old; {len(dumps)} backups, {total_gb:.1f} GB."
    if age > BACKUP_MAX_AGE_DAYS or total_gb > BACKUPS_WARN_GB:
        return Result("resources.backups", "warn", summary, value=round(age, 1), details=details,
                      expected=f"newest under {BACKUP_MAX_AGE_DAYS} days, all under {BACKUPS_WARN_GB:g} GB",
                      action="Take a backup (scripts/backup_db.py); ask the owner before deleting old ones.",
                      action_class="safe-auto")
    return Result("resources.backups", "ok", summary, value=round(age, 1), details=details)


@check("resources.disk", "resources")
def disk() -> Result:
    free_gb = shutil.disk_usage(ROOT).free / 1e9
    status = "fail" if free_gb < DISK_FAIL_GB else "warn" if free_gb < DISK_WARN_GB else "ok"
    return Result("resources.disk", status, f"{free_gb:.0f} GB free on the disk IRIS runs from.",
                  value=round(free_gb, 1), expected=f"over {DISK_WARN_GB} GB",
                  action=None if status == "ok" else "Free space: old backups (ask the owner), caches.",
                  action_class="needs-owner")


@check("money.spend", "resources")
def spend() -> Result:
    budget = settings.DAILY_BUDGET_USD
    local_midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = _rows("""SELECT started_at >= %s AS today, attributes->>'iris.llm.purpose',
                           sum((attributes->>'iris.llm.cost_usd')::float)
                      FROM obs_spans
                     WHERE started_at > NOW() - interval '7 days' AND attributes ? 'iris.llm.cost_usd'
                     GROUP BY 1, 2""", local_midnight)
    today = sum(cost for is_today, _, cost in rows if is_today)
    week = sum(cost for _, _, cost in rows)
    by_purpose: dict[str, float] = {}
    for _, purpose, cost in rows:
        by_purpose[purpose or "other"] = round(by_purpose.get(purpose or "other", 0) + cost, 3)
    details = {"today_usd": round(today, 3), "week_usd": round(week, 3), "budget_usd": budget,
               "week_by_purpose": dict(sorted(by_purpose.items(), key=lambda kv: -kv[1])[:6])}
    summary = f"${today:.2f} on models today, ${week:.2f} in the last 7 days (budget ${budget:.2f} a day)."
    if today > budget or week / 7 > budget:
        return Result("money.spend", "warn", summary, value=round(today, 3), details=details,
                      expected=f"under ${budget:.2f} a day",
                      causes=["A pattern update retried after long failed attempts (see queue.wasted).",
                              "A large run over the archive."],
                      action="See details for which purpose spent it.", action_class="read-only")
    return Result("money.spend", "ok", summary, value=round(today, 3), details=details,
                  expected=f"under ${budget:.2f} a day")


@check("queue.wasted", "resources")
def wasted() -> Result:
    rows = _rows("""SELECT attributes->>'iris.queue.source_type', count(*), sum(duration_ms) / 60000
                      FROM obs_spans
                     WHERE name = 'queue.job' AND started_at > NOW() - interval '7 days'
                       AND attributes->>'iris.queue.outcome' IN ('retry_scheduled', 'exhausted')
                     GROUP BY 1""")
    minutes = sum(m or 0 for _, _, m in rows)
    details = {"failed_attempts": {kind: [count, round(m or 0)] for kind, count, m in rows}}
    if minutes > WASTED_WARN_MIN:
        worst = max(rows, key=lambda r: r[2] or 0)
        return Result("queue.wasted", "warn",
                      f"Failed attempts threw away {minutes / 60:.1f} h of work this week, most in {worst[0]} jobs.",
                      value=round(minutes), expected=f"under {WASTED_WARN_MIN} min a week", details=details,
                      causes=["The Flex tier refusing calls for capacity (429) partway through a long run.",
                              "Restarts during a pattern update."],
                      action="See errors.new_kinds for the failure; consider retrying synthesis calls in place "
                             "instead of failing the whole run.", action_class="needs-owner")
    return Result("queue.wasted", "ok", f"Failed attempts cost {minutes:.0f} min of work this week.",
                  value=round(minutes), details=details)


@check("errors.new_kinds", "resources")
def new_error_kinds() -> Result:
    rows = _rows("""SELECT name,
                           coalesce((SELECT e->'attributes'->>'exception.type'
                                       FROM jsonb_array_elements(events) e
                                      WHERE e->>'name' = 'exception' LIMIT 1), 'error') AS kind,
                           started_at > NOW() - interval '1 day' AS recent
                      FROM obs_spans
                     WHERE status = 'error' AND started_at > NOW() - interval '7 days'""")
    recent: dict[str, int] = {}
    known: set[str] = set()
    for name, kind, is_recent in rows:
        key = f"{name}: {kind}"
        if is_recent:
            recent[key] = recent.get(key, 0) + 1
        else:
            known.add(key)
    new = {k: n for k, n in recent.items() if k not in known}
    details = {"last_day": recent, "new": new}
    if new:
        return Result("errors.new_kinds", "warn",
                      f"{len(new)} kind(s) of error appeared in the last day that the week before had not seen.",
                      value=len(new), expected="0 new kinds", details=details,
                      causes=["A change that broke something.", "A provider behaving differently."],
                      action="Open the Observatory's errors view for these span names.", action_class="read-only")
    total = sum(recent.values())
    return Result("errors.new_kinds", "ok",
                  f"{total} error(s) in the last day, all of kinds seen before." if total else "No errors in the last day.",
                  value=0, details=details)
