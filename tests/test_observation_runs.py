"""What a reading run leaves behind, and what a rerun does with it.

An independent review asked how many raw observations preceded consolidation on
the historical run. Nothing had recorded it, so the merge could only be judged
by its output — and, as the review put it, that "prevents assigning every
undesirable final candidate specifically to consolidation rather than an initial
extraction error".

Two other gaps came with it. A read where half the passes failed was
indistinguishable from one that found little, because only findings came back.
And re-reading unchanged writing offered the owner proposals they had already
rejected, since nothing tied a proposal to its own identity between runs.

Every entry below is invented.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from agent import constructs
from agent.database import db
from agent.observations import ObservationEngine
from agent.trackers.reflections import ReflectionService

CERTAIN = "I went all in on the opening I was most certain about and lost half the pieces."
AGAIN = "Doubled down again on the one game I felt sure of, and it went against me."
CLAIM = "The boldest moves appeared alongside the strongest expressions of certainty"

QUOTE_ONE = "I went all in on the opening I was most certain about"
QUOTE_TWO = "Doubled down again on the one game I felt sure of"


@pytest.fixture
def archive(test_user, process_queue):
    service = ReflectionService(test_user["id"])
    ids = {}
    for offset, text in ((120, CERTAIN), (80, AGAIN)):
        ids[text] = service.create_reflection(
            content=text, reflection_date=date.today() - timedelta(days=offset))
    process_queue()
    return ids


class FakeModel:
    """Returns a scripted reply per call, or raises where the script says to."""

    model = "fake-model"

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    def chat(self, messages, system_prompt, **kwargs):
        self.calls += 1
        reply = self.replies.pop(0) if self.replies else '{"observations": []}'
        if isinstance(reply, Exception):
            raise reply
        return reply


def _finding(archive, claim=CLAIM):
    return json.dumps({"observations": [{"claim": claim, "quotes": [
        {"entryId": archive[CERTAIN], "sourceType": "reflection", "text": QUOTE_ONE},
        {"entryId": archive[AGAIN], "sourceType": "reflection", "text": QUOTE_TWO},
    ]}]})


def _runs(user_id):
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id, status, passes_planned, passes_completed, entries_read,
                      raw_observations, candidates_staged, model, prompt_version, error
                 FROM observation_runs WHERE user_id = %s ORDER BY id;""",
            (user_id,))
        keys = ("id", "status", "planned", "completed", "entries_read",
                "raw", "staged", "model", "prompt_version", "error")
        return [dict(zip(keys, r)) for r in cur.fetchall()]


# --- the run says what it covered ---------------------------------------------

def test_a_completed_read_is_recorded_as_complete(test_user, archive):
    engine = ObservationEngine(test_user["id"], intelligence=FakeModel(_finding(archive)))
    findings, run_id = engine.read_archive(include_staged=False)

    run = _runs(test_user["id"])[0]
    assert run["id"] == run_id
    assert run["status"] == "complete"
    assert run["completed"] == run["planned"]
    assert run["entries_read"] == 2
    assert run["model"] == "fake-model" and run["prompt_version"]
    assert findings


def test_the_raw_findings_are_kept_before_anything_is_merged(test_user, archive):
    """So consolidation can be judged later without re-reading private writing."""
    engine = ObservationEngine(test_user["id"], intelligence=FakeModel(_finding(archive)))
    engine.read_archive(include_staged=False)

    raw = _runs(test_user["id"])[0]["raw"]
    assert raw, "the pre-merge output was not preserved"
    assert raw[0]["claim"] == CLAIM
    assert len(raw[0]["citations"]) == 2, "citations were kept with the claim"


def test_a_read_that_found_nothing_is_not_a_failed_read(test_user, archive):
    engine = ObservationEngine(test_user["id"], intelligence=FakeModel('{"observations": []}'))
    findings, _ = engine.read_archive(include_staged=False)

    assert findings == []
    assert _runs(test_user["id"])[0]["status"] == "complete", (
        "finding nothing is an answer, not a failure")


def test_a_read_where_every_pass_failed_says_so(test_user, archive):
    engine = ObservationEngine(test_user["id"],
                               intelligence=FakeModel(RuntimeError("upstream is down")))
    findings, _ = engine.read_archive(include_staged=False)

    run = _runs(test_user["id"])[0]
    assert findings == []
    assert run["status"] == "failed"
    assert run["completed"] == 0
    assert "upstream is down" in (run["error"] or ""), "the reason is recorded"


def test_an_archive_too_small_to_read_records_no_run(test_user, process_queue):
    ReflectionService(test_user["id"]).create_reflection(
        content=CERTAIN, reflection_date=date.today())
    process_queue()

    findings, run_id = ObservationEngine(
        test_user["id"], intelligence=FakeModel()).read_archive(include_staged=False)
    assert (findings, run_id) == ([], None)
    assert _runs(test_user["id"]) == []


# --- a decision the owner made is respected by the next run -------------------

def test_a_rejected_proposal_is_not_offered_again(test_user, archive):
    first = constructs.discover(test_user["id"], intelligence=FakeModel(_finding(archive)),
                                include_staged=False)
    assert len(first) == 1
    constructs.reject(int(first[0]["id"]))

    again = constructs.discover(test_user["id"], intelligence=FakeModel(_finding(archive)),
                                include_staged=False)
    assert again == [], "a rejection that a rerun ignores is not a rejection"


def test_a_confirmed_construct_is_not_duplicated_by_a_rerun(test_user, archive):
    first = constructs.discover(test_user["id"], intelligence=FakeModel(_finding(archive)),
                                include_staged=False)
    constructs.confirm(int(first[0]["id"]))

    constructs.discover(test_user["id"], intelligence=FakeModel(_finding(archive)),
                        include_staged=False)

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT count(*) FROM themes
                        WHERE user_id = %s AND origin = 'observed';""", (test_user["id"],))
        assert cur.fetchone()[0] == 1, "the same finding was staged twice"


def test_a_proposal_key_survives_rewording_of_nothing(test_user, archive):
    """The same claim over the same sentences is the same proposal, whichever
    order the passes returned them in."""
    from agent.observations import Citation, Observation

    def observation(citations):
        return Observation(claim=CLAIM, citations=tuple(citations), span_start=None,
                           span_end=None, entries_read=2, confidence_level="low")

    a = Citation(entry_id=1, entry_date=date(2026, 1, 1), text=QUOTE_ONE)
    b = Citation(entry_id=2, entry_date=date(2026, 2, 1), text=QUOTE_TWO)
    assert constructs.proposal_key(observation([a, b])) == \
           constructs.proposal_key(observation([b, a]))


def test_a_different_finding_is_a_different_proposal(test_user, archive):
    from agent.observations import Citation, Observation

    cites = (Citation(entry_id=1, entry_date=date(2026, 1, 1), text=QUOTE_ONE),
             Citation(entry_id=2, entry_date=date(2026, 2, 1), text=QUOTE_TWO))
    one = Observation(claim=CLAIM, citations=cites, span_start=None, span_end=None,
                      entries_read=2, confidence_level="low")
    other = Observation(claim="Something else entirely", citations=cites, span_start=None,
                        span_end=None, entries_read=2, confidence_level="low")
    assert constructs.proposal_key(one) != constructs.proposal_key(other)


# --- the run counts what it staged --------------------------------------------

def test_the_run_records_how_many_proposals_reached_the_owner(test_user, archive):
    constructs.discover(test_user["id"], intelligence=FakeModel(_finding(archive)),
                        include_staged=False)
    assert _runs(test_user["id"])[0]["staged"] == 1
