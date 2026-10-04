"""A personal dynamic retains outcomes only when recorded and checked."""

from dataclasses import replace
from datetime import date
import json
import re

import pytest

from agent.claim_checks import SYSTEM_PROMPT as CHECK_PROMPT
from agent.connections import discover_dynamics
from agent.dynamics import DiscoveryDraft, project_range
from agent.episodes import ReadUnavailable
from agent.observations import Citation
from agent.personal_patterns import SYSTEM_PROMPT as NARRATIVE_PROMPT, build_patterns
from tests.test_connections import ScriptedDecisions, _event


class NarrativeDecisions(ScriptedDecisions):
    def chat(self, *, messages, system_prompt, **kwargs):
        if system_prompt == NARRATIVE_PROMPT:
            content = messages[0]["content"]
            source_id = re.search(r"Included support accounts: (a[1-9]\d*)\b", content).group(1)
            return json.dumps({
                "context": {"text": "Someone waited for my answer",
                            "refs": [{"accountId": source_id, "field": "situation", "citationIndex": 0}]},
                "response": {"text": "I agreed before checking my capacity",
                             "refs": [{"accountId": source_id, "field": "response", "citationIndex": 0}]},
                "immediateReturn": None, "laterCost": None, "possibleMeaning": None,
                "alternative": None,
                "openQuestion": "Did someone waiting distinguish these occasions, or was something else relevant?"})
        if system_prompt == CHECK_PROMPT:
            source_id = re.search(r"accountId=(a[1-9]\d*)\b", messages[0]["content"]).group(1)
            return json.dumps({"clauses": [
                {"index": index, "verdict": "supported",
                 "refs": [{"accountId": source_id, "field": "situation", "citationIndex": 0}]}
                for index in range(3)], "hypotheses": []})
        return super().chat(messages=messages, system_prompt=system_prompt, **kwargs)

class UnknownNarrativeAccount(NarrativeDecisions):
    def chat(self, *, messages, system_prompt, **kwargs):
        answer = super().chat(messages=messages, system_prompt=system_prompt, **kwargs)
        if system_prompt == NARRATIVE_PROMPT:
            parsed = json.loads(answer)
            parsed["context"]["refs"][0]["accountId"] = "a999"
            return json.dumps(parsed)
        return answer

class MeaningDecisions(NarrativeDecisions):
    def chat(self, *, messages, system_prompt, **kwargs):
        content = messages[0]["content"]
        if system_prompt == NARRATIVE_PROMPT:
            answer = json.loads(super().chat(messages=messages, system_prompt=system_prompt, **kwargs))
            account = re.search(r"Included support accounts: (a[1-9]\d*)\b", content).group(1)
            group = re.search(r"Groups: (g[1-9]\d*):support", content).group(1)
            premise = {"text": "I wanted to end the wait and help the person.",
                       "refs": [{"accountId": account, "field": "concern", "citationIndex": 0}]}
            answer["possibleMeaning"] = {
                "text": "One possibility is that ending the wait mattered.",
                "premises": [premise], "scopeGroupIds": [group], "ownerReportIds": []}
            answer["alternative"] = {
                "text": "Another possibility is that helping the person mattered.",
                "premises": [premise], "scopeGroupIds": [group], "ownerReportIds": []}
            return json.dumps(answer)
        if system_prompt == CHECK_PROMPT:
            account = re.search(r"accountId=(a[1-9]\d*)\b", content).group(1)
            count = len(re.findall(r"(?m)^\[\d+\] \{", content))
            def ref(field):
                return [{"accountId": account, "field": field, "citationIndex": 0}]
            return json.dumps({
                "clauses": [{"index": i, "verdict": "supported", "refs": ref("situation")}
                            for i in range(count)],
                "hypotheses": [{"index": i, "relevance": "supported",
                                "counterevidence": "none_found", "refs": ref("concern"),
                                "tentative": True, "distinctRival": True,
                                "disconfirmingQuestion": True, "diagnosisOrInventedHistory": False}
                               for i in range(2)]})
        return super().chat(messages=messages, system_prompt=system_prompt, **kwargs)


def test_three_observed_occasions_publish_without_an_invented_cost_or_motive():
    episodes = [_event(i) for i in (1, 2, 3)]
    intelligence = NarrativeDecisions(episodes)
    draft = discover_dynamics(episodes, intelligence)
    bound = DiscoveryDraft.from_dict({**draft.as_dict(), "userId": 9})
    projected = project_range(bound, "all", date(2026, 9, 30))
    patterns = build_patterns(bound, projected, "all", date(2026, 9, 30), [], intelligence)
    assert len(patterns) == 1
    card = patterns[0]
    assert card.evidence_state == "recurring"
    assert card.independent_group_count == 3
    assert card.account_count == 3
    assert card.immediate_return is None and card.later_cost is None
    assert card.possible_meaning is None and card.alternative is None
    assert card.example.citation["entryId"] in {"1", "2", "3"}
    assert card.example.citation["text"] in {e.citations[0].text for e in episodes}
    assert {ref.account_id for clause in (card.context, card.response) for ref in clause.refs} <= set(bound.episodes)

