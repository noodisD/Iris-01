"""Day features are a cache of confirmed readings. They never carry coordinates."""

import json
from datetime import date

from fastapi.testclient import TestClient

from agent.days.places import create_place
from agent.database import db
from agent.days.recompute import list_days, recompute
from agent.sensors.repository import SensorRepository
from agent.sensors.adapters import PixelAdapter
from iris_api import app, get_current_user_id


def _client(user_id: int) -> TestClient:
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    return TestClient(app)


def _stage(source: str, day: date, observations: list[dict], key: str) -> int:
    return SensorRepository().stage_delivery(
        {"source": source, "observations": observations, "dropped_count": 0,
         "raw_payload_hash": key},
        delivery_key=key, review_day=day, clock_skew_seconds=None,
    )


def test_days_never_return_coordinates_and_a_reject_does_not_change_them(test_user):
    user_id = test_user["id"]
    client = _client(user_id)
    staged: list[int] = []
    try:
        create_place(user_id, name="Kitchen", kind="home", lat=0.0, lon=0.0, radius_m=500)
        day = date(2026, 1, 2)
        home = _stage("pixel", day, [{
            "source_type": "pixel_location",
            "occurred_at": "2026-01-02T08:00:00Z",
            "lat": 0.0, "lon": 0.0, "accuracy_m": 12,
            "payload_hash": "home-fix",
        }], "days-home")
        staged.append(home)
        assert client.post(
            f"/api/sensors/batches/{home}/confirm",
            json={"links": {}, "observation_count": 1},
        ).status_code == 200
        before = list_days(user_id)
        assert before and before[0]["homeMinutes"] == 5

        office = _stage("pixel", day, [{
            "source_type": "pixel_location",
            "occurred_at": "2026-01-02T09:00:00Z",
            "lat": 0.02, "lon": 0.0, "accuracy_m": 12,
            "payload_hash": "office-fix",
        }], "days-office")
        staged.append(office)
        assert client.post(f"/api/sensors/batches/{office}/reject").status_code == 200
        after = list_days(user_id)
        assert after[0]["homeMinutes"] == before[0]["homeMinutes"]

        body = client.get("/api/days").json()
        banned = {"lat", "lon", "latitude", "longitude", "coordinates"}

        def walk(value):
            if isinstance(value, dict):
                assert not (banned & set(value))
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(body)
        assert "0.02" not in json.dumps(body)
        local_id = db.local_user_id()
        recompute(local_id, [day])
        assert not any(row["day"] == day.isoformat() for row in list_days(local_id))
        assert client.delete(f"/api/sensors/batches/{home}").status_code == 200
        assert not any(row["day"] == day.isoformat() for row in list_days(user_id))
    finally:
        repo = SensorRepository()
        for batch_id in staged:
            if repo.get_batch(batch_id) is not None:
                repo.delete_batch(batch_id)
        app.dependency_overrides.clear()

def test_timeline_upload_requires_review_then_confirm_range_builds_days(test_user):
    client = _client(test_user["id"])
    staged: list[int] = []
    try:
        document = {"semanticSegments": [
            {"startTime": "2042-04-03T08:00:00Z", "endTime": "2042-04-03T11:00:00Z",
             "visit": {"topCandidate": {
                 "semanticType": "HOME", "placeLocation": {"latLng": "0.0°, 0.0°"}}}},
            {"startTime": "2042-04-03T11:00:00Z", "endTime": "2042-04-03T17:00:00Z",
             "visit": {"topCandidate": {
                 "semanticType": "WORK", "placeLocation": {"latLng": "0.02°, 0.0°"}}}},
        ]}
        response = client.post(
            "/api/sensors/import/google-timeline",
            files={"file": ("timeline.json", json.dumps(document), "application/json")},
        )
        assert response.status_code == 200
        staged = response.json()["batches"]
        assert len(staged) == 1
        assert not any(day["day"] == "2042-04-03" for day in list_days(test_user["id"]))
        assert client.get("/api/places/suggestions").json() == {"home": None, "office": None}
        response = client.post(
            "/api/sensors/confirm-range",
            json={"start": "2042-04-03", "end": "2042-04-03", "links": {}},
        )
        assert response.status_code == 200
        assert response.json()["confirmed"] == staged
        suggested = client.get("/api/places/suggestions").json()
        assert suggested["home"]["lat"] == 0.0
        assert suggested["office"]["lat"] == 0.02
        assert client.post("/api/places", json={
            "name": "Office", "kind": "office", "lat": 0.02, "lon": 0.0, "radiusM": 500,
        }).status_code == 200
        day = next(day for day in client.get("/api/days").json()["days"] if day["day"] == "2042-04-03")
        assert day["officeMinutes"] == 360
        assert day["dayKind"] == "office"
    finally:
        repo = SensorRepository()
        for batch_id in staged:
            if repo.get_batch(batch_id) is not None:
                repo.delete_batch(batch_id)
        app.dependency_overrides.clear()

def test_date_only_step_counts_stay_on_the_owner_calendar_day(test_user):
    user_id = test_user["id"]
    db.upsert_app_settings(user_id, timezone="America/Los_Angeles")
    client = _client(user_id)
    batch_id = None
    try:
        parsed = PixelAdapter().parse_from_dict({
            "device": "Pixel", "tiers": {"steps": [{"date": "2041-01-02", "count": 123}]},
        })
        batch_id = SensorRepository().stage_delivery(
            parsed, delivery_key=f"day-steps-{user_id}", review_day=date(2041, 1, 2),
            clock_skew_seconds=None,
        )
        assert client.post(f"/api/sensors/batches/{batch_id}/confirm", json={
            "links": {}, "observation_count": 1,
        }).status_code == 200
        rows = {row["day"]: row for row in list_days(user_id)}
        assert rows["2041-01-02"]["steps"] == 123
        assert "2041-01-01" not in rows
    finally:
        if batch_id is not None:
            SensorRepository().delete_batch(batch_id)
        app.dependency_overrides.clear()
