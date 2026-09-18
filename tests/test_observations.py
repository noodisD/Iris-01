"""What an engine that reads entries is allowed to come back with.

The counting engines can report that a theme occurred nine times in three weeks.
They cannot notice "you commit hardest where you feel most certain",
because that is not a frequency — it is something a reader sees. So one engine
reads the entries. Everything here exists because a model given somebody's
journal will produce fluent, confident, unfalsifiable sentences about them, and
the only defence is refusing the ones it cannot prove it read.

Each fixture's correct answer is known by construction (ADR-0009): the entries
are written here, so what is quotable from them is not a matter of opinion.

Every entry below is invented.
"""

from __future__ import annotations

import json
import pathlib
from datetime import date, timedelta

import pytest

from agent.constants import OBSERVATION_MIN_QUOTE_CHARS
from agent.observations import ObservationEngine, apply_preferences
from agent.preferences import UserPreferencesService
from agent.trackers.reflections import ReflectionService

CERTAIN = "I went all in on the opening I was most certain about and lost half the pieces."
AGAIN = "Doubled down again on the one game I felt sure of, and it went against me."
SMALL = "Took a quiet line while unsure, and that is the one that worked out."
QUIET = "Walked by the river and did not look at a chart all day."


@pytest.fixture
def archive(test_user):
    """Four entries across four months, each on its own day."""
    service = ReflectionService(test_user["id"])
    ids = {}
    for offset, text in ((120, CERTAIN), (80, AGAIN), (40, SMALL), (5, QUIET)):
        rid = service.create_reflection(
            content=text, reflection_date=date.today() - timedelta(days=offset))
        ids[text] = rid
    return ids


class FakeModel:
    """Stands in for the model. Returns exactly what the test wants said."""

    def __init__(self, payload):
        self.payload = payload
        self.prompts: list[str] = []

    def chat(self, messages, system_prompt, **kwargs):
        self.prompts.append(messages[0]["content"])
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload)


def _engine(user_id, payload):
    return ObservationEngine(user_id, intelligence=FakeModel(payload))


def _claim(text, quotes):
    return {"observations": [{"claim": text, "quotes": quotes}]}


# --- what survives ------------------------------------------------------------

def test_an_observation_backed_by_real_quotes_is_kept(test_user, archive):
    engine = _engine(test_user["id"], _claim(
        "Boldness was largest in the entries expressing the most certainty",
        [{"entryId": archive[CERTAIN], "text": "I went all in on the opening I was most certain about"},
         {"entryId": archive[AGAIN], "text": "Doubled down again on the one game I felt sure of"}]))

    observations = engine.read()
    assert len(observations) == 1
    assert len(observations[0].citations) == 2
    assert {c.entry_id for c in observations[0].citations} == {archive[CERTAIN], archive[AGAIN]}


def test_an_observation_carries_the_span_it_was_read_from(test_user, archive):
    engine = _engine(test_user["id"], _claim(
        "Certainty and boldness appeared together",
        [{"entryId": archive[CERTAIN], "text": "I went all in on the opening I was most certain about"},
         {"entryId": archive[AGAIN], "text": "Doubled down again on the one game I felt sure of"}]))

    observation = engine.read()[0]
    assert observation.span_start == date.today() - timedelta(days=120)
    assert observation.span_end == date.today() - timedelta(days=5)
    assert observation.entries_read == 4


def test_only_whitespace_may_differ_from_what_was_written(test_user, archive):
    """Reflowing a quoted line is not misquoting. Changing a word is."""
    engine = _engine(test_user["id"], _claim(
        "Certainty and boldness appeared together",
        [{"entryId": archive[CERTAIN], "text": "I went all in\n   on the opening I was most certain about"},
         {"entryId": archive[AGAIN], "text": "Doubled down again on the one game I felt sure of"}]))

    assert len(engine.read()) == 1


# --- what is refused ----------------------------------------------------------

def test_a_quote_that_appears_in_no_entry_drops_the_observation(test_user, archive):
    engine = _engine(test_user["id"], _claim(
        "A confident pattern of overcommitment",
        [{"entryId": archive[CERTAIN], "text": "I always double down when I am winning"},
         {"entryId": archive[AGAIN], "text": "Doubled down again on the one game I felt sure of"}]))

    assert engine.read() == [], "an invented quote is not repaired, it is refused"


def test_a_quote_attributed_to_the_wrong_entry_is_refused(test_user, archive):
    """The words exist — in a different entry. A citation that points at the
    wrong day is how a false pattern gets built out of true sentences."""
    engine = _engine(test_user["id"], _claim(
        "Certainty and boldness appeared together",
        [{"entryId": archive[SMALL], "text": "I went all in on the opening I was most certain about"},
         {"entryId": archive[AGAIN], "text": "Doubled down again on the one game I felt sure of"}]))

    assert engine.read() == []


