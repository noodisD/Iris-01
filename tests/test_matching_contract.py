"""An entry's construct memberships must not depend on when it arrived.

An independent review found that replay and ingestion used incompatible
definitions. `scan` gave an entry to every construct it matched; clustering gave
it to exactly one theme, the closest, across clusters *and* constructs. So the
same entry could join a construct when the archive was replayed at confirmation,
and lose it to a topical cluster when it arrived through the ordinary pipeline —
which meant confirming a construct changed its measured frequency for reasons
that were routing artifacts, not changes in the writing.

The contract these tests hold: clustering is exclusive among clusters, construct
classification is independent, and a frozen archive produces the same construct
occurrences whether it was written before or after the construct was confirmed.

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
LATER = "Went all in again on the opening I felt most certain about, and it cost me."
CLAIM = "The boldest moves appeared alongside the strongest expressions of certainty"


#: Enough other writing that the shared voice can be measured. Below
#: PERSISTENCE_STYLE_MIN_ENTRIES the mean is mostly the entries themselves, so
#: comparison stays raw at a 0.70 bar — a regime the real archive left long ago
#: (135 entries, mean applied, matching at 0.40). A contract test run below that
#: floor would be asserting about a situation this system is never in.
FILLER = [
    "Cooked properly for once and read a few chapters before bed.",
    "Long call with the client about the migration timeline.",
    "Ran the usual loop by the river, legs felt heavy the whole way.",
    "Spent the evening reorganising the bookshelves, oddly satisfying.",
    "The train was delayed again so I worked from the platform cafe.",
    "Tried the new bakery on the corner, the sourdough is worth it.",
    "Watched a documentary about deep sea vents and forgot the time.",
    "Cleared the inbox down to nothing, which never lasts.",
    "Took the long way home to think about the architecture problem.",
    "Rain all day, so the garden work waited another weekend.",
]


def _write(user_id, text, days_ago):
    return ReflectionService(user_id).create_reflection(
        content=text, reflection_date=date.today() - timedelta(days=days_ago))


def _give_the_archive_a_voice(user_id):
    """Write enough that the shared voice is measurable, as it is live."""
    service = ReflectionService(user_id)
    for i, text in enumerate(FILLER * 4):
        service.create_reflection(
            content=text, reflection_date=date.today() - timedelta(days=200 + i))


def _candidate(user_id, first_id, second_id):
    observation = Observation(
        claim=CLAIM,
        citations=(
            Citation(entry_id=first_id, entry_date=date.today() - timedelta(days=120),
                     text="I went all in on the opening I was most certain about"),
            Citation(entry_id=second_id, entry_date=date.today() - timedelta(days=80),
                     text="Doubled down again on the one game I felt sure of"),
        ),
        span_start=date.today() - timedelta(days=120),
        span_end=date.today() - timedelta(days=80),
        entries_read=2, confidence_level="low")
    return constructs.promote(user_id, observation)


@pytest.fixture
def confirmed(test_user, process_queue):
    """A construct the owner has confirmed, built from two entries."""
    uid = test_user["id"]
    _give_the_archive_a_voice(uid)
    first, second = _write(uid, CERTAIN, 120), _write(uid, AGAIN, 80)
    process_queue()
    theme_id = _candidate(uid, first, second)
    constructs.confirm(theme_id)
    return theme_id


def _members(theme_id):
    return {(o["source_type"], o["source_id"]) for o in db.get_theme_occurrences(theme_id)}


# --- the same writing, whichever order it arrived in ---------------------------

def test_an_entry_written_after_confirmation_joins_the_same_construct(
        test_user, confirmed, process_queue):
    """The acceptance criterion: ingestion must agree with replay."""
    before = _members(confirmed)
    new_id = _write(test_user["id"], LATER, 10)
    process_queue()

    after = _members(confirmed)
    assert ("reflection", new_id) in after, (
        "an entry the construct describes was lost because it arrived late")
    assert before < after


def test_replaying_the_archive_finds_what_ingestion_found(test_user, confirmed, process_queue):
    """Scanning again must not discover a different archive than ingestion saw."""
    _write(test_user["id"], LATER, 10)
    process_queue()
    from_ingestion = _members(confirmed)

    constructs.scan(confirmed)
    from_replay = _members(confirmed)

    assert from_ingestion == from_replay, (
        "replay and ingestion disagree about what this construct contains")


# --- clusters and constructs do not compete -----------------------------------

def test_a_cluster_cannot_take_an_entry_away_from_a_construct(
        test_user, confirmed, process_queue):
    """A topical cluster scoring higher used to win the entry outright, so a
    construct silently stopped accruing evidence once a cluster formed."""
    uid = test_user["id"]
    # A cluster whose centroid is the new entry itself, so it outscores everything.
    new_id = _write(uid, LATER, 10)
    process_queue()

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT e.vector FROM embeddings e
                       WHERE e.source_type='reflection' AND e.source_id=%s;""", (new_id,))
        vector = cur.fetchone()[0]
    db.create_theme(uid, constructs._as_vector(vector).tolist(), "a very close cluster",
                    date.today().isoformat(), date.today().isoformat())

    later_id = _write(uid, LATER, 5)
    process_queue()

    assert ("reflection", later_id) in _members(confirmed), (
        "a cluster took an entry the construct also describes")


