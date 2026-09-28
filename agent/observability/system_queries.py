"""Module graph and one selected invocation. Does not import iris_api."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import psycopg2

from agent.observability import catalog
from agent.observability.hub import hub
from agent.observability.io import parts_for, strip_payload_attributes
from agent.observability.queries import _percentile, _since, _ts

_SUMMARY_ATTRS = (
    "http.response.status_code",
    "http.route",
    "iris.door",
    "iris.client",
    "iris.http.streaming",
    "gen_ai.request.model",
    "iris.llm.ttft_ms",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "iris.queue.outcome",
    "db.response.returned_rows",
    "iris.db.queries",
    "iris.db.spans_dropped",
    "iris.db.fetch_spans_dropped",
    "iris.admission.failed_closed",
    "iris.admission.unavailable",
)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def summary_select() -> str:
    attr_sql = ", ".join(f"attributes->'{key}'" for key in _SUMMARY_ATTRS)
    return f"""
        trace_id, span_id, parent_span_id, name, component, kind, started_at,
        duration_ms, self_ms, status, left(status_message, 300),
        module_id, parent_module_id, links, {attr_sql}
    """


def summary_row(row: tuple[Any, ...], *, running: bool = False) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    for key, value in zip(_SUMMARY_ATTRS, row[14:], strict=False):
        if value is not None:
            attrs[key] = value
    return {
        "trace_id": row[0],
        "span_id": row[1],
        "parent_span_id": row[2],
        "name": row[3],
        "component": row[4],
        "kind": row[5],
        "started_at": _ts(row[6]),
        "duration_ms": row[7],
        "self_ms": None if running else row[8],
        "status": "running" if running else row[9],
        "status_message": row[10],
        "module_id": row[11],
        "parent_module_id": row[12],
        "links": row[13] or [],
        "attrs": attrs,
    }


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


def _node(spec: catalog.ModuleSpec, stats: dict[str, Any] | None, active: int) -> dict[str, Any]:
    body = spec.as_dict()
    body["stats"] = None if spec.kind == "state" else stats
    body["active"] = active
    body["latest_state"] = None
    if spec.id == "android.collector.state":
        state = hub.client_state.get("android")
        if isinstance(state, dict):
            body["latest_state"] = state
    return body


def _empty_stats() -> dict[str, Any]:
    return {
        "calls": 0,
        "errors": 0,
        "rate_per_min": None,
        "p50_ms": None,
        "p95_ms": None,
        "self_ms_total": 0,
        "last_seen": None,
    }


def system_view(cur: Any, window_s: int, trace_id: str | None = None) -> dict[str, Any]:
    since = _since(window_s)
    trace_clause = " AND trace_id = %s" if trace_id else ""
    params: list[Any] = [since]
    if trace_id:
        params.append(trace_id)
    cur.execute("SELECT min(started_at) FROM obs_spans")
    retained_since = _ts(cur.fetchone()[0])
    cur.execute(
        f"""
        SELECT module_id, component, count(*),
               count(*) FILTER (WHERE status = 'error'),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms),
               percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms),
               coalesce(sum(self_ms), 0), max(started_at)
        FROM obs_spans
        WHERE started_at >= %s AND name <> 'db.connection'{trace_clause}
        GROUP BY module_id, component
        """,
        params,
    )
    observed: dict[str, dict[str, Any]] = {}
    for row in cur.fetchall():
        calls = int(row[2] or 0)
        observed[row[0]] = {
            "component": row[1],
            "calls": calls,
            "errors": int(row[3] or 0),
            "rate_per_min": (calls / window_s) * 60 if window_s else None,
            "p50_ms": row[4],
            "p95_ms": row[5],
            "self_ms_total": float(row[6] or 0),
            "last_seen": _ts(row[7]),
        }
    cur.execute(
        f"""
        SELECT parent.module_id, child.module_id, count(*),
               count(*) FILTER (WHERE child.status = 'error'),
               percentile_cont(0.95) WITHIN GROUP (ORDER BY child.duration_ms)
        FROM obs_spans child
        JOIN obs_spans parent
          ON parent.trace_id = child.trace_id AND parent.span_id = child.parent_span_id
        WHERE child.started_at >= %s
          AND child.name <> 'db.connection'
          AND parent.name <> 'db.connection'
          AND child.module_id IS NOT NULL
          AND parent.module_id IS NOT NULL
          AND child.module_id <> parent.module_id
          {trace_clause.replace('trace_id', 'child.trace_id')}
        GROUP BY parent.module_id, child.module_id
        """,
        params,
    )
    call_edges = {
        (row[0], row[1]): {"calls": int(row[2] or 0), "errors": int(row[3] or 0), "p95_ms": row[4]}
        for row in cur.fetchall()
    }
    causal = _causal_edges(cur, since, trace_id)
    unresolved = _unresolved_parents(cur, since, trace_id)
    dropped_db, dropped_fetch = _dropped(cur, since, trace_id)
    return _assemble(
        window_s,
        trace_id,
        source="database",
        partial=False,
        retained_since=retained_since,
        observed=observed,
        call_edges=call_edges,
        causal=causal,
        unresolved=unresolved,
        dropped_db=dropped_db,
        dropped_fetch=dropped_fetch,
    )


def system_memory(window_s: int, trace_id: str | None = None) -> dict[str, Any]:
    since = _since(window_s)
    summaries = [
        item
        for item in hub.recent_spans(2000)
        if item.get("name") != "db.connection"
        and (trace_id is None or item.get("trace_id") == trace_id)
        and _in_window(item.get("started_at"), since)
    ]
    observed: dict[str, dict[str, Any]] = {}
    durations: dict[str, list[float]] = {}
    for item in summaries:
        module_id = item.get("module_id") or item.get("name")
        if not module_id or item.get("status") == "running":
            continue
        stats = observed.setdefault(module_id, {**_empty_stats(), "component": item.get("component")})
        stats["calls"] += 1
        if item.get("status") == "error":
            stats["errors"] += 1
        stats["self_ms_total"] += float(item.get("self_ms") or 0)
        stats["last_seen"] = item.get("started_at")
        if isinstance(item.get("duration_ms"), (int, float)):
            durations.setdefault(module_id, []).append(float(item["duration_ms"]))
    for module_id, values in durations.items():
        values.sort()
        observed[module_id]["p50_ms"] = _percentile(values, 0.5)
        observed[module_id]["p95_ms"] = _percentile(values, 0.95)
        observed[module_id]["rate_per_min"] = (observed[module_id]["calls"] / window_s) * 60 if window_s else None
    started = [item["started_at"] for item in summaries if item.get("started_at")]
    oldest = min(started) if started else None
    return _assemble(
        window_s,
        trace_id,
        source="memory",
        partial=True,
        retained_since=None,
        observed=observed,
        call_edges={},
        causal=[],
        unresolved=0,
        dropped_db=0,
        dropped_fetch=0,
        memory_since=oldest,
    )


def module_calls(
    cur: Any,
    module_id: str,
    window_s: int,
    trace_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    since = _since(window_s)
    clauses = ["module_id = %s", "started_at >= %s", "name <> 'db.connection'"]
    params: list[Any] = [module_id, since]
    if trace_id:
        clauses.append("trace_id = %s")
        params.append(trace_id)
    cur.execute(
        f"""
        SELECT {summary_select()}
        FROM obs_spans
        WHERE {' AND '.join(clauses)}
        ORDER BY started_at DESC, trace_id DESC, span_id DESC
        LIMIT %s
        """,
        [*params, limit],
    )
    recent = [summary_row(row) for row in cur.fetchall()]
    return _merge_calls(module_id, recent, trace_id, source="database", partial=False)


def module_calls_memory(
    module_id: str,
    trace_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    recent = [
        item
        for item in reversed(hub.recent_spans(2000))
        if item.get("module_id") == module_id and (trace_id is None or item.get("trace_id") == trace_id)
    ][:limit]
    return _merge_calls(module_id, recent, trace_id, source="memory", partial=True)


def invocation_from_record(record: dict[str, Any], *, source: str) -> dict[str, Any]:
    attributes = record.get("attributes") or {}
    if not isinstance(attributes, dict):
        attributes = {}
    running = record.get("status") == "running"
    parts = parts_for(
        str(record.get("name") or ""),
        str(record.get("component") or ""),
        attributes,
        status=str(record.get("status") or "ok"),
        status_message=record.get("status_message"),
        running=running,
    )
    span = {
        "trace_id": record.get("trace_id"),
        "span_id": record.get("span_id"),
        "parent_span_id": record.get("parent_span_id"),
        "name": record.get("name"),
        "component": record.get("component"),
        "kind": record.get("kind"),
        "started_at": record.get("started_at"),
        "duration_ms": record.get("duration_ms"),
        "self_ms": record.get("self_ms"),
        "status": record.get("status"),
        "status_message": record.get("status_message"),
        "attrs": record.get("attrs") or {},
        "module_id": record.get("module_id"),
        "parent_module_id": record.get("parent_module_id"),
        "links": record.get("links") or [],
    }
    return {
        "span": span,
        "io": {
            "inputs": [part.as_dict() for part in parts if part.label.lower().startswith(("argument", "request", "prompt", "statement", "client", "collector")) or "input" in part.label.lower()],
            "outputs": [part.as_dict() for part in parts if part not in parts[:1] or len(parts) == 1],
        },
        "attributes": strip_payload_attributes(attributes),
        "events": record.get("events") or [],
        "logs": record.get("logs") or [],
        "related": record.get("related") or [],
        "source": source,
    }


def split_parts(parts: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    inputs: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    for part in parts:
        body = part.as_dict() if hasattr(part, "as_dict") else part
        label = str(body.get("label") or "")
        if label in {"Result", "Response body", "Completion", "Affected/result row count", "Columns and fetched rows"}:
            outputs.append(body)
        elif label in {"Arguments", "Request metadata", "Request body", "Prompt", "Statement", "Parameters", "Client metadata", "Collector state"}:
            inputs.append(body)
        else:
            inputs.append(body)
    return inputs, outputs


def _causal_edges(cur: Any, since: datetime, trace_id: str | None) -> list[dict[str, Any]]:
    clauses = ["job.name = 'queue.job'", "job.started_at >= %s"]
    params: list[Any] = [since]
    if trace_id:
        clauses.append("job.trace_id = %s")
        params.append(trace_id)
    cur.execute(
        f"""
        SELECT origin.module_id, job.module_id, count(*),
               count(*) FILTER (WHERE job.status = 'error')
        FROM obs_spans job
        CROSS JOIN LATERAL jsonb_array_elements(job.links) link
        LEFT JOIN obs_spans origin
          ON origin.trace_id = link->>'trace_id' AND origin.span_id = link->>'span_id'
        WHERE {' AND '.join(clauses)} AND origin.module_id IS NOT NULL
        GROUP BY origin.module_id, job.module_id
        """,
        params,
    )
    return [
        {
            "source": row[0],
            "target": row[1],
            "kind": "causal",
            "evidence": "observed",
            "calls": int(row[2] or 0),
            "errors": int(row[3] or 0),
            "p95_ms": None,
        }
        for row in cur.fetchall()
        if row[0] != row[1]
    ]


def _unresolved_parents(cur: Any, since: datetime, trace_id: str | None) -> int:
    clauses = ["started_at >= %s", "parent_span_id IS NOT NULL", "parent_module_id IS NULL", "name <> 'db.connection'"]
    params: list[Any] = [since]
    if trace_id:
        clauses.append("trace_id = %s")
        params.append(trace_id)
    cur.execute(f"SELECT count(*) FROM obs_spans WHERE {' AND '.join(clauses)}", params)
    missing = int(cur.fetchone()[0] or 0)
    link_clauses = ["name = 'queue.job'", "started_at >= %s"]
    link_params: list[Any] = [since]
    if trace_id:
        link_clauses.append("job.trace_id = %s")
        link_params.append(trace_id)
    cur.execute(
        f"""
        SELECT count(*)
        FROM obs_spans job
        CROSS JOIN LATERAL jsonb_array_elements(job.links) link
        LEFT JOIN obs_spans origin
          ON origin.trace_id = link->>'trace_id' AND origin.span_id = link->>'span_id'
        WHERE {' AND '.join(link_clauses).replace('name', 'job.name').replace('started_at', 'job.started_at')}
          AND origin.span_id IS NULL
        """,
        link_params,
    )
    return missing + int(cur.fetchone()[0] or 0)


def _dropped(cur: Any, since: datetime, trace_id: str | None) -> tuple[int, int]:
    clauses = ["started_at >= %s", "is_entry"]
    params: list[Any] = [since]
    if trace_id:
        clauses.append("trace_id = %s")
        params.append(trace_id)
    cur.execute(
        f"""
        SELECT coalesce(sum(
                   CASE WHEN jsonb_typeof(attributes->'iris.db.spans_dropped') = 'number'
                        THEN (attributes->>'iris.db.spans_dropped')::float ELSE 0 END
               ), 0),
               coalesce(sum(
                   CASE WHEN jsonb_typeof(attributes->'iris.db.fetch_spans_dropped') = 'number'
                        THEN (attributes->>'iris.db.fetch_spans_dropped')::float ELSE 0 END
               ), 0)
        FROM obs_spans
        WHERE {' AND '.join(clauses)}
        """,
        params,
    )
    row = cur.fetchone()
    return int(_number(row[0])), int(_number(row[1]))


def _assemble(
    window_s: int,
    trace_id: str | None,
    *,
    source: str,
    partial: bool,
    retained_since: str | None,
    observed: dict[str, dict[str, Any]],
    call_edges: dict[tuple[str, str], dict[str, Any]],
    causal: list[dict[str, Any]],
    unresolved: int,
    dropped_db: int,
    dropped_fetch: int,
    memory_since: str | None = None,
) -> dict[str, Any]:
    active_by_module: dict[str, int] = {}
    active = []
    for item in hub.active_summaries():
        if trace_id is not None and item.get("trace_id") != trace_id:
            continue
        module_id = item.get("module_id")
        if module_id:
            active_by_module[module_id] = active_by_module.get(module_id, 0) + 1
        active.append(item)
    nodes = []
    seen: set[str] = set()
    for spec in catalog.specs():
        seen.add(spec.id)
        stats = observed.get(spec.id)
        if stats is None and spec.kind != "state":
            stats = _empty_stats()
            stats["rate_per_min"] = None
            stats["self_ms_total"] = None
        elif stats is not None:
            stats = dict(stats)
            stats.setdefault("rate_per_min", None)
        nodes.append(_node(spec, stats if spec.kind != "state" else None, active_by_module.get(spec.id, 0)))
    for module_id, stats in observed.items():
        if module_id in seen or not module_id:
            continue
        spec = catalog.lookup(module_id, stats.get("component"))
        nodes.append(_node(spec, stats, active_by_module.get(module_id, 0)))
    edges = []
    declared = {(edge.source, edge.target, edge.kind) for edge in catalog.declared_edges()}
    for edge in catalog.declared_edges():
        measured = call_edges.get((edge.source, edge.target)) if edge.kind == "call" else None
        edges.append({
            "source": edge.source,
            "target": edge.target,
            "kind": edge.kind,
            "evidence": "both" if measured else "declared",
            "calls": measured["calls"] if measured else None,
            "errors": measured["errors"] if measured else None,
            "p95_ms": measured["p95_ms"] if measured else None,
        })
    for (source_id, target_id), measured in call_edges.items():
        if (source_id, target_id, "call") in declared:
            continue
        edges.append({
            "source": source_id,
            "target": target_id,
            "kind": "call",
            "evidence": "observed",
            **measured,
        })
    edges.extend(causal)
    return {
        "at": _now(),
        "window_s": window_s,
        "trace_id": trace_id,
        "source": source,
        "partial": partial,
        "coverage": {
            "retained_since": retained_since,
            "memory_since": memory_since,
            "unresolved_parent_count": unresolved,
            "active_complete": hub.active_complete(),
            "dropped_db_spans": dropped_db,
            "dropped_db_fetch_spans": dropped_fetch,
        },
        "nodes": nodes,
        "edges": edges,
        "active": active,
    }


def _merge_calls(
    module_id: str,
    recent: list[dict[str, Any]],
    trace_id: str | None,
    *,
    source: str,
    partial: bool,
) -> dict[str, Any]:
    by_id = {(item.get("trace_id"), item.get("span_id")): item for item in recent}
    active = []
    for item in hub.active_summaries():
        if item.get("module_id") != module_id:
            continue
        if trace_id is not None and item.get("trace_id") != trace_id:
            continue
        key = (item.get("trace_id"), item.get("span_id"))
        if key in by_id:
            continue
        active.append(item)
    ordered = sorted(
        by_id.values(),
        key=lambda item: (item.get("started_at") or "", item.get("trace_id") or "", item.get("span_id") or ""),
        reverse=True,
    )
    return {
        "module_id": module_id,
        "at": _now(),
        "source": source,
        "partial": partial,
        "active": active,
        "recent": ordered,
    }


def _in_window(started_at: object, since: datetime) -> bool:
    if not isinstance(started_at, str):
        return False
    try:
        moment = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    return moment >= since


def storage_error(exc: BaseException) -> bool:
    return isinstance(exc, (psycopg2.Error, psycopg2.OperationalError))
