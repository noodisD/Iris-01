"""Measured day comparisons. Dates, scores and packages are invented."""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from agent import approved_context
from agent.database import db
from agent.day_differences import calculate, permutation_p, scores_from_rows
from iris_api import app, get_current_user_id

START = date(2040, 1, 1)


def _day(index: int, kind: str, *, steps: int | None = None,
         full_day: bool = False, coverage: float = 1.0) -> dict:
    return {
        "day": (START + timedelta(days=index)).isoformat(), "dayKind": kind,
        "locationCoverage": coverage, "commuteMinutes": 0,
        "steps": steps, "stepsFullDay": full_day,
        "screenMinutes": 0, "screenByCategory": {}, "sleepMinutes": None,
    }


def _groups(n: int = 5) -> tuple[list[dict], dict[str, dict[str, float]]]:
    rows = [_day(index, "office" if index < n else "home") for index in range(n * 2)]
    scores = {row["day"]: {"energy": 2.0 if index < n else 8.0}
              for index, row in enumerate(rows)}
    return rows, scores


def test_five_days_each_side_are_required_and_four_are_not():
    rows, scores = _groups()
    difference = next(row for row in calculate(rows, scores) if row["split"] == "office_home")
    assert (difference["leftCount"], difference["rightCount"]) == (5, 5)
    assert (difference["leftMean"], difference["rightMean"]) == (2.0, 8.0)
    assert difference["pValue"] <= 0.01
    assert "5 days" in difference["sentence"] and "office days" in difference["sentence"]
    assert not any(word in difference["sentence"].lower() for word in ("caused", "because", "means"))
    assert calculate(rows[:-1], scores) == []


def test_gap_of_point_nine_never_qualifies_even_with_a_strong_permutation():
    rows, scores = _groups(10)
    for index, row in enumerate(rows):
        scores[row["day"]]["energy"] = 4.1 if index < 10 else 5.0
    assert calculate(rows, scores) == []
    for index, row in enumerate(rows):
        if index >= 10:
            scores[row["day"]]["energy"] = 5.1
    assert len(calculate(rows, scores)) == 1


def test_median_ties_and_partial_step_days_are_not_a_side():
    rows = [_day(index, "other", steps=100 if index < 6 else 200, full_day=True)
            for index in range(12)]
    rows += [_day(index, "other", steps=150, full_day=True) for index in range(12, 16)]
    rows.append(_day(16, "other", steps=300, full_day=False))
    scores = {row["day"]: {"mood": 2.0 if index < 6 else 8.0}
              for index, row in enumerate(rows)}
    difference = next(d for d in calculate(rows, scores) if d["split"] == "steps")
    assert (difference["leftCount"], difference["rightCount"]) == (6, 6)
    assert difference["outcome"] == "mood"


def test_location_comparisons_exclude_low_coverage_days():
    rows, scores = _groups()
    for index in range(10, 16):
        row = _day(index, "office", coverage=0.49)
        rows.append(row)
        scores[row["day"]] = {"energy": 9.0}
    difference = next(d for d in calculate(rows, scores) if d["split"] == "office_home")
    assert (difference["leftCount"], difference["rightCount"]) == (5, 5)

def test_commute_needs_location_coverage_but_social_share_needs_screen_categories():
    rows, scores = _groups()
    for index, row in enumerate(rows):
        row["commuteMinutes"] = 60 if index < 5 else 10
        row["screenMinutes"] = 100
        row["screenByCategory"] = {"social": 100} if index < 5 else {"other": 100}
    unmeasured = _day(10, "office", coverage=0.49)
    unmeasured["commuteMinutes"] = 1000
    rows.append(unmeasured)
    scores[unmeasured["day"]] = {"energy": 9.0}
    differences = calculate(rows, scores)
    for split in ("commute", "social_share"):
        comparison = next(row for row in differences if row["split"] == split)
        assert (comparison["leftCount"], comparison["rightCount"]) == (5, 5)


def test_two_thousand_seeded_shuffles_are_reproducible():
    left, right = [2.0] * 5, [8.0] * 5
    first = permutation_p(left, right, seed=23)
    assert first == permutation_p(left, right, seed=23) == 0.0069965017491254375
    assert first <= 0.01


def test_only_explicit_checkin_metrics_count_and_multiple_entries_make_one_day():
    scores = scores_from_rows([
        (START, 4, {"mood": {"value": 3, "scale": 10, "source": "checkin"},
                    "stress": {"value": 6, "scale": 10, "source": "checkin"},
                    "sleep_quality": {"value": 7, "source": "checkin"}}),
        (START, 6, {"mood": {"value": 5, "scale": 10, "source": "checkin"},
                    "focus": {"value": 8, "source": "checkin"}}),
        (START + timedelta(days=1), None,
         {"mood": {"value": 9, "source": "inferred"}}),
    ])
    assert scores == {START.isoformat(): {
        "energy": 5.0, "mood": 4.0, "stress": 6.0, "sleep_quality": 7.0, "focus": 8.0,
    }}


def test_verdict_survives_disappearing_difference_and_only_rings_true_reaches_chat(test_user):
    user_id = test_user["id"]
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    client = TestClient(app)
    try:
        with db.connection() as conn, conn.cursor() as cur:
            for index in range(10):
                day = START + timedelta(days=index)
                kind = "office" if index < 5 else "home"
                cur.execute(
                    """INSERT INTO day_features
                       (user_id, day, day_kind, office_minutes, home_minutes, location_coverage)
                       VALUES (%s, %s, %s, %s, %s, 1.0)""",
                    (user_id, day, kind, 540 if index < 5 else 0, 540 if index >= 5 else 0),
                )
            conn.commit()
        for index in range(10):
            db.create_reflection(user_id, content="", reflection_date=START + timedelta(days=index),
                                 energy_level=2 if index < 5 else 8)

        body = client.get("/api/day-differences")
        assert body.status_code == 200
        rows = body.json()["differences"]
        assert len(rows) == 1 and rows[0]["split"] == "office_home"
        assert (rows[0]["leftCount"], rows[0]["rightCount"]) == (5, 5)
        assert "lat" not in str(body.json()).lower()
        sentence = rows[0]["sentence"]
        rejected = client.put("/api/day-differences/energy/office_home/verdict",
                              json={"verdict": "does_not"})
        assert rejected.status_code == 200
        assert sentence not in approved_context.approved_context(user_id)
        accepted = client.put("/api/day-differences/energy/office_home/verdict",
                              json={"verdict": "rings_true"})
        assert accepted.status_code == 200
        block = approved_context.approved_context(user_id)
        assert sentence in block and "never causes" in block
        assert client.get("/api/day-differences").json()["differences"][0]["verdict"]["verdict"] == "rings_true"
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM day_features WHERE user_id = %s AND day = %s",
                        (user_id, START + timedelta(days=9)))
            conn.commit()
        assert client.get("/api/day-differences").json()["differences"] == []
        assert sentence not in approved_context.approved_context(user_id)
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT verdict FROM day_difference_verdicts WHERE user_id = %s AND outcome = 'energy' AND split = 'office_home'", (user_id,))
            assert cur.fetchone()[0] == "rings_true"
        assert client.put("/api/day-differences/energy/unknown/verdict",
                          json={"verdict": "rings_true"}).status_code == 404
    finally:
        app.dependency_overrides.clear()
