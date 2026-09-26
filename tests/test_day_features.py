"""Day features from invented readings near 0,0. No journal text."""

from datetime import UTC, date, datetime

from agent.days.features import (
    Activity,
    Fix,
    Place,
    Sleep,
    Usage,
    Visit,
    category_for,
    compute_day,
)

ZONE = UTC
DAY = date(2026, 1, 2)
HOME = Place("home", 0.0, 0.0, 500)
OFFICE = Place("office", 0.02, 0.0, 500)


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 1, 2, hour, minute, tzinfo=ZONE)


def test_a_poor_fix_and_a_gap_do_not_count_as_known():
    features = compute_day(
        day=DAY, zone=ZONE, places=[HOME],
        fixes=[
            Fix(_at(6), 0.0, 0.0, 20),
            Fix(_at(6, 10), 0.0, 0.0, 250),
            Fix(_at(6, 20), 0.0, 0.0, 15),
        ],
        visits=[], activities=[], usage=[], sleep=[], steps=[],
    )
    # 06:00 covers five minutes. 06:10 is too inaccurate. 06:20 covers five.
    assert features["home_minutes"] == 10
    assert features["location_coverage"] < 0.5
    assert features["day_kind"] == "unknown"


def test_a_fix_crossing_midnight_stops_at_the_window():
    features = compute_day(
        day=DAY, zone=ZONE, places=[HOME],
        fixes=[Fix(datetime(2026, 1, 2, 23, 58, tzinfo=ZONE), 0.0, 0.0, 10)],
        visits=[], activities=[], usage=[], sleep=[], steps=[],
    )
    assert features["home_minutes"] == 2


def test_timeline_overlaps_gps_and_wins():
    features = compute_day(
        day=DAY, zone=ZONE, places=[HOME, OFFICE],
        fixes=[Fix(_at(8), 0.0, 0.0, 10)],
        visits=[Visit(_at(8, 1), _at(8, 4), 0.02, 0.0, "WORK")],
        activities=[], usage=[], sleep=[], steps=[],
    )
    assert features["office_minutes"] == 3
    assert features["home_minutes"] == 2


def test_an_office_day_needs_coverage_and_three_hours():
    features = compute_day(
        day=DAY, zone=ZONE, places=[OFFICE],
        fixes=[],
        visits=[Visit(_at(8), _at(17), 0.02, 0.0, "WORK")],
        activities=[], usage=[], sleep=[], steps=[],
    )
    assert features["office_minutes"] == 9 * 60
    assert features["location_coverage"] >= 0.5
    assert features["day_kind"] == "office"


def test_sleep_counts_on_the_morning_you_wake():
    woken = compute_day(
        day=DAY, zone=ZONE, places=[],
        fixes=[], visits=[], activities=[], usage=[], steps=[],
        sleep=[Sleep(datetime(2026, 1, 1, 23, 0, tzinfo=ZONE), _at(7))],
    )
    previous = compute_day(
        day=date(2026, 1, 1), zone=ZONE, places=[],
        fixes=[], visits=[], activities=[], usage=[], steps=[],
        sleep=[Sleep(datetime(2026, 1, 1, 23, 0, tzinfo=ZONE), _at(7))],
    )
    assert woken["sleep_minutes"] == 8 * 60
    assert previous["sleep_minutes"] is None

def test_sleep_uses_asleep_minutes_not_time_in_bed():
    features = compute_day(
        day=DAY, zone=ZONE, places=[], fixes=[], visits=[], activities=[], usage=[], steps=[],
        sleep=[Sleep(datetime(2026, 1, 1, 23, tzinfo=ZONE), _at(7), 420)],
    )
    assert features["sleep_minutes"] == 420


def test_commute_is_travel_between_home_and_office():
    features = compute_day(
        day=DAY, zone=ZONE, places=[HOME, OFFICE],
        fixes=[], visits=[],
        activities=[Activity(_at(8), _at(8, 40), "WALKING", 0.0, 0.0, 0.02, 0.0)],
        usage=[], sleep=[], steps=[],
    )
    assert features["commute_minutes"] == 40
    assert features["commute_mode"] == "WALKING"


def test_category_priority_is_override_then_phone_then_other():
    assert category_for("com.example.chat", "social", "game") == "social"
    assert category_for("com.example.chat", None, "game") == "game"
    assert category_for("com.example.chat", None, None) == "other"
    features = compute_day(
        day=DAY, zone=ZONE, places=[], fixes=[], visits=[], activities=[],
        usage=[Usage("com.example.chat", 120, "game"), Usage("com.example.maps", 60, None)],
        sleep=[], steps=[], overrides={"com.example.chat": "social"},
    )
    assert features["screen_by_category"] == {"social": 2, "other": 1}
