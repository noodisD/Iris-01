"""Discovery must check the complete cohort before counting independent occasions."""

from __future__ import annotations

import json
import re
from datetime import date

import pytest

from agent.connections import (DISCOVER_PROMPT, FIELD_PROMPT, IDENTITY_PROMPT, MEMBERSHIP_PROMPT,
                               SPECIFICITY_PROMPT, check_account_fields, discover_dynamics)
from agent.episodes import Episode, ReadUnavailable
from agent.observations import Citation
from agent.reference_evaluation import account_fingerprint


def _event(entry_id, response="I agreed before checking my capacity", kind="event"):
    text = (f"At the distinct meeting #{entry_id}, someone was waiting for my answer. "
            f"{response}. I recorded the event separately.")
    return Episode(actor="self", record_kind=kind,
                   situation="someone was waiting for my answer", response=response,
                   demand=None, information=None, feeling=None, concern=None,
                   immediate_outcome=None, later_outcome=None, explanation=None,
                   self_report=None, domain=None, recorded_on=date(2026, 9, entry_id),
                   citations=(Citation(entry_id, date(2026, 9, entry_id), text),))


class ScriptedDecisions:
    def __init__(self, episodes, missing=False, bad_id=False):
        self.episodes = {account_fingerprint(e.as_dict()): e for e in episodes}
        self.missing = missing
        self.bad_id = bad_id
        self.calls = []

    def chat(self, *, messages, system_prompt, **_):
        self.calls.append(system_prompt)
        content = messages[0]["content"]
        ids = re.findall(r"^accountId=(a[1-9]\d*)\b", content, re.M)
        if system_prompt == DISCOVER_PROMPT:
            return json.dumps({"definitions": [{
                "contextPredicate": "Someone waited for my answer",
                "responsePredicate": "I agreed before checking capacity",
                "title": "Agreeing quickly while someone waits",
                "proposedAccountIds": ids, "ownerReportIds": []}]})
        if system_prompt == SPECIFICITY_PROMPT:
            return json.dumps({"discriminating": True, "contextMarker": "someone waiting",
                               "concreteResponse": "agreeing without a capacity check"})
        if system_prompt == MEMBERSHIP_PROMPT:
            # Definitions and accounts are shown once; the pairs to decide are listed.
            rows = [{"definitionIndex": int(index), "accountId": id_, "context": "present",
                     "response": "present", "relation": "linked",
                     "refs": [{"accountId": id_, "field": "situation", "citationIndex": 0}]}
                    for index, id_ in re.findall(
                        r"^definitionIndex=(\d+) accountId=(a[1-9]\d*)$", content, re.M)]
            if self.bad_id and rows:
                rows[0]["accountId"] = "a999"
            return json.dumps({"decisions": rows[:-1] if self.missing else rows})
        if system_prompt == IDENTITY_PROMPT:
            requested = re.findall(r"^leftAccountId=(a[1-9]\d*) rightAccountId=(a[1-9]\d*)$",
                                   content, re.M)
            return json.dumps({"pairs": [{
                "leftAccountId": left, "rightAccountId": right,
                "decision": "distinct_events",
                "refs": [{"accountId": id_, "field": "situation", "citationIndex": 0}
                         for id_ in (left, right)]}
                for left, right in requested]})
        raise AssertionError("Unexpected semantic stage")


def test_three_event_occurrences_have_a_lower_bound_not_a_label_count():
    episodes = [_event(i) for i in (1, 2, 3)]
    decisions = ScriptedDecisions(episodes)
    draft = discover_dynamics(episodes, decisions)
    assert len(draft.definitions) == 1
    key = next(iter(draft.independent_group_ids))
    assert len(draft.independent_group_ids[key]) == 3
    assert all(row.role == "support" for row in draft.memberships)
    assert len(draft.pair_decisions) == 3
    full_ids = {account_fingerprint(episode.as_dict()) for episode in episodes}
    assert set(draft.episodes) == full_ids
    assert {row.account_id for row in draft.memberships} == full_ids
    assert all(ref.account_id in full_ids for row in draft.memberships for ref in row.refs)
    assert all(pair.left_account_id in full_ids and pair.right_account_id in full_ids
               for pair in draft.pair_decisions)
    assert decisions.calls.count(MEMBERSHIP_PROMPT) >= 1


def test_missing_membership_row_is_unavailability_not_no_pattern():
    episodes = [_event(i) for i in (1, 2)]
    with pytest.raises(ReadUnavailable, match="invalid_matrix"):
        discover_dynamics(episodes, ScriptedDecisions(episodes, missing=True))


def test_unknown_provider_account_handle_cannot_become_membership():
    episodes = [_event(i) for i in (1, 2)]
    with pytest.raises(ReadUnavailable, match="invalid_matrix"):
        discover_dynamics(episodes, ScriptedDecisions(episodes, bad_id=True))


def test_field_checker_requires_all_grounded_fields_and_source_selectors():
    episode = _event(7)
    account_id = account_fingerprint(episode.as_dict())

    class FieldModel:
        def __init__(self, omit_response=False, ref_id="account"):
            self.omit_response = omit_response
            self.ref_id = ref_id

        def chat(self, *, system_prompt, **_):
            assert system_prompt == FIELD_PROMPT
            fields = ["situation"] if self.omit_response else ["situation", "response"]
            return json.dumps({"fields": [
                {"field": field, "verdict": "supported",
                 "refs": [{"accountId": self.ref_id, "field": field, "citationIndex": 0}]}
                for field in fields]})

    result = check_account_fields(episode, FieldModel())
    assert {row.field for row in result.checks} == {"situation", "response"}
    assert all(ref.account_id == account_id for row in result.checks for ref in row.refs)
    with pytest.raises(ReadUnavailable, match="invalid_selector"):
        check_account_fields(episode, FieldModel(ref_id=account_id))
    with pytest.raises(ReadUnavailable, match="invalid_matrix"):
        check_account_fields(episode, FieldModel(omit_response=True))
