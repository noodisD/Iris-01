import json
import logging
import time
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from openai import BadRequestError

from agent.database import db
from agent.observability.hub import hub
from agent.observability.store import sink


def _client(test_user):
    from iris_api import app, get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    client = TestClient(app)
    return client


def _spans(captured, name):
    return [span for span in captured if span.name == name or span.name.startswith(name)]


def test_http_span_uses_the_route_template(test_user, captured_spans):
    client = _client(test_user)
    response = client.get("/api/ideas/12345")
    client.app.dependency_overrides.clear()
    span = next(item for item in captured_spans if item.name.startswith("GET /api/ideas/"))
    assert span.name == "GET /api/ideas/{idea_id}"
    assert span.attributes["http.response.status_code"] == response.status_code == 404
    assert span.status.status_code.name == "UNSET" or span.status.status_code.name == "OK"
    assert response.headers["x-iris-trace"] == f"{span.context.trace_id:032x}"


def test_incoming_traceparent_is_the_parent(test_user, captured_spans):
    client = _client(test_user)
    trace = "0123456789abcdef0123456789abcdef"
    parent = "fedcba9876543210"
    client.get("/health", headers={"traceparent": f"00-{trace}-{parent}-01"})
    span = next(item for item in captured_spans if item.name.startswith("GET "))
    assert f"{span.context.trace_id:032x}" == trace
    assert span.parent is not None and f"{span.parent.span_id:016x}" == parent


def test_json_body_is_stored(test_user, captured_spans):
    client = _client(test_user)
    client.post("/api/journal", json={"lines": ["salt"], "energy": 3})
    span = next(item for item in captured_spans if item.name.startswith("POST /api/journal"))
    assert "salt" in span.attributes["iris.http.request_body"]


def test_observatory_reads_are_not_traced(test_user, captured_spans):
    client = _client(test_user)
    before = len(captured_spans)
    client.get("/api/observatory/overview")
    assert captured_spans[before:] == []


def test_sql_span_carries_statement_params_and_parent(observatory, captured_spans):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT %s::int + 1", (41,))
        assert cur.fetchone()[0] == 42
    query = next(span for span in captured_spans if span.attributes and "db.query.text" in span.attributes)
    connection = next(span for span in captured_spans if span.name == "db.connection")
    assert "41" in query.attributes["db.query.parameters"]
    assert query.attributes["db.response.returned_rows"] == 1
    assert query.parent.span_id == connection.context.span_id


def test_a_vector_parameter_is_summarised(observatory, captured_spans):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT %s::text", ([0.1] * 1536,))
        cur.fetchone()
    query = next(span for span in captured_spans if "db.query.parameters" in (span.attributes or {}))
    assert "<vector dim=1536>" in query.attributes["db.query.parameters"]


def test_missing_table_is_an_error_span(observatory, captured_spans):
    with db.connection() as conn, conn.cursor() as cur:
        with pytest.raises(Exception):
            cur.execute("SELECT * FROM no_such_table")
    error = next(span for span in captured_spans if span.status.status_code.name == "ERROR")
    assert error.attributes["db.response.status_code"] == "42P01"


def test_a_trace_drops_sql_spans_past_the_budget(observatory, captured_spans):
    from agent import observability as obs
    with obs.span("budget", "system", entry=True):
        with db.connection() as conn, conn.cursor() as cur:
            for _ in range(1005):
                cur.execute("SELECT 1")
    entry = next(span for span in captured_spans if span.name == "budget")
    sql = [span for span in captured_spans if span.attributes and span.attributes.get("db.system.name") == "postgresql"]
    assert len(sql) == 1000
    assert entry.attributes["iris.db.queries"] == 1005
    assert entry.attributes["iris.db.spans_dropped"] == 5


