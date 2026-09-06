"""
API contract test for the body slice.

By design there is no wearable/biometric data source, so the body source
endpoint reports the truth: no device connected. No biometrics are fabricated.
The BodyScreen itself stays on mocks for the demo. Single-user auth overridden.
"""

import pytest
from fastapi.testclient import TestClient

from iris_api import app, get_current_user_id


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_body_source_reports_no_device(client):
    r = client.get("/api/body/source")
    assert r.status_code == 200
    source = r.json()
    assert source["kind"] == "none"
    assert source["connected"] is False
    assert "label" in source
