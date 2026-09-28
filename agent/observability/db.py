"""Every application query runs through TracedCursor."""

from __future__ import annotations

import hashlib
import re
import time
from typing import Any

import psycopg2
import psycopg2.extensions

from agent.observability.content import MAX_SQL, json_attr, render_text
from agent.observability.hub import hub
from agent.observability.io import capture_input, capture_output
from agent.observability.tracing import (
    MAX_DB_FETCH_SPANS_PER_TRACE,
    MAX_DB_SPANS_PER_TRACE,
    current_budget,
    recording,
    span,
)
from opentelemetry.trace import Link, SpanContext, SpanKind, TraceFlags

_WHITESPACE = re.compile(r"\s+")
_LITERAL = re.compile(r"'(?:[^']|'')*'")
_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")
_VALUES = re.compile(r"(VALUES\s*\([^)]*\))(?:\s*,\s*\([^)]*\))+", re.IGNORECASE)
_KEYWORD = re.compile(r"^\s*(?:WITH\b.*?\b)?(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE|EXPLAIN)\b", re.IGNORECASE | re.DOTALL)
_TABLE = re.compile(
    r"\b(?:FROM|INTO|UPDATE|JOIN|TABLE)\s+"
    r"(?:ONLY\s+)?(?:IF\s+(?:NOT\s+)?EXISTS\s+)?"
    r"(?:[\w\"]+\.)?(\"[^\"]+\"|[\w]+)",
    re.IGNORECASE,
)


def statement_text(query: object, cursor: psycopg2.extensions.cursor) -> str:
    if isinstance(query, str):
        return query
    if isinstance(query, bytes):
        return query.decode("utf-8", errors="replace")
    as_string = getattr(query, "as_string", None)
    if callable(as_string):
        rendered = as_string(cursor)
        return rendered if isinstance(rendered, str) else str(rendered)
    return str(query)


def normalize(stmt: str) -> str:
    collapsed = _WHITESPACE.sub(" ", stmt).strip()
    collapsed = _LITERAL.sub("?", collapsed)
    collapsed = _NUMBER.sub("?", collapsed)
    collapsed = _VALUES.sub(r"\1", collapsed)
    return collapsed


def fingerprint(stmt: str) -> str:
    return hashlib.sha1(normalize(stmt).encode("utf-8")).hexdigest()[:16]


def summarize(stmt: str) -> str:
    match = _KEYWORD.search(stmt)
    keyword = match.group(1).upper() if match else "SQL"
    table = _TABLE.search(stmt)
    if table is None:
        return keyword
    name = table.group(1).strip('"')
    return f"{keyword} {name}"


