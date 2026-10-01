"""Independent check retains an observed action while withholding a rejected motive."""

from datetime import date
import json

import pytest

from agent.claim_checks import SYSTEM_PROMPT, assess
from agent.dynamics import GroundedClause, Hypothesis, QuoteRef
from agent.episodes import Episode, ReadUnavailable
from agent.observations import Citation
from agent.reference_evaluation import account_fingerprint


TEXT = ("Before the ferry left I checked the safety latch twice because procedure required it. "
        "I was not worried about anybody's approval; I wanted a safe inspection record.")


def _account():
    return Episode(actor="self", record_kind="event",
                   situation="Before the ferry left", response="I checked the safety latch twice",
                   demand=None, information=None, feeling=None,
                   concern="I wanted a safe inspection record",
                   immediate_outcome=None, later_outcome=None,
                   explanation="because procedure required it", self_report=None, domain=None,
                   recorded_on=date(2026, 9, 12),
                   citations=(Citation(1, date(2026, 9, 12), TEXT),))


class Judgments:
    def __init__(self, *, incomplete=False, foreign=False):
        self.incomplete = incomplete
        self.foreign = foreign

    def chat(self, *, system_prompt, **_):
        assert system_prompt == SYSTEM_PROMPT
        source_id = "a2" if self.foreign else "a1"
        answer = {"clauses": [{"index": 0, "verdict": "supported",
                                "refs": [{"accountId": source_id, "field": "response", "citationIndex": 0}]}],
                  "hypotheses": [{"index": 0, "relevance": "contradicted", "counterevidence": "found",
                                  "refs": [{"accountId": source_id, "field": "explanation", "citationIndex": 0}],
                                  "tentative": True, "distinctRival": True,
                                  "disconfirmingQuestion": True,
                                  "diagnosisOrInventedHistory": False}]}
        if self.incomplete:
            answer["hypotheses"] = []
        return json.dumps(answer)


def test_owner_rejection_withholds_speculative_motive_not_observation():
    episode = _account()
    aid = account_fingerprint(episode.as_dict())
    accounts = {aid: episode}
    observed = GroundedClause(text="I checked the latch twice", refs=[QuoteRef(
        account_id=aid, field="response", citation_index=0)])
    premise = GroundedClause(text="I wanted a safe inspection record", refs=[QuoteRef(
        account_id=aid, field="concern", citation_index=0)])
    one = Hypothesis(text="One possibility is I was seeking approval.", premises=[premise],
                     scope_group_ids=[aid], owner_report_ids=[])
    rival = Hypothesis(text="Another possibility is the safety procedure mattered.",
                       premises=[premise], scope_group_ids=[aid], owner_report_ids=[])
    checked = assess([observed], [one], [rival], ["Was it the safety rule or something else?"],
                     accounts, [], Judgments())
    assert checked.clauses == (True,)
    assert checked.hypotheses == (False,)
    assert checked.contradicted == 1
    with pytest.raises(ReadUnavailable, match="invalid_matrix"):
        assess([observed], [one], [rival], ["Was it the safety rule or something else?"],
               accounts, [], Judgments(incomplete=True))
    with pytest.raises(ReadUnavailable, match="invalid_selector"):
        assess([observed], [one], [rival], ["Was it the safety rule or something else?"],
               accounts, [], Judgments(foreign=True))
