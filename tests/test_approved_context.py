"""Chat sees what the owner approved, and nothing still waiting for them.

Every idea, occasion, decision and reading here is invented.
"""

from __future__ import annotations

from datetime import date

from agent import approved_context as approved
from agent import decisions, discovery
from agent.database import db
from tests.test_api_patterns import LABELS, READING, SETBACK, X
from tests.test_ideas_meaning import GARDEN, KITCHEN, SHARED, framework  # noqa: F401 - fixture


def test_accepted_ideas_and_their_accepted_links_are_in_the_block(framework):  # noqa: F811
    client, script, ids = framework
    script.pairs = [{"a": ids[GARDEN], "b": ids[KITCHEN], "rationale": SHARED}]
    client.post("/api/ideas/meanings/discover")
    block_before = approved.approved_context(_user(client))
    assert GARDEN in block_before and "means the same as" not in block_before  # a proposal is not approved

    link = next(item for item in client.get("/api/ideas/review").json()["links"])
    client.post(f"/api/ideas/links/{link['id']}/confirm")
    block = approved.approved_context(_user(client))
    assert "[markets, endorsed]" in block
    assert "means the same as" in block


def _user(client) -> int:
    from iris_api import app, get_current_user_id
    return app.dependency_overrides[get_current_user_id]()


def test_only_insights_and_patterns_that_ring_true_are_in_the_block(test_user):
    discovery.load_reading(test_user["id"], READING, LABELS)
    block = approved.approved_context(test_user["id"])
    assert "## Differences in outcome they said ring true" in block and "None yet." in block

    discovery.set_difference_verdict(test_user["id"], X, SETBACK, "rings_true")
    discovery.set_pattern_verdict(test_user["id"], SETBACK, "does_not")
    discovery.set_pattern_verdict(test_user["id"], X, "rings_true")
    block = approved.approved_context(test_user["id"])
    assert "was there 3 of 3 times it went worse and 0 of 1 times it went better" in block
    patterns = block.split("## Patterns they said ring true")[1].split("## ")[0]
    assert patterns.count("\n- ") == 1  # the one they rejected stays out


def test_decisions_are_in_the_block_with_their_outcome(test_user):
    made = decisions.create(test_user["id"], what="Planted the whole bed at once", decided_on=date(2026, 5, 1),
                            stake="a_lot", confidence=80, pressures=["urge"])
    decisions.record_outcome(test_user["id"], made["id"], outcome="Half of it failed", followed_plan="no",
                             would_repeat="no")
    block = approved.approved_context(test_user["id"])
    assert "[2026-05-01] Planted the whole bed at once (stake a_lot; confidence 80%; pressures urge)" in block
    assert "Outcome: Half of it failed; followed plan: no" in block


def test_only_accepted_phone_readings_are_summarised_and_never_coordinates(test_user):
    today = date.today()
    batches: list[int] = []
    try:
        _readings_summarised(test_user, today, batches)
    finally:
        # Sensor batches belong to no user, so the per-user cleanup misses
        # them; left behind, they show up in other tests' pending lists.
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_batches WHERE id = ANY(%s)", (batches,))
            conn.commit()


def _readings_summarised(test_user, today, batches):
    with db.connection() as conn, conn.cursor() as cur:
        for status, value in (("confirmed", 4000.0), ("pending", 99999.0)):
            cur.execute("""INSERT INTO sensor_batches (source, payload_path, status)
                           VALUES ('pixel', 'test', %s) RETURNING id""", (status,))
            batch = cur.fetchone()[0]
            batches.append(batch)
            cur.execute("""INSERT INTO sensor_observations
                             (batch_id, source_type, occurred_date, value_num, lat, lon, payload_hash)
                           VALUES (%s, 'pixel_steps', %s, %s, 51.5, -0.1, %s)""",
                        (batch, today, value, f"h{batch}"))
        conn.commit()
    sensors = approved.approved_context(test_user["id"]).split("## Phone readings")[1].split("## ")[0]
    assert "pixel_steps: 1 readings over 1 days, average 4000.0" in sensors
    assert "99999" not in sensors and "51.5" not in sensors


def test_a_part_that_fails_says_so_instead_of_looking_empty(test_user, monkeypatch):
    def broken(_user_id):
        raise RuntimeError("database away")
    monkeypatch.setattr(approved, "PARTS", [("decisions", broken)])
    block = approved.approved_context(test_user["id"])
    assert "## decisions: could not be loaded just now (not the same as none)." in block


def test_their_check_ins_reach_chat_as_their_own_numbers(test_user):
    from agent.trackers.reflections import ReflectionService
    ReflectionService(test_user["id"]).create_reflection(
        content="Planted beans before lunch.", reflection_date=date.today(), energy_level=6,
        metrics={"mood": {"value": 7, "scale": 10, "source": "checkin"},
                 "stress": {"value": 3, "scale": 10, "source": "checkin"},
                 "sleep_quality": {"value": 9, "scale": 5, "source": "import"}})
    block = approved.approved_context(test_user["id"])
    checkins = block.split("## Their check-ins")[1].split("## ")[0]
    assert f"- {date.today().isoformat()}: energy 6, mood 7, stress 3" in checkins
    assert "sleep quality" not in checkins  # an imported value on another scale is not theirs

    from agent.core import PersonalAICompanion
    recent = PersonalAICompanion(user_id=test_user["id"])._get_reflections_context()
    assert "energy 6/10, mood 7/10, stress 3/10" in recent


def test_measured_days_reach_chat_without_coordinates(test_user):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO day_features (user_id, day, day_kind, commute_minutes, commute_mode,
                         steps, steps_full_day, screen_minutes, screen_by_category, sleep_minutes, location_coverage)
                       VALUES (%s, %s, 'office', 40, 'walking', 8000, true, 120, '{}'::jsonb, 420, 0.9)""",
                    (test_user["id"], date.today()))
        conn.commit()
    days = approved.approved_context(test_user["id"]).split("## Their measured days")[1].split("## ")[0]
    assert "office day, commute 40 min by walking, 8000 steps, screen 120 min, slept 420 min" in days
    assert "lat" not in days