def test_a_queued_job_links_to_the_request(test_user, observatory, captured_spans):
    from agent import observability as obs
    from agent import work_queue
    with obs.span("cause", "http", entry=True) as cause:
        work_queue.enqueue("transcription", 9_999_999, test_user["id"])
        trace = f"{cause.context.trace_id:032x}"
    work_queue.process_due()
    job = next(span for span in captured_spans if span.name == "queue.job" and span.attributes.get("iris.queue.source_id") == 9_999_999)
    assert job.parent is None
    assert f"{job.links[0].context.trace_id:032x}" == trace
    assert job.attributes["iris.queue.outcome"] == "retired"
    assert job.attributes["iris.queue.attempt"] == 1


def test_a_failed_job_is_scheduled_or_exhausted(test_user, observatory, captured_spans, monkeypatch):
    from agent import work_queue
    monkeypatch.setattr(work_queue, "_run", MagicMock(side_effect=RuntimeError("down")))
    work_queue.enqueue("transcription", 9_999_998, test_user["id"])
    work_queue.process_due()
    job = next(span for span in captured_spans if span.name == "queue.job")
    assert job.attributes["iris.queue.outcome"] == "retry_scheduled"
    assert job.attributes["iris.queue.retry_in_s"] == 60
    assert job.status.status_code.name == "ERROR"
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE processing_queue SET attempts = 6, next_attempt_at = now() WHERE source_id = %s", (9_999_998,))
        conn.commit()
    captured_spans.clear()
    work_queue.process_due()
    exhausted = next(span for span in captured_spans if span.name == "queue.job")
    assert exhausted.attributes["iris.queue.outcome"] == "exhausted"


def test_stream_records_usage_and_the_reply(observatory, captured_spans):
    from agent.intelligence import Intelligence
    intel = Intelligence.__new__(Intelligence)
    intel.base_url = ""
    intel.model = "gpt-test"
    intel.openai_client = MagicMock()
    usage = MagicMock()
    usage.prompt_tokens = 12
    usage.completion_tokens = 2
    usage.completion_tokens_details = None
    usage.prompt_tokens_details = None
    def chunk(text=None, used=None):
        choice = MagicMock()
        choice.delta.content = text
        choice.finish_reason = None
        item = MagicMock()
        item.choices = [] if text is None else [choice]
        item.usage = used
        return item
    seen = {}
    def create(**kwargs):
        seen.update(kwargs)
        return iter([chunk("Hel"), chunk("lo"), chunk(used=usage)])
    intel.openai_client.chat.completions.create.side_effect = create
    assert "".join(intel.stream([{"role": "user", "content": "hi"}], "sys")) == "Hello"
    span = next(item for item in captured_spans if item.name == "llm.chat_stream")
    assert span.attributes["gen_ai.usage.input_tokens"] == 12
    assert span.attributes["gen_ai.usage.output_tokens"] == 2
    assert "iris.llm.ttft_ms" in span.attributes
    assert span.attributes["iris.llm.output"] == "Hello"
    assert seen["stream_options"] == {"include_usage": True}


def test_temperature_retry_is_two_chat_spans(observatory, captured_spans):
    from agent.intelligence import Intelligence
    intel = Intelligence.__new__(Intelligence)
    intel.base_url = "http://local"
    intel.model = "gpt-test"
    intel.openai_client = MagicMock()
    ok = MagicMock()
    ok.usage = None
    ok.choices = [MagicMock()]
    ok.choices[0].message.content = "kept"
    intel.openai_client.chat.completions.create.side_effect = [
        BadRequestError("temperature unsupported", response=MagicMock(status_code=400), body=None),
        ok,
    ]
    assert intel._chat_openai([{"role": "user", "content": "hi"}], "sys") == "kept"
    chats = [span for span in captured_spans if span.name == "llm.chat"]
    assert len(chats) == 2
    assert chats[0].status.status_code.name == "ERROR"