def test_clusters_still_compete_only_among_themselves(test_user, process_queue):
    """Exclusivity is right for topical grouping: one entry, one cluster."""
    uid = test_user["id"]
    _give_the_archive_a_voice(uid)
    entry_id = _write(uid, CERTAIN, 30)
    process_queue()

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT count(*) FROM theme_occurrences o
                       JOIN themes t ON t.id = o.theme_id
                       WHERE o.source_type='reflection' AND o.source_id=%s
                         AND t.origin='clustered';""", (entry_id,))
        assert cur.fetchone()[0] <= 1, "an entry joined more than one cluster"


# --- a memory-only entry is still excluded ------------------------------------

def test_a_memory_only_entry_is_classified_into_nothing(test_user, confirmed, process_queue):
    ReflectionService(test_user["id"]).create_reflection(
        content=LATER, reflection_date=date.today() - timedelta(days=3),
        evidence_eligible=False)
    process_queue()

    eligible = {(e["source_type"], e["source_id"])
                for e in db.get_entries_with_vectors(test_user["id"])}
    assert _members(confirmed) <= eligible


# --- an occurrence still says how it got there --------------------------------

def test_an_entry_matched_on_ingest_is_marked_as_a_detector_match(
        test_user, confirmed, process_queue):
    """The owner read the seeded quotes. They never saw this one."""
    new_id = _write(test_user["id"], LATER, 10)
    process_queue()

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT admission_basis FROM theme_occurrences
                       WHERE theme_id=%s AND source_id=%s;""", (confirmed, new_id))
        row = cur.fetchone()
    assert row and row[0] == "similarity"


# --- a candidate is still measured by nothing ---------------------------------

def test_an_unconfirmed_construct_gains_nothing_from_new_writing(test_user, process_queue):
    uid = test_user["id"]
    _give_the_archive_a_voice(uid)
    first, second = _write(uid, CERTAIN, 120), _write(uid, AGAIN, 80)
    process_queue()
    theme_id = _candidate(uid, first, second)

    _write(uid, LATER, 10)
    process_queue()

    assert db.get_theme_occurrences(theme_id) == [], (
        "a proposal nobody has agreed to was accruing evidence")


# --- a quote is the owner's words, not the text that was embedded ---------------

def test_a_matched_entry_is_quoted_in_its_own_words(confirmed, test_user, process_queue):
    """Both online writers — the cluster matcher and the construct classifier —
    were handed the embedded text, which wraps a reflection in "Anchor: ... |
    Mood: okay ... | Content: ...", and stored a slice of it as the quote. One
    day's ingest produced 47 of them, invented mood included."""
    uid = test_user["id"]
    _write(uid, LATER, 10)
    for text in FILLER[:3]:  # arrivals that match the clusters the voice formed
        _write(uid, text, 5)
    process_queue()

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT t.origin, o.snippet FROM theme_occurrences o
                         JOIN themes t ON t.id = o.theme_id WHERE t.user_id = %s;""", (uid,))
        rows = cur.fetchall()

    assert {origin for origin, _ in rows} >= {"observed", "clustered"}, "both writers ran"
    assert not [s for _, s in rows if (s or "").startswith("Anchor:")]


# --- re-measuring replaces, and keeps what the owner vouched for -------------------------

def _bases(theme_id):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT source_type, source_id, admission_basis FROM theme_occurrences
                        WHERE theme_id = %s;""", (theme_id,))
        return {(t, i): b for t, i, b in cur.fetchall()}


def test_rescanning_keeps_a_quote_the_owner_vouched_for(confirmed):
    """scan() re-added every membership without its basis, and the upsert wrote
    the default over it: every entry the owner had read and confirmed became a
    detector's similarity match on the first re-measure."""
    cited = {k for k, b in _bases(confirmed).items() if b == "citation"}
    assert cited, "precondition: the confirmation cited entries"

    constructs.scan(confirmed)

    after = _bases(confirmed)
    assert all(after[k] == "citation" for k in cited)


def test_rescanning_forgets_an_entry_that_no_longer_matches(confirmed, test_user):
    """Adding on top kept every entry that had ever matched."""
    stray = _write(test_user["id"], "Bought a new kettle, the old one leaked.", 30)
    db.add_theme_occurrence(confirmed, "reflection", stray, "kettle", 0.9,
                            (date.today() - timedelta(days=30)).isoformat())

    constructs.scan(confirmed)

    assert ("reflection", stray) not in _bases(confirmed)
