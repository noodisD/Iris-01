"""Duplicate named places return an actionable client error, not a server failure."""

from fastapi.testclient import TestClient

from iris_api import app, get_current_user_id


def test_duplicate_create_and_rename_preserve_existing_places(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    client = TestClient(app)
    office = {"name": "Office", "kind": "office", "lat": 0.02, "lon": 0.0}
    studio = {"name": "Studio", "kind": "other", "lat": 0.04, "lon": 0.0}
    try:
        first = client.post("/api/places", json=office)
        second = client.post("/api/places", json=studio)
        assert first.status_code == second.status_code == 200
        assert client.post("/api/places", json=office).status_code == 400
        assert client.patch(f"/api/places/{second.json()['id']}", json=office).status_code == 400
        places = client.get("/api/places").json()["places"]
        assert [(place["id"], place["name"]) for place in places] == [
            (first.json()["id"], "Office"), (second.json()["id"], "Studio"),
        ]
    finally:
        app.dependency_overrides.clear()
