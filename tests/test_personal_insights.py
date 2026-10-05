"""Selected-range insights require independent occasions and source-stated premises."""
from __future__ import annotations

import json
import re
from datetime import date

from agent import personal_insights
from agent.dynamics import (DiscoveryDraft, GroundedClause, PersonalPattern, QuoteRef,
                            definition_key, dynamic_id, project_range)
from agent.episodes import Episode
from agent.observations import Citation
from agent.reference_evaluation import account_fingerprint
from tests.test_dynamics import D, definition, draft, membership, pair


def _account(n: int, *, exception: bool = False, outcome: bool = False,
             day: date = D, reason: str = "concern") -> tuple[str, dict]:
    situation = "Someone was waiting for a response."
    response = ("I checked my calendar before answering." if exception else
                "I agreed before checking my capacity.")
    concern = "I wanted to end the wait and to be helpful."
    result = "I felt relieved once the wait ended." if outcome else None
    text = " ".join(part for part in (situation, response, concern, result) if part)
    ep = Episode(actor="self", record_kind="event", situation=situation, response=response,
                 demand=None, information=None,
                 feeling=concern if reason == "feeling" else None,
                 concern=concern if reason == "concern" else None,
                 immediate_outcome=result, later_outcome=None, explanation=None,
                 self_report=None, domain=None, recorded_on=day,
                 citations=(Citation(entry_id=n, entry_date=day, text=text),))
    raw = ep.as_dict()
    return account_fingerprint(raw), raw


def _cohort(n_support: int, n_exceptions: int = 0, *, outcome: bool = False, reason: str = "concern"):
    data = [_account(n, exception=n >= n_support, outcome=outcome and n == 0, reason=reason)
            for n in range(n_support + n_exceptions)]
    ids = [key for key, _ in data]
    sources = dict(data)
    key = definition_key(definition())
    rows = [membership(key, aid, response="absent" if i >= n_support else "present")
            for i, aid in enumerate(ids)]
    pairs = [pair(a, b, "distinct_events") for i, a in enumerate(ids)
             for b in ids[i + 1:]]
    raw = draft(sources, rows, pairs)
    bound = DiscoveryDraft.from_dict({**raw.as_dict(), "userId": 25})
    return bound, project_range(bound, "all", D), ids


def _pattern(d: DiscoveryDraft) -> PersonalPattern:
    aid = next(iter(d.episodes))
    ref = QuoteRef(account_id=aid, field="situation", citation_index=0)
    clause = GroundedClause(text="Someone waited for a response", refs=[ref])
    return PersonalPattern(id=dynamic_id(d.user_id, definition()), title="Answering requests",
                           context=clause, response=clause, evidence_state="emerging",
                           owner_meanings=[], immediate_return=None, later_cost=None,
                           possible_meaning=None, alternative=None, open_question="What else mattered?",
                           lens_matches=[], exception_group_ids=[], response_elsewhere_group_ids=[],
                           independent_group_count=2, account_count=2, entry_count=2,
                           recorded_from=D, recorded_to=D, undated_account_count=0,
                           exception_count=0, unknown_account_count=0, example=None,
                           range="all", as_of=D, claim_hash="sample", snapshot="sample",
                           feedback=None)


def _proposal(d: DiscoveryDraft, ids: list[str], *, context: bool = False) -> dict:
    key = definition_key(definition())
    groups = {g.account_ids[0]: g.id for g in d.groups[key]}
    def cited(aid, field):
        return {"accountId": aid, "field": field, "citationIndex": 0}
    group_ids = [groups[aid] for aid in ids[:2]]
    premises = [{"text": "I wanted to end the wait and to be helpful",
                 "refs": [cited(aid, "concern")]} for aid in ids[:2]]
    observation_refs = ([cited(ids[0], "response"), cited(ids[2], "response")]
                        if context else [cited(ids[0], "response"), cited(ids[1], "response")])
    return {"title": "How I answer a waiting person",
            "observation": {"text": "My answers differed while someone waited" if context else
                            "I agreed before checking capacity on separate occasions",
                            "refs": observation_refs},
            "possibleMeaning": {"text": "One possibility is that I wanted to end the wait.",
                                "premises": premises, "scopeGroupIds": group_ids,
                                "ownerReportIds": []},
            "alternative": {"text": "Another possibility is that I wanted to help.",
                            "premises": [premises[0]], "scopeGroupIds": group_ids,
                            "ownerReportIds": []},
            "immediateReturn": ({"text": "I felt relieved once the wait ended",
                                 "refs": [cited(ids[0], "immediate_outcome")]}
                                if not context else None), "laterCost": None,
            "question": "Would a request without a wait change which answer I give?",
            "leftLabel": "I agreed before checking capacity" if context else None,
            "rightLabel": "I checked before answering" if context else None}


