"""A pattern the owner confirmed, and what it is allowed to do before they do.

Clustering produced themes nobody named — on the real archive it split one
subject into five near-identical themes of two to seven occurrences each, so no
single one carried enough evidence to say anything. A construct comes the other
way: the reading engine notices something and proves it with verbatim quotes,
the owner confirms it, and only then is it measured.

The tests here guard the three rules that keep that honest: a construct is
anchored in the owner's sentences and never in the model's description of them;
a candidate is not measured by anything; and confirming is what turns a claim
into occurrences.

Every entry below is invented.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from agent import constructs
from agent.database import db
from agent.observations import Citation, Observation
from agent.trackers.reflections import ReflectionService

CERTAIN = "I went all in on the opening I was most certain about and lost half the pieces."
AGAIN = "Doubled down again on the one game I felt sure of, and it went against me."
UNRELATED = "Repotted the plants and finally fixed the squeaky kitchen door hinge."

CLAIM = "The boldest moves appeared alongside the strongest expressions of certainty"


#: Enough other writing that the shared voice can be measured. Below
#: PERSISTENCE_STYLE_MIN_ENTRIES the mean is mostly the entries themselves, so
#: comparison stays raw at a 0.7 bar — a regime the real archive left long ago
#: (135 entries, mean applied, matching at 0.4). A construct test that ran below
#: that floor would be measuring a situation this system is never in again.
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


def _write(service, ids, offsets=((120, CERTAIN), (80, AGAIN), (20, UNRELATED))):
    for offset, text in offsets:
        ids[text] = service.create_reflection(
            content=text, reflection_date=date.today() - timedelta(days=offset))
    return ids


@pytest.fixture
def archive(test_user, process_queue):
    """The three entries that matter, embedded.

    Writing an entry only *enqueues* the embedding (ADR-0011), so draining is
    where a test that matches against vectors says it waits for that work.
    """
    ids = _write(ReflectionService(test_user["id"]), {})
    process_queue()
    return ids


@pytest.fixture
def archive_with_voice(test_user, process_queue):
    """The same three entries, plus enough writing to have a measurable voice.

    Matching only happens in the mean-centred space once there is enough
    evidence to measure the shared voice; below that floor comparison stays raw
    at a 0.7 bar. The real archive is long past it (135 entries, matching at
    0.4), so a matching test run below it would be measuring a regime this
    system is never in again. Only the tests that actually match pay for this —
    building it for all of them cost a minute of suite time.
    """
    service = ReflectionService(test_user["id"])
    ids = _write(service, {})
    for i, text in enumerate(FILLER * 4):
        service.create_reflection(
            content=text, reflection_date=date.today() - timedelta(days=200 + i))
    process_queue()
    return ids


def _observation(archive, claim=CLAIM):
    return Observation(
        claim=claim,
        citations=(
            Citation(entry_id=archive[CERTAIN], entry_date=date.today() - timedelta(days=120),
                     text="I went all in on the opening I was most certain about"),
            Citation(entry_id=archive[AGAIN], entry_date=date.today() - timedelta(days=80),
                     text="Doubled down again on the one game I felt sure of"),
        ),
        span_start=date.today() - timedelta(days=120),
        span_end=date.today() - timedelta(days=80),
        entries_read=3,
        confidence_level="low",
    )


# --- what a construct is anchored in ------------------------------------------

def test_a_construct_is_anchored_in_the_owners_sentences(test_user, archive):
    theme_id = constructs.promote(test_user["id"], _observation(archive))

    prototypes = db.get_theme_prototypes(theme_id)
    assert len(prototypes) == 2
    quotes = {p["quote"] for p in prototypes}
    assert "I went all in on the opening I was most certain about" in quotes
    for p in prototypes:
        assert p["quote"] in (CERTAIN + AGAIN), "a prototype must be text the owner wrote"


def test_the_models_wording_never_enters_the_vector(test_user, archive, monkeypatch):
    """The claim describes the pattern; the quotes *are* it (ADR-0014).

    Embedding the claim would anchor a construct in how a model talks, and it
    would then match entries for resembling that voice rather than the owner's.
    """
    # Patched where it lives, not where it is used: constructs imports it inside
    # promote() rather than at module scope, because binding agent.pipeline at
    # import time made the whole package uncircular-importable.
    import agent.pipeline as pipeline

    embedded: list[str] = []
    real = pipeline.generate_embedding
    monkeypatch.setattr(pipeline, "generate_embedding",
                        lambda text: embedded.append(text) or real(text))

    constructs.promote(test_user["id"], _observation(archive))

    assert embedded, "nothing was embedded"
    assert CLAIM not in embedded
    assert all(quote in (CERTAIN + AGAIN) for quote in embedded)


def test_the_claim_is_kept_whole_beside_the_short_name(test_user, archive):
    theme_id = constructs.promote(test_user["id"], _observation(archive))
    theme = db.get_theme_by_id(theme_id)

    assert theme["definition"] == CLAIM, "the full claim is not thrown away"
    assert theme["summary"], "and a card-sized name exists"
    assert len(theme["summary"]) <= constructs.SUMMARY_MAX_CHARS + 1


def test_an_observation_with_no_citations_is_not_promoted(test_user):
    empty = Observation(claim="Something felt true", citations=(), span_start=None,
                        span_end=None, entries_read=0, confidence_level="low")
    assert constructs.promote(test_user["id"], empty) is None


# --- a candidate is not measured ----------------------------------------------

def test_a_candidate_is_invisible_to_every_engine(test_user, archive):
    theme_id = constructs.promote(test_user["id"], _observation(archive))

    assert db.get_theme_by_id(theme_id)["status"] == "candidate"
    assert theme_id not in [t["id"] for t in db.get_themes(test_user["id"])], (
        "an unconfirmed candidate must not reach the engines")
    assert theme_id in [t["id"] for t in db.get_themes_by_status(test_user["id"], "candidate")]


def test_a_candidate_claims_no_occurrences_it_has_not_measured(test_user, archive):
    theme_id = constructs.promote(test_user["id"], _observation(archive))
    assert db.get_theme_by_id(theme_id)["occurrence_count"] == 0
    assert db.get_theme_occurrences(theme_id) == []


def test_rejecting_measures_nothing(test_user, archive):
    theme_id = constructs.promote(test_user["id"], _observation(archive))
    constructs.reject(theme_id)

    assert db.get_theme_by_id(theme_id)["status"] == "rejected"
    assert db.get_theme_occurrences(theme_id) == []
    assert theme_id not in [t["id"] for t in db.get_themes(test_user["id"])]


# --- confirming is what turns a claim into evidence ---------------------------

def test_confirming_finds_the_entries_the_construct_describes(test_user, archive_with_voice):
    theme_id = constructs.promote(test_user["id"], _observation(archive_with_voice))
    written = constructs.confirm(theme_id)

    theme = db.get_theme_by_id(theme_id)
    assert theme["status"] == "active"
    assert theme["confirmed_at"] is not None, "when the owner vouched for it is provenance"
    assert written > 0

    cited = {o["source_id"] for o in db.get_theme_occurrences(theme_id)}
    assert archive_with_voice[CERTAIN] in cited and archive_with_voice[AGAIN] in cited


def test_an_unrelated_entry_is_not_swept_in(test_user, archive_with_voice):
    """The failure this guards against is the one clustering already made once:
    comparing raw, one theme matched 121 of 132 entries."""
    theme_id = constructs.promote(test_user["id"], _observation(archive_with_voice))
    constructs.confirm(theme_id)

    cited = {o["source_id"] for o in db.get_theme_occurrences(theme_id)}
    assert archive_with_voice[UNRELATED] not in cited


def test_a_confirmed_construct_is_measured_like_any_theme(test_user, archive_with_voice):
    """The whole point of storing it as a theme: no new arithmetic."""
    from agent.trajectory import TrajectoryEngine

    theme_id = constructs.promote(test_user["id"], _observation(archive_with_voice))
    constructs.confirm(theme_id)

    measured = {t["theme_id"] for t in TrajectoryEngine(test_user["id"]).analyze_all_themes()}
    assert theme_id in measured


def test_a_memory_only_entry_can_never_become_an_occurrence(test_user, archive_with_voice, process_queue):
    """Placeholders and copied text stay searchable and stop being proof."""
    ReflectionService(test_user["id"]).create_reflection(
        content=CERTAIN, reflection_date=date.today() - timedelta(days=5),
        evidence_eligible=False)
    process_queue()

    theme_id = constructs.promote(test_user["id"], _observation(archive_with_voice))
    constructs.confirm(theme_id)

    eligible = {e["source_id"] for e in db.get_entries_with_vectors(test_user["id"])}
    cited = {o["source_id"] for o in db.get_theme_occurrences(theme_id)}
    assert cited <= eligible


def test_scanning_an_unknown_construct_is_harmless(test_user):
    assert constructs.scan(999999) == 0


def test_the_stored_centroid_is_the_mean_of_its_prototypes(test_user, archive):
    theme_id = constructs.promote(test_user["id"], _observation(archive))
    prototypes = db.get_theme_prototypes(theme_id)

    expected = np.mean([constructs._as_vector(p["vector"]) for p in prototypes], axis=0)
    stored = constructs._as_vector(db.get_theme_by_id(theme_id)["centroid_embedding"])
    assert np.allclose(stored, expected, atol=1e-6)
