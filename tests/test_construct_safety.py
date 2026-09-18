"""What confirmation must never do.

An independent review found the construct pipeline unsafe to confirm, and every
claim checked against the running system held. These tests are that review's
findings turned into failures: each one passed silently before the fix.

The findings, in the review's numbering:

- C-03 a bare id is not an identity. `import_item:158` and `reflection:158` are
  unrelated writing, and on the owner's archive 15 staged ids also name a
  reflection. Keying seeds on the number alone forced 12 unrelated reflections
  into two candidates — entries below the bar, cited by nothing.
- C-05 confirmation committed `active` before writing evidence, so a failure
  left an active construct with nothing behind it, gone from the only screen
  that would have shown the owner what happened. Rejection changed a status and
  left the occurrences in place.
- C-06 rebuilding clusters deleted every construct, prototype and decision.
- C-01 a fabricated quote was skipped and its siblings kept, so an observation
  could look fully verified while one of its citations was invented.
- C-12 candidate constructs were counted in the owner's theme totals.

Every entry below is invented.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from agent import constructs
from agent.database import db
from agent.insights_service import InsightsService
from agent.observations import Citation, Observation, ObservationEngine
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


def _candidate(user_id, archive, source_type="reflection", entry_ids=None):
    """A candidate whose prototypes point where the test says they point."""
    ids = entry_ids or [archive[CERTAIN], archive[AGAIN]]
    observation = Observation(
        claim=CLAIM,
        citations=(
            Citation(entry_id=ids[0], entry_date=date.today() - timedelta(days=120),
                     text="I went all in on the opening I was most certain about",
                     source_type=source_type),
            Citation(entry_id=ids[1], entry_date=date.today() - timedelta(days=80),
                     text="Doubled down again on the one game I felt sure of",
                     source_type=source_type),
        ),
        span_start=date.today() - timedelta(days=120),
        span_end=date.today() - timedelta(days=80),
        entries_read=2, confidence_level="low")
    return constructs.promote(user_id, observation)


# --- C-03: a number is not an identity -----------------------------------------

def test_a_staged_citation_cannot_seed_a_reflection_with_the_same_number(test_user, archive):
    """The exact shape of the 12 forced memberships: prototypes that name
    import items, whose numbers happen to match reflections."""
    theme_id = _candidate(test_user["id"], archive, source_type="import_item",
                          entry_ids=[archive[CERTAIN], archive[AGAIN]])
    constructs.confirm(theme_id)

    seeded = {(o["source_type"], o["source_id"]) for o in db.get_theme_occurrences(theme_id)}
    assert (("reflection", archive[CERTAIN])) not in seeded, (
        "a staged citation seeded a reflection by numeric coincidence")


def test_a_reflection_citation_still_seeds_its_own_entry(test_user, archive):
    theme_id = _candidate(test_user["id"], archive)
    constructs.confirm(theme_id)

    seeded = {o["source_id"] for o in db.get_theme_occurrences(theme_id)}
    assert archive[CERTAIN] in seeded and archive[AGAIN] in seeded


# --- C-05: confirmation is all or nothing --------------------------------------

def test_a_failure_while_matching_leaves_the_construct_reviewable(test_user, archive, monkeypatch):
    theme_id = _candidate(test_user["id"], archive)
    monkeypatch.setattr(constructs, "_memberships",
                        lambda tid: (_ for _ in ()).throw(RuntimeError("matching died")))

    with pytest.raises(RuntimeError):
        constructs.confirm(theme_id)

    assert db.get_theme_by_id(theme_id)["status"] == "candidate", (
        "a failure must not leave an active construct with no evidence")
    assert theme_id in [t["id"] for t in db.get_themes_by_status(test_user["id"], "candidate")]


def test_confirming_twice_does_not_confirm_twice(test_user, archive):
    theme_id = _candidate(test_user["id"], archive)
    first = constructs.confirm(theme_id)
    stamped = db.get_theme_by_id(theme_id)["confirmed_at"]

    second = constructs.confirm(theme_id)

    assert first > 0 and second == -1, "a second confirmation is refused, not repeated"
    assert db.get_theme_by_id(theme_id)["confirmed_at"] == stamped, "the decision keeps its moment"


def test_a_rejected_construct_cannot_be_confirmed_by_a_stale_request(test_user, archive):
    theme_id = _candidate(test_user["id"], archive)
    constructs.reject(theme_id)

    assert constructs.confirm(theme_id) == -1
    assert db.get_theme_by_id(theme_id)["status"] == "rejected"
    assert db.get_theme_occurrences(theme_id) == []


def test_rejecting_an_active_construct_withdraws_its_evidence(test_user, archive):
    """Status alone is not a retraction: cached readers join themes without
    checking it, so the occurrences have to go too."""
    theme_id = _candidate(test_user["id"], archive)
    constructs.confirm(theme_id)
    assert db.get_theme_occurrences(theme_id), "precondition: it had evidence"

    assert constructs.reject(theme_id) is True
    assert db.get_theme_by_id(theme_id)["status"] == "rejected"
    assert db.get_theme_occurrences(theme_id) == [], "withdrawn evidence must not survive"
    assert theme_id not in [t["id"] for t in db.get_themes(test_user["id"])]


def test_rejecting_keeps_the_owners_own_sentences(test_user, archive):
    theme_id = _candidate(test_user["id"], archive)
    constructs.reject(theme_id)
    assert db.get_theme_prototypes(theme_id), "the record of what was proposed is kept"


# --- C-06: cluster maintenance is not a decision eraser ------------------------

def test_rebuilding_clusters_preserves_constructs_and_decisions(test_user, archive):
    from agent.persistence import PersistenceEngine

    candidate = _candidate(test_user["id"], archive)
    active = _candidate(test_user["id"], archive)
    constructs.confirm(active)
    rejected = _candidate(test_user["id"], archive)
    constructs.reject(rejected)

    PersistenceEngine(test_user["id"]).rebuild_themes()

    for theme_id, expected in ((candidate, "candidate"), (active, "active"), (rejected, "rejected")):
        theme = db.get_theme_by_id(theme_id)
        assert theme is not None, f"the {expected} construct was destroyed by a cluster rebuild"
        assert theme["status"] == expected, "the owner's decision was lost"
        assert db.get_theme_prototypes(theme_id), "its prototypes were destroyed"


# --- C-01: one bad citation drops the claim ------------------------------------

def test_two_real_quotes_and_one_invented_one_drop_the_observation(test_user):
    entries = [
        {"id": 1, "source_type": "reflection", "date": date(2026, 1, 1), "content": CERTAIN},
        {"id": 2, "source_type": "reflection", "date": date(2026, 2, 1), "content": AGAIN},
    ]
    raw = [{"claim": CLAIM, "quotes": [
        {"entryId": 1, "sourceType": "reflection",
         "text": "I went all in on the opening I was most certain about"},
        {"entryId": 2, "sourceType": "reflection",
         "text": "Doubled down again on the one game I felt sure of"},
        {"entryId": 1, "sourceType": "reflection",
         "text": "I always double down when I am winning"},
    ]}]

    kept = ObservationEngine(test_user["id"], intelligence=object())._verified(raw, entries)
    assert kept == [], (
        "a model that fabricated one quote was not careful about the others")


# --- C-12: a proposal is not a finding -----------------------------------------

def test_candidates_are_not_counted_among_measured_themes(test_user, archive):
    _candidate(test_user["id"], archive)
    coverage = InsightsService(test_user["id"]).coverage()

    assert coverage["themes"] == 0, "an unconfirmed proposal was counted as a theme"
    assert coverage["candidateConstructs"] == 1, "and it is reported in its own right"


def test_confirming_moves_a_candidate_into_the_measured_count(test_user, archive):
    theme_id = _candidate(test_user["id"], archive)
    constructs.confirm(theme_id)
    coverage = InsightsService(test_user["id"]).coverage()

    assert coverage["themes"] == 1
    assert coverage["candidateConstructs"] == 0
