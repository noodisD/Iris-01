"""Merging findings that are the same finding in different words.

Passes are disjoint, so they share no citations, and citation overlap cannot
reach across them. Wording can — but only carefully. An independent review was
explicit that claim similarity alone establishes nothing: "opposite or nested
claims may share vocabulary", and a merge that swallowed a narrower claim into a
broader one would put the narrower claim's evidence behind a statement it never
supported.

So the synthesis pass asks rather than assumes, and acts on one answer only.
These tests are the rails: what may merge, what may not, and what happens when
the answer cannot be trusted.

Every claim below is invented.
"""

from __future__ import annotations

import json
from datetime import date

from agent.observations import Citation, Observation, synthesise

BIG = "The boldest moves appeared alongside the strongest expressions of certainty"
SAME = "Boldness was greatest where the writing expressed most confidence"
NARROW = "One position in March was the largest of the year"
OPPOSITE = "The boldest moves appeared where the writing expressed most doubt"


def _obs(claim, ids, entries_read=5):
    return Observation(
        claim=claim,
        citations=tuple(Citation(entry_id=i, entry_date=date(2026, 1, i), text=f"quote {i}")
                        for i in ids),
        span_start=date(2026, 1, 1), span_end=date(2026, 3, 1),
        entries_read=entries_read, confidence_level="low")


class Model:
    """Answers the synthesis question with a scripted verdict."""

    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def chat(self, messages, system_prompt, **kwargs):
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def _pairs(*triples):
    return json.dumps({"pairs": [{"a": a, "b": b, "relationship": r} for a, b, r in triples]})


# --- what may merge ------------------------------------------------------------

def test_two_statements_of_one_finding_become_one():
    merged = synthesise([_obs(BIG, [1, 2]), _obs(SAME, [7, 8])],
                        Model(_pairs((0, 1, "equivalent"))))

    assert len(merged) == 1
    assert {c.entry_id for c in merged[0].citations} == {1, 2, 7, 8}, "evidence is pooled"


def test_the_surviving_claim_is_one_that_was_actually_made():
    """Never a new sentence written to cover both. A merged finding has to be
    something the model already said and the citations already backed."""
    merged = synthesise([_obs(BIG, [1, 2]), _obs(SAME, [7, 8])],
                        Model(_pairs((0, 1, "equivalent"))))

    assert merged[0].claim in (BIG, SAME)


def test_a_merge_records_what_it_was_made_from():
    merged = synthesise([_obs(BIG, [1, 2]), _obs(SAME, [7, 8])],
                        Model(_pairs((0, 1, "equivalent"))))

    assert set(merged[0].merged_from) == {BIG, SAME}, (
        "a merge the owner cannot see is a merge they cannot undo")


def test_an_unmerged_finding_carries_no_merge_history():
    kept = synthesise([_obs(BIG, [1, 2]), _obs(NARROW, [7, 8])],
                      Model(_pairs((0, 1, "narrower"))))
    assert all(o.merged_from == () for o in kept)


# --- what may not --------------------------------------------------------------

def test_a_narrower_claim_is_not_swallowed_by_a_broader_one():
    """Merging these would put one entry's evidence behind a claim about the
    whole year that it never supported."""
    kept = synthesise([_obs(BIG, [1, 2]), _obs(NARROW, [7, 8])],
                      Model(_pairs((0, 1, "narrower"))))
    assert len(kept) == 2


def test_contradictory_claims_are_never_merged():
    kept = synthesise([_obs(BIG, [1, 2]), _obs(OPPOSITE, [7, 8])],
                      Model(_pairs((0, 1, "contradictory"))))
    assert len(kept) == 2


def test_related_is_not_equivalent():
    kept = synthesise([_obs(BIG, [1, 2]), _obs(NARROW, [7, 8])],
                      Model(_pairs((0, 1, "related"))))
    assert len(kept) == 2


def test_an_unrecognised_verdict_does_not_merge():
    kept = synthesise([_obs(BIG, [1, 2]), _obs(SAME, [7, 8])],
                      Model(_pairs((0, 1, "probably the same honestly"))))
    assert len(kept) == 2


# --- when the answer cannot be trusted -----------------------------------------

def test_a_failed_synthesis_leaves_findings_unmerged():
    """Failing to merge is visible and harmless. Failing into a wrong merge is
    neither."""
    kept = synthesise([_obs(BIG, [1, 2]), _obs(SAME, [7, 8])],
                      Model(RuntimeError("upstream is down")))
    assert len(kept) == 2


def test_a_reply_that_is_not_json_leaves_findings_unmerged():
    kept = synthesise([_obs(BIG, [1, 2]), _obs(SAME, [7, 8])],
                      Model("I think the first two are the same, roughly"))
    assert len(kept) == 2


def test_indices_outside_the_list_are_ignored():
    kept = synthesise([_obs(BIG, [1, 2]), _obs(SAME, [7, 8])],
                      Model(_pairs((0, 99, "equivalent"))))
    assert len(kept) == 2


def test_a_claim_cannot_be_merged_with_itself():
    kept = synthesise([_obs(BIG, [1, 2]), _obs(SAME, [7, 8])],
                      Model(_pairs((1, 1, "equivalent"))))
    assert len(kept) == 2


# --- the model is not asked when there is nothing to ask ------------------------

def test_a_single_finding_is_not_sent_anywhere():
    model = Model(_pairs())
    assert len(synthesise([_obs(BIG, [1, 2])], model)) == 1
    assert model.calls == 0, "a pointless call still sends private writing"


def test_no_model_means_no_merging():
    assert len(synthesise([_obs(BIG, [1, 2]), _obs(SAME, [7, 8])], None)) == 2


# --- order must not decide the outcome -----------------------------------------

def test_the_result_does_not_depend_on_which_pass_finished_first():
    a, b = _obs(BIG, [1, 2]), _obs(SAME, [7, 8])
    forward = synthesise([a, b], Model(_pairs((0, 1, "equivalent"))))
    backward = synthesise([b, a], Model(_pairs((0, 1, "equivalent"))))

    assert len(forward) == len(backward) == 1
    assert forward[0].claim == backward[0].claim
    assert {c.entry_id for c in forward[0].citations} == \
           {c.entry_id for c in backward[0].citations}


def test_entries_read_is_not_inflated_by_merging():
    merged = synthesise([_obs(BIG, [1, 2], entries_read=5),
                         _obs(SAME, [7, 8], entries_read=5)],
                        Model(_pairs((0, 1, "equivalent"))))
    assert merged[0].entries_read == 5, "two five-entry passes did not read ten entries"
