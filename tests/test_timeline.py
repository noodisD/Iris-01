"""Timeline export parsing. Coordinates are invented near 0,0."""

import pytest

from agent.sensors.timeline import parse_latlng, parse_timeline


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
