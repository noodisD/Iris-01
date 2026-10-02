"""A candidate definition must recur before it is checked against the archive."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import date

from test_connections import _event

from agent import connections
from agent.connections import DISCOVER_PROMPT
from agent.episodes import Episode
from agent.observations import Citation
from agent.reference_evaluation import account_fingerprint


def _self_report(entry_id: int) -> Episode:
    text = f"Whenever someone waits on me, I say yes before I check my week. (entry {entry_id})"
    return replace(_event(entry_id), record_kind="self_report", situation=None, response=None,
                   self_report="Whenever someone waits on me, I say yes before I check my week.",
                   citations=(Citation(entry_id, date(2026, 9, entry_id), text),))


class Proposer:
    """Names the given handles, chosen by a function of the request's accounts."""

    def __init__(self, choose):
        self.choose = choose
        self.requests: list[str] = []

    def chat(self, *, messages, system_prompt, **_):
        assert system_prompt == DISCOVER_PROMPT
        content = messages[0]["content"]
        self.requests.append(content)
        listed = re.findall(r"^accountId=(a\d+) kind=(\w+)", content, re.M)
        events = [h for h, kind in listed if kind == "event"]
        reports = [h for h, kind in listed if kind == "self_report"]
        return json.dumps({"definitions": self.choose(events, reports)})


def _definition(events, reports=()):
    return {"contextPredicate": "Someone is waiting on my answer",
            "responsePredicate": "I agree before checking my capacity",
            "title": "Agreeing while someone waits",
            "proposedAccountIds": list(events), "ownerReportIds": list(reports)}


def _propose(episodes, choose, new=None):
    accounts = {account_fingerprint(e.as_dict()): e for e in episodes}
    handles = {id_: f"a{index}" for index, id_ in enumerate(sorted(accounts), 1)}
    model = Proposer(choose)
    found = connections._propose(accounts, handles, {h: i for i, h in handles.items()}, model,
                                 new=None if new is None else {account_fingerprint(e.as_dict()) for e in new})
    return found, model


def test_a_candidate_seen_once_is_dropped_before_it_costs_a_check():
    found, _ = _propose([_event(1), _event(2)], lambda events, reports: [_definition(events[:1])])
    assert found == []


def test_two_events_from_one_entry_do_not_recur():
    text = ("At the distinct meeting #1, someone was waiting for my answer. I agreed before "
            "checking my capacity. Later someone waited again and I said yes again before checking.")
    one_entry = (Citation(1, date(2026, 9, 1), text),)
    first = replace(_event(1), citations=one_entry)
    second = replace(_event(1), response="I said yes again before checking", citations=one_entry)
    found, _ = _propose([first, second], lambda events, reports: [_definition(events)])
    assert found == []


def test_events_from_different_entries_or_the_owners_own_statement_are_kept():
    found, model = _propose([_event(1), _event(2), _self_report(3)], lambda events, reports: (
        [_definition(events)] if events else [_definition([], reports)]))
    assert [len(d.proposed_account_ids) for d in found] == [2, 0]
    assert [len(d.owner_report_ids) for d in found] == [0, 1]
    assert len(model.requests) == 2, "events and self-reports are proposed in separate passes"


def test_proposals_are_read_from_extracted_fields_not_source_passages():
    _, model = _propose([_event(1), _event(2)], lambda events, reports: [])
    assert "situation: someone was waiting for my answer" in model.requests[0]
    assert "I recorded the event separately" not in model.requests[0], "no passage text"


def test_a_new_entry_proposes_only_what_includes_it():
    earlier = [_event(1), _event(2)]
    new = _event(3)
    found, model = _propose([*earlier, new], lambda events, reports: [
        _definition(events[:2]), _definition(events)], new=[new])
    marked = re.findall(r"^accountId=(a\d+) .*new=yes", model.requests[0], re.M)
    assert len(marked) == 1
    assert all(any(account_fingerprint(new.as_dict()) == aid for aid in d.proposed_account_ids)
               for d in found), "every kept candidate names the new account"
