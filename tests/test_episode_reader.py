"""The reader preserves missing results and original contextual passages."""

from __future__ import annotations

import json
from datetime import date

import pytest

from agent.episodes import (Episode, EpisodeReader, ReadUnavailable,
                            occurrence_accounts, verified_episodes)
from agent.reference_evaluation import account_fingerprint

CONTENT = ("My sister agreed without checking.\n\n"
           "On Tuesday someone waited while I decided. I said yes before checking "
           "the calendar. I felt relieved then, but I later felt stretched.\n\n"
           "Next week I want to pause; I have not yet done that.")
ENTRY = {"id": 12, "source_type": "reflection", "date": date(2026, 9, 20),
         "content": CONTENT}
PARAGRAPH = CONTENT.split("\n\n")[1]


def _account(**kwargs):
    return {"actor": "self", "recordKind": "event", "situation": "someone waited while I decided",
            "response": "I said yes before checking the calendar", "feeling": None,
            "immediateOutcome": "I felt relieved then", "laterOutcome": "I later felt stretched",
            "quotes": [{"entryId": 12, "sourceType": "reflection",
                        "text": "someone waited while I decided. I said yes before checking the calendar"}],
            **kwargs}


class Model:
    def __init__(self, response):
        self.response = response

    def chat(self, **_):
        return json.dumps(self.response) if not isinstance(self.response, str) else self.response


def test_event_without_outcome_counts_as_one_occurrence_and_preserves_context():
    account = _account()
    account["immediateOutcome"] = account["laterOutcome"] = None
    episode = verified_episodes([account], [ENTRY])[0]
    assert episode.immediate_outcome is None and episode.later_outcome is None
    assert episode.citations[0].text == PARAGRAPH
    assert episode.recorded_on == ENTRY["date"]
    assert Episode.from_dict(episode.as_dict()) == episode
    assert occurrence_accounts([episode]) == [episode]
    assert len(account_fingerprint(episode.as_dict())) == 64


def test_optional_unlocated_field_is_omitted_without_losing_event():
    account = _account()
    account["laterOutcome"] = "a cost that was never stated"
    reader = EpisodeReader(1, Model({"episodes": [account]}))
    episodes = reader.read([ENTRY])
    assert len(episodes) == 1
    assert episodes[0].later_outcome is None
    assert (reader.omitted_accounts, reader.omitted_fields) == (0, 1)


def test_required_unlocated_passage_drops_event():
    account = _account()
    account["response"] = "a fabricated action"
    reader = EpisodeReader(1, Model({"episodes": [account]}))
    assert reader.read([ENTRY]) == []
    assert reader.omitted_accounts == 1


def test_report_intention_and_other_actor_do_not_multiply_events():
    report = _account()
    report.update(recordKind="self_report", situation=None, response=None,
                  immediateOutcome=None, laterOutcome=None,
                  selfReport="I said yes before checking the calendar")
    plan = _account()
    plan.update(recordKind="intention", situation="Next week", response="I want to pause",
                immediateOutcome=None, laterOutcome=None,
                quotes=[{"entryId": 12, "sourceType": "reflection",
                         "text": "Next week I want to pause; I have not yet done that."}])
    other = _account()
    other.update(actor="other", situation="My sister", response="agreed without checking",
                 immediateOutcome=None, laterOutcome=None,
                 quotes=[{"entryId": 12, "sourceType": "reflection",
                          "text": "My sister agreed without checking."}])
    episodes = verified_episodes([report, plan, other], [ENTRY])
    assert [e.record_kind for e in episodes] == ["self_report", "intention", "event"]
    assert occurrence_accounts(episodes) == []


@pytest.mark.parametrize("document", ["not json", {}, {"episodes": None},
                                       {"episodes": [], "surprise": 1},
                                       {"episodes": [{"actor": "self"}]},
                                       {"episodes": [{**_account(), "actor": 1}]}])
def test_malformed_envelope_or_account_is_not_a_successful_empty_read(document):
    with pytest.raises(ReadUnavailable, match="invalid_schema"):
        EpisodeReader(1, Model(document)).read([ENTRY])


def test_empty_input_needs_no_provider_and_nonempty_input_does():
    assert EpisodeReader(1).read([]) == []
    with pytest.raises(ReadUnavailable, match="no_provider"):
        EpisodeReader(1).read([ENTRY])
    assert EpisodeReader(1, Model({"episodes": []})).read([ENTRY]) == []


def test_source_over_input_budget_fails_before_provider_call():
    with pytest.raises(ReadUnavailable, match="source_too_large"):
        EpisodeReader(1, Model({"episodes": []})).read([{**ENTRY, "content": "word " * 20000}])


def test_v3_account_cannot_be_reused_as_v4_identity():
    with pytest.raises(ValueError, match="invalid v4 account"):
        account_fingerprint({"actor": "self", "modality": "happened", "outcome": "good",
                             "citations": []})
