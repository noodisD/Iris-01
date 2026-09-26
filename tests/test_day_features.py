"""Day features from invented readings near 0,0. No journal text."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from agent.days.features import (
    Activity,
    Fix,
    Place,
    Sleep,
    Steps,
    Usage,
    Visit,
    category_for,
    compute_day,
)
from agent.days.recompute import _group, _host_zone, _steps, _zone

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


def test_overlapping_sleep_sessions_count_covered_time_once():
    night = Sleep(datetime(2026, 1, 1, 22, tzinfo=UTC), _at(6))
    edited = Sleep(datetime(2026, 1, 1, 23, tzinfo=UTC), _at(7))
    features = compute_day(
        day=DAY, zone=ZONE, places=[], fixes=[], visits=[], activities=[],
        usage=[], steps=[], sleep=[night, night, edited],
    )
    assert features["sleep_minutes"] == 9 * 60
    assert compute_day(
        day=date(2026, 1, 1), zone=ZONE, places=[], fixes=[], visits=[],
        activities=[], usage=[], steps=[], sleep=[night, edited],
    )["sleep_minutes"] is None


def test_overlapping_reported_asleep_minutes_do_not_sum_provider_duplicates():
    night = Sleep(datetime(2026, 1, 1, 23, tzinfo=UTC), _at(7), 420)
    features = compute_day(
        day=DAY, zone=ZONE, places=[], fixes=[], visits=[], activities=[],
        usage=[], steps=[], sleep=[night, night],
    )
    assert features["sleep_minutes"] == 420
    assert compute_day(
        day=DAY, zone=ZONE, places=[], fixes=[], visits=[], activities=[],
        usage=[], steps=[], sleep=[Sleep(_at(7), _at(7), 0)],
    )["sleep_minutes"] == 0


def test_cumulative_step_snapshots_keep_daily_total_and_partial_status():
    def measured(steps):
        return compute_day(
            day=DAY, zone=ZONE, places=[], fixes=[], visits=[], activities=[],
            usage=[], sleep=[], steps=steps,
        )

    assert measured([Steps(1200, True), Steps(4500, True), Steps(9000, True)])[
        "steps"
    ] == 9000
    partial_then_full = measured([Steps(1200, False), Steps(4500, True), Steps(9000, True)])
    assert partial_then_full["steps"] == 9000
    assert partial_then_full["steps_full_day"] is False
    assert measured([Steps(1200, True), Steps(9000, True)])["steps_full_day"] is True
    assert measured([])["steps"] is None


def test_host_iana_zone_used_for_default_or_invalid_setting():
    host = ZoneInfo("America/Los_Angeles")
    with patch("agent.days.recompute._host_zone", return_value=host), patch(
        "agent.days.recompute.db.get_app_settings", return_value={"timezone": "UTC"}
    ) as settings:
        assert _zone(123) == host
        settings.return_value = {"timezone": "unknown/zone"}
        assert _zone(123) == host
        settings.return_value = {"timezone": "Europe/Stockholm"}
        assert _zone(123) == ZoneInfo("Europe/Stockholm")

def test_host_zone_reads_localtime_iana_name_not_a_fixed_current_offset():
    with patch("agent.days.recompute.os.environ", {}), patch(
        "agent.days.recompute.Path.resolve",
        return_value=Path("/usr/share/zoneinfo/America/Los_Angeles"),
    ), patch("agent.days.recompute.Path.read_text", return_value="UTC"):
        zone = _host_zone()
    assert zone.key == "America/Los_Angeles"
    assert datetime(2026, 1, 2, tzinfo=zone).utcoffset() == timedelta(hours=-8)
    assert datetime(2026, 7, 2, tzinfo=zone).utcoffset() == timedelta(hours=-7)


def test_non_utc_local_window_and_step_calendar_day():
    zone = ZoneInfo("America/Los_Angeles")
    visit = Visit(datetime(2026, 7, 2, 12, 30, tzinfo=UTC),
                  datetime(2026, 7, 2, 14, tzinfo=UTC), 0.0, 0.0)
    features = compute_day(
        day=date(2026, 7, 2), zone=zone, places=[HOME], fixes=[], visits=[visit],
        activities=[], usage=[], sleep=[], steps=[],
    )
    # 05:30–07:00 local: only 06:00–07:00 belongs in the measured window.
    assert features["home_minutes"] == 60
    rows = [{
        "source_type": "pixel_steps",
        "occurred_at": datetime(2026, 7, 2, tzinfo=UTC),
        "occurred_date": date(2026, 7, 2),
        "value_num": 9000,
        "value_text": None,
    }]
    assert list(_group(rows, zone, None)) == [date(2026, 7, 2)]
    assert _steps(rows, date(2026, 7, 2), zone) == [Steps(9000, True)]


def test_local_midnight_clips_even_when_utc_date_differs():
    zone = ZoneInfo("America/Los_Angeles")
    features = compute_day(
        day=date(2026, 7, 2), zone=zone, places=[HOME], fixes=[],
        visits=[Visit(datetime(2026, 7, 3, 6, 30, tzinfo=UTC),
                      datetime(2026, 7, 3, 7, 30, tzinfo=UTC), 0.0, 0.0)],
        activities=[], usage=[], sleep=[], steps=[],
    )
    assert features["home_minutes"] == 30


def test_sleep_across_daylight_saving_transition_uses_elapsed_minutes():
    zone = ZoneInfo("America/Los_Angeles")
    night = Sleep(datetime(2026, 3, 8, 0, tzinfo=zone),
                  datetime(2026, 3, 8, 8, tzinfo=zone))
    features = compute_day(
        day=date(2026, 3, 8), zone=zone, places=[], fixes=[], visits=[],
        activities=[], usage=[], sleep=[night, night], steps=[],
    )
    assert features["sleep_minutes"] == 7 * 60


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
