"""Component health. Pure: the same inputs always yield the same reasons."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from collections.abc import Mapping

HEALTH_WINDOW_S = 300
_W = "5 minutes"
State = Literal["idle", "ok", "degraded", "failing"]

LABELS: dict[str, str] = {
    "http": "HTTP doors",
    "db": "PostgreSQL",
    "queue": "Ingest queue",
    "pipeline": "Evidence pipeline",
    "engine": "Engines",
    "admission": "Admission gates",
    "chat": "Chat",
    "voice": "Voice",
    "llm": "OpenAI",
    "import": "Import",
    "sensors": "Sensors",
    "ideas": "Ideas",
    "insights": "Insights",
    "system": "Process",
    "web": "Web app",
    "android": "Android app",
}

_FEATURE = ("chat", "voice", "import", "sensors", "ideas", "insights")
_GAUGE = frozenset({"queue", "db", "system"})
_PIPELINE_LOGGERS = ("agent.persistence", "agent.pipeline", "agent.constructs")


@dataclass
class WindowStats:
    calls: int = 0
    errors: int = 0
    p95_ms: float | None = None
    server_errors: int = 0
    nonstreaming_p95_ms: float | None = None
    pipeline_run_errors: int = 0
    pipeline_last3_all_error: bool = False
    warning_logs: dict[str, int] = field(default_factory=dict)
    engine_errors: dict[str, int] = field(default_factory=dict)
    engine_errors_hour: dict[str, int] = field(default_factory=dict)
    failed_closed: int = 0
    unavailable: list[str] = field(default_factory=list)
    ttft_p95_ms: float | None = None
    connection_errors: int = 0
    slow_queries: int = 0
    sql_errors: int = 0
    web_errors_5m: int = 0
    web_errors_15m: int = 0
    android_errors_15m: int = 0


@dataclass
class ComponentHealth:
    id: str
    state: State
    reasons: list[str]


def _plural(count: int, one: str, many: str) -> str:
    word = one if count == 1 else many
    return f"{count} {word}"


def _num(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


def _probe_stale(probe: Mapping[str, Any] | None) -> bool:
    if not probe:
        return True
    return bool(probe.get("stale"))


def _section(probe: Mapping[str, Any] | None, name: str) -> dict[str, Any]:
    if not probe:
        return {}
    section = probe.get(name) or {}
    return section if isinstance(section, dict) else {}


def _increased(probe: Mapping[str, Any] | None, key: str) -> int:
    """How much `key` grew versus the sample at least 5 minutes older."""
    observatory = _section(probe, "observatory")
    history = observatory.get("history")
    current = observatory.get(key)
    if not isinstance(history, list) or not isinstance(current, (int, float)):
        return 0
    now = observatory.get("history_now")
    if not isinstance(now, (int, float)):
        return 0
    earlier = None
    for point in history:
        if not isinstance(point, dict):
            continue
        at = point.get("at")
        if isinstance(at, (int, float)) and now - at >= HEALTH_WINDOW_S:
            earlier = point.get(key)
    if not isinstance(earlier, (int, float)):
        return 0
    return max(0, int(current - earlier))


def _http(stats: WindowStats, probe: Mapping[str, Any] | None) -> tuple[list[str], list[str]]:
    failing: list[str] = []
    degraded: list[str] = []
    calls = stats.calls
    server_errors = stats.server_errors
    if calls >= 5 and calls and server_errors / calls >= 0.20:
        failing.append(
            f"{server_errors} of {calls} requests failed with a server error in the last {_W}"
        )
    elif server_errors:
        degraded.append(
            f"{_plural(server_errors, 'request', 'requests')} failed with a server error in the last {_W}"
        )
    if stats.nonstreaming_p95_ms is not None and stats.nonstreaming_p95_ms > 2000:
        degraded.append(
            f"95% of requests finished within {_num(stats.nonstreaming_p95_ms)} ms; slower than 2000 ms"
        )
    listeners = _section(probe, "listeners")
    if listeners.get("lan_error"):
        degraded.append(f"Phone listener: {listeners['lan_error']}")
    if listeners.get("tailnet_error"):
        degraded.append(f"Tailnet door: {listeners['tailnet_error']}")
    return failing, degraded


def _feature(stats: WindowStats) -> tuple[list[str], list[str]]:
    failing: list[str] = []
    degraded: list[str] = []
    if stats.calls >= 3 and stats.calls and stats.errors / stats.calls >= 0.5:
        failing.append(f"{stats.errors} of {stats.calls} operations failed in the last {_W}")
    elif stats.errors:
        degraded.append(
            f"{_plural(stats.errors, 'operation', 'operations')} failed in the last {_W}"
        )
    return failing, degraded


def _queue(probe: Mapping[str, Any] | None) -> tuple[list[str], list[str]]:
    from agent.work_queue import MAX_ATTEMPTS

    failing: list[str] = []
    degraded: list[str] = []
    if _probe_stale(probe):
        return failing, degraded
    queue = _section(probe, "queue")
    worker = _section(probe, "worker")
    exhausted = int(queue.get("exhausted") or 0)
    due = int(queue.get("due") or 0)
    retry = int(queue.get("scheduled_retry") or 0)
    age = queue.get("oldest_due_age_s")
    if exhausted:
        failing.append(
            f"{_plural(exhausted, 'item', 'items')} gave up after {MAX_ATTEMPTS} attempts"
        )
    if isinstance(age, (int, float)) and age > 900:
        failing.append(f"Oldest due item has waited {int(age // 60)} min")
    if worker.get("alive") is False:
        failing.append("The ingest worker thread is not running")
    if due > 10:
        degraded.append(f"{due} items due")
    if isinstance(age, (int, float)) and 120 < age <= 900:
        degraded.append(f"Oldest due item has waited {int(age)} s")
    if retry:
        degraded.append(
            f"{_plural(retry, 'item', 'items')} waiting to retry after a failure"
        )
    return failing, degraded


def _pipeline(stats: WindowStats) -> tuple[list[str], list[str]]:
    failing: list[str] = []
    degraded: list[str] = []
    if stats.pipeline_last3_all_error:
        failing.append("The last 3 pipeline runs failed")
    if stats.pipeline_run_errors:
        degraded.append(
            f"{_plural(stats.pipeline_run_errors, 'pipeline run', 'pipeline runs')} failed in the last {_W}"
        )
    for logger in _PIPELINE_LOGGERS:
        count = stats.warning_logs.get(logger, 0)
        if count:
            degraded.append(f"{_plural(count, 'warning', 'warnings')} from {logger} in the last {_W}")
    return failing, degraded


def _engine(stats: WindowStats) -> tuple[list[str], list[str]]:
    failing = [
        f"Engine {name} failed in the last {_W}"
        for name, count in stats.engine_errors.items() if count
    ]
    degraded = [
        f"Engine {name} failed in the last hour"
        for name, count in stats.engine_errors_hour.items()
        if count and name not in stats.engine_errors
    ]
    return failing, degraded


def _admission(stats: WindowStats) -> tuple[list[str], list[str]]:
    failing: list[str] = []
    degraded: list[str] = []
    if stats.failed_closed:
        failing.append("A gate failed and withheld every finding")
    if stats.unavailable:
        degraded.append("Last run could not use: " + ", ".join(stats.unavailable))
    return failing, degraded


def _llm(stats: WindowStats) -> tuple[list[str], list[str]]:
    failing: list[str] = []
    degraded: list[str] = []
    if stats.calls >= 2 and stats.calls and stats.errors / stats.calls >= 0.5:
        failing.append(f"{stats.errors} of {stats.calls} model calls failed in the last {_W}")
    elif stats.errors:
        degraded.append(
            f"{_plural(stats.errors, 'model call', 'model calls')} failed in the last {_W}"
        )
    if stats.ttft_p95_ms is not None and stats.ttft_p95_ms > 10_000:
        degraded.append(
            f"Chat replies took {_num(stats.ttft_p95_ms)} ms to start (95th percentile)"
        )
    return failing, degraded


def _db(stats: WindowStats, probe: Mapping[str, Any] | None) -> tuple[list[str], list[str]]:
    failing: list[str] = []
    degraded: list[str] = []
    server = _section(probe, "db")
    pool = _section(probe, "pool")
    if not _probe_stale(probe) and server.get("reachable") is False:
        failing.append(f"PostgreSQL unreachable: {server.get('error') or 'unknown'}")
    in_use = pool.get("in_use")
    maximum = pool.get("max")
    if (
        not _probe_stale(probe)
        and isinstance(in_use, int)
        and isinstance(maximum, int)
        and maximum > 0
        and in_use >= maximum
    ):
        failing.append(f"All {maximum} pooled connections are in use")
    if stats.connection_errors:
        failing.append(
            f"{_plural(stats.connection_errors, 'connection checkout', 'connection checkouts')} "
            f"failed in the last {_W}"
        )
    streak = server.get("blocked_streak") or 0
    blocked = server.get("blocked") or 0
    if isinstance(streak, int) and streak >= 3:
        failing.append(
            f"{_plural(int(blocked or streak), 'session', 'sessions')} blocked by locks for over 30 s"
        )
    if (
        not _probe_stale(probe)
        and isinstance(in_use, int)
        and isinstance(maximum, int)
        and in_use >= 15
        and (maximum <= 0 or in_use < maximum)
    ):
        degraded.append(f"{in_use} of {maximum} pooled connections in use")
    if stats.slow_queries:
        noun = "query" if stats.slow_queries == 1 else "queries"
        degraded.append(f"{stats.slow_queries} {noun} took longer than 1 s in the last {_W}")
    idle = server.get("oldest_idle_in_xact_s")
    if isinstance(idle, (int, float)) and idle > 60:
        degraded.append(f"A session has been idle in a transaction for {int(idle)} s")
    if stats.sql_errors:
        noun = "query" if stats.sql_errors == 1 else "queries"
        degraded.append(f"{stats.sql_errors} {noun} failed in the last {_W}")
    return failing, degraded


def _system(probe: Mapping[str, Any] | None) -> tuple[list[str], list[str]]:
    failing: list[str] = []
    degraded: list[str] = []
    if _probe_stale(probe):
        return failing, degraded
    loop = _section(probe, "loop")
    process = _section(probe, "process")
    lag = loop.get("lag_ms_max")
    if isinstance(lag, (int, float)) and lag > 1000:
        failing.append(f"The event loop stalled for {_num(float(lag))} ms")
    elif isinstance(lag, (int, float)) and lag > 200:
        degraded.append(f"The event loop stalled for {_num(float(lag))} ms")
    busy = loop.get("threadpool_busy")
    total = loop.get("threadpool_total")
    if isinstance(busy, int) and busy >= 36:
        degraded.append(f"{busy} of {total} worker threads busy")
    dropped = _increased(probe, "dropped")
    if dropped:
        degraded.append(f"The Observatory dropped {_plural(dropped, 'span', 'spans')}")
    failures = _increased(probe, "write_failures")
    if failures:
        degraded.append(
            f"The Observatory could not write to PostgreSQL {_plural(failures, 'time', 'times')}"
        )
    rss = process.get("rss_bytes")
    if isinstance(rss, (int, float)) and rss > 2 * 1024 ** 3:
        degraded.append(f"Memory use is {_num(float(rss) / (1024 ** 3))} GiB")
    return failing, degraded


def _web(stats: WindowStats) -> tuple[list[str], list[str]]:
    failing: list[str] = []
    degraded: list[str] = []
    if stats.web_errors_5m >= 5:
        failing.append(f"{stats.web_errors_5m} browser errors in the last 5 minutes")
    elif stats.web_errors_15m:
        degraded.append(
            f"{_plural(stats.web_errors_15m, 'browser error', 'browser errors')} in the last 15 minutes"
        )
    return failing, degraded


def _ago(seconds: float) -> str:
    if seconds < 90:
        return f"{int(seconds)} s ago"
    if seconds < 90 * 60:
        return f"{int(seconds // 60)} min ago"
    return f"{int(seconds // 3600)} h ago"


def _android(
    stats: WindowStats,
    probe: Mapping[str, Any] | None,
    client_state: Mapping[str, Any],
) -> tuple[list[str], list[str]]:
    failing: list[str] = []
    degraded: list[str] = []
    state = client_state.get("android") or {}
    body = state.get("state") if isinstance(state, dict) else None
    if not isinstance(body, dict):
        body = state if isinstance(state, dict) and "collector" in state else {}
    collector = body.get("collector") if isinstance(body, dict) else None
    collector = collector if isinstance(collector, dict) else {}
    problems = body.get("problems") if isinstance(body, dict) else None
    streak = collector.get("unreachable_streak") or body.get("unreachable_streak") or 0
    if isinstance(streak, int) and streak >= 3:
        failing.append(f"The phone could not reach IRIS {streak} times in a row")
    if isinstance(problems, list):
        for problem in problems:
            if isinstance(problem, dict) and problem.get("code") == "BLOCKED":
                failing.append(f"The phone reports: {problem.get('message') or 'BLOCKED'}")
    elif isinstance(body, dict) and body.get("problem") == "BLOCKED":
        failing.append(f"The phone reports: {body.get('message') or 'BLOCKED'}")
    waiting = collector.get("waiting_payloads")
    if isinstance(waiting, int) and waiting > 0:
        last = collector.get("last_success_age_s")
        if isinstance(last, (int, float)) and last > 30 * 60:
            degraded.append(
                f"{_plural(waiting, 'payload', 'payloads')} waiting on the phone; "
                f"last delivery {_ago(float(last))}"
            )
    if stats.android_errors_15m:
        degraded.append(
            f"{_plural(stats.android_errors_15m, 'app error', 'app errors')} in the last 15 minutes"
        )
    phone = _section(probe, "phone")
    if phone.get("paired") and isinstance(phone.get("last_seen_age_s"), (int, float)):
        age = float(phone["last_seen_age_s"])
        if age > 60 * 60:
            degraded.append(f"The phone has not been heard from for {int(age // 3600)} h")
    return failing, degraded


def _rules(
    component: str,
    stats: WindowStats,
    probe: Mapping[str, Any] | None,
    client_state: Mapping[str, Any],
) -> tuple[list[str], list[str]]:
    if component == "http":
        return _http(stats, probe)
    if component in _FEATURE:
        return _feature(stats)
    if component == "queue":
        return _queue(probe)
    if component == "pipeline":
        return _pipeline(stats)
    if component == "engine":
        return _engine(stats)
    if component == "admission":
        return _admission(stats)
    if component == "llm":
        return _llm(stats)
    if component == "db":
        return _db(stats, probe)
    if component == "system":
        return _system(probe)
    if component == "web":
        return _web(stats)
    if component == "android":
        return _android(stats, probe, client_state)
    return [], []


def evaluate(
    stats: Mapping[str, WindowStats],
    probe: Mapping[str, Any] | None,
    client_state: Mapping[str, Any],
) -> list[ComponentHealth]:
    results: list[ComponentHealth] = []
    for component in LABELS:
        window = stats.get(component) or WindowStats()
        failing, degraded = _rules(component, window, probe, client_state)
        if failing:
            state: State = "failing"
            reasons = failing + degraded
        elif degraded:
            state = "degraded"
            reasons = degraded
        elif component in _GAUGE:
            state = "idle" if _probe_stale(probe) else "ok"
            reasons = []
        elif component == "android" and not _paired(probe) and "android" not in client_state:
            state = "idle"
            reasons = []
        elif window.calls == 0 and component not in ("web",):
            state = "idle"
            reasons = []
        elif component == "web" and window.web_errors_5m == 0 and window.web_errors_15m == 0 and window.calls == 0:
            state = "idle"
            reasons = []
        else:
            state = "ok"
            reasons = []
        results.append(ComponentHealth(component, state, reasons))
    return results


def _paired(probe: Mapping[str, Any] | None) -> bool:
    return bool(_section(probe, "phone").get("paired"))
