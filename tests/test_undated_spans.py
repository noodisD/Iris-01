"""A construct built from undated writing must not claim a date.

Voice transcripts carry no date, by design: a date is read or it is absent,
never invented (ADR-0013). But theme timestamps are NOT NULL, so promotion
needed a value and used the moment of discovery — which made four candidates
record a span of the day they were found. On the review screen that reads as
though the owner wrote those recordings that afternoon.

The columns still hold a value the schema requires. A flag says that value means
nothing, and the review surface reports no span at all rather than a placeholder
dressed as a date.

Every entry below is invented.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from agent import constructs
from agent.database import db
from agent.observations import Citation, Observation
from agent.trackers.reflections import ReflectionService

CERTAIN = "I went all in on the opening I was most certain about and lost half the pieces."
AGAIN = "Doubled down again on the one game I felt sure of, and it went against me."
CLAIM = "The boldest moves appeared alongside the strongest expressions of certainty"


@pytest.fixture
def archive(test_user, process_queue):
    service = ReflectionService(test_user["id"])
    ids = {}
    for offset, text in ((120, CERTAIN), (80, AGAIN)):
        ids[text] = service.create_reflection(
            content=text, reflection_date=date.today() - timedelta(days=offset))
    process_queue()
    return ids


def _observation(citations):
    return Observation(claim=CLAIM, citations=tuple(citations), span_start=None,
                       span_end=None, entries_read=2, confidence_level="low")


def _dated(archive):
    return [
        Citation(entry_id=archive[CERTAIN], entry_date=date.today() - timedelta(days=120),
                 text="I went all in on the opening I was most certain about"),
        Citation(entry_id=archive[AGAIN], entry_date=date.today() - timedelta(days=80),
                 text="Doubled down again on the one game I felt sure of"),
    ]


def _undated():
    """Citations from staged recordings, which carry no date at all."""
    return [
        Citation(entry_id=901, entry_date=None, source_type="import_item",
                 text="I went all in on the opening I was most certain about"),
        Citation(entry_id=902, entry_date=None, source_type="import_item",
                 text="Doubled down again on the one game I felt sure of"),
    ]


# --- undated writing produces no span -------------------------------------------

def test_a_construct_from_undated_recordings_is_marked_undated(test_user, archive):
    theme_id = constructs.promote(test_user["id"], _observation(_undated()))
    assert db.get_theme_by_id(theme_id)["span_is_undated"] is True


def test_the_review_screen_shows_no_span_rather_than_todays_date(test_user, archive):
    """This is the live symptom: four candidates reading as written today."""
    constructs.promote(test_user["id"], _observation(_undated()))
    candidate = constructs.candidates(test_user["id"])[0]

    assert candidate["spanStart"] is None
    assert candidate["spanEnd"] is None


def test_the_stored_timestamps_still_satisfy_the_schema(test_user, archive):
    """The columns are NOT NULL. They keep a value; the flag says it means
    nothing, so no consumer has to learn about null."""
    theme_id = constructs.promote(test_user["id"], _observation(_undated()))
    theme = db.get_theme_by_id(theme_id)

    assert theme["first_seen_at"] is not None
    assert theme["last_seen_at"] is not None


# --- dated writing is unaffected -------------------------------------------------

def test_a_construct_from_dated_entries_keeps_its_real_span(test_user, archive):
    theme_id = constructs.promote(test_user["id"], _observation(_dated(archive)))
    theme = db.get_theme_by_id(theme_id)

    assert theme["span_is_undated"] is False
    candidate = [c for c in constructs.candidates(test_user["id"])
                 if c["id"] == str(theme_id)][0]
    # A full timestamp, as this payload has always carried; the screen formats
    # it through formatEventDate. The day is what matters here.
    assert candidate["spanStart"].startswith(
        (date.today() - timedelta(days=120)).isoformat())
    assert candidate["spanEnd"].startswith(
        (date.today() - timedelta(days=80)).isoformat())


def test_one_dated_citation_is_enough_for_a_span(test_user, archive):
    """A mixed candidate has a real span, covering the part that has dates."""
    mixed = [_dated(archive)[0], _undated()[1]]
    theme_id = constructs.promote(test_user["id"], _observation(mixed))

    theme = db.get_theme_by_id(theme_id)
    assert theme["span_is_undated"] is False


def test_a_clustered_theme_is_never_marked_undated(test_user):
    theme_id = db.create_theme(test_user["id"], [0.1] * 1536, "a cluster",
                               date.today().isoformat(), date.today().isoformat())
    assert db.get_theme_by_id(theme_id)["span_is_undated"] is False
