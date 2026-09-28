from unittest.mock import patch

from fastapi.testclient import TestClient

from agent.database import db
from agent.observability.queries import PG_STAT_HINT
from agent.observability.runtime import Probe
from agent.observability.store import sink


def _client(test_user):
    from iris_api import app, get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    return TestClient(app)


def test_an_exhausted_item_fails_the_queue(test_user, observatory):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO processing_queue (user_id, source_type, source_id, attempts)
               VALUES (%s, 'reflection', 1, 7)""",
            (test_user["id"],),
        )
        conn.commit()
    Probe().tick()
    body = _client(test_user).get("/api/observatory/overview").json()
    queue = next(item for item in body["components"] if item["id"] == "queue")
    assert queue["state"] == "failing"
    assert any("gave up after 7 attempts" in reason for reason in queue["reasons"])
    assert "recording_since" in body
    assert "last_journal_at" in body
    assert "last_chat_at" in body


def test_a_client_span_is_the_parent_of_the_server_span(test_user, observatory):
    client = _client(test_user)
    trace = "a" * 32
    span = "b" * 16
    posted = client.post("/api/observatory/client-events", json={
        "source": "web",
        "spans": [{
            "trace_id": trace, "span_id": span, "parent_span_id": None,
            "name": "POST /api/journal", "started_at_ms": 1_700_000_000_000,
            "duration_ms": 12, "status": "ok", "attributes": {},
        }],
    })
    assert posted.status_code == 200
    client.get("/health", headers={"traceparent": f"00-{trace}-{span}-01"})
    sink.flush_now()
    detail = client.get(f"/api/observatory/traces/{trace}").json()
    assert {item["span_id"] for item in detail["spans"]} >= {span}
    server = next(item for item in detail["spans"] if item["component"] == "http")
    assert server["parent_span_id"] == span


def test_a_malformed_trace_id_is_rejected(test_user):
    assert _client(test_user).get("/api/observatory/traces/not-a-trace").status_code == 422


def test_remote_doors_only_accept_client_events(test_user):
    from agent.config import settings
    from agent.mobile_auth import hash_token
    from scripts.serve_iris import lan_app, tailnet_app
    token = "a" * 64
    with patch.object(settings, "LAN_BIND_ENABLED", True), patch.object(
        settings, "MOBILE_BEARER_HASH", hash_token(token)
    ):
        phone = TestClient(lan_app, base_url="https://192.168.1.42",
                           headers={"Authorization": f"Bearer {token}"})
        assert phone.post("/api/observatory/client-events", json={"source": "android", "spans": []}).status_code == 200
        assert phone.get("/api/observatory/overview").status_code == 404
    tailnet = TestClient(tailnet_app, base_url="http://testserver")
    assert tailnet.get("/api/observatory/overview").status_code == 404


def test_error_traces_operations_and_database(test_user, observatory, captured_spans):
    from agent import observability as obs
    with obs.span("ok-one", "chat", entry=True):
        pass
    with obs.span("bad-one", "chat", entry=True) as span:
        obs.mark_error(span, RuntimeError("no"))
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 42")
        cur.fetchone()
    sink.flush_now()
    client = _client(test_user)
    traces = client.get("/api/observatory/traces?status=error&window=900").json()
    assert traces and all(item["status"] == "error" or item["errors"] for item in traces)
    assert any(item["name"] == "bad-one" for item in traces)
    assert all(item["name"] != "ok-one" for item in traces)
    operations = client.get("/api/observatory/operations?window=900").json()
    assert operations == sorted(operations, key=lambda item: item["self_ms_total"], reverse=True)
    assert sum(item["self_share"] for item in operations) <= 1.0001
    fingerprint = next(
        span.attributes["iris.db.fingerprint"] for span in captured_spans
        if span.attributes and span.attributes.get("iris.db.fingerprint")
    )
    database = client.get("/api/observatory/database?window=900").json()
    assert any(item["fingerprint"] == fingerprint for item in database["statements"])
    extension = database["pg_stat_statements"]
    assert extension["available"] is True or extension["hint"] == PG_STAT_HINT
