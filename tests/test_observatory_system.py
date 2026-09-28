"""Behavioral boundaries for the module map, not source-text checks."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agent.database import db
from agent.observability.hub import hub
from agent.observability.store import sink


def _client(test_user):
    from iris_api import app, get_current_user_id

    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    return TestClient(app)


def _io(span, side: str):
    raw = span.attributes.get(f"iris.io.{side}")
    assert raw is not None, side
    if span.attributes.get(f"iris.io.{side}.format") == "json":
        return json.loads(raw)
    return raw


def test_input_is_snapshotted_before_mutation(observatory, captured_spans):
    from agent.observability.tracing import traced

    @traced("sample.mutate", "system")
    def mutate(item):
        item["nested"]["n"] = 2
        return item["nested"]["n"]

    assert mutate({"nested": {"n": 1}}) == 2
    span = next(item for item in captured_spans if item.name == "sample.mutate")
    assert _io(span, "input")["item"]["nested"]["n"] == 1
    assert _io(span, "output") == 2


def test_render_limits_and_literal_values(observatory, captured_spans):
    from agent.observability.io import capture_input, render_io
    from agent.observability.tracing import traced
    import agent.observability.tracing as tracing

    shared = {"n": 1}
    loop = {}
    loop["self"] = loop
    rendered = render_io({"left": shared, "right": shared, "loop": loop})
    parsed = json.loads(rendered.text)
    assert parsed["left"] == parsed["right"] == {"n": 1}
    assert parsed["loop"]["self"] == "<cycle>"
    assert "cycle" in (rendered.reason or "")
    assert "<vector" not in render_io({"ids": list(range(50))}).text
    assert json.loads(render_io({"ids": list(range(50))}).text)["ids"] == list(range(50))

    class Bad:
        def __repr__(self):
            raise RuntimeError("repr")

        def __str__(self):
            raise RuntimeError("str")

    opaque = render_io({"obj": Bad()})
    assert "repr" not in opaque.text and "Bad" in opaque.text
    huge = render_io("é" * 300_000)
    assert len(huge.text) <= 262_144 and huge.truncated

    @traced("sample.literal", "system")
    def literal(kind):
        return {"none": None, "false": False, "zero": 0, "empty": ""}[kind]

    for kind, expected in (("none", None), ("false", False), ("zero", 0), ("empty", "")):
        captured_spans.clear()
        literal(kind)
        assert _io(captured_spans[-1], "output") == expected

    real = tracing.capture_input

    def boom(*_args, **_kwargs):
        raise RuntimeError("capture")

    tracing.capture_input = boom
    try:
        @traced("sample.fail", "system")
        def app():
            raise RuntimeError("app")

        with pytest.raises(RuntimeError, match="app"):
            app()
    finally:
        tracing.capture_input = real
    assert tracing.capture_input is capture_input


def test_confidence_gate_records_before_and_after(observatory, captured_spans):
    from agent.pipeline_orchestrator import AnalysisPipeline, confidence_gate

    pipeline = AnalysisPipeline(1)
    pipeline.register_gate("confidence", confidence_gate)
    kept = pipeline.gate(
        [
            {"confidence_level": "high", "engine_name": "fake", "label": "kept", "pattern_key": "k"},
            {"confidence_level": "low", "engine_name": "fake", "label": "dropped", "pattern_key": "d"},
        ],
        {"min_confidence": "medium"},
    )
    assert [item["label"] for item in kept] == ["kept"]
    span = next(item for item in captured_spans if item.name == "admission.confidence")
    recorded = _io(span, "input")
    assert {item["label"] for item in recorded["findings"]} == {"kept", "dropped"}
    output = _io(span, "output")
    assert [item["label"] for item in output["findings"]] == ["kept"]
    assert output["reasons"]["low_confidence"] == 1

    def explode(findings, _context):
        findings.append({"mutated": True})
        raise RuntimeError("closed")

    pipeline.register_gate("explode", explode)
    captured_spans.clear()
    assert pipeline.gate([{"label": "x"}], {}) == []
    failed = next(item for item in captured_spans if item.name == "admission.explode")
    closed = _io(failed, "output")
    assert closed["findings"] == [] and closed["failed_closed"] is True
    assert failed.status.status_code.name == "ERROR"


def test_fetch_returns_only_consumed_rows(observatory, captured_spans):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT generate_series(1, 3) AS n")
        assert cur.fetchone() == (1,)
        assert cur.fetchmany(1) == [(2,)]
        assert cur.fetchall() == [(3,)]
        cur.execute("SELECT 1 AS n, 2 AS n")
        duplicate = cur.fetchone()
        assert duplicate == (1, 2)
        cur.execute("SELECT %s::int", (9,))
        assert cur.fetchone() == (9,)
    fetches = [span for span in captured_spans if span.name.startswith("db.fetch")]
    portions = [_io(span, "output")["rows"] for span in fetches[:3]]
    assert portions == [[[1]], [[2]], [[3]]]
    execute = next(span for span in captured_spans if span.attributes and span.attributes.get("db.query.text", "").startswith("SELECT generate_series"))
    linked = {span.attributes.get("iris.db.query_span_id") for span in fetches[:3]}
    assert linked == {f"{execute.context.span_id:016x}"}
    duplicate_fetch = next(span for span in fetches if _io(span, "output")["columns"] == ["n", "n"])
    assert _io(duplicate_fetch, "output")["rows"] == [[1, 2]]


def test_system_snapshot_keeps_idle_modules(test_user, observatory):
    sink.flush_now()
    body = _client(test_user).get("/api/observatory/system?window=3600").json()
    ids = {node["id"] for node in body["nodes"]}
    assert "chat.context" in ids
    idle = next(node for node in body["nodes"] if node["id"] == "chat.narrative")
    assert idle["stats"]["p50_ms"] is None
    assert body["source"] == "database"
    assert any(edge["kind"] == "flow" and edge["evidence"] == "declared" for edge in body["edges"])


def test_migration_backfill_does_not_invent_io(observatory):
    sql = Path("migrations/0040_observatory_modules.sql").read_text()
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TEMP TABLE obs_spans (LIKE public.obs_spans INCLUDING DEFAULTS)
            ON COMMIT DROP
            """
        )
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'obs_spans' AND table_schema LIKE 'pg_temp%'
            """
        )
        present = {row[0] for row in cur.fetchall()}
        if "module_id" in present:
            cur.execute("ALTER TABLE obs_spans DROP COLUMN module_id")
        if "parent_module_id" in present:
            cur.execute("ALTER TABLE obs_spans DROP COLUMN parent_module_id")
        cur.execute(
            """
            INSERT INTO obs_spans (
                trace_id, span_id, parent_span_id, name, component, kind, is_entry, started_at,
                duration_ms, self_ms, status, attributes
            ) VALUES
              ('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'bbbbbbbbbbbbbbbb', NULL, 'chat.context',
               'chat', 'internal', true, now(), 1, 1, 'ok', '{}'),
              ('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'cccccccccccccccc', 'bbbbbbbbbbbbbbbb',
               'db.connection', 'db', 'client', false, now(), 1, 1, 'ok', '{}'),
              ('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'dddddddddddddddd', 'cccccccccccccccc',
               'SELECT reflections', 'db', 'client', false, now(), 1, 1, 'ok',
               '{"db.collection.name": "reflections"}')
            """
        )
        for statement in [part.strip() for part in sql.split(";") if part.strip()]:
            cur.execute(statement)
        cur.execute(
            """
            SELECT span_id, module_id, parent_module_id, attributes
            FROM obs_spans ORDER BY span_id
            """
        )
        rows = {row[0]: row for row in cur.fetchall()}
        assert rows["bbbbbbbbbbbbbbbb"][1] == "chat.context"
        assert rows["dddddddddddddddd"][1] == "db:reflections"
        assert rows["dddddddddddddddd"][2] == "chat.context"
        assert "iris.io.input" not in (rows["bbbbbbbbbbbbbbbb"][3] or {})
        conn.rollback()


def test_held_span_is_inspectable_before_flush(observatory):
    from agent.observability.tracing import span

    held = span("chat.turn", "chat")
    current = held.__enter__()
    current.set_attribute("iris.io.input", "{}")
    active = hub.active_summaries()
    assert any(item["name"] == "chat.turn" and item["status"] == "running" for item in active)
    trace_id = f"{current.get_span_context().trace_id:032x}"
    span_id = f"{current.get_span_context().span_id:016x}"
    detail = hub.invocation_record(trace_id, span_id)
    assert detail is not None and detail["status"] == "running"
    held.__exit__(None, None, None)
    assert all(item["span_id"] != span_id for item in hub.active_summaries())
    cached = hub.invocation_record(trace_id, span_id)
    assert cached is not None and cached["status"] == "ok"


def test_stream_reply_does_not_persist_a_cancelled_partial(observatory, captured_spans):
    from agent.core import PersonalAICompanion

    class Intel:
        def stream(self, **_kwargs):
            yield "partial"
            yield " reply"

    companion = PersonalAICompanion.__new__(PersonalAICompanion)
    companion.user_id = 7
    companion.intelligence = Intel()
    companion.memory = type("Memory", (), {"add_message": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("persisted"))})()
    generator = companion.stream_reply([{"role": "user", "content": "hi"}], "prompt")
    box = {}

    def advance():
        box["text"] = next(generator)

    worker = threading.Thread(target=advance)
    worker.start()
    worker.join()
    assert box["text"] == "partial"
    generator.close()
    spans = [item for item in captured_spans if item.name == "chat.stream_reply"]
    assert len(spans) == 1
    assert spans[0].attributes.get("iris.io.output.partial") is True
    assert spans[0].attributes.get("iris.stream.cancelled") is True
    assert spans[0].end_time is not None


def test_new_routes_reject_bad_ids_and_remote_doors(test_user):
    client = _client(test_user)
    assert client.get("/api/observatory/system?window=12").status_code == 422
    assert client.get("/api/observatory/spans/nope/abcd").status_code == 422
    from agent.config import settings
    from agent.mobile_auth import hash_token
    from scripts.serve_iris import lan_app, tailnet_app

    token = "b" * 64
    with patch.object(settings, "LAN_BIND_ENABLED", True), patch.object(
        settings, "MOBILE_BEARER_HASH", hash_token(token)
    ):
        phone = TestClient(lan_app, base_url="https://192.168.1.42", headers={"Authorization": f"Bearer {token}"})
        assert phone.get("/api/observatory/system").status_code == 404
        assert phone.get("/api/observatory/module-calls?module_id=chat.context").status_code == 404
        assert phone.get("/api/observatory/spans/" + "a" * 32 + "/" + "b" * 16).status_code == 404
    assert TestClient(tailnet_app, base_url="http://testserver").get("/api/observatory/system").status_code == 404
