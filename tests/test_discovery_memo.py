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
    assert first.calls.count(MEMBERSHIP_PROMPT) == 1, "three accounts, one definition: one request"

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
    assert fresh.calls.count(MEMBERSHIP_PROMPT) == 1
    assert len(draft.memberships) == 3


def test_rows_answered_before_a_failure_are_kept_and_only_the_rest_asked_again(test_user):
    episodes = [_event(i) for i in (1, 2, 3)]
    with pytest.raises(ReadUnavailable, match="invalid_matrix"), memo.remembering(test_user["id"]):
        discover_dynamics(episodes, ScriptedDecisions(episodes, missing=True))
    # The last row is left out every time, even asked alone: unchecked stays
    # unavailable rather than "not a member". The two answered rows are kept.
    assert _kept(test_user["id"]).get("membership") == 2

    retry = ScriptedDecisions(episodes)
    with memo.remembering(test_user["id"]):
        discover_dynamics(episodes, retry)
    assert retry.calls.count(MEMBERSHIP_PROMPT) == 1, "only the missing row is asked again"


class LeavesOutTheLast(ScriptedDecisions):
    """Always leaves the last definition out of a request for several, but
    answers it when asked on its own: the model quirk seen on the archive."""

    def chat(self, *, messages, system_prompt, **kwargs):
        text = super().chat(messages=messages, system_prompt=system_prompt, **kwargs)
        if system_prompt == MEMBERSHIP_PROMPT:
            rows = json.loads(text)["decisions"]
            if len(rows) > 1:
                return json.dumps({"decisions": rows[:-1]})
        return text


def test_a_row_left_out_of_every_full_request_is_answered_when_asked_alone(test_user):
    episodes = [_event(i) for i in (1, 2, 3)]
    model = LeavesOutTheLast(episodes)
    with memo.remembering(test_user["id"]):
        draft = discover_dynamics(episodes, model)
    key = next(iter(draft.independent_group_ids))
    assert len(draft.independent_group_ids[key]) == 3
    assert len(draft.memberships) == 3


def test_a_failed_run_forgets_only_the_reply_that_failed(test_user):
    """Earlier replies passed their checks; keeping them lets a retry propose the
    same definitions and reuse what was already paid for."""
    class Model:
        model = "scripted"

        def chat(self, *, messages, system_prompt, **_):
            return json.dumps({"ok": messages[0]["content"]})

    with pytest.raises(RuntimeError), memo.remembering(test_user["id"]):
        memo.chat(Model(), "a prompt", "asked before an outage")
        memo.chat(Model(), "a prompt", "asked just before an outage")
        raise RuntimeError("an outage, not a failed check")
    assert _kept(test_user["id"]) == {"reply": 2}, "an outage says nothing against the replies"

    with pytest.raises(ReadUnavailable), memo.remembering(test_user["id"]):
        memo.chat(Model(), "a prompt", "the first request")
        memo.chat(Model(), "a prompt", "the request whose reply failed")
        raise ReadUnavailable("invalid_schema")
    assert _kept(test_user["id"]) == {"reply": 3}, "only the reply that failed is forgotten"

    calls = []

    class Counting(Model):
        def chat(self, *, messages, system_prompt, **kwargs):
            calls.append(messages[0]["content"])
            return super().chat(messages=messages, system_prompt=system_prompt, **kwargs)

    with memo.remembering(test_user["id"]):
        memo.chat(Counting(), "a prompt", "the first request")
        memo.chat(Counting(), "a prompt", "the request whose reply failed")
    assert calls == ["the request whose reply failed"]


class SlipsOnce(ScriptedDecisions):
    """Leaves one row out of its first membership reply, as a model sometimes does."""

    def __init__(self, episodes):
        super().__init__(episodes)
        self.slipped = False

    def chat(self, *, messages, system_prompt, **kwargs):
        text = super().chat(messages=messages, system_prompt=system_prompt, **kwargs)
        if system_prompt == MEMBERSHIP_PROMPT and not self.slipped:
            self.slipped = True
            reply = json.loads(text)
            return json.dumps({"decisions": reply["decisions"][:-1]})
        return text


def test_a_batch_missing_a_row_is_asked_again_rather_than_failing_the_run(test_user):
    episodes = [_event(i) for i in (1, 2, 3)]
    model = SlipsOnce(episodes)
    with memo.remembering(test_user["id"]):
        draft = discover_dynamics(episodes, model)
    assert model.calls.count(MEMBERSHIP_PROMPT) == 2, "one request, then the missing row alone"
    key = next(iter(draft.independent_group_ids))
    assert len(draft.independent_group_ids[key]) == 3


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


def _row(definition_key, account_id, context="unclear", response="unclear", relation="unclear"):
    from agent.dynamics import Membership, derive_role

    return Membership(dynamic_id=definition_key, account_id=account_id, context_decision=context,
                      response_decision=response, relation_decision=relation,
                      role=derive_role(context, response, relation), refs=[])


def test_a_row_unclear_on_everything_is_not_sent_as_evidence():
    from agent.dynamics import informative

    assert not informative(_row("d", "a"))
    assert informative(_row("d", "a", context="present"))
    assert informative(_row("d", "a", "present", "present", "linked"))


def test_refinement_sends_only_rows_that_say_something_and_skips_what_will_not_fit(monkeypatch):
    from agent import connections
    from agent.dynamics import Definition, definition_key

    episodes = {f"acc{i}": _event(i) for i in range(1, 29)}
    definition = Definition(context_predicate="Someone waited for my answer",
                            response_predicate="I agreed before checking capacity", title="t",
                            proposed_account_ids=["acc1"], owner_report_ids=[])
    key = definition_key(definition)
    rows = [_row(key, "acc1", "present", "unclear", "unclear")] + [_row(key, f"acc{i}") for i in range(2, 29)]
    sent = []

    def fake_ask(intelligence, prompt, content, shape, **_):
        sent.append(content)
        return shape(narrowerContext=None, reason=None)

    monkeypatch.setattr(connections, "_ask", fake_ask)
    assert connections._refine(definition, rows, episodes, object()) is None
    assert len(sent) == 1 and sent[0].count("checkedRole=") == 1, "27 all-unclear rows are not sent"

    sent.clear()
    monkeypatch.setattr(connections, "BUDGET", 100)
    assert connections._refine(definition, rows, episodes, object()) is None
    assert sent == [], "too much to send skips the optional refinement instead of failing"


def test_until_valid_asks_again_with_the_failed_reply_discarded(test_user):
    class Model:
        model = "scripted"

        def __init__(self):
            self.replies = iter(["malformed", "well formed"])

        def chat(self, *, messages, system_prompt, **_):
            return next(self.replies)

    model = Model()
    seen = []

    def attempt():
        text = memo.chat(model, "a prompt", "a request")
        seen.append(text)
        if text == "malformed":
            raise ReadUnavailable("invalid_selector")
        return text

    with memo.remembering(test_user["id"]):
        assert memo.until_valid(attempt) == "well formed"
    assert seen == ["malformed", "well formed"], "the malformed reply was not replayed from memory"
    assert _kept(test_user["id"]) == {"reply": 1}
