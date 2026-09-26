"""Timeline export parsing. Coordinates are invented near 0,0."""

import json
from datetime import UTC, date, datetime

import pytest

from agent.sensors.adapters import to_timestamp
from agent.sensors.timeline import parse_latlng, parse_timeline, stage_export


def test_a_degree_pair_parses_and_a_bare_pair_does_not():
    assert parse_latlng("0.1°, 0.2°") == (0.1, 0.2)
    assert parse_latlng("52.1, 21.0") is None
    assert parse_latlng("not a place") is None
    assert parse_latlng("geo:0.0,0.0") == (0.0, 0.0)


def test_visits_and_trips_become_readings():
    parsed = parse_timeline({"semanticSegments": [
        {
            "startTime": "2026-01-02T08:00:00Z",
            "endTime": "2026-01-02T12:00:00Z",
            "visit": {"topCandidate": {
                "semanticType": "HOME",
                "placeLocation": {"latLng": "0.1°, 0.2°"},
            }},
        },
        {
            "startTime": "2026-01-02T12:00:00Z",
            "endTime": "2026-01-02T12:30:00Z",
            "activity": {
                "start": {"latLng": "0.1°, 0.2°"},
                "end": {"latLng": "0.3°, 0.2°"},
                "distanceMeters": 400,
                "topCandidate": {"type": "WALKING"},
            },
        },
    ]})
    kinds = [item["source_type"] for item in parsed["observations"]]
    assert kinds == ["timeline_visit", "timeline_activity"]
    visit, trip = parsed["observations"]
    assert visit["value_text"] == "HOME"
    assert visit["lat"] == 0.1
    assert trip["value_text"] == "WALKING"
    assert trip["value_num"] == 400
    assert trip["detail"]["start_lat"] == 0.1
    assert parsed["dropped_count"] == 0


def test_a_malformed_segment_is_dropped_and_a_bad_document_is_refused():
    parsed = parse_timeline({"semanticSegments": [
        {"startTime": "2026-01-02T08:00:00Z", "visit": {"topCandidate": {"semanticType": "WORK"}}},
        {"note": "not a segment"},
        "nope",
    ]})
    assert len(parsed["observations"]) == 1
    assert parsed["dropped_count"] == 2
    with pytest.raises(ValueError):
        parse_timeline({"hello": "world"})

def test_reversed_visit_interval_is_not_staged():
    parsed = parse_timeline({"semanticSegments": [{
        "startTime": "2026-01-02T12:00:00Z",
        "endTime": "2026-01-02T08:00:00Z",
        "visit": {"topCandidate": {"semanticType": "HOME", "placeLocation": {"latLng": "0.0°, 0.0°"}}},
    }]})
    assert parsed["observations"] == []
    assert parsed["dropped_count"] == 1

def test_a_malformed_location_never_becomes_a_home_visit():
    parsed = parse_timeline({"semanticSegments": [{
        "startTime": "2026-01-02T08:00:00Z",
        "endTime": "2026-01-02T10:00:00Z",
        "visit": {"topCandidate": {"semanticType": "HOME", "placeLocation": {"latLng": "bad"}}},
    }]})
    assert parsed["observations"] == []
    assert parsed["dropped_count"] == 1


@pytest.mark.parametrize(("label", "expected"), [
    ("INFERRED_HOME", "HOME"),
    ("INFERRED_WORK", "WORK"),
    ("TYPE_HOME", "HOME"),
    ("TYPE_WORK", "WORK"),
    ("TYPE_OTHER", "OTHER"),
    ("OTHER", "OTHER"),
])
def test_visit_semantics_preserve_home_and_work_for_inferred_labels(label, expected):
    parsed = parse_timeline({"semanticSegments": [{
        "startTime": "2026-01-02T08:00:00+02:00",
        "visit": {"topCandidate": {"semanticType": label}},
    }]})
    observation = parsed["observations"][0]
    assert observation["value_text"] == expected
    assert observation["detail"]["semantic_type"] == expected


def test_staged_timeline_days_follow_export_offsets_and_reimports_are_stable():
    from agent.sensors.repository import SensorRepository

    export = {"semanticSegments": [
        {
            "startTime": "2081-01-01T23:30:00+02:00",
            "visit": {"semanticType": "INFERRED_WORK"},
        },
        {
            "startTime": "2081-01-02T00:20:00+02:00",
            "visit": {"semanticType": "INFERRED_HOME"},
        },
        {
            "startTime": "2081-01-02T01:10:00+02:00",
            "activity": {"type": "WALKING"},
        },
        {"startTime": "bad timestamp", "visit": {"semanticType": "HOME"}},
    ]}
    ids: list[int] = []
    repo = SensorRepository()
    try:
        raw = json.dumps(export).encode()
        first = stage_export(raw)
        ids = first["batches"]
        assert stage_export(raw) == first
        assert first["observations"] == 3
        assert first["dropped"] == 1
        assert len(ids) == 2
        days = {
            repo.get_batch(batch_id)["review_day"]:
            repo.get_batch(batch_id)["parsed_payload"]["observations"]
            for batch_id in ids
        }
        assert set(days) == {date(2081, 1, 1), date(2081, 1, 2)}
        assert [obs["value_text"] for obs in days[date(2081, 1, 1)]] == ["WORK"]
        assert [obs["value_text"] for obs in days[date(2081, 1, 2)]] == ["HOME", "WALKING"]
        midnight_visit = days[date(2081, 1, 2)][0]
        assert midnight_visit["occurred_at"] == "2081-01-02T00:20:00+02:00"
        assert to_timestamp(midnight_visit["occurred_at"]) == datetime(
            2081, 1, 1, 22, 20, tzinfo=UTC,
        )
    finally:
        for batch_id in ids:
            repo.delete_batch(batch_id)