def test_an_observation_resting_on_one_entry_is_not_a_pattern(test_user, archive):
    engine = _engine(test_user["id"], _claim(
        "A tendency to go all in",
        [{"entryId": archive[CERTAIN], "text": "I went all in on the opening I was most certain about"},
         {"entryId": archive[CERTAIN], "text": "lost half the pieces"}]))

    assert engine.read() == []


def test_causal_and_prescriptive_wording_is_refused(test_user, archive):
    quotes = [{"entryId": archive[CERTAIN], "text": "I went all in on the opening I was most certain about"},
              {"entryId": archive[AGAIN], "text": "Doubled down again on the one game I felt sure of"}]
    for claim in ("Certainty caused the bolder moves",
                  "You should size down when certain",
                  "The losses were due to overconfidence"):
        assert _engine(test_user["id"], _claim(claim, quotes)).read() == [], claim


def test_one_bad_claim_does_not_discard_the_good_ones(test_user, archive):
    quotes = [{"entryId": archive[CERTAIN], "text": "I went all in on the opening I was most certain about"},
              {"entryId": archive[AGAIN], "text": "Doubled down again on the one game I felt sure of"}]
    engine = _engine(test_user["id"], {"observations": [
        {"claim": "Certainty caused the bolder moves", "quotes": quotes},
        {"claim": "The boldest moves appeared alongside the strongest certainty", "quotes": quotes},
    ]})

    kept = engine.read()
    assert len(kept) == 1
    assert kept[0].claim.startswith("The boldest moves")


def test_a_quote_too_short_to_mean_anything_does_not_count(test_user, archive):
    short = "all in"
    assert len(short) < OBSERVATION_MIN_QUOTE_CHARS
    engine = _engine(test_user["id"], _claim(
        "A pattern of certainty",
        [{"entryId": archive[CERTAIN], "text": short},
         {"entryId": archive[AGAIN], "text": "Doubled down again on the one game I felt sure of"}]))

    assert engine.read() == []


def test_an_answer_that_is_not_json_yields_nothing(test_user, archive):
    assert _engine(test_user["id"], "Here's what I noticed about you: …").read() == []


def test_a_model_failure_yields_nothing_rather_than_a_guess(test_user, archive):
    class Broken:
        def chat(self, *a, **kw):
            raise RuntimeError("upstream is down")

    assert ObservationEngine(test_user["id"], intelligence=Broken()).read() == []


# --- what it is allowed to read -----------------------------------------------

def test_memory_only_entries_are_never_read_or_quoted(test_user, archive):
    """Copied text and placeholders stay searchable, but must not become the
    evidence under a statement about the person."""
    rid = ReflectionService(test_user["id"]).create_reflection(
        content="Copied setup text that appears in the archive twice over.",
        reflection_date=date.today() - timedelta(days=10), evidence_eligible=False)

    engine = _engine(test_user["id"], _claim(
        "Something about the copied text",
        [{"entryId": rid, "text": "Copied setup text that appears in the archive twice over."},
         {"entryId": archive[AGAIN], "text": "Doubled down again on the one game I felt sure of"}]))
    observations = engine.read()

    assert observations == []
    assert "Copied setup text" not in engine.intelligence.prompts[0], "it was not even sent"


def test_chat_is_never_read(test_user, archive):
    """Conversation informs recall, never proof (ADR-0003)."""
    engine = _engine(test_user["id"], {"observations": []})
    engine.read()
    prompt = engine.intelligence.prompts[0]
    for text in (CERTAIN, AGAIN, SMALL, QUIET):
        assert text in prompt
    assert "said in chat" not in prompt


def test_nothing_reads_the_archive_unless_it_is_asked(test_user):
    """The whole design rests on this: no background path reaches the engine,
    so the journal is never sent anywhere the owner did not send it."""
    root = pathlib.Path(__file__).resolve().parent.parent / "agent"
    for name in ("pipeline.py", "core.py", "pipeline_orchestrator.py", "insights_service.py"):
        source = (root / name).read_text()
        assert "ObservationEngine" not in source, f"{name} can reach the reader"
        assert "from .observations" not in source, f"{name} imports the reader"


# --- the same policy as everything else ---------------------------------------

def test_the_owners_confidence_threshold_governs_here_too(test_user, archive):
    engine = _engine(test_user["id"], _claim(
        "The boldest moves appeared alongside the strongest certainty",
        [{"entryId": archive[CERTAIN], "text": "I went all in on the opening I was most certain about"},
         {"entryId": archive[AGAIN], "text": "Doubled down again on the one game I felt sure of"}]))
    observations = engine.read()
    assert observations and observations[0].confidence_level == "low"

    prefs = UserPreferencesService(test_user["id"])
    prefs.update_pref("min_confidence", "high")
    assert apply_preferences(observations, test_user["id"]) == []

    prefs.update_pref("min_confidence", "low")
    assert apply_preferences(observations, test_user["id"]) == observations
