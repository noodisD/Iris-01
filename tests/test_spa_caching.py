"""The app page is revalidated on every load, so an update shows up at once.

The page names the current build's hashed assets. Served without a
Cache-Control header, browsers kept a copy by heuristic and went on running
the previous app after an update.
"""

from fastapi.testclient import TestClient

import iris_api


def test_the_app_page_is_never_served_from_a_stale_copy(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<!doctype html><title>IRIS</title>")
    monkeypatch.setattr(iris_api, "FRONTEND_DIST", str(tmp_path))
    response = TestClient(iris_api.app).get("/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
