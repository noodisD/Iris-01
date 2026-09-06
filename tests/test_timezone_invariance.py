"""
Analytical results must not depend on the host's timezone.

Every timestamp column is TIMESTAMPTZ, so the database returns aware UTC. The
engines used to strip that offset and compare against a naive datetime.now(),
which is *local* time — so every sliding window was displaced by the host's UTC
offset: two hours in CEST, one in CET. An occurrence near a window boundary
could therefore be classified one way in summer and another in winter, on
identical data, and a laptop that travelled would disagree with itself.

These tests place occurrences deliberately close to a window edge, where that
displacement decides the answer.
"""

import os
import time
from datetime import timedelta

import pytest

from agent.constants import RESOLUTION_RECENT_DAYS, TRAJECTORY_RECENT_DAYS
from agent.database import db, themes
from agent.resolution import ResolutionEngine
from agent.timeutils import utc_now
from agent.trajectory import TrajectoryEngine


@pytest.fixture
def restore_timezone():
    original = os.environ.get("TZ")
    yield
    if original is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = original
    time.tzset()


def _set_timezone(name: str) -> None:
    os.environ["TZ"] = name
    time.tzset()


def _theme_on_the_boundary(user_id: int) -> int:
    """A theme whose occurrences sit within an hour of the recent/baseline edge.

    An offset error of even one hour moves them across it.
    """
    theme_id = themes.create_theme(
        user_id=user_id,
        centroid_embedding=[0.11] * 1536,
        summary="Boundary Theme",
        first_seen_at=(utc_now() - timedelta(days=80)).isoformat(),
        last_seen_at=utc_now().isoformat(),
        occurrence_count=0,
    )
    edge = utc_now() - timedelta(days=RESOLUTION_RECENT_DAYS)
    moments = [
        edge + timedelta(minutes=30),   # just inside the recent window
        edge + timedelta(minutes=45),
        edge - timedelta(minutes=30),   # just outside it
        edge - timedelta(minutes=45),
        utc_now() - timedelta(days=60),
        utc_now() - timedelta(days=70),
    ]
    for i, moment in enumerate(moments):
        themes.add_occurrence(
            theme_id=theme_id, source_type="reflection", source_id=900000 + i,
            snippet=f"boundary {i}", similarity_score=0.9,
            occurred_at=moment.isoformat(),
        )
    return theme_id


def test_resolution_is_the_same_in_utc_and_in_a_shifted_timezone(test_user, restore_timezone):
    theme_id = _theme_on_the_boundary(test_user["id"])
    engine = ResolutionEngine(test_user["id"])

    _set_timezone("UTC")
    in_utc = engine.analyze_theme(theme_id, force_recompute=True)

    _set_timezone("Europe/Warsaw")  # UTC+1/+2
    shifted = engine.analyze_theme(theme_id, force_recompute=True)

    assert in_utc["resolution_label"] == shifted["resolution_label"]
    assert in_utc["recent_count"] == shifted["recent_count"], (
        "the recent/baseline split moved with the host timezone"
    )
    assert in_utc["past_count"] == shifted["past_count"]


def test_trajectory_is_the_same_in_utc_and_in_a_shifted_timezone(test_user, restore_timezone):
    user_id = test_user["id"]
    theme_id = themes.create_theme(
        user_id=user_id, centroid_embedding=[0.12] * 1536, summary="Trajectory Boundary",
        first_seen_at=(utc_now() - timedelta(days=40)).isoformat(),
        last_seen_at=utc_now().isoformat(), occurrence_count=0,
    )
    edge = utc_now() - timedelta(days=TRAJECTORY_RECENT_DAYS)
    for i, moment in enumerate([edge + timedelta(minutes=20), edge - timedelta(minutes=20),
                                utc_now() - timedelta(days=30), utc_now() - timedelta(days=35)]):
        themes.add_occurrence(
            theme_id=theme_id, source_type="reflection", source_id=910000 + i,
            snippet=f"t {i}", similarity_score=0.9, occurred_at=moment.isoformat(),
        )

    engine = TrajectoryEngine(user_id)
    _set_timezone("UTC")
    in_utc = engine.analyze_theme(theme_id)
    _set_timezone("Europe/Warsaw")
    shifted = engine.analyze_theme(theme_id)

    assert in_utc["trajectory_label"] == shifted["trajectory_label"]
    assert in_utc["recent_count"] == shifted["recent_count"]
    assert in_utc["past_count"] == shifted["past_count"]


def test_stored_timestamps_come_back_as_utc(test_user):
    """The premise of all of the above: the database hands back aware UTC."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT now();")
        value = cur.fetchone()[0]
    assert value.tzinfo is not None, "TIMESTAMPTZ must arrive timezone-aware"
    assert value.utcoffset().total_seconds() == 0, "and normalised to UTC"
