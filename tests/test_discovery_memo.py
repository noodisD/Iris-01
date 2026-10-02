"""Discovery asks the model about each unchanged thing once, not on every run."""

from __future__ import annotations

import json
import re

import pytest
from test_connections import ScriptedDecisions, _event

from agent import discovery_memo as memo
from agent.connections import (DISCOVER_PROMPT, EQUIVALENCE_PROMPT, IDENTITY_PROMPT, MEMBERSHIP_PROMPT,
                               discover_dynamics)
from agent.database import db
from agent.episodes import ReadUnavailable


class SameWording(ScriptedDecisions):
    """Proposes the same relationship every time, so a new proposal and a
    carried definition are the same definition."""

    def chat(self, *, messages, system_prompt, **kwargs):
        if system_prompt != EQUIVALENCE_PROMPT:
            return super().chat(messages=messages, system_prompt=system_prompt, **kwargs)
        self.calls.append(system_prompt)
        indexes = [int(i) for i in re.findall(r"^\[(\d+)\]", messages[0]["content"], re.M)]
        return json.dumps({"pairs": [
            {"a": indexes[i], "b": indexes[i + 1], "contextAB": True, "contextBA": True,
             "responseAB": True, "responseBA": True, "incompatible": False}
            for i in range(0, len(indexes), 2)]})


def _kept(user_id: int) -> dict[str, int]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT kind, count(*) FROM discovery_memo WHERE user_id = %s GROUP BY kind", (user_id,))
        return dict(cur.fetchall())


def test_a_second_run_over_the_same_archive_asks_nothing(test_user):
    episodes = [_event(i) for i in (1, 2, 3)]
    first = ScriptedDecisions(episodes)
    with memo.remembering(test_user["id"]):
        draft = discover_dynamics(episodes, first)
    assert first.calls.count(MEMBERSHIP_PROMPT) == 3, "one request per account, not per row"

    again = ScriptedDecisions(episodes)
    with memo.remembering(test_user["id"]):
        repeat = discover_dynamics(episodes, again, previous=draft)
    assert again.calls == []
    assert repeat.as_dict() == draft.as_dict()


def test_a_new_entry_is_asked_about_and_nothing_else(test_user):
    episodes = [_event(i) for i in (1, 2, 3)]
    with memo.remembering(test_user["id"]):
        draft = discover_dynamics(episodes, ScriptedDecisions(episodes))

    grown = [*episodes, _event(4)]
    later = SameWording(grown)
    with memo.remembering(test_user["id"]):
        updated = discover_dynamics(grown, later, previous=draft)

    assert later.calls.count(DISCOVER_PROMPT) == 1, "only the unseen account is read for proposals"
    assert later.calls.count(MEMBERSHIP_PROMPT) == 1, "only the new account is checked"
    assert later.calls.count(IDENTITY_PROMPT) == 1, "only its three new pairs are compared"
    assert later.calls.count(EQUIVALENCE_PROMPT) == 1, "its proposal is compared with the carried one"
    key = next(iter(updated.independent_group_ids))
    assert len(updated.independent_group_ids[key]) == 4
    assert len(updated.pair_decisions) == 6


def test_without_a_previous_draft_every_account_is_still_checked(test_user):
    episodes = [_event(i) for i in (1, 2, 3)]
    with memo.remembering(test_user["id"]):
        discover_dynamics(episodes, ScriptedDecisions(episodes))
    fresh = ScriptedDecisions(episodes)
    draft = discover_dynamics(episodes, fresh)  # outside a memo scope: nothing reused
    assert fresh.calls.count(MEMBERSHIP_PROMPT) == 3
    assert len(draft.memberships) == 3


def test_an_incomplete_reply_is_not_kept(test_user):
    episodes = [_event(i) for i in (1, 2, 3)]
    with pytest.raises(ReadUnavailable), memo.remembering(test_user["id"]):
        discover_dynamics(episodes, ScriptedDecisions(episodes, missing=True))
    assert "membership" not in _kept(test_user["id"])


def test_a_failed_run_forgets_the_whole_replies_it_kept(test_user):
    class Model:
        model = "scripted"

        def chat(self, *, messages, system_prompt, **_):
            return json.dumps({"ok": True})

    with pytest.raises(RuntimeError), memo.remembering(test_user["id"]):
        memo.chat(Model(), "a prompt", "a request")
        assert _kept(test_user["id"]) == {"reply": 1}
        raise RuntimeError("a later check rejected the reply")
    assert _kept(test_user["id"]) == {}

    with memo.remembering(test_user["id"]):
        memo.chat(Model(), "a prompt", "a request")
    assert _kept(test_user["id"]) == {"reply": 1}


def test_the_estimate_compares_only_events_and_asks_only_about_what_is_new():
    from agent.discovery import synthesis_steps

    first = synthesis_steps(accounts=870, events=161, eligible=354)
    # Pairs are only the owner's grounded events: 161, not all 870 accounts.
    assert first["identity"] == -(-(161 * 160 // 2) // 12)
    assert first["membership"] == 2 * 870  # 24 definitions, 12 per request
    later = synthesis_steps(accounts=875, events=162, eligible=356,
                            known_accounts=870, known_events=161, known_definitions=24)
    assert later["membership"] == 2 * 5
    assert later["identity"] == -(-161 // 12)  # the one new event against the rest
    assert sum(later.values()) < sum(first.values()) / 20
