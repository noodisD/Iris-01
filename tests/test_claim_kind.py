"""What a construct's occurrences are counting.

An independent review found the pipeline treated several propositions as one:
the words exist, the words support the claim, the entry records an occurrence,
the owner validated the detector. Only the first was ever verified. Its sharpest
demonstration was two authentic quotations explicitly *denying* a behaviour,
accepted as proving it — because verification checks that a quote appears in an
entry and nothing more.

So a construct now says which kind of claim it makes. 'mention' is what a
verified quote can support. 'behaviour' claims the thing happened, needs an
evidence contract nobody has built, and is refused at confirmation rather than
quietly measured.

Every entry below is invented.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from agent import constructs
from agent.database import db
from agent.insights_service import InsightsService
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


def _candidate(user_id, archive):
    observation = Observation(
        claim=CLAIM,
        citations=(
            Citation(entry_id=archive[CERTAIN], entry_date=date.today() - timedelta(days=120),
                     text="I went all in on the opening I was most certain about"),
            Citation(entry_id=archive[AGAIN], entry_date=date.today() - timedelta(days=80),
                     text="Doubled down again on the one game I felt sure of"),
        ),
        span_start=date.today() - timedelta(days=120),
        span_end=date.today() - timedelta(days=80),
        entries_read=2, confidence_level="low")
    return constructs.promote(user_id, observation)


# --- nothing is born claiming a behaviour --------------------------------------

def test_a_discovered_construct_claims_only_that_the_subject_was_written_about(test_user, archive):
    theme_id = _candidate(test_user["id"], archive)
    assert db.get_theme_by_id(theme_id)["claim_kind"] == constructs.CLAIM_MENTION


def test_the_review_surface_says_which_kind_of_claim_it_is_asking_about(test_user, archive):
    _candidate(test_user["id"], archive)
    candidate = constructs.candidates(test_user["id"])[0]
    assert candidate["claimKind"] == constructs.CLAIM_MENTION, (
        "the owner cannot judge a claim without being told what confirming it means")


def test_a_clustered_theme_counts_mentions_too(test_user):
    """Clustering never made a claim — it grouped entries and labelled them
    afterwards. 'mention' is the honest reading of what its counts have meant."""
    theme_id = db.create_theme(test_user["id"], [0.1] * 1536, "a cluster",
                               date.today().isoformat(), date.today().isoformat())
    assert db.get_theme_by_id(theme_id)["claim_kind"] == constructs.CLAIM_MENTION


# --- a behaviour claim is refused, not measured --------------------------------

def test_a_behaviour_claim_cannot_be_confirmed(test_user, archive):
    """Two authentic quotes denying a behaviour currently pass verification, so
    a behaviour count would rest on a proof nobody has built."""
    theme_id = _candidate(test_user["id"], archive)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE themes SET claim_kind = %s WHERE id = %s;",
                    (constructs.CLAIM_BEHAVIOUR, theme_id))
        conn.commit()

    assert constructs.confirm(theme_id) == -1
    assert db.get_theme_by_id(theme_id)["status"] == "candidate", "it stays reviewable"
    assert db.get_theme_occurrences(theme_id) == [], "and measures nothing"


def test_a_mention_claim_still_confirms(test_user, archive):
    theme_id = _candidate(test_user["id"], archive)
    assert constructs.confirm(theme_id) > 0


# --- every occurrence says why it was admitted ---------------------------------

def test_an_occurrence_records_whether_the_owner_read_it(test_user, archive):
    """Confirming a claim and authorising a detector are different acts. A row
    seeded by a quote they read is not the same as one a detector proposed."""
    theme_id = _candidate(test_user["id"], archive)
    constructs.confirm(theme_id)

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT source_id, admission_basis FROM theme_occurrences
                       WHERE theme_id = %s;""", (theme_id,))
        basis = dict(cur.fetchall())

    assert basis[archive[CERTAIN]] == "citation", "a sentence the owner actually read"
    assert basis[archive[AGAIN]] == "citation"
    assert set(basis.values()) <= {"citation", "similarity"}


# --- the screen can tell a construct from a cluster ----------------------------

def test_an_insight_carries_where_it_came_from(test_user, archive):
    from agent.trajectory import TrajectoryEngine

    theme_id = _candidate(test_user["id"], archive)
    constructs.confirm(theme_id)
    # The engines must produce something for this theme before it can be shaped
    # into an insight payload.
    assert theme_id in {t["theme_id"] for t in TrajectoryEngine(test_user["id"]).analyze_all_themes()}

    service = InsightsService(test_user["id"])
    provenance = service._provenance(theme_id)

    assert provenance["origin"] == "observed", (
        "a construct the owner vouched for read as a machine-named cluster")
    assert provenance["claimKind"] == constructs.CLAIM_MENTION
    assert provenance["confirmedAt"] is not None


def test_provenance_is_absent_rather_than_invented(test_user):
    """Tension and leverage span two patterns, so a single origin would be a
    fiction. Absent is the honest answer."""
    service = InsightsService(test_user["id"])
    assert service._provenance(None) == {}
    assert service._provenance("12-13") == {}
    assert service._provenance(999999) == {}
