"""What was true just before each occasion of a known pattern.

Every account below is invented: a chess club. The tool suggests and the
owner decides, so these pin what gets suggested, where it is attached, and
that nothing is counted the owner did not confirm.
"""

from __future__ import annotations

import pytest

from scripts import what_came_before as wcb

PATTERN = "more-than-can-be-taken-back"


def account(situation, response, outcome="It went as it went.", *, on="2024-05-10",
            actor="self", modality="happened", entry=1, demand=None):
    return {"actor": actor, "modality": modality, "domain": "chess club",
            "situation": situation, "demand": demand, "information": None,
            "response": response, "outcome": outcome, "explanation": None,
            "occurredOn": on,
            "citations": [{"entryId": str(entry), "entryDate": on,
                           "sourceType": "reflection", "text": situation}]}


LOSS = account("Lost the club final badly", "Resigned early", on="2024-05-05", entry=1)
PLAN = account("Planning the next season", "Wrote a schedule", modality="planned",
               outcome=None, on="2024-05-06", entry=2)
BIG = account("The rent was due and the prize would cover it", "Entered every tournament at once",
              "Lost three of them", on="2024-05-10", entry=3)
UNLABELLED = account("A quiet club night", "Played one game", on="2024-05-11", entry=4)

EPISODES = [LOSS, PLAN, BIG, UNLABELLED]
# Labels are keyed by position in comparable(): PLAN is not comparable, so
# LOSS is 0, BIG is 1, UNLABELLED is 2.
LABELS = {"accounts": 3, "labels": {
    PATTERN: {"1": {"tone": "worse", "size": "large"}},
    "continuing-after-a-setback": {"1": {"tone": "worse", "size": "large"}},
    "paid-off-sometimes": {"0": {"tone": "worse", "size": "moderate"}},
}}


def test_labels_are_read_through_the_list_they_were_made_against():
    """Position 1 in the labels is BIG, not the second account in the cache."""
    assert [i for i, _ in wcb.occasions(EPISODES, LABELS, PATTERN)] == [2]


def test_labels_made_against_a_different_list_are_refused():
    """A label set for another cache would attach to the wrong accounts."""
    with pytest.raises(ValueError):
        wcb.occasions(EPISODES, dict(LABELS, accounts=9), PATTERN)


def test_a_setback_label_on_the_same_account_is_offered():
    found = wcb.evidence(EPISODES, LABELS, 2)
    assert any("continuing-after-a-setback" in s for s in found["setback"])


def test_an_occasion_that_went_worse_in_the_days_before_is_offered():
    """LOSS, five days earlier and labelled worse, is offered as a setback."""
    found = wcb.evidence(EPISODES, LABELS, 2)
    assert any(s.startswith("#0, 5 day(s) before") for s in found["setback"])


def test_money_named_in_the_account_is_offered():
    found = wcb.evidence(EPISODES, LABELS, 2)
    assert any("rent" in s for s in found["money"])


def test_nothing_is_offered_where_the_writing_offers_nothing():
    """A quiet night with no labels and no named conditions suggests nothing."""
    found = wcb.evidence(EPISODES, LABELS, 3)
    assert found["money"] == [] and found["tired"] == [] and found["win"] == []


def test_an_occasion_after_this_one_is_never_offered_as_before_it():
    later_loss = dict(LOSS, occurredOn="2024-05-20")
    later_loss["citations"] = [dict(LOSS["citations"][0], entryDate="2024-05-20")]
    found = wcb.evidence([later_loss, PLAN, BIG, UNLABELLED], LABELS, 2)
    assert not any(s.startswith("#0,") for s in found["setback"])


def fill(text, is_it, before, note=""):
    text = text.replace("`is_it:` \n", f"`is_it:` {is_it}\n", 1)
    text = text.replace("`before:` \n", f"`before:` {before}\n", 1)
    return text.replace("`note:` \n", f"`note:` {note}\n", 1)


def test_answers_read_back_and_are_counted_only_when_confirmed():
    sheet = wcb.sheet(EPISODES, LABELS, PATTERN, "Committed more than could be taken back")
    answers = wcb.read(fill(sheet, "yes", "setback, money", "the final"), EPISODES)
    row = next(iter(answers["occasions"].values()))
    assert row == {"index": 2, "is_it": "yes", "before": ["setback", "money"], "note": "the final"}
    s = wcb.summary(answers, LABELS, EPISODES)
    assert s["confirmed"] == 1
    assert s["by_tone"] == {"worse": {"occasions": 1, "setback": 1, "money": 1}}


def test_an_occasion_the_owner_says_is_not_the_pattern_is_not_counted():
    sheet = wcb.sheet(EPISODES, LABELS, PATTERN, "x")
    s = wcb.summary(wcb.read(fill(sheet, "no", "setback"), EPISODES), LABELS, EPISODES)
    assert s["confirmed"] == 0 and s["not_this_pattern"] == 1 and s["by_tone"] == {}


@pytest.mark.parametrize("before", ["because of the loss", "setback and money", "maybe"])
def test_free_text_is_refused_rather_than_interpreted(before):
    sheet = wcb.sheet(EPISODES, LABELS, PATTERN, "x")
    with pytest.raises(ValueError):
        wcb.read(fill(sheet, "yes", before), EPISODES)


def test_an_answer_about_an_account_that_has_since_changed_is_refused():
    sheet = fill(wcb.sheet(EPISODES, LABELS, PATTERN, "x"), "yes", "none")
    changed = [LOSS, PLAN, dict(BIG, response="Entered one tournament"), UNLABELLED]
    with pytest.raises(ValueError):
        wcb.read(sheet, changed)