class TracedCursor(psycopg2.extensions.cursor):
    def execute(self, query: Any, vars: Any = None) -> Any:  # noqa: A002
        self._clear_query()
        return self._traced(query, vars, many=False)

    def executemany(self, query: Any, vars_list: Any) -> None:  # type: ignore[override]
        self._clear_query()
        self._traced(query, vars_list, many=True)

    def fetchone(self) -> Any:
        row = psycopg2.extensions.cursor.fetchone(self)
        self._capture_fetch("fetchone", None, [] if row is None else [row])
        return row

    def fetchmany(self, size: int | None = None) -> list[Any]:
        if size is None:
            rows = psycopg2.extensions.cursor.fetchmany(self)
        else:
            rows = psycopg2.extensions.cursor.fetchmany(self, size)
        self._capture_fetch("fetchmany", size, rows)
        return rows

    def fetchall(self) -> list[Any]:
        rows = psycopg2.extensions.cursor.fetchall(self)
        self._capture_fetch("fetchall", None, rows)
        return rows

    def _clear_query(self) -> None:
        self._query_trace_id = None
        self._query_span_id = None
        self._query_table = None

    def _remember_query(self, current: Any, table: object) -> None:
        context = current.get_span_context()
        if not context.is_valid:
            return
        self._query_trace_id = f"{context.trace_id:032x}"
        self._query_span_id = f"{context.span_id:016x}"
        self._query_table = table if isinstance(table, str) and table else None

    def _capture_fetch(self, method: str, size: int | None, rows: list[Any]) -> None:
        trace_id = getattr(self, "_query_trace_id", None)
        span_id = getattr(self, "_query_span_id", None)
        if not trace_id or not span_id or not recording():
            return
        budget = current_budget()
        if budget is not None and budget.db_fetch_spans >= MAX_DB_FETCH_SPANS_PER_TRACE:
            budget.db_fetch_spans_dropped += 1
            return
        if budget is not None:
            budget.db_fetch_spans += 1
        table = getattr(self, "_query_table", None)
        name = f"db.fetch {table}" if table else "db.fetch"
        columns = [col[0] for col in self.description] if self.description else []
        positional = [list(row) for row in rows]
        link = Link(SpanContext(
            trace_id=int(trace_id, 16),
            span_id=int(span_id, 16),
            is_remote=False,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
        ))
        attrs: dict[str, object] = {
            "db.system.name": "postgresql",
            "iris.db.fetch_method": method,
            "iris.db.query_trace_id": trace_id,
            "iris.db.query_span_id": span_id,
        }
        if table:
            attrs["db.collection.name"] = table
        if size is not None:
            attrs["iris.db.fetch_size"] = size
        try:
            with span(name, "db", attrs, kind=SpanKind.CLIENT, links=[link]) as current:
                capture_input(
                    {"method": method, "size": size, "query_span_id": span_id},
                    span=current,
                )
                capture_output({"columns": columns, "rows": positional}, span=current)
        except Exception:
            hub.note_internal()

    def _traced(self, query: Any, vars: Any, *, many: bool) -> Any:  # noqa: A002
        if not recording():
            return self._delegate(query, vars, many)
        budget = current_budget()
        if budget is not None:
            budget.db_queries += 1
            if budget.db_spans >= MAX_DB_SPANS_PER_TRACE:
                started = time.perf_counter()
                try:
                    return self._delegate(query, vars, many)
                finally:
                    budget.db_ms += (time.perf_counter() - started) * 1000
            budget.db_spans += 1
        stmt = statement_text(query, self)
        parameters: object = vars
        batch_size = None
        if many and isinstance(vars, (list, tuple)):
            parameters = list(vars[:20])
            batch_size = len(vars)
        attrs: dict[str, object] = {
            "db.system.name": "postgresql",
            "db.namespace": self.connection.info.dbname if self.connection is not None else "",
            "db.operation.name": summarize(stmt).split(" ", 1)[0],
            "db.query.text": render_text(stmt, MAX_SQL),
            "db.query.parameters": json_attr(parameters, MAX_SQL),
            "iris.db.fingerprint": fingerprint(stmt),
            "iris.db.many": many,
        }
        collection = summarize(stmt)
        table = collection.split(" ", 1)[1] if " " in collection else None
        if table:
            attrs["db.collection.name"] = table
        if batch_size is not None:
            attrs["iris.db.batch_size"] = batch_size
        started = time.perf_counter()
        try:
            with span(collection, "db", attrs, kind=SpanKind.CLIENT) as current:
                self._remember_query(current, table)
                try:
                    result = self._delegate(query, vars, many)
                except psycopg2.Error as exc:
                    self._clear_query()
                    current.set_attribute("db.response.status_code", exc.pgcode or "")
                    raise
                else:
                    current.set_attribute("db.response.returned_rows", self.rowcount)
                    return result
        finally:
            if budget is not None:
                budget.db_ms += (time.perf_counter() - started) * 1000

    def _delegate(self, query: Any, vars: Any, many: bool) -> Any:  # noqa: A002
        if many:
            return psycopg2.extensions.cursor.executemany(self, query, vars)
        return psycopg2.extensions.cursor.execute(self, query, vars)
