"""Sensor review is the boundary between measured bytes and theme evidence."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.database import db
from agent.sensors.repository import SensorRepository
from iris_api import app, get_current_user_id

PIXEL_EXPORT = Path(__file__).parent / "fixtures" / "pixel_export_minimal.json"
LEGACY_HEALTH_EXPORT = Path(__file__).parent / "fixtures" / "fitbit_export_minimal.json"


@pytest.fixture
def sensor_client(test_user, monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_current_user_id,
                        lambda: test_user["id"])
    return TestClient(app), test_user["id"]


def _theme(user_id: int, *, status: str = "active") -> int:
    return db.create_theme(
        user_id, [1.0] + [0.0] * 1535, "Walking", "2026-09-20T00:00:00Z",
        "2026-09-20T00:00:00Z", status=status,
    )


def _intake(client: TestClient) -> int:
    response = client.post(
        "/api/mobile/sensor/intake",
        content=PIXEL_EXPORT.read_bytes(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["observation_count"] == 5
    batch_id = response.json()["batch_id"]
    detail = client.get(f"/api/sensors/batches/{batch_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "pending"
    assert detail.json()["parsed_payload"]["observations"]
    return batch_id


def test_review_admits_only_linked_capped_readings_and_retracts_them(sensor_client):
    client, user_id = sensor_client
    theme_id = _theme(user_id)
    batch_id = _intake(client)
    try:
        assert db.get_theme_occurrences(theme_id) == []
        assert client.get(f"/api/sensors/batches/{batch_id}").json()["status"] == "pending"
        links = {"pixel_location": theme_id, "pixel_steps": theme_id}
        result = client.post(f"/api/sensors/batches/{batch_id}/confirm",
                             json={"links": links, "observation_count": 5})
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "confirmed"
        assert result.json()["theme_links"] == links

        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM sensor_observations WHERE batch_id = %s", (batch_id,))
            assert cur.fetchone()[0] == 5
        listing = client.get("/api/sensors/batches")
        assert listing.status_code == 200
        summary = next(b for b in listing.json() if b["id"] == batch_id)
        assert summary["observation_count"] == 5
        assert "parsed_payload" not in summary  # listing omits full readings
        # Two location pings in one day count once; app usage remains unlinked.
        occurrences = db.get_theme_occurrences(theme_id)
        assert {row["source_type"] for row in occurrences} == {"pixel_location", "pixel_steps"}
        assert len(occurrences) == 2
        assert len(db.get_sensor_occurrences(theme_id)) == 2
        assert db.get_theme_by_id(theme_id)["occurrence_count"] == 2

        # A repeated request is harmless; changed links cannot rewrite the decision.
        again = client.post(f"/api/sensors/batches/{batch_id}/confirm",
                            json={"links": links, "observation_count": 5})
        assert again.status_code == 200, again.text
        assert len(db.get_theme_occurrences(theme_id)) == 2
        changed = client.post(f"/api/sensors/batches/{batch_id}/confirm",
                              json={"links": {"pixel_steps": theme_id}, "observation_count": 5})
        assert changed.status_code == 400, changed.text
        assert client.post(f"/api/sensors/batches/{batch_id}/reject").status_code == 400
    finally:
        deleted = client.delete(f"/api/sensors/batches/{batch_id}")
        assert deleted.status_code == 200, deleted.text
    assert db.get_theme_occurrences(theme_id) == []
    assert db.get_theme_by_id(theme_id)["occurrence_count"] == 0


def test_health_connect_sources_share_review_with_queued_legacy_fitbit(sensor_client):
    client, user_id = sensor_client
    theme_id = _theme(user_id)
    legacy_payload = json.loads(LEGACY_HEALTH_EXPORT.read_bytes())
    legacy_payload["device"] = "Fitbit (Health Connect)"
    legacy = json.dumps(legacy_payload).encode()
    first = client.post("/api/mobile/sensor/intake", content=legacy)
    assert first.status_code == 200, first.text
    batch_id = first.json()["batch_id"]
    try:
        # A pre-update outbox item keeps its exact bytes and delivery key.
        retry = client.post("/api/mobile/sensor/intake", content=legacy)
        assert retry.status_code == 200, retry.text
        assert retry.json()["batch_id"] == batch_id
        assert retry.json()["observation_count"] == 4

        google = json.loads(legacy)
        google["device"] = "Health Connect"
        google["tiers"]["heart_rate"] = [
            {"ts": "2026-09-23T08:00:00Z", "bpm": 59,
             "origin_package": "com.google.android.apps.fitness"},
        ]
        google["tiers"]["sleep"] = []
        google["tiers"]["spo2"] = []
        current = client.post("/api/mobile/sensor/intake", json=google)
        assert current.status_code == 200, current.text
        assert current.json()["batch_id"] == batch_id
        assert current.json()["observation_count"] == 5

        detail = client.get(f"/api/sensors/batches/{batch_id}").json()
        assert detail["source"] == "health_connect"
        assert detail["status"] == "pending"
        assert db.get_theme_occurrences(theme_id) == []
        readings = detail["parsed_payload"]["observations"]
        assert {row["source_type"] for row in readings} == {
            "health_connect_heart_rate", "health_connect_sleep", "health_connect_spo2",
        }
        assert next(row for row in readings if row.get("origin_package"))["origin_package"] == (
            "com.google.android.apps.fitness"
        )

        confirmed = client.post(
            f"/api/sensors/batches/{batch_id}/confirm",
            json={"links": {"health_connect_heart_rate": theme_id}, "observation_count": 5},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["theme_links"] == {"health_connect_heart_rate": theme_id}
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT source_type FROM sensor_observations WHERE batch_id = %s",
                        (batch_id,))
            assert {row[0] for row in cur.fetchall()} == {
                "health_connect_heart_rate", "health_connect_sleep", "health_connect_spo2",
            }
        occurrences = db.get_sensor_occurrences(theme_id)
        assert {(row["source_type"], row["value_num"]) for row in occurrences} == {
            ("health_connect_heart_rate", 134.0),
            ("health_connect_heart_rate", 59.0),
        }
    finally:
        SensorRepository().delete_batch(batch_id)
    assert db.get_theme_occurrences(theme_id) == []


def test_invalid_links_never_partially_confirm(sensor_client):
    client, user_id = sensor_client
    theme_id = _theme(user_id)
    inactive_id = _theme(user_id, status="candidate")
    batch_id = _intake(client)
    try:
        for links in (
            {"pixel_steps": theme_id, "unrecognized_source": theme_id},
            {"pixel_steps": theme_id, "pixel_location": inactive_id},
        ):
            response = client.post(f"/api/sensors/batches/{batch_id}/confirm",
                                   json={"links": links, "observation_count": 5})
            assert response.status_code == 400, response.text
            assert client.get(f"/api/sensors/batches/{batch_id}").json()["status"] == "pending"
            with db.connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM sensor_observations WHERE batch_id = %s", (batch_id,))
                assert cur.fetchone()[0] == 0
            assert db.get_theme_occurrences(theme_id) == []
    finally:
        SensorRepository().delete_batch(batch_id)


def test_phone_retry_reuses_staged_batch_until_owner_rejects(sensor_client):
    client, _ = sensor_client
    batch_id = _intake(client)
    retry = client.post(
        "/api/mobile/sensor/intake",
        content=PIXEL_EXPORT.read_bytes(),
        headers={"Content-Type": "application/json"},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["batch_id"] == batch_id
    try:
        detail = client.get(f"/api/sensors/batches/{batch_id}")
        assert detail.status_code == 200
        assert detail.json()["parsed_payload"]["observations"]
        assert detail.json()["status"] == "pending"
        assert client.post(f"/api/sensors/batches/{batch_id}/reject").json()["status"] == "rejected"
        assert client.post(f"/api/sensors/batches/{batch_id}/confirm",
                           json={"links": {}, "observation_count": 5}).status_code == 400
    finally:
        SensorRepository().delete_batch(batch_id)


def test_same_day_deliveries_share_a_batch_and_stale_confirm_is_409(sensor_client):
    client, _ = sensor_client
    first = json.loads(PIXEL_EXPORT.read_text())
    second = json.loads(PIXEL_EXPORT.read_text())
    second["tiers"]["steps"][0]["count"] = 9000
    headers = {"X-Iris-Sent-At": (datetime.now(UTC) - timedelta(seconds=30)).isoformat()}
    first_response = client.post("/api/mobile/sensor/intake", json=first, headers=headers)
    assert first_response.status_code == 200, first_response.text
    batch_id = first_response.json()["batch_id"]
    try:
        second_response = client.post("/api/mobile/sensor/intake", json=second, headers=headers)
        assert second_response.status_code == 200, second_response.text
        assert second_response.json()["batch_id"] == batch_id
        assert second_response.json()["observation_count"] == 10
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT clock_skew_seconds FROM sensor_batches WHERE id = %s", (batch_id,))
            assert abs(cur.fetchone()[0] - 30) <= 5
        stale = client.post(f"/api/sensors/batches/{batch_id}/confirm",
                            json={"links": {}, "observation_count": 5})
        assert stale.status_code == 409
        assert client.get(f"/api/sensors/batches/{batch_id}").json()["status"] == "pending"
        current = client.post(f"/api/sensors/batches/{batch_id}/confirm",
                              json={"links": {}, "observation_count": 10})
        assert current.status_code == 200, current.text
    finally:
        SensorRepository().delete_batch(batch_id)


def test_malformed_phone_payload_is_refused_or_dropped_not_500(sensor_client):
    client, _ = sensor_client
    bad = client.post("/api/mobile/sensor/intake",
                      json={"device": "Pixel 10a", "tiers": None})
    assert bad.status_code == 400
    dropped = client.post("/api/mobile/sensor/intake", json={
        "device": "Pixel 10a",
        "tiers": {"location": ["x", {"ts": "not-a-time", "lat": 1, "lon": 2}]},
    })
    assert dropped.status_code == 200, dropped.text
    batch_id = dropped.json()["batch_id"]
    try:
        assert dropped.json()["dropped_count"] == 2
        assert dropped.json()["observation_count"] == 0
    finally:
        SensorRepository().delete_batch(batch_id)


def test_listing_shows_every_pending_batch(sensor_client):
    client, _ = sensor_client
    pending = _intake(client)
    rejected: list[int] = []
    try:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("UPDATE sensor_batches SET received_at = now() - interval '60 days' "
                        "WHERE id = %s", (pending,))
            for index in range(51):
                cur.execute(
                    "INSERT INTO sensor_batches (source, payload_path, status) "
                    "VALUES ('pixel', %s, 'rejected') RETURNING id",
                    (f"listing:{index}",),
                )
                rejected.append(cur.fetchone()[0])
            conn.commit()
        listed = client.get("/api/sensors/batches").json()
        assert listed[0]["id"] == pending
        assert listed[0]["status"] == "pending"
        assert len([item for item in listed if item["id"] in rejected]) == 50
    finally:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_batches WHERE id = ANY(%s)",
                        ([pending, *rejected],))
            conn.commit()
