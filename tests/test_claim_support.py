"""A real quote is not the same as a quote that supports the claim.

Verification proves the words exist in the entry they were attributed to. It
says nothing about whether they are an instance of what the claim describes.
The review's case: two authentic quotes that *deny* a behaviour — "I did not
double down this time", "held back on the one I felt sure of" — passed every
check and came out as evidence that the owner doubles down. Nothing could be
allowed to claim a behaviour while that was true.

check_support asks one narrow question per finding and fails closed. Every
quote below is invented.
"""

from __future__ import annotations

import json
from datetime import date

from agent.observations import (
    SUPPORT_PROMPT,
    Citation,
    Observation,
    ObservationEngine,
    check_support,
)

CLAIM = "The boldest moves appeared alongside the strongest expressions of certainty"


def _obs(*texts, entries=None):
    entries = entries or list(range(1, len(texts) + 1))
    return Observation(
        claim=CLAIM,
        citations=tuple(Citation(entry_id=e, entry_date=date(2025, 1, e), text=t)
                        for e, t in zip(entries, texts)),
        span_start=date(2025, 1, 1), span_end=date(2025, 6, 1),
        entries_read=20, confidence_level="medium")


class Verdicts:
    """Answers the support question with the verdicts a test scripts."""

    def __init__(self, *verdicts, fail=False, reply=None):
        self.verdicts, self.fail, self.reply = verdicts, fail, reply
        self.asked: list[str] = []

    def chat(self, messages, system_prompt, **kwargs):
        assert system_prompt == SUPPORT_PROMPT
        self.asked.append(messages[0]["content"])
        if self.fail:
            raise RuntimeError("provider went away")
        if self.reply is not None:
            return self.reply
        return json.dumps({"quotes": [{"i": i, "verdict": v} for i, v in enumerate(self.verdicts)]})


# --- the case that made behaviour claims unsafe ------------------------------------

def test_two_real_quotes_that_deny_a_behaviour_are_not_evidence_for_it():
    denying = _obs("I did not double down this time, for once",
                   "held back on the one game I felt sure of")

    assert check_support([denying], Verdicts("denies", "denies")) == []


def test_one_denial_among_supporting_quotes_drops_the_finding():
    """A claim contradicted by its own evidence is not a finding with a caveat."""
    mixed = _obs("went all in on the opening I was most certain about",
                 "doubled down again on the one game I felt sure of",
                 "did not double down this time")

    assert check_support([mixed], Verdicts("supports", "supports", "denies")) == []


# --- mentioning the subject is not an instance of it ----------------------------------

def test_a_quote_that_only_mentions_the_subject_is_removed():
    found = _obs("went all in on the opening I was most certain about",
                 "doubled down again on the one game I felt sure of",
                 "played chess with my brother on Sunday")

    kept = check_support([found], Verdicts("supports", "supports", "mentions"))

    assert len(kept) == 1
    assert [c.entry_id for c in kept[0].citations] == [1, 2]


def test_mentions_that_leave_too_little_support_drop_the_finding():
    found = _obs("went all in on the opening I was most certain about",
                 "played chess with my brother on Sunday")

    assert check_support([found], Verdicts("supports", "mentions")) == []


def test_support_from_one_entry_is_still_an_anecdote():
    found = _obs("went all in on the opening", "and then doubled down on it",
                 entries=[7, 7])

    assert check_support([found], Verdicts("supports", "supports")) == []


# --- it fails closed --------------------------------------------------------------------

def test_a_finding_whose_support_could_not_be_checked_is_dropped():
    """Unlike an unmerged restatement, an unchecked claim on screen is not
    harmless — so a failed check keeps nothing."""
    found = _obs("went all in on the opening", "doubled down again")

    assert check_support([found], Verdicts(fail=True)) == []
    assert check_support([found], Verdicts(reply="not json")) == []
    assert check_support([found], Verdicts("supports")) == [], "an answer missing a quote"
    assert check_support([found], Verdicts("supports", "probably")) == [], "an unknown verdict"
    assert check_support([found], None) == []


def test_one_failed_check_does_not_take_the_others_with_it():
    class OneFails:
        calls = 0

        def chat(self, messages, system_prompt, **kwargs):
            OneFails.calls += 1
            if OneFails.calls == 1:
                raise RuntimeError("once")
            return json.dumps({"quotes": [{"i": 0, "verdict": "supports"},
                                          {"i": 1, "verdict": "supports"}]})

    first, second = _obs("a first quote here", "a second quote here"), \
        _obs("a third quote here", "a fourth quote here")

    kept = check_support([first, second], OneFails())
    assert [c.text for o in kept for c in o.citations] == [c.text for c in second.citations]


def test_confidence_is_recomputed_from_what_supports_the_claim():
    """Removing quotes removes evidence, so the confidence label must follow."""
    found = _obs("went all in on the opening", "doubled down again", "played chess on Sunday")
    kept = check_support([found], Verdicts("supports", "supports", "mentions"))[0]
    assert kept.confidence_level == "low", "two entries, not the three it arrived with"


# --- the reader applies it ----------------------------------------------------------------

def test_the_reader_drops_a_finding_its_own_quotes_deny(test_user):
    """End to end: the reading pass proposes a claim with verbatim quotes, and
    the support check finds they deny it."""
    from agent.trackers.reflections import ReflectionService

    service = ReflectionService(test_user["id"])
    a = service.create_reflection(content="I did not double down this time, for once.",
                                  reflection_date=date(2025, 1, 5))
    b = service.create_reflection(content="Held back on the one game I felt sure of.",
                                  reflection_date=date(2025, 2, 5))

    class Reader:
        def chat(self, messages, system_prompt, **kwargs):
            if system_prompt == SUPPORT_PROMPT:
                return json.dumps({"quotes": [{"i": 0, "verdict": "denies"},
                                              {"i": 1, "verdict": "denies"}]})
            return json.dumps({"observations": [{"claim": CLAIM, "quotes": [
                {"entryId": a, "sourceType": "reflection", "text": "I did not double down this time"},
                {"entryId": b, "sourceType": "reflection", "text": "Held back on the one game I felt sure of"},
            ]}]})

    assert ObservationEngine(test_user["id"], intelligence=Reader()).read() == []