def test_embeddings_record_tokens_and_dimension(observatory, captured_spans, monkeypatch):
    from agent import pipeline
    response = MagicMock()
    response.data = [MagicMock(embedding=[0.0] * 1536)]
    response.usage = MagicMock(prompt_tokens=7, completion_tokens=None)
    monkeypatch.setattr(pipeline.openai.embeddings, "create", lambda **_kwargs: response)
    assert len(pipeline.generate_embedding("salt")) == 1536
    span = next(item for item in captured_spans if item.name == "llm.embeddings")
    assert span.attributes["gen_ai.usage.input_tokens"] == 7
    assert span.attributes["iris.llm.output"] == "<vector dim=1536>"


def test_confidence_gate_and_fail_closed(observatory, captured_spans):
    from agent.pipeline_orchestrator import AnalysisPipeline, confidence_gate
    pipeline = AnalysisPipeline(1)
    pipeline.register_gate("confidence", confidence_gate)
    findings = [
        {"confidence_level": "low", "engine_name": "fake", "label": "a"},
        {"confidence_level": "high", "engine_name": "fake", "label": "b"},
        {"confidence_level": "high", "engine_name": "fake", "label": "c"},
    ]
    kept = pipeline.gate(findings, {"min_confidence": "medium"})
    assert len(kept) == 2
    span = next(item for item in captured_spans if item.name == "admission.confidence")
    assert span.attributes["iris.admission.in"] == 3
    assert span.attributes["iris.admission.out"] == 2
    reasons = span.attributes["iris.admission.reasons"]
    if isinstance(reasons, str):
        reasons = json.loads(reasons)
    assert reasons == {"low_confidence": 1}
    def boom(_findings, _context):
        raise RuntimeError("no")
    pipeline.register_gate("boom", boom)
    captured_spans.clear()
    assert pipeline.gate([{"confidence_level": "high"}], {}) == []
    failed = next(item for item in captured_spans if item.name == "admission.boom")
    assert failed.attributes["iris.admission.failed_closed"] is True
    assert failed.status.status_code.name == "ERROR"


def test_a_warning_is_a_span_event_and_a_log_row(observatory, captured_spans):
    from agent import observability as obs
    with obs.span("drill", "system"):
        logging.getLogger("agent.test").warning("drill")
    assert any(event.name == "log" for span in captured_spans for event in span.events)
    sink.flush_now()
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT trace_id FROM obs_logs WHERE message = 'drill'")
        assert cur.fetchone()[0] == f"{captured_spans[0].context.trace_id:032x}"


def test_log_files_include_the_trace_id(tmp_path, captured_spans):
    from agent.logging_config import configure_logging
    from agent import observability as obs
    agent_logger = logging.getLogger("agent")
    for handler in list(agent_logger.handlers):
        agent_logger.removeHandler(handler)
    configure_logging(str(tmp_path))
    with obs.span("logged", "system") as span:
        logging.getLogger("agent").info("trace drill")
        trace = f"{span.context.trace_id:032x}"
    assert f"[{trace}]" in (tmp_path / "iris.log").read_text()


def test_self_time_excludes_the_child(observatory):
    from agent import observability as obs
    with obs.span("parent", "system"):
        with obs.span("child", "system"):
            time.sleep(0.05)
    parent = next(item for item in hub.recent_spans(20) if item["name"] == "parent")
    assert parent["self_ms"] <= parent["duration_ms"] - 45


def test_prune_keeps_only_the_retention_window(observatory):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO obs_spans (
                   trace_id, span_id, name, component, kind, is_entry, started_at,
                   duration_ms, self_ms, status, module_id
               ) VALUES (%s, %s, 'old', 'system', 'internal', false, now() - interval '40 days', 1, 1, 'ok', 'old'),
                        (%s, %s, 'new', 'system', 'internal', false, now(), 1, 1, 'ok', 'new')""",
            ("a" * 32, "b" * 16, "c" * 32, "d" * 16),
        )
        conn.commit()
    sink.prune()
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT name FROM obs_spans ORDER BY name")
        assert [row[0] for row in cur.fetchall()] == ["new"]
