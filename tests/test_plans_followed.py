"""Plans, and whether anything followed them.

Every account below is invented. The tool may only retrieve: whether a plan was
carried out is the owner's answer, so these tests pin what gets offered, what
never does, and that nothing is counted the owner did not say.
"""

from __future__ import annotations

import sys

import pytest

from scripts import plans_followed as pf


def account(situation, response, *, modality="happened", actor="self",
            on="2024-03-01", domain="home", entry=1):
    return {"actor": actor, "modality": modality, "domain": domain,
            "situation": situation, "response": response, "demand": None,
            "information": None, "outcome": None, "explanation": None,
            "occurredOn": on, "complete": False, "hasShape": False,
            "citations": [{"entryId": str(entry), "entryDate": on,
                           "sourceType": "reflection", "text": situation}]}


PLAN = account("The shed roof leaks and the bicycle stays wet",
               "Intends to patch the shed roof on Saturday",
               modality="planned", on="2024-03-01", entry=1)
DONE = account("Saturday morning with the ladder out at the shed",
               "Patched the shed roof and dried the bicycle", on="2024-03-02", entry=2)
BREAD = account("A slow evening in the kitchen",
                "Baked two loaves of bread", on="2024-03-03", entry=3)


def test_a_later_occasion_sharing_the_plans_words_is_offered():
    """Retrieval finds the occasion that carried the plan out."""
    found = pf.candidates([PLAN, DONE, BREAD], 0)
    assert [i for _, i, _ in found] == [1]
    assert found[0][2] == "after"


def test_an_occasion_written_before_the_plan_is_never_offered():
    """Something that happened before the plan cannot be the plan carried out."""
    earlier = dict(DONE, occurredOn="2024-02-01")
    assert pf.candidates([PLAN, earlier], 0) == []


def test_an_undated_occasion_is_offered_with_its_order_marked_unknown():
    """Undated writing can still be the answer, but it is shown as unordered."""
    undated = dict(DONE, occurredOn=None)
    found = pf.candidates([PLAN, undated], 0)
    assert found and found[0][2] == "unknown"


def test_other_peoples_occasions_and_other_plans_are_not_offered():
    """Only the owner's own occasions that happened can carry a plan out."""
    theirs = dict(DONE, actor="other")
    another_plan = dict(DONE, modality="planned")
    assert pf.candidates([PLAN, theirs, another_plan], 0) == []


def test_only_the_owners_plans_are_asked_about():
    """Someone else's intention is not the owner's plan."""
    theirs = dict(PLAN, actor="other")
    assert pf.plans([PLAN, DONE, theirs]) == [0]


def filled(episodes, answer, note=""):
    text = pf.sheet(episodes)
    text = text.replace("`answer:` \n", f"`answer:` {answer}\n", 1)
    return text.replace("`note:` \n", f"`note:` {note}\n", 1)


@pytest.mark.parametrize("given,answer,as_account", [
    ("yes #1", "yes", 1), ("yes", "yes", None), ("partly", "partly", None),
    ("no", "no", None), ("unsure", "unsure", None)])
def test_each_written_answer_reads_back_as_itself(given, answer, as_account):
    """The answers in the sheet are the only ones accepted, and none is altered."""
    episodes = [PLAN, DONE, BREAD]
    row = pf.read(filled(episodes, given, "rained"), episodes)["plans"][pf.account_key(PLAN)]
    assert row["answer"] == answer
    assert row["carried_out_as"] == as_account
    assert row["note"] == "rained"


def test_an_unanswered_plan_stays_unanswered():
    """A blank line is not a "no"."""
    episodes = [PLAN, DONE]
    row = pf.read(pf.sheet(episodes), episodes)["plans"][pf.account_key(PLAN)]
    assert row["answer"] is None


def test_an_answer_that_is_not_on_the_list_is_refused_rather_than_guessed():
    """'its not' was once read backwards. Free text is rejected, not interpreted."""
    episodes = [PLAN, DONE]
    with pytest.raises(ValueError):
        pf.read(filled(episodes, "its not"), episodes)


def test_an_answer_about_a_plan_that_has_since_changed_is_refused():
    """An answer belongs to the content it was given about."""
    episodes = [PLAN, DONE]
    text = filled(episodes, "no")
    changed = [dict(PLAN, domain="garden"), DONE]
    with pytest.raises(ValueError):
        pf.read(text, changed)


def test_the_summary_counts_only_what_the_owner_said():
    """No plan is counted as not carried out unless the owner said so."""
    second = account("The kitchen tap drips", "Plans to replace the washer",
                     modality="planned", on="2024-03-05", domain="kitchen", entry=4)
    episodes = [PLAN, DONE, second]
    answers = pf.read(filled(episodes, "no"), episodes)
    s = pf.summary(answers, episodes)
    assert s["answers"] == {"no": 1, "unanswered": 1}
    assert s["not_carried_out_by_area"] == {"home": 1}
    assert s["recorded_occasion_found"] == 0


def test_building_refuses_to_overwrite_a_sheet_that_may_hold_answers(tmp_path, monkeypatch):
    """Rebuilding must never erase the owner's work."""
    import json
    cache = tmp_path / "episodes.json"
    cache.write_text(json.dumps({"episodes": [PLAN, DONE]}))
    target = tmp_path / "plans.md"
    target.write_text("answers live here")
    monkeypatch.setattr(sys, "argv", ["plans_followed.py", "build",
                                      "--cache", str(cache), "--sheet", str(target)])
    assert pf.main() == 1
    assert target.read_text() == "answers live here"
