"""Read-side SQL for the Observatory. Handlers stay thin."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg2

from agent.observability.health import LABELS, WindowStats, evaluate
from agent.observability.hub import hub

PG_STAT_HINT = (
    "pg_stat_statements is not enabled on this PostgreSQL. To enable it once: "
    "run `ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements';` as a superuser, "
    "restart the PostgreSQL container, then run `CREATE EXTENSION IF NOT EXISTS pg_stat_statements;` "
    "in this database."
)
_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _ts(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=UTC)
        return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return str(value)

def _coverage(cur: Any) -> dict[str, str | None]:
    """When recording began, and the last journal or chat that predates it."""
    cur.execute("SELECT min(started_at) FROM obs_spans")
    started = cur.fetchone()[0]
    journal = _max_created(cur, "reflections")
    message = _max_created(cur, "conversation_messages")
    session = _max_created(cur, "chat_sessions")
    chats = [item for item in (message, session) if item is not None]
    return {
        "recording_since": _ts(started),
        "last_journal_at": _ts(journal),
        "last_chat_at": _ts(max(chats) if chats else None),
    }


def _max_created(cur: Any, table: str) -> object:
    cur.execute(f"SELECT max(created_at) FROM {table}")
    return cur.fetchone()[0]


def _num(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _int(value: object) -> int | None:
    number = _num(value)
    return int(number) if number is not None else None


def _since(window_s: int) -> datetime:
    return datetime.now(UTC) - timedelta(seconds=window_s)


def _parse_started(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def overview(cur: Any, window_s: int) -> dict[str, Any]:
    try:
        body = _overview(cur, window_s)
    except psycopg2.Error:
        cur.connection.rollback()
        return overview_memory(window_s)
    return body


def overview_memory(window_s: int) -> dict[str, Any]:
    stats = _stats_from_memory(300)
    health = evaluate(stats, hub.latest_probe, hub.client_state)
    by_id = {item.id: item for item in health}
    components = []
    for component, label in LABELS.items():
        spans = [
            item for item in hub.recent_spans(2000)
            if item.get("component") == component and item.get("name") != "db.connection"
            and _within(item.get("started_at"), window_s)
        ]
        durations = sorted(float(item["duration_ms"]) for item in spans if item.get("duration_ms") is not None)
        errors = sum(1 for item in spans if item.get("status") == "error")
        state = by_id[component]
        components.append({
            "id": component,
            "label": label,
            "state": state.state,
            "reasons": state.reasons,
            "calls": len(spans),
            "errors": errors,
            "rate_per_min": len(spans) / (window_s / 60) if window_s else 0,
            "p50_ms": _percentile(durations, 0.5),
            "p95_ms": _percentile(durations, 0.95),
            "self_ms_total": sum(float(item.get("self_ms") or 0) for item in spans),
            "series": _series_from_memory(component),
        })
    return {
        "generated_at": _now(),
        "window_s": window_s,
        "source": "memory",
        "recording_since": None,
        "last_journal_at": None,
        "last_chat_at": None,
        "components": components,
        "edges": [],
        "probe": hub.latest_probe,
    }


def health_now(cur: Any) -> dict[str, Any]:
    try:
        stats = _stats_from_db(cur, 300)
        source = "database"
        probe = hub.latest_probe
    except psycopg2.Error:
        cur.connection.rollback()
        stats = _stats_from_memory(300)
        source = "memory"
        probe = hub.latest_probe
    return {
        "generated_at": _now(),
        "source": source,
        "components": [
            {"id": item.id, "state": item.state, "reasons": item.reasons}
            for item in evaluate(stats, probe, hub.client_state)
        ],
    }


def health_memory() -> dict[str, Any]:
    return {
        "generated_at": _now(),
        "source": "memory",
        "components": [
            {"id": item.id, "state": item.state, "reasons": item.reasons}
            for item in evaluate(_stats_from_memory(300), hub.latest_probe, hub.client_state)
        ],
    }


def traces(
    cur: Any, *, component: str | None, status: str | None, min_ms: float,
    q: str | None, window_s: int, limit: int,
) -> list[dict[str, Any]]:
    clauses = ["is_entry", "started_at >= %s"]
    params: list[Any] = [_since(window_s)]
    if component:
        clauses.append("component = %s")
        params.append(component)
    if min_ms:
        clauses.append("duration_ms >= %s")
        params.append(min_ms)
    if q:
        clauses.append("name ILIKE %s")
        params.append(f"%{q}%")
    if status == "error":
        clauses.append(
            "trace_id IN (SELECT trace_id FROM obs_spans WHERE status = 'error' AND started_at >= %s)"
        )
        params.append(_since(window_s))
    elif status:
        clauses.append("status = %s")
        params.append(status)
    cur.execute(
        f"""
        SELECT DISTINCT ON (trace_id)
               trace_id, started_at, name, component, duration_ms, status, status_message
        FROM obs_spans
        WHERE {' AND '.join(clauses)}
        ORDER BY trace_id, started_at
        """,
        params,
    )
    entries = cur.fetchall()
    entries.sort(key=lambda row: row[1], reverse=True)
    entries = entries[:limit]
    if not entries:
        return []
    ids = [row[0] for row in entries]
    cur.execute(
        """
        SELECT trace_id,
               count(*),
               count(*) FILTER (WHERE status = 'error'),
               min(attributes->>'iris.door') FILTER (WHERE component = 'http'),
               min(attributes->>'iris.client') FILTER (WHERE component = 'http'),
               max((attributes->>'iris.db.queries')::int) FILTER (
                   WHERE is_entry AND attributes->>'iris.db.queries' ~ '^[0-9]+$'
               ),
               max((attributes->>'iris.llm.calls')::int) FILTER (
                   WHERE is_entry AND attributes->>'iris.llm.calls' ~ '^[0-9]+$'
               )
        FROM obs_spans
        WHERE trace_id = ANY(%s)
        GROUP BY trace_id
        """,
        (ids,),
    )
    grouped = {row[0]: row for row in cur.fetchall()}
    rows = []
    for trace_id, started, name, component, duration, entry_status, message in entries:
        extra = grouped.get(trace_id)
        client = component if component in ("web", "android") else (extra[4] if extra else None)
        rows.append({
            "trace_id": trace_id,
            "started_at": _ts(started),
            "name": name,
            "component": component,
            "duration_ms": duration,
            "status": entry_status,
            "status_message": message,
            "spans": extra[1] if extra else 1,
            "errors": extra[2] if extra else 0,
            "door": extra[3] if extra else None,
            "client": client,
            "db_queries": extra[5] if extra else None,
            "llm_calls": extra[6] if extra else None,
        })
    return rows


def trace_detail(cur: Any, trace_id: str) -> dict[str, Any] | None:
    from agent.observability.system_queries import summary_row, summary_select

    cur.execute("SELECT count(*) FROM obs_spans WHERE trace_id = %s", (trace_id,))
    total = int(cur.fetchone()[0] or 0)
    cur.execute(
        f"""
        SELECT {summary_select()}
        FROM obs_spans WHERE trace_id = %s ORDER BY started_at LIMIT 5000
        """,
        (trace_id,),
    )
    spans = [_merge_trace_span(summary_row(row)) for row in cur.fetchall()]
    spans = _merge_live_trace(trace_id, spans)
    if not spans and total == 0:
        return None
    cur.execute(
        """
        SELECT at, source, level, logger, message, exception, trace_id, span_id, attributes
        FROM obs_logs WHERE trace_id = %s ORDER BY at
        """,
        (trace_id,),
    )
    logs = [_log_row(row) for row in cur.fetchall()]
    cur.execute(
        """
        SELECT DISTINCT link->>'trace_id'
        FROM obs_spans, jsonb_array_elements(links) link
        WHERE trace_id = %s AND link->>'trace_id' IS NOT NULL AND link->>'trace_id' <> %s
        """,
        (trace_id, trace_id),
    )
    caused_by = [row[0] for row in cur.fetchall()]
    cur.execute(
        """
        SELECT DISTINCT trace_id
        FROM obs_spans, jsonb_array_elements(links) link
        WHERE name = 'queue.job' AND link->>'trace_id' = %s AND trace_id <> %s
        """,
        (trace_id, trace_id),
    )
    caused = [row[0] for row in cur.fetchall()]
    return {
        "trace_id": trace_id,
        "spans": spans,
        "logs": logs,
        "caused_by": caused_by,
        "caused": caused,
        "total_spans": max(total, len(spans)),
        "truncated": total > 5000,
    }


def _merge_trace_span(item: dict[str, Any]) -> dict[str, Any]:
    return item


def _merge_live_trace(trace_id: str, spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {item["span_id"]: item for item in spans}
    for item in hub.recent_spans(2000):
        if item.get("trace_id") == trace_id and item.get("span_id") not in by_id:
            by_id[item["span_id"]] = item
    for item in hub.active_summaries():
        if item.get("trace_id") == trace_id and item.get("span_id") not in by_id:
            by_id[item["span_id"]] = item
    return sorted(by_id.values(), key=lambda item: (item.get("started_at") or "", item.get("span_id") or ""))


def operations(cur: Any, window_s: int, component: str | None) -> list[dict[str, Any]]:
    clauses = ["started_at >= %s", "name <> 'db.connection'"]
    params: list[Any] = [_since(window_s)]
    if component:
        clauses.append("component = %s")
        params.append(component)
    cur.execute(
        f"""
        SELECT component, name, count(*),
               count(*) FILTER (WHERE status = 'error'),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms),
               percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms),
               percentile_cont(0.99) WITHIN GROUP (ORDER BY duration_ms),
               max(duration_ms), sum(duration_ms), sum(self_ms),
               (array_agg(status_message ORDER BY started_at DESC)
                   FILTER (WHERE status = 'error'))[1],
               (array_agg(trace_id ORDER BY duration_ms DESC))[1]
        FROM obs_spans
        WHERE {' AND '.join(clauses)}
        GROUP BY component, name
        ORDER BY sum(self_ms) DESC
        LIMIT 200
        """,
        params,
    )
    fetched = cur.fetchall()
    total_self = sum(float(row[9] or 0) for row in fetched) or 0.0
    return [
        {
            "component": row[0],
            "name": row[1],
            "calls": row[2],
            "errors": row[3],
            "p50_ms": row[4],
            "p95_ms": row[5],
            "p99_ms": row[6],
            "max_ms": row[7],
            "total_ms": row[8],
            "self_ms_total": row[9],
            "self_share": (float(row[9] or 0) / total_self) if total_self else 0.0,
            "last_error": row[10],
            "slowest_trace_id": row[11],
        }
        for row in fetched
    ]


def queue_view(cur: Any) -> dict[str, Any]:
    from agent.work_queue import BACKOFF_SECONDS, MAX_ATTEMPTS, leased_ids

    leased = set(leased_ids())
    cur.execute(
        """
        SELECT id, source_type, source_id, attempts, next_attempt_at, created_at,
               last_error, origin_traceparent
        FROM processing_queue
        ORDER BY next_attempt_at
        LIMIT 500
        """
    )
    now = datetime.now(UTC)
    items = []
    for row in cur.fetchall():
        attempts = row[3] or 0
        nxt = row[4]
        if nxt is not None and nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=UTC)
        if attempts >= MAX_ATTEMPTS:
            state = "exhausted"
        elif row[0] in leased:
            state = "leased"
        elif nxt is not None and nxt <= now:
            state = "due"
        elif attempts > 0:
            state = "scheduled_retry"
        else:
            state = "waiting"
        origin = row[7] or ""
        origin_trace = origin[3:35] if origin.startswith("00-") and len(origin) >= 35 else None
        items.append({
            "id": row[0],
            "source_type": row[1],
            "source_id": row[2],
            "attempts": attempts,
            "max_attempts": MAX_ATTEMPTS,
            "state": state,
            "next_attempt_at": _ts(row[4]),
            "created_at": _ts(row[5]),
            "last_error": row[6],
            "origin_trace_id": origin_trace,
        })
    cur.execute(
        f"""
        SELECT {__import__('agent.observability.system_queries', fromlist=['summary_select']).summary_select()}
        FROM obs_spans WHERE name = 'queue.job'
        ORDER BY started_at DESC LIMIT 50
        """
    )
    from agent.observability.system_queries import summary_row

    recent = [summary_row(row) for row in cur.fetchall()]
    probe = hub.latest_probe or {}
    queue = probe.get("queue") or {}
    return {
        "counts": {
            "due": queue.get("due"),
            "leased": queue.get("leased"),
            "scheduled_retry": queue.get("scheduled_retry"),
            "exhausted": queue.get("exhausted"),
            "total": queue.get("total"),
        },
        "oldest_due_age_s": queue.get("oldest_due_age_s"),
        "by_source_type": queue.get("by_source_type") or [],
        "items": items,
        "recent_jobs": recent,
        "backoff_s": list(BACKOFF_SECONDS),
        "max_attempts": MAX_ATTEMPTS,
    }


def database_view(cur: Any, window_s: int) -> dict[str, Any]:
    probe = hub.latest_probe or {}
    cur.execute(
        """
        SELECT pid, application_name, state, wait_event_type, wait_event,
               EXTRACT(EPOCH FROM (now() - xact_start)),
               EXTRACT(EPOCH FROM (now() - query_start)),
               pg_blocking_pids(pid), left(query, 16384)
        FROM pg_stat_activity
        WHERE datname = current_database() AND pid <> pg_backend_pid()
        ORDER BY query_start NULLS LAST
        """
    )
    activity = [
        {
            "pid": row[0],
            "application_name": row[1],
            "state": row[2],
            "wait_event_type": row[3],
            "wait_event": row[4],
            "xact_age_s": _num(row[5]),
            "query_age_s": _num(row[6]),
            "blocking_pids": list(row[7] or []),
            "query": row[8],
        }
        for row in cur.fetchall()
    ]
    cur.execute(
        """
        SELECT db_fingerprint,
               (array_agg(name ORDER BY duration_ms DESC))[1],
               (array_agg(attributes->>'db.query.text' ORDER BY duration_ms DESC))[1],
               count(*),
               count(*) FILTER (WHERE status = 'error'),
               sum(duration_ms), avg(duration_ms),
               percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms),
               max(duration_ms),
               avg(CASE WHEN attributes->>'db.response.returned_rows' ~ '^-?[0-9]+$'
                        THEN (attributes->>'db.response.returned_rows')::float END),
               (array_agg(trace_id ORDER BY duration_ms DESC))[1]
        FROM obs_spans
        WHERE db_fingerprint IS NOT NULL AND started_at >= %s
        GROUP BY db_fingerprint
        ORDER BY sum(duration_ms) DESC
        LIMIT 100
        """,
        (_since(window_s),),
    )
    statements = [
        {
            "fingerprint": row[0],
            "summary": row[1],
            "sample": row[2],
            "calls": row[3],
            "errors": row[4],
            "total_ms": row[5],
            "mean_ms": row[6],
            "p95_ms": row[7],
            "max_ms": row[8],
            "rows_mean": row[9],
            "slowest_trace_id": row[10],
        }
        for row in cur.fetchall()
    ]
    cur.execute(
        """
        SELECT relname, n_live_tup, n_dead_tup, seq_scan, idx_scan,
               pg_total_relation_size(relid), last_autovacuum, last_autoanalyze
        FROM pg_stat_user_tables
        ORDER BY pg_total_relation_size(relid) DESC
        LIMIT 100
        """
    )
    tables = [
        {
            "name": row[0],
            "live_rows": row[1],
            "dead_rows": row[2],
            "seq_scans": row[3],
            "idx_scans": row[4],
            "size_bytes": row[5],
            "last_autovacuum": _ts(row[6]),
            "last_autoanalyze": _ts(row[7]),
        }
        for row in cur.fetchall()
    ]
    statements_ext = _pg_stat_statements(cur)
    return {
        "pool": probe.get("pool"),
        "server": probe.get("db"),
        "activity": activity,
        "statements": statements,
        "tables": tables,
        "pg_stat_statements": statements_ext,
    }


def llm_view(cur: Any, window_s: int) -> dict[str, Any]:
    cur.execute(
        """
        SELECT name,
               attributes->>'gen_ai.request.model',
               attributes->>'iris.llm.purpose',
               count(*),
               count(*) FILTER (WHERE status = 'error'),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms),
               percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY (attributes->>'iris.llm.ttft_ms')::float)
                   FILTER (WHERE attributes ? 'iris.llm.ttft_ms'),
               percentile_cont(0.95) WITHIN GROUP (ORDER BY (attributes->>'iris.llm.ttft_ms')::float)
                   FILTER (WHERE attributes ? 'iris.llm.ttft_ms'),
               sum(CASE WHEN attributes->>'gen_ai.usage.input_tokens' ~ '^[0-9]+$'
                        THEN (attributes->>'gen_ai.usage.input_tokens')::int END),
               sum(CASE WHEN attributes->>'gen_ai.usage.output_tokens' ~ '^[0-9]+$'
                        THEN (attributes->>'gen_ai.usage.output_tokens')::int END),
               sum((attributes->>'iris.llm.cost_usd')::float)
                   FILTER (WHERE attributes ? 'iris.llm.cost_usd')
        FROM obs_spans
        WHERE component = 'llm' AND started_at >= %s
        GROUP BY 1, 2, 3
        ORDER BY count(*) DESC
        """,
        (_since(window_s),),
    )
    groups = [
        {
            "name": row[0], "model": row[1], "purpose": row[2], "calls": row[3], "errors": row[4],
            "p50_ms": row[5], "p95_ms": row[6], "ttft_p50_ms": row[7], "ttft_p95_ms": row[8],
            "input_tokens": row[9], "output_tokens": row[10], "cost_usd": row[11],
        }
        for row in cur.fetchall()
    ]
    cur.execute(
        f"""
        SELECT {__import__('agent.observability.system_queries', fromlist=['summary_select']).summary_select()}
        FROM obs_spans WHERE component = 'llm' AND started_at >= %s
        ORDER BY started_at DESC LIMIT 50
        """,
        (_since(window_s),),
    )
    from agent.observability.system_queries import summary_row as _summary_row

    return {"window_s": window_s, "groups": groups, "recent": [_summary_row(row) for row in cur.fetchall()]}


def analysis_view(cur: Any, limit: int) -> dict[str, Any]:
    cur.execute(
        """
        SELECT trace_id, span_id, started_at
        FROM obs_spans WHERE name = 'admission.admit'
        ORDER BY started_at DESC LIMIT %s
        """,
        (limit,),
    )
    admits = cur.fetchall()
    if not admits:
        return {"runs": []}
    ids = list({row[0] for row in admits})
    cur.execute(
        """
        SELECT trace_id, span_id, parent_span_id, name, started_at, duration_ms, status,
               attributes, is_entry
        FROM obs_spans WHERE trace_id = ANY(%s) ORDER BY started_at
        """,
        (ids,),
    )
    by_trace: dict[str, list[tuple[Any, ...]]] = {}
    for row in cur.fetchall():
        by_trace.setdefault(row[0], []).append(row)
    runs = []
    for trace_id, admit_id, _started in admits:
        spans = by_trace.get(trace_id, [])
        admit = next((row for row in spans if row[1] == admit_id), None)
        if admit is None:
            continue
        collect = None
        for row in spans:
            if row[3] == "admission.collect" and row[4] <= admit[4]:
                collect = row
        entry = next((row for row in spans if row[8]), None)
        engines = []
        if collect is not None:
            engines = [
                _engine_row(row) for row in spans if row[2] == collect[1] and str(row[3]).startswith("engine.")
            ]
        gates = [
            _gate_row(row) for row in spans if row[2] == admit_id
        ]
        attrs = admit[7] or {}
        collect_attrs = (collect[7] if collect else None) or {}
        runs.append({
            "trace_id": trace_id,
            "caller": entry[3] if entry else None,
            "started_at": _ts(admit[4]),
            "duration_ms": admit[5],
            "unavailable": collect_attrs.get("iris.admission.unavailable") or [],
            "findings_in": attrs.get("iris.admission.in"),
            "findings_out": attrs.get("iris.admission.out"),
            "conflicts_suppressed": attrs.get("iris.admission.conflicts"),
            "engines": engines,
            "gates": gates,
        })
    return {"runs": runs}


def errors_view(cur: Any, window_s: int) -> dict[str, Any]:
    since = _since(window_s)
    cur.execute(
        """
        SELECT component, name,
               (
                   SELECT e->'attributes'->>'exception.type'
                   FROM jsonb_array_elements(events) e
                   WHERE e->>'name' = 'exception' LIMIT 1
               ),
               regexp_replace(left(coalesce(status_message, ''), 300), '\\d+', 'N', 'g'),
               count(*), min(started_at), max(started_at),
               (array_agg(trace_id ORDER BY started_at DESC))[1]
        FROM obs_spans
        WHERE status = 'error' AND started_at >= %s
        GROUP BY 1, 2, 3, 4
        ORDER BY max(started_at) DESC
        LIMIT 200
        """,
        (since,),
    )
    groups = [
        {
            "source": "server",
            "component": row[0],
            "name": row[1],
            "level": "ERROR",
            "error_type": row[2],
            "message": row[3],
            "count": row[4],
            "first_seen": _ts(row[5]),
            "last_seen": _ts(row[6]),
            "sample_trace_id": row[7],
        }
        for row in cur.fetchall()
    ]
    cur.execute(
        """
        SELECT source, logger, level,
               regexp_replace(left(message, 300), '\\d+', 'N', 'g'),
               count(*), min(at), max(at),
               (array_agg(trace_id ORDER BY at DESC))[1]
        FROM obs_logs
        WHERE at >= %s AND level IN ('WARNING', 'ERROR', 'CRITICAL')
        GROUP BY 1, 2, 3, 4
        ORDER BY max(at) DESC
        LIMIT 200
        """,
        (since,),
    )
    groups.extend(
        {
            "source": row[0],
            "component": row[0] if row[0] in ("web", "android") else "system",
            "name": row[1],
            "level": row[2],
            "error_type": None,
            "message": row[3],
            "count": row[4],
            "first_seen": _ts(row[5]),
            "last_seen": _ts(row[6]),
            "sample_trace_id": row[7],
        }
        for row in cur.fetchall()
    )
    groups.sort(key=lambda item: item["last_seen"] or "", reverse=True)
    return {"window_s": window_s, "groups": groups[:200]}


def logs(
    cur: Any, *, level: str, source: str | None, q: str | None,
    trace_id: str | None, window_s: int, limit: int,
) -> list[dict[str, Any]]:
    minimum = _LEVELS.get(level, 20)
    allowed = [name for name, value in _LEVELS.items() if value >= minimum]
    clauses = ["at >= %s", "level = ANY(%s)"]
    params: list[Any] = [_since(window_s), allowed]
    if source:
        clauses.append("source = %s")
        params.append(source)
    if q:
        clauses.append("message ILIKE %s")
        params.append(f"%{q}%")
    if trace_id:
        clauses.append("trace_id = %s")
        params.append(trace_id)
    params.append(limit)
    cur.execute(
        f"""
        SELECT at, source, level, logger, message, exception, trace_id, span_id, attributes
        FROM obs_logs WHERE {' AND '.join(clauses)}
        ORDER BY at DESC LIMIT %s
        """,
        params,
    )
    return [_log_row(row) for row in cur.fetchall()]


def samples(cur: Any, names: list[str], window_s: int) -> dict[str, Any]:
    if window_s <= 3600:
        return {"series": {name: [[at, value] for at, value in hub.series(name)] for name in names}}
    cur.execute(
        """
        SELECT name, at, value FROM obs_samples
        WHERE name = ANY(%s) AND at >= %s
        ORDER BY at
        """,
        (names, _since(window_s)),
    )
    series: dict[str, list[list[Any]]] = {name: [] for name in names}
    for name, at, value in cur.fetchall():
        series.setdefault(name, []).append([_ts(at), value])
    return {"series": series}


def clients_view(cur: Any) -> dict[str, Any]:
    probe = hub.latest_probe or {}
    return {
        "web": _client_side(cur, "web"),
        "android": {**_client_side(cur, "android"), "state": _client_state(cur, "android")},
        "phone": probe.get("phone"),
        "listeners": probe.get("listeners"),
    }


def _overview(cur: Any, window_s: int) -> dict[str, Any]:
    stats = _stats_from_db(cur, 300)
    health = {item.id: item for item in evaluate(stats, hub.latest_probe, hub.client_state)}
    cur.execute(
        """
        SELECT component, count(*),
               count(*) FILTER (WHERE status = 'error'),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms),
               percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms),
               sum(self_ms)
        FROM obs_spans
        WHERE started_at >= %s AND name <> 'db.connection'
        GROUP BY component
        """,
        (_since(window_s),),
    )
    found = {row[0]: row for row in cur.fetchall()}
    series = _series_from_db(cur)
    components = []
    for component, label in LABELS.items():
        row = found.get(component)
        calls = row[1] if row else 0
        state = health[component]
        components.append({
            "id": component,
            "label": label,
            "state": state.state,
            "reasons": state.reasons,
            "calls": calls,
            "errors": row[2] if row else 0,
            "rate_per_min": calls / (window_s / 60) if window_s else 0,
            "p50_ms": row[3] if row else None,
            "p95_ms": row[4] if row else None,
            "self_ms_total": row[5] if row else 0,
            "series": series.get(component, _empty_series()),
        })
    coverage = _coverage(cur)
    return {
        "generated_at": _now(),
        "window_s": window_s,
        "source": "database",
        **coverage,
        "components": components,
        "edges": _edges(cur, window_s),
        "probe": hub.latest_probe,
    }


def _edges(cur: Any, window_s: int) -> list[dict[str, Any]]:
    since = _since(window_s)
    cur.execute(
        """
        SELECT parent.component, child.component, count(*),
               count(*) FILTER (WHERE child.status = 'error'),
               percentile_cont(0.95) WITHIN GROUP (ORDER BY child.duration_ms)
        FROM obs_spans child
        JOIN obs_spans parent
          ON parent.trace_id = child.trace_id AND parent.span_id = child.parent_span_id
        WHERE child.started_at >= %s AND parent.component <> child.component
        GROUP BY parent.component, child.component
        """,
        (since,),
    )
    edges = [
        {"source": row[0], "target": row[1], "calls": row[2], "errors": row[3], "p95_ms": row[4]}
        for row in cur.fetchall()
    ]
    cur.execute(
        """
        SELECT other.component, count(*),
               count(*) FILTER (WHERE job.status = 'error'),
               percentile_cont(0.95) WITHIN GROUP (ORDER BY job.duration_ms)
        FROM obs_spans job
        CROSS JOIN LATERAL jsonb_array_elements(job.links) link
        JOIN obs_spans other
          ON other.trace_id = link->>'trace_id' AND other.span_id = link->>'span_id'
        WHERE job.name = 'queue.job' AND job.started_at >= %s
        GROUP BY other.component
        """,
        (since,),
    )
    edges.extend(
        {"source": row[0], "target": "queue", "calls": row[1], "errors": row[2], "p95_ms": row[3]}
        for row in cur.fetchall()
    )
    return edges


def _series_from_db(cur: Any) -> dict[str, dict[str, list[Any]]]:
    cur.execute(
        """
        SELECT component, date_trunc('minute', started_at),
               count(*), count(*) FILTER (WHERE status = 'error'),
               percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)
        FROM obs_spans
        WHERE started_at >= now() - interval '60 minutes' AND name <> 'db.connection'
        GROUP BY component, 2
        """
    )
    buckets: dict[str, dict[datetime, tuple[int, int, float | None]]] = {}
    for component, minute, calls, errors, p95 in cur.fetchall():
        buckets.setdefault(component, {})[minute] = (calls, errors, p95)
    return {component: _fill_minutes(points) for component, points in buckets.items()}


def _stats_from_db(cur: Any, window_s: int) -> dict[str, WindowStats]:
    since = _since(window_s)
    hour = _since(3600)
    fifteen = _since(900)
    stats = {name: WindowStats() for name in LABELS}
    cur.execute(
        """
        SELECT component, count(*), count(*) FILTER (WHERE status = 'error')
        FROM obs_spans
        WHERE started_at >= %s AND name <> 'db.connection'
        GROUP BY component
        """,
        (since,),
    )
    for component, calls, errors in cur.fetchall():
        if component in stats:
            stats[component].calls = calls
            stats[component].errors = errors
    cur.execute(
        """
        SELECT count(*),
               count(*) FILTER (WHERE (attributes->>'http.response.status_code') ~ '^[0-9]+$'
                                  AND (attributes->>'http.response.status_code')::int >= 500),
               percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)
                   FILTER (WHERE coalesce(attributes->>'iris.http.streaming', 'false') <> 'true')
        FROM obs_spans
        WHERE component = 'http' AND started_at >= %s
        """,
        (since,),
    )
    calls, server_errors, p95 = cur.fetchone()
    stats["http"].calls = calls or 0
    stats["http"].server_errors = server_errors or 0
    stats["http"].nonstreaming_p95_ms = _num(p95)
    cur.execute(
        """
        SELECT count(*) FROM obs_spans
        WHERE name = 'pipeline.run' AND status = 'error' AND started_at >= %s
        """,
        (since,),
    )
    stats["pipeline"].pipeline_run_errors = cur.fetchone()[0]
    cur.execute(
        """
        SELECT status FROM obs_spans
        WHERE name = 'pipeline.run' AND started_at >= %s
        ORDER BY started_at DESC LIMIT 3
        """,
        (hour,),
    )
    last = [row[0] for row in cur.fetchall()]
    stats["pipeline"].pipeline_last3_all_error = len(last) == 3 and all(item == "error" for item in last)
    cur.execute(
        """
        SELECT logger, count(*) FROM obs_logs
        WHERE at >= %s AND level IN ('WARNING', 'ERROR', 'CRITICAL')
          AND logger = ANY(%s)
        GROUP BY logger
        """,
        (since, ["agent.persistence", "agent.pipeline", "agent.constructs"]),
    )
    stats["pipeline"].warning_logs = {row[0]: row[1] for row in cur.fetchall()}
    cur.execute(
        """
        SELECT name, count(*) FROM obs_spans
        WHERE component = 'engine' AND status = 'error' AND started_at >= %s
        GROUP BY name
        """,
        (since,),
    )
    stats["engine"].engine_errors = {row[0].removeprefix("engine."): row[1] for row in cur.fetchall()}
    cur.execute(
        """
        SELECT name, count(*) FROM obs_spans
        WHERE component = 'engine' AND status = 'error' AND started_at >= %s
        GROUP BY name
        """,
        (hour,),
    )
    stats["engine"].engine_errors_hour = {row[0].removeprefix("engine."): row[1] for row in cur.fetchall()}
    cur.execute(
        """
        SELECT count(*) FROM obs_spans
        WHERE started_at >= %s
          AND attributes->>'iris.admission.failed_closed' IN ('true', 'True')
        """,
        (since,),
    )
    stats["admission"].failed_closed = cur.fetchone()[0]
    cur.execute(
        """
        SELECT attributes->'iris.admission.unavailable'
        FROM obs_spans WHERE name = 'admission.collect'
        ORDER BY started_at DESC LIMIT 1
        """
    )
    row = cur.fetchone()
    if row and isinstance(row[0], list):
        stats["admission"].unavailable = [str(item) for item in row[0]]
    cur.execute(
        """
        SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY (attributes->>'iris.llm.ttft_ms')::float)
        FROM obs_spans
        WHERE name = 'llm.chat_stream' AND started_at >= %s AND attributes ? 'iris.llm.ttft_ms'
        """,
        (since,),
    )
    stats["llm"].ttft_p95_ms = _num(cur.fetchone()[0])
    cur.execute(
        """
        SELECT count(*) FILTER (WHERE name = 'db.connection' AND status = 'error'),
               count(*) FILTER (WHERE name <> 'db.connection' AND duration_ms > 1000),
               count(*) FILTER (WHERE name <> 'db.connection' AND status = 'error')
        FROM obs_spans WHERE component = 'db' AND started_at >= %s
        """,
        (since,),
    )
    connection_errors, slow, sql_errors = cur.fetchone()
    stats["db"].connection_errors = connection_errors or 0
    stats["db"].slow_queries = slow or 0
    stats["db"].sql_errors = sql_errors or 0
    cur.execute(
        """
        SELECT
            count(*) FILTER (WHERE at >= %s),
            count(*) FILTER (WHERE at >= %s)
        FROM obs_logs
        WHERE source = 'web' AND level IN ('ERROR', 'CRITICAL') AND at >= %s
        """,
        (since, fifteen, fifteen),
    )
    web5, web15 = cur.fetchone()
    cur.execute(
        """
        SELECT count(*) FILTER (WHERE started_at >= %s), count(*)
        FROM obs_spans
        WHERE component = 'web' AND status = 'error' AND started_at >= %s
        """,
        (since, fifteen),
    )
    span5, span15 = cur.fetchone()
    stats["web"].web_errors_5m = (web5 or 0) + (span5 or 0)
    stats["web"].web_errors_15m = (web15 or 0) + (span15 or 0)
    stats["web"].calls = stats["web"].web_errors_5m
    cur.execute(
        "SELECT count(*) FROM obs_logs WHERE source = 'android' AND level IN ('ERROR', 'CRITICAL') AND at >= %s",
        (fifteen,),
    )
    stats["android"].android_errors_15m = cur.fetchone()[0]
    return stats


def _stats_from_memory(window_s: int) -> dict[str, WindowStats]:
    stats = {name: WindowStats() for name in LABELS}
    spans = [item for item in hub.recent_spans(2000) if _within(item.get("started_at"), window_s)]
    hour = [item for item in hub.recent_spans(2000) if _within(item.get("started_at"), 3600)]
    for item in spans:
        component = str(item.get("component") or "")
        if component in stats and item.get("name") != "db.connection":
            stats[component].calls += 1
            if item.get("status") == "error":
                stats[component].errors += 1
    http = [item for item in spans if item.get("component") == "http"]
    stats["http"].calls = len(http)
    stats["http"].server_errors = sum(
        1 for item in http if _int((item.get("attrs") or {}).get("http.response.status_code")) is not None
        and (_int((item.get("attrs") or {}).get("http.response.status_code")) or 0) >= 500
    )
    quiet = [
        float(item["duration_ms"]) for item in http
        if not (item.get("attrs") or {}).get("iris.http.streaming") and item.get("duration_ms") is not None
    ]
    stats["http"].nonstreaming_p95_ms = _percentile(sorted(quiet), 0.95)
    runs = [item for item in spans if item.get("name") == "pipeline.run" and item.get("status") == "error"]
    stats["pipeline"].pipeline_run_errors = len(runs)
    last = [item for item in hour if item.get("name") == "pipeline.run"][-3:]
    stats["pipeline"].pipeline_last3_all_error = len(last) == 3 and all(item.get("status") == "error" for item in last)
    for item in hub.recent_logs(1000):
        if not _within(item.get("at"), window_s):
            continue
        if item.get("level") in ("WARNING", "ERROR", "CRITICAL") and item.get("logger") in (
            "agent.persistence", "agent.pipeline", "agent.constructs"
        ):
            stats["pipeline"].warning_logs[item["logger"]] = stats["pipeline"].warning_logs.get(item["logger"], 0) + 1
    for item in spans:
        if item.get("component") == "engine" and item.get("status") == "error":
            name = str(item.get("name") or "").removeprefix("engine.")
            stats["engine"].engine_errors[name] = stats["engine"].engine_errors.get(name, 0) + 1
    for item in hour:
        if item.get("component") == "engine" and item.get("status") == "error":
            name = str(item.get("name") or "").removeprefix("engine.")
            stats["engine"].engine_errors_hour[name] = stats["engine"].engine_errors_hour.get(name, 0) + 1
    for item in spans:
        attrs = item.get("attrs") or {}
        if attrs.get("iris.admission.failed_closed") in (True, "true", "True"):
            stats["admission"].failed_closed += 1
    collects = [item for item in hub.recent_spans(2000) if item.get("name") == "admission.collect"]
    if collects:
        unavailable = (collects[-1].get("attrs") or {}).get("iris.admission.unavailable") or []
        if isinstance(unavailable, list):
            stats["admission"].unavailable = [str(item) for item in unavailable]
    ttft = sorted(
        float((item.get("attrs") or {})["iris.llm.ttft_ms"])
        for item in spans if item.get("name") == "llm.chat_stream" and (item.get("attrs") or {}).get("iris.llm.ttft_ms") is not None
    )
    stats["llm"].ttft_p95_ms = _percentile(ttft, 0.95)
    db_spans = [item for item in spans if item.get("component") == "db"]
    stats["db"].connection_errors = sum(1 for item in db_spans if item.get("name") == "db.connection" and item.get("status") == "error")
    stats["db"].slow_queries = sum(1 for item in db_spans if item.get("name") != "db.connection" and float(item.get("duration_ms") or 0) > 1000)
    stats["db"].sql_errors = sum(1 for item in db_spans if item.get("name") != "db.connection" and item.get("status") == "error")
    web_logs_5 = sum(1 for item in hub.recent_logs(1000) if item.get("source") == "web" and item.get("level") in ("ERROR", "CRITICAL") and _within(item.get("at"), 300))
    web_logs_15 = sum(1 for item in hub.recent_logs(1000) if item.get("source") == "web" and item.get("level") in ("ERROR", "CRITICAL") and _within(item.get("at"), 900))
    web_spans_5 = sum(1 for item in spans if item.get("component") == "web" and item.get("status") == "error")
    web_spans_15 = sum(1 for item in hub.recent_spans(2000) if item.get("component") == "web" and item.get("status") == "error" and _within(item.get("started_at"), 900))
    stats["web"].web_errors_5m = web_logs_5 + web_spans_5
    stats["web"].web_errors_15m = web_logs_15 + web_spans_15
    stats["web"].calls = stats["web"].web_errors_5m
    stats["android"].android_errors_15m = sum(
        1 for item in hub.recent_logs(1000)
        if item.get("source") == "android" and item.get("level") in ("ERROR", "CRITICAL") and _within(item.get("at"), 900)
    )
    return stats


def _client_side(cur: Any, source: str) -> dict[str, Any]:
    since = _since(86400)
    cur.execute(
        """
        SELECT count(*), count(*) FILTER (WHERE status = 'error'),
               percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms),
               max(started_at)
        FROM obs_spans WHERE component = %s AND started_at >= %s
        """,
        (source, since),
    )
    calls, errors, p95, last = cur.fetchone()
    cur.execute(
        """
        SELECT coalesce(attributes->>'iris.client.route', name), count(*),
               count(*) FILTER (WHERE status = 'error')
        FROM obs_spans WHERE component = %s AND started_at >= %s
        GROUP BY 1 ORDER BY count(*) DESC LIMIT 20
        """,
        (source, since),
    )
    by_route = [{"route": row[0], "calls": row[1], "errors": row[2]} for row in cur.fetchall()]
    cur.execute(
        """
        SELECT at, source, level, logger, message, exception, trace_id, span_id, attributes
        FROM obs_logs
        WHERE source = %s AND level IN ('WARNING', 'ERROR', 'CRITICAL') AND at >= %s
        ORDER BY at DESC LIMIT 20
        """,
        (source, since),
    )
    return {
        "last_seen": _ts(last),
        "requests": calls or 0,
        "errors": errors or 0,
        "p95_ms": p95,
        "by_route": by_route,
        "recent_errors": [_log_row(row) for row in cur.fetchall()],
    }


def _client_state(cur: Any, source: str) -> dict[str, Any] | None:
    cur.execute("SELECT received_at, state FROM obs_client_state WHERE source = %s", (source,))
    row = cur.fetchone()
    if row is None:
        cached = hub.client_state.get(source)
        return cached
    return {"received_at": _ts(row[0]), "state": row[1]}


def _pg_stat_statements(cur: Any) -> dict[str, Any]:
    try:
        cur.execute(
            """
            SELECT query, calls, total_exec_time, mean_exec_time, rows
            FROM pg_stat_statements
            WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
            ORDER BY total_exec_time DESC
            LIMIT 20
            """
        )
        return {
            "available": True,
            "rows": [
                {"query": row[0], "calls": row[1], "total_exec_time": row[2],
                 "mean_exec_time": row[3], "rows": row[4]}
                for row in cur.fetchall()
            ],
        }
    except psycopg2.Error:
        cur.connection.rollback()
        return {"available": False, "hint": PG_STAT_HINT}




def _log_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "at": _ts(row[0]), "source": row[1], "level": row[2], "logger": row[3],
        "message": row[4], "exception": row[5], "trace_id": row[6], "span_id": row[7],
        "attributes": row[8] or {},
    }


def _within(value: object, window_s: int) -> bool:
    parsed = _parse_started(value)
    if parsed is None:
        return False
    return parsed >= _since(window_s)


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    index = (len(values) - 1) * q
    low = int(index)
    high = min(low + 1, len(values) - 1)
    weight = index - low
    return values[low] * (1 - weight) + values[high] * weight


def _empty_series() -> dict[str, list[Any]]:
    return _fill_minutes({})


def _fill_minutes(points: dict[datetime, tuple[int, int, float | None]]) -> dict[str, list[Any]]:
    end = datetime.now(UTC).replace(second=0, microsecond=0)
    minutes, calls, errors, p95 = [], [], [], []
    for offset in range(59, -1, -1):
        minute = end - timedelta(minutes=offset)
        found = None
        for key, value in points.items():
            key_minute = key if key.tzinfo else key.replace(tzinfo=UTC)
            if key_minute.astimezone(UTC).replace(second=0, microsecond=0) == minute:
                found = value
                break
        minutes.append(minute.strftime("%Y-%m-%dT%H:%M:%SZ"))
        calls.append(found[0] if found else 0)
        errors.append(found[1] if found else 0)
        p95.append(found[2] if found else None)
    return {"minute": minutes, "calls": calls, "errors": errors, "p95_ms": p95}


def _series_from_memory(component: str) -> dict[str, list[Any]]:
    points: dict[datetime, list[float]] = {}
    errors: dict[datetime, int] = {}
    for item in hub.recent_spans(2000):
        if item.get("component") != component or item.get("name") == "db.connection":
            continue
        started = _parse_started(item.get("started_at"))
        if started is None or started < _since(3600):
            continue
        minute = started.astimezone(UTC).replace(second=0, microsecond=0)
        points.setdefault(minute, []).append(float(item.get("duration_ms") or 0))
        if item.get("status") == "error":
            errors[minute] = errors.get(minute, 0) + 1
    packed = {
        minute: (len(values), errors.get(minute, 0), _percentile(sorted(values), 0.95))
        for minute, values in points.items()
    }
    return _fill_minutes(packed)


def _engine_row(row: tuple[Any, ...]) -> dict[str, Any]:
    attrs = row[7] or {}
    cache = {key.removeprefix("iris.cache."): value for key, value in attrs.items() if str(key).startswith("iris.cache.")}
    return {
        "name": str(row[3]).removeprefix("engine."),
        "duration_ms": row[5],
        "findings": attrs.get("iris.engine.findings"),
        "status": row[6],
        "cache": cache,
    }


def _gate_row(row: tuple[Any, ...]) -> dict[str, Any]:
    attrs = row[7] or {}
    return {
        "name": str(row[3]).removeprefix("admission."),
        "in": attrs.get("iris.admission.in"),
        "out": attrs.get("iris.admission.out"),
        "reasons": attrs.get("iris.admission.reasons"),
        "failed_closed": attrs.get("iris.admission.failed_closed"),
    }