def test_unknown_narrative_account_fails_instead_of_publishing():
    episodes = [_event(i) for i in (1, 2, 3)]
    draft = discover_dynamics(episodes, NarrativeDecisions(episodes))
    bound = DiscoveryDraft.from_dict({**draft.as_dict(), "userId": 9})
    with pytest.raises(ReadUnavailable, match="invalid_narrative"):
        build_patterns(bound, project_range(bound, "all", date(2026, 9, 30)),
                       "all", date(2026, 9, 30), [], UnknownNarrativeAccount(episodes))

def test_two_grounded_rivals_keep_stable_scope_and_source_citations():
    episodes = []
    for i in (1, 2, 3):
        event = _event(i)
        text = event.citations[0].text + " I wanted to end the wait and help the person."
        episodes.append(replace(event, concern="I wanted to end the wait and help the person.",
                                citations=(Citation(i, date(2026, 9, i), text),)))
    draft = discover_dynamics(episodes, NarrativeDecisions(episodes))
    bound = DiscoveryDraft.from_dict({**draft.as_dict(), "userId": 9})
    cards = build_patterns(bound, project_range(bound, "all", date(2026, 9, 30)),
                           "all", date(2026, 9, 30), [], MeaningDecisions(episodes))
    assert len(cards) == 1
    meaning, rival = cards[0].possible_meaning, cards[0].alternative
    assert meaning is not None and rival is not None
    groups = {group.id for group in bound.groups[next(iter(bound.groups))]}
    assert set(meaning.scope_group_ids + rival.scope_group_ids) <= groups
    assert {ref.account_id for proposal in (meaning, rival) for premise in proposal.premises
            for ref in premise.refs} <= set(bound.episodes)


class UngroundedResult(NarrativeDecisions):
    """States an immediate result citing a field the account does not record, as
    the model did three times on the archive for a self-report."""

    def chat(self, *, messages, system_prompt, **kwargs):
        answer = super().chat(messages=messages, system_prompt=system_prompt, **kwargs)
        if system_prompt == NARRATIVE_PROMPT:
            parsed = json.loads(answer)
            source = parsed["context"]["refs"][0]["accountId"]
            parsed["immediateReturn"] = {"text": "It ended the wait at once.",
                                         "refs": [{"accountId": source, "field": "immediate_outcome",
                                                   "citationIndex": 0}]}
            return json.dumps(parsed)
        return answer


def test_an_ungrounded_result_is_withheld_and_the_observed_pattern_still_published():
    episodes = [_event(i) for i in (1, 2, 3)]
    intelligence = UngroundedResult(episodes)
    draft = discover_dynamics(episodes, intelligence)
    bound = DiscoveryDraft.from_dict({**draft.as_dict(), "userId": 9})
    projected = project_range(bound, "all", date(2026, 9, 30))
    patterns = build_patterns(bound, projected, "all", date(2026, 9, 30), [], intelligence)
    assert len(patterns) == 1
    card = patterns[0]
    assert card.immediate_return is None, "a result the sources do not record is not published"
    assert card.context.refs and card.response.refs


class TitleClaimsTooMuch(NarrativeDecisions):
    def chat(self, *, messages, system_prompt, **kwargs):
        if system_prompt == CHECK_PROMPT:
            source_id = re.search(r"accountId=(a[1-9]\d*)\b", messages[0]["content"]).group(1)
            return json.dumps({"clauses": [
                {"index": index, "verdict": "supported" if index < 2 else "not_stated",
                 "refs": [{"accountId": source_id, "field": "situation", "citationIndex": 0}]
                 if index < 2 else []}
                for index in range(3)], "hypotheses": []})
        return super().chat(messages=messages, system_prompt=system_prompt, **kwargs)


def test_a_title_that_claims_too_much_is_replaced_and_the_pattern_kept():
    episodes = [_event(i) for i in (1, 2, 3)]
    intelligence = TitleClaimsTooMuch(episodes)
    draft = discover_dynamics(episodes, intelligence)
    bound = DiscoveryDraft.from_dict({**draft.as_dict(), "userId": 9})
    projected = project_range(bound, "all", date(2026, 9, 30))
    patterns = build_patterns(bound, projected, "all", date(2026, 9, 30), [], intelligence)
    assert len(patterns) == 1, "the observed relationship is still published"
    assert patterns[0].evidence_state == "recurring"
    assert patterns[0].title == "I agreed before checking my capacity"
