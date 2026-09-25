"""Sensor adapter boundaries: reject missing measurements and label observed steps."""

from agent.sensors.adapters import PixelAdapter


def test_missing_date_drops_the_observation():
    payload = {"device": "Pixel 10a", "tiers": {"location": [
        {"ts": None, "lat": 0, "lon": 0},
    ]}}
    batch = PixelAdapter().parse_from_dict(payload)
    assert batch["observations"] == []
    assert batch["dropped_count"] == 1


def test_live_step_delta_is_labeled_as_observed_not_a_daily_total():
    payload = {"device": "Pixel 10a", "tiers": {"steps": [
        {"date": "2026-09-22", "count": 12, "count_kind": "observed"},
    ]}}
    observation, = PixelAdapter().parse_from_dict(payload)["observations"]
    assert PixelAdapter.describe_observation(observation) == (
        "12 steps (recorded while IRIS was running)"
    )
