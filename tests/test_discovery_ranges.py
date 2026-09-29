"""Recorded-period discovery and replacement feedback with invented source passages."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from agent import discovery
from agent.database import db
from agent.episodes import EXTRACTION_VERSION
from agent.library import library_hash, load as load_library
from agent.readable import locate
from iris_api import app, get_current_user_id

PATTERN = "more-than-can-be-taken-back"
OTHER = "continuing-after-a-setback"


@pytest.fixture
def writing(test_user):
    today = date.today()
    user_id = test_user["id"]
    episodes, revisions = [], {}
    # The future/undated records distinguish all available writing from the recent windows.
    for index, days_ago in enumerate((0, 29, 30, 89, 90, None, -1)):
        on = today - timedelta(days=days_ago) if days_ago is not None else None
        situation = f"I returned to the garden bed number {index} after a hard morning"
        response = f"I chose a new planting order for garden bed number {index}"
        outcome = f"The work felt different for garden bed number {index}"
        passage = f"{situation}. {response}. {outcome}"
        entry_id = db.create_reflection(user_id, passage, reflection_date=on,
                                        undated=on is None)
        revisions[entry_id] = 1
        episodes.append({
            "actor": "self", "modality": "happened", "domain": "garden",
            "situation": situation, "response": response, "outcome": outcome,
            "demand": None, "information": None, "explanation": None,
            "occurredOn": on.isoformat() if on else None,
            "citations": [{"entryId": str(entry_id), "entryDate": on.isoformat() if on else None,
                           "sourceType": "reflection", "text": locate(passage, passage)}],
        })
    patterns = load_library()
    labels = {
        "accounts": len(episodes), "by": {PATTERN: "reader", OTHER: "reader"},
        "labels": {p.id: {} for p in patterns},
        "extractionVersion": EXTRACTION_VERSION, "libraryHash": library_hash(patterns),
    }
    for index in range(len(episodes)):
        labels["labels"][PATTERN][str(index)] = {
            "tone": "better" if index % 2 == 0 else "worse", "size": "small"}
        if index in (0, 1, 3, 5):
            labels["labels"][OTHER][str(index)] = {"tone": "worse", "size": "small"}
    discovery.load_reading(user_id, episodes, labels, source_revisions=revisions,
                           extraction_version=EXTRACTION_VERSION,
                           library_hash=labels["libraryHash"])
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    yield TestClient(app)
    app.dependency_overrides.clear()


def _pattern(client, period="all"):
    response = client.get("/api/patterns", params={"range": period})
    assert response.status_code == 200
    return next(p for p in response.json()["patterns"] if p["id"] == PATTERN)


def test_inclusive_recorded_period_and_source_coverage(writing):
    assert discovery.period_bounds("30d", date(2026, 9, 29)) == (date(2026, 8, 31), date(2026, 9, 29))
    assert discovery.period_bounds("90d", date(2026, 9, 29)) == (date(2026, 7, 2), date(2026, 9, 29))
    with pytest.raises(ValueError):
        discovery.period_bounds("yesterday")
    assert writing.get("/api/patterns", params={"range": "yesterday"}).status_code == 422
    assert writing.get(f"/api/patterns/{PATTERN}", params={"range": "yesterday"}).status_code == 422
    assert writing.get("/api/differences", params={"range": "yesterday"}).status_code == 422
    assert writing.get("/api/day-differences", params={"range": "yesterday"}).status_code == 422
    for period, expected, undated in (("all", 7, 1), ("30d", 2, 0), ("90d", 4, 0)):
        summary = _pattern(writing, period)
        detail = writing.get(f"/api/patterns/{PATTERN}", params={"range": period}).json()
        overall = writing.get("/api/patterns", params={"range": period}).json()["coverage"]
        assert summary["occasions"] == expected
        assert summary["entryCount"] == expected
        assert detail["coverage"] == summary["coverage"]
        assert overall["entryCount"] == expected
        assert detail["coverage"]["undatedAccountCount"] == undated
        assert summary["snapshot"] == detail["snapshot"]
        assert len(summary["examples"]) == 2
        assert {o["tone"] for o in summary["examples"]} == {"better", "worse"}
        assert all("recordedOn" in o and "occurredOn" not in o for o in detail["occasions"])
        assert all(o["citations"][0]["entryId"] for o in detail["occasions"])
    assert writing.get("/api/differences", params={"range": "30d"}).json()["coverage"]["entryCount"] == 2


def test_tone_note_clear_and_last_rejection_remain_inspectable(writing):
    before = _pattern(writing)
    selected = writing.get(f"/api/patterns/{PATTERN}").json()["occasions"][0]
    url = f"/api/patterns/{PATTERN}/occasions/{selected['id']}"
    assert writing.put(url, json={"verdict": None, "note": "  worth reconsidering  ",
                                  "ownerTone": "mixed"}).status_code == 200
    changed = _pattern(writing)
    assert changed["snapshot"] != before["snapshot"]
    account = next(o for o in writing.get(f"/api/patterns/{PATTERN}").json()["occasions"]
                   if o["id"] == selected["id"])
    assert (account["suggestedTone"], account["ownerTone"], account["tone"]) == (
        selected["suggestedTone"], "mixed", "mixed")
    assert account["ownerVerdict"] is None and account["verdictNote"] == "worth reconsidering"
    assert writing.put(url, json={"verdict": "no", "note": "worth reconsidering"}).status_code == 200
    assert next(o for o in writing.get(f"/api/patterns/{PATTERN}").json()["occasions"]
                if o["id"] == selected["id"])["ownerTone"] == "mixed"
    assert writing.put(url, json={"verdict": None, "note": "worth reconsidering",
                                  "ownerTone": None}).status_code == 200
    restored = next(o for o in writing.get(f"/api/patterns/{PATTERN}").json()["occasions"]
                    if o["id"] == selected["id"])
    assert restored["ownerTone"] is None and restored["tone"] == selected["suggestedTone"]
    for o in writing.get(f"/api/patterns/{PATTERN}").json()["occasions"]:
        assert writing.put(f"/api/patterns/{PATTERN}/occasions/{o['id']}",
                           json={"verdict": "no", "note": None}).status_code == 200
    dismissed = _pattern(writing)
    assert dismissed["occasions"] == 0 and dismissed["rejected"] == 7
    assert dismissed["examples"] == []
    assert len(writing.get(f"/api/patterns/{PATTERN}").json()["occasions"]) == 7
    assert dismissed["snapshot"] != changed["snapshot"]


def test_optional_judgment_does_not_erase_note_or_prefer_comparison_direction(writing, test_user):
    pattern_url = f"/api/patterns/{PATTERN}/verdict"
    difference_url = f"/api/differences/{PATTERN}/{OTHER}/verdict"
    for url in (pattern_url, difference_url):
        assert writing.put(url, json={"verdict": None, "note": "  maybe later  "}).status_code == 200
    assert _pattern(writing)["verdict"] == {"verdict": None, "note": "maybe later"}
    found = next(row for row in writing.get("/api/differences").json()["differences"]
                 if row["patternId"] == PATTERN and row["otherId"] == OTHER)
    assert found["verdict"] == {"verdict": None, "note": "maybe later"}
    a = {"patternId": PATTERN, "otherId": OTHER, "worse": 2, "worseTotal": 3,
         "better": 0, "betterTotal": 3, "verdict": {"verdict": None, "note": "maybe later"},
         "patternName": "One"}
    b = {**a, "patternId": OTHER, "otherId": PATTERN, "worse": 3,
         "verdict": None, "patternName": "Two"}
    assert discovery.one_per_pair([a, b]) == [b]
    assert writing.put(pattern_url, json={"verdict": "rings_true", "note": "maybe later"}).status_code == 200
    assert writing.put(pattern_url, json={"verdict": None, "note": "maybe later"}).status_code == 200
    assert _pattern(writing)["verdict"] == {"verdict": None, "note": "maybe later"}
    assert writing.put(pattern_url, json={"verdict": None, "note": "  "}).status_code == 200
    assert _pattern(writing)["verdict"] is None
    assert writing.put(difference_url, json={"verdict": None, "note": None}).status_code == 200
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT count(*) FROM difference_verdicts
                WHERE user_id = %s AND pattern_id = %s AND other_pattern_id = %s""",
            (test_user["id"], PATTERN, OTHER))
        assert cur.fetchone()[0] == 0
