"""A lens only annotates a checked, range-scoped personal process."""

from __future__ import annotations

import json
import re
from datetime import date

import pytest

from agent.dynamics import (Definition, DiscoveryDraft, Membership, PairDecision, QuoteRef,
                            count_independent, definition_key, partition_events, project_range)
from agent.episodes import Episode, ReadUnavailable
from agent.lens_matching import match_lenses
from agent.library import Lens, Source
from agent.observations import Citation
from agent.reference_evaluation import account_fingerprint


def _account(entry: int, *, kind: str = "event", text: str | None = None) -> Episode:
    text = text or (f"On distinct occasion {entry}, a colleague waited for an answer. "
                    "I agreed immediately and later felt stretched.")
    day = date(2026, 9, entry)
    return Episode(actor="self", record_kind=kind,
                   situation="a colleague waited for an answer" if kind == "event" else None,
                   response="I agreed immediately" if kind == "event" else None,
                   demand=None, information=None, feeling=None, concern=None,
                   immediate_outcome=None, later_outcome=None, explanation=None,
                   self_report=text if kind == "self_report" else None,
                   domain=None, recorded_on=day,
                   citations=(Citation(entry, day, text),))


def _lens(lens_id: str = "quick-agreement") -> Lens:
    source = Source("basis", "Editorial basis", "https://example.org/basis",
                    "theoretical_overview", "A heuristic, not validation of a person or match")
    return Lens(lens_id, "belonging", "Quick agreement", "request → agreement → strain",
                "A possible purpose, NOT a personal fact", "A possible return", "A possible cost",
                ("agreement before capacity check", "later strain is recorded"),
                "the choice was made after considering capacity", "urgency may explain it",
                "Was the urgency decisive?", ("basis",), (source,))


def _draft(episodes: list[Episode], *, report_ids: list[str] | None = None) -> tuple[DiscoveryDraft, str, list[str]]:
    ids = [account_fingerprint(ep.as_dict()) for ep in episodes]
    accounts = dict(zip(ids, (ep.as_dict() for ep in episodes)))
    definition = Definition(context_predicate="a colleague waits for an answer",
                            response_predicate="I agree immediately", title="Agreeing when asked",
                            proposed_account_ids=[id_ for id_, ep in zip(ids, episodes)
                                                  if ep.actor == "self" and ep.record_kind == "event"],
                            owner_report_ids=report_ids or [])
    key = definition_key(definition)
    rows = [Membership(dynamic_id=key, account_id=id_,
                       context_decision="present" if ep.actor == "self" and ep.record_kind in
                       {"event", "self_report"} else "unclear",
                       response_decision="present" if ep.actor == "self" and ep.record_kind in
                       {"event", "self_report"} else "unclear",
                       relation_decision="linked" if ep.actor == "self" and ep.record_kind in
                       {"event", "self_report"} else "unclear",
                       role="support" if ep.actor == "self" and ep.record_kind in
                       {"event", "self_report"} else "unclear",
                       refs=[QuoteRef(account_id=id_, field="situation" if ep.record_kind == "event"
                                      else "self_report", citation_index=0)]
                       if ep.actor == "self" and ep.record_kind in {"event", "self_report"} else [])
            for id_, ep in zip(ids, episodes)]
    pairs = [PairDecision(left_account_id=ids[i], right_account_id=ids[j],
                          decision="distinct_events",
                          refs=[QuoteRef(account_id=ids[k], field="situation", citation_index=0)
                                for k in (i, j)])
             for i in range(len(ids)) for j in range(i + 1, len(ids))
             if episodes[i].actor == episodes[j].actor == "self" and
             episodes[i].record_kind == episodes[j].record_kind == "event"]
    groups, rows = partition_events(key, rows, pairs, accounts)
    groups, independent = count_independent(groups, pairs, accounts)
    draft = DiscoveryDraft(episodes=accounts, definitions=[definition], memberships=rows,
                           pair_decisions=pairs, groups={key: groups},
                           independent_group_ids={key: independent}, counts={})
    return project_range(draft, "all", date(2026, 9, 30)), key, ids


