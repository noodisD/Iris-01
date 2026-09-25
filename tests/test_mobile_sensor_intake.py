"""Live phone intake rejects unrecognised or incomplete source envelopes."""

from fastapi.testclient import TestClient

from iris_api import app


def test_intake_rejects_payload_with_no_device():
    with TestClient(app) as client:
        response = client.post("/api/mobile/sensor/intake", json={"tiers": {}})
    assert response.status_code == 400


def test_intake_rejects_unknown_device():
    with TestClient(app) as client:
        response = client.post("/api/mobile/sensor/intake", json={
            "device": "MysteryGadget", "tiers": {"steps": []},
        })
    assert response.status_code == 400
