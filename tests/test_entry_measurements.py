"""What the originals recorded, and what counts as evidence.

The earlier-IRIS export carries typed wellbeing values on every entry — mood
and energy on all 24, plus sleep, exercise, nutrition, anxiety or stress on
most. The importer read the prose beside them and dropped the numbers, so all
138 imported reflections arrived with no energy, no clarity, and the mood
"okay" that gets inferred when an entry has no tags: a default presented as
something the owner had recorded.

Separately, copied setup text and six-character placeholders were counted as
occurrences of a pattern. They stay searchable; they stop being proof that
anything recurred.

Every value below is invented.
"""

from __future__ import annotations

import json

import pytest

from agent.database import db
from agent.importing import Bundle, get
from agent.trackers.reflections import ReflectionService

ENTRY = {
    "id": "a1",
    "date": "2025-11-08T20:50:07",
    "wellbeing": {"mood": 6, "energy": 5, "sleep_hours": 7.5, "sleep_quality": 6,
                  "exercise": "yes", "nutrition": "ok", "anxiety": 3, "stress": 4,
                  "notes": "tired but fine"},
    "reflections": "Long day, but the deployment finally went out.",
    "ideas": [], "goals": [], "execution": [],
}


@pytest.fixture
def bundle(tmp_path):
    (tmp_path / "journal_entries.json").write_text(json.dumps([ENTRY]), encoding="utf-8")
    return Bundle(tmp_path)


def test_every_recorded_measurement_is_kept_with_its_scale(bundle):
    entry = list(get("iris_og_journal").parse(bundle))[0]

    assert entry.metrics, "the typed values were dropped entirely"
    assert entry.metrics["sleep_hours"] == {"value": 7.5, "scale": "hours",
                                            "source": "iris_og.wellbeing"}
    assert set(entry.metrics) == {"mood", "energy", "sleep_hours", "sleep_quality",
                                  "exercise", "nutrition", "anxiety", "stress"}


def test_an_unrecorded_value_is_absent_rather_than_invented(tmp_path):
    thin = dict(ENTRY, wellbeing={"mood": 6, "notes": "fine"})
    (tmp_path / "journal_entries.json").write_text(json.dumps([thin]), encoding="utf-8")
    entry = list(get("iris_og_journal").parse(Bundle(tmp_path)))[0]

    assert set(entry.metrics) == {"mood"}
    assert "stress" not in entry.metrics


def test_the_prose_still_reads_as_the_owner_wrote_it(bundle):
    entry = list(get("iris_og_journal").parse(bundle))[0]
    assert "Long day, but the deployment finally went out." in entry.content
    assert "tired but fine" in entry.content, "wellbeing notes are prose, not a measurement"


# --- mood is not a default ----------------------------------------------------

def test_an_entry_with_no_tags_has_no_mood(test_user):
    rid = ReflectionService(test_user["id"]).create_reflection(content="Nothing much to report.")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT mood FROM reflections WHERE id = %s;", (rid,))
        assert cur.fetchone()[0] is None, "'okay' was a default dressed as a self-report"


def test_tags_still_infer_a_mood(test_user):
    rid = ReflectionService(test_user["id"]).create_reflection(
        content="Good session today.", tags=["excited"])
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT mood FROM reflections WHERE id = %s;", (rid,))
        assert cur.fetchone()[0] == "great"


def test_measurements_reach_the_stored_entry(test_user):
    rid = ReflectionService(test_user["id"]).create_reflection(
        content="Slept badly, still got the work done.",
        metrics={"sleep_hours": {"value": 5.0, "scale": "hours", "source": "iris_og.wellbeing"}},
        date_source="json_field", date_confidence="certain")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT metrics, date_source, date_confidence FROM reflections WHERE id = %s;", (rid,))
        metrics, source, confidence = cur.fetchone()
    assert metrics["sleep_hours"]["value"] == 5.0
    assert (source, confidence) == ("json_field", "certain")


# --- memory is not evidence ---------------------------------------------------

def test_an_ineligible_entry_is_not_an_observation(test_user):
    """A placeholder must not make a day count as one the owner journalled."""
    from datetime import date, timedelta

    from agent.coverage import observation_coverage

    service = ReflectionService(test_user["id"])
    service.create_reflection(content="x", reflection_date=date.today(),
                              evidence_eligible=False)
    assert observation_coverage(test_user["id"]).observed_days_in_window == 0

    service.create_reflection(content="A real entry about the day.",
                              reflection_date=date.today() - timedelta(days=1))
    assert observation_coverage(test_user["id"]).observed_days_in_window == 1


def test_an_ineligible_entry_is_never_offered_to_the_engines(test_user, monkeypatch):
    from agent import pipeline

    rid = ReflectionService(test_user["id"]).create_reflection(
        content="Copied setup text that appears twice.", evidence_eligible=False)
    called = []
    monkeypatch.setattr(pipeline.PersistenceEngine, "check_persistence",
                        lambda *a, **kw: called.append(1))
    pipeline.run_processing_pipeline("reflection", rid)

    assert called == [], "memory-only entries must not form or reinforce a theme"
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM embeddings WHERE source_type='reflection' AND source_id=%s;", (rid,))
        assert cur.fetchone()[0] == 1, "but it is still embedded, so chat can recall it"