class ScriptedLens:
    def __init__(self, judgments: dict[str, dict], *, bad: str | None = None):
        self.judgments = judgments
        self.bad = bad
        self.calls = []

    def chat(self, *, messages, system_prompt, **kwargs):
        content = messages[0]["content"]
        self.calls.append(content)
        rows = []
        for lens, unit in re.findall(r"^lensId=(\S+) unitId=(\S+)$", content, re.M):
            account = re.search(r"accountId=(a[1-9]\d*)\b",
                                content.split(f"lensId={lens} unitId={unit}", 1)[1]).group(1)
            field = ("self_report" if "kind=self_report" in
                     content.split(f"lensId={lens} unitId={unit}", 1)[1].split("\nlensId=", 1)[0]
                     else "situation")
            ref = {"accountId": account, "field": field, "citationIndex": 0}
            choices = self.judgments.get(unit, {})
            row = {"lensId": lens, "unitId": unit,
                   "requirementOne": choices.get("one", "present"),
                   "requirementTwo": choices.get("two", "present"),
                   "process": choices.get("process", "linked"),
                   "notWhen": choices.get("not_when", "absent"),
                   "requirementOneRefs": [ref] if choices.get("one", "present") == "present" else [],
                   "requirementTwoRefs": [ref] if choices.get("two", "present") == "present" else [],
                   "processRefs": [ref] if choices.get("process", "linked") == "linked" else [],
                   "notWhenRefs": [ref] if choices.get("not_when") == "present" else []}
            rows.append(row)
        if self.bad == "missing":
            rows.pop()
        elif self.bad == "duplicate":
            rows.append(rows[0])
        elif self.bad == "foreign":
            rows[0]["requirementOneRefs"] = [{"accountId": "foreign", "field": "situation", "citationIndex": 0}]
        elif self.bad == "enum":
            rows[0]["process"] = "probably"
        elif self.bad == "provider":
            raise RuntimeError("provider unavailable")
        return json.dumps({"decisions": rows})


def test_split_requirements_never_combine_across_groups():
    draft, key, ids = _draft([_account(1), _account(2)])
    provider = ScriptedLens({"u1": {"two": "unclear"},
                             "u2": {"one": "unclear"}})
    assert match_lenses(draft, key, [_lens()], "emerging", provider) == []
    assert len(provider.calls) == 1


def test_not_when_excludes_only_that_occasion_and_requires_two_independent_others():
    draft, key, ids = _draft([_account(1), _account(2), _account(3)])
    provider = ScriptedLens({"u1": {"not_when": "present"}})
    matches = match_lenses(draft, key, [_lens()], "recurring", provider)
    assert len(matches) == 1
    assert set(matches[0].qualifying_group_ids) == set(ids[1:])
    assert matches[0].excluded_group_ids == [ids[0]]
    assert {ref.account_id for ref in matches[0].requirement_refs} == set(ids[1:])
    assert all(ref.account_id in draft.episodes for ref in matches[0].requirement_refs)


def test_owner_described_requires_explicit_linked_self_report():
    report = _account(4, kind="self_report",
                      text="When a colleague waits for my answer, I usually agree immediately.")
    draft, key, ids = _draft([report], report_ids=[account_fingerprint(report.as_dict())])
    matches = match_lenses(draft, key, [_lens()], "owner_described", ScriptedLens({}))
    assert len(matches) == 1 and matches[0].self_report_ids == ids
    assert matches[0].qualifying_group_ids == []
    assert match_lenses(draft, key, [_lens()], "owner_described",
                        ScriptedLens({"u1": {"process": "unclear"}})) == []


def test_single_independent_group_cannot_annotate_emerging_dynamic():
    draft, key, _ = _draft([_account(1)])
    assert match_lenses(draft, key, [_lens()], "emerging", ScriptedLens({})) == []


def test_bare_behavior_does_not_establish_linked_process():
    draft, key, _ = _draft([_account(1), _account(2), _account(3)])
    provider = ScriptedLens({f"u{index}": {"process": "unclear"}
                             for index, _ in enumerate(draft.groups[key], 1)})
    assert match_lenses(draft, key, [_lens()], "recurring", provider) == []


@pytest.mark.parametrize("failure,reason", [("missing", "invalid_lens_matrix"),
                                           ("duplicate", "invalid_lens_matrix"),
                                           ("foreign", "invalid_selector"),
                                           ("enum", "invalid_schema"),
                                           ("provider", "provider_failure")])
def test_incomplete_or_unavailable_check_cannot_become_no_match(failure, reason):
    draft, key, _ = _draft([_account(1), _account(2)])
    with pytest.raises(ReadUnavailable, match=reason):
        match_lenses(draft, key, [_lens()], "emerging", ScriptedLens({}, bad=failure))


def test_over_budget_original_context_fails_instead_of_truncating():
    text = "a colleague waited for an answer. I agreed immediately. " + ("context " * 17000)
    draft, key, _ = _draft([_account(1, text=text)])
    with pytest.raises(ReadUnavailable, match="source_too_large"):
        match_lenses(draft, key, [_lens()], "emerging", ScriptedLens({}))