class Decisions:
    def __init__(self, proposal: dict, *, approve: bool = True):
        self.proposal = proposal
        self.approve = approve
        self.prompts: list[str] = []

    def chat(self, *, messages, system_prompt, **kwargs):
        self.prompts.append(system_prompt)
        if system_prompt == personal_insights.PROMPT:
            assert "candidateIndex=0" in messages[0]["content"]
            return json.dumps({"rows": [{"candidateIndex": 0, "proposal": self.proposal}]})
        if system_prompt == personal_insights.claim_checks.SYSTEM_PROMPT:
            content = messages[0]["content"]
            claim_count = len(re.findall(r"(?m)^\[\d+\] \{", content))
            aid = next(iter(re.findall(r"accountId=(a[1-9]\d*)\b", content)))
            selected = [{"accountId": aid, "field": "concern", "citationIndex": 0}]
            return json.dumps({"clauses": [
                {"index": i, "verdict": "supported" if self.approve else "not_stated",
                 "refs": selected if self.approve else []} for i in range(claim_count)],
                "hypotheses": [
                    {"index": i, "relevance": "supported", "counterevidence": "none_found",
                     "refs": selected, "tentative": True, "distinctRival": True,
                     "disconfirmingQuestion": True, "diagnosisOrInventedHistory": False}
                    for i in range(2)]})
        raise AssertionError("unexpected prompt")


def test_tradeoff_requires_stated_consequence_and_withholds_rejected_claims():
    missing, view, ids = _cohort(2)
    assert personal_insights.build_insights(missing, view, [_pattern(missing)], "all", D, None) == []
    bound, projected, ids = _cohort(2, outcome=True)
    model = Decisions(_proposal(bound, ids))
    found = personal_insights.build_insights(bound, projected, [_pattern(bound)], "all", D, model)
    assert len(found) == 1
    assert found[0].kind == "function_and_tradeoff"
    assert found[0].immediate_return.text == "I felt relieved once the wait ended"
    assert found[0].later_cost is None
    rejected = Decisions(_proposal(bound, ids), approve=False)
    assert personal_insights.build_insights(bound, projected, [_pattern(bound)], "all", D, rejected) == []


def test_contrast_requires_two_occasions_per_side_and_distinct_event_cross_checks():
    insufficient, view, _ = _cohort(2, 1)
    assert personal_insights.build_insights(insufficient, view, [_pattern(insufficient)],
                                            "all", D, None) == []
    bound, projected, ids = _cohort(2, 2)
    model = Decisions(_proposal(bound, ids, context=True))
    found = personal_insights.build_insights(bound, projected, [_pattern(bound)], "all", D, model)
    assert len(found) == 1
    assert found[0].kind == "contextual_difference"
    assert len(found[0].left_group_ids) == len(found[0].right_group_ids) == 2
    assert not set(found[0].left_group_ids) & set(found[0].right_group_ids)


def test_cross_side_identity_uncertainty_blocks_contrast_even_with_four_groups():
    bound, _, ids = _cohort(2, 2)
    pairs = [p if {p.left_account_id, p.right_account_id} != {ids[0], ids[2]}
             else pair(ids[0], ids[2], "unclear") for p in bound.pair_decisions]
    raw = draft(bound.episodes, [m.model_copy(update={"group_id": None})
                                 for m in bound.memberships], pairs)
    changed = DiscoveryDraft.from_dict({**raw.as_dict(), "userId": 25})
    projected = project_range(changed, "all", D)
    assert personal_insights.build_insights(changed, projected, [_pattern(changed)],
                                            "all", D, None) == []


def test_a_stated_feeling_counts_as_a_reason_for_an_occasion():
    bound, projected, _ = _cohort(2, outcome=True, reason="feeling")
    accounts = {aid: Episode.from_dict(raw) for aid, raw in projected.episodes.items()}
    candidates = personal_insights._candidates(bound, projected, [_pattern(bound)], accounts)
    assert [c.kind for c in candidates] == ["function_and_tradeoff"]
    bound, projected, _ = _cohort(2, outcome=True, reason="none")
    accounts = {aid: Episode.from_dict(raw) for aid, raw in projected.episodes.items()}
    assert personal_insights._candidates(bound, projected, [_pattern(bound)], accounts) == []
