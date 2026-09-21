"""What a proposed connection has to survive before anyone is shown it.

This is the first thing in IRIS allowed to say something the owner did not
write: the accounts are grounded, the relationship between them is the model's.
Everything below is the price of that licence, and all of it is checked after
the model answers rather than asked for in the prompt — a rule a prompt states
is a rule a model can forget.

With a few dozen accounts there are hundreds of pairings and plenty of them
read well, so the cases here are mostly refusals.

Every account below is invented.
"""

from __future__ import annotations

import json
from datetime import date

from agent.connections import MAX_CANDIDATES, Candidate, propose, render, vet
from agent.episodes import Citation, Episode

RELATION = ("The decisions reconsidered afterwards were the ones made while someone "
            "was waiting for an answer")
QUESTION = "Was there a decision you reconsidered when nobody was waiting for an answer?"
RETIRING = "An account of reconsidering a decision made with time to think"


def _episode(domain, situation="a decision was needed", outcome="it was reconsidered later",
             **over):
    fields = {
        "actor": "self", "modality": "happened", "domain": domain,
        "situation": situation, "response": "agreed on the spot",
        "demand": None, "information": None, "outcome": outcome,
        "explanation": None, "occurred_on": date(2026, 3, 1),
        "citations": (Citation(entry_id=1, entry_date=date(2026, 3, 1),
                               text="said yes before I had thought about it"),),
    }
    return Episode(**{**fields, **over})


EPISODES = [
    _episode("work"),
    _episode("household"),
    _episode("training"),
    _episode("work", situation="a decision with time to consider",
             outcome="it stood"),
]


def _proposal(**over):
    base = {
        "relation": RELATION,
        "condition": "someone was waiting for an answer",
        "followed": "the decision was reconsidered later",
        "supporting": [0, 1, 2],
        "contrast": 3,
        "contrast_kind": "condition_without_outcome",
        "explanations": ["Nothing had been settled in advance",
                         "The other person's waiting shortened the time taken"],
        "question": QUESTION,
        "retiring_answer": RETIRING,
        "already_stated": False,
    }
    return {**base, **over}


# --- what survives ---------------------------------------------------------------

def test_a_relationship_across_domains_with_a_contrast_is_kept():
    kept = vet([_proposal()], EPISODES)

    assert len(kept) == 1
    candidate = kept[0]
    assert candidate.relation == RELATION
    assert candidate.domains == ("household", "training", "work")
    assert candidate.contrast is EPISODES[3]
    assert candidate.retiring_answer == RETIRING


def test_a_connection_the_owner_already_drew_is_marked_as_theirs():
    """Not finding it stated proves nothing about what they know; finding it
    stated proves IRIS did not discover it."""
    kept = vet([_proposal(already_stated=True)], EPISODES)

    assert kept[0].already_stated is True


# --- what is refused --------------------------------------------------------------

def test_two_accounts_are_not_a_shape():
    assert vet([_proposal(supporting=[0, 1])], EPISODES) == []


def test_a_shape_inside_one_domain_is_a_topic():
    same = [_episode("work"), _episode("work"), _episode("work"),
            _episode("work", outcome="it stood")]

    assert vet([_proposal()], same) == []


def test_a_candidate_with_no_contrast_was_never_tested():
    """Drawn from the accounts it came from, and never set against the rest."""
    assert vet([_proposal(contrast=None)], EPISODES) == []
    assert vet([_proposal(contrast=0)], EPISODES) == [], "a supporting account is not a contrast"


def test_one_explanation_is_an_assertion():
    assert vet([_proposal(explanations=["Nothing had been settled in advance"])], EPISODES) == []


def test_a_question_with_no_retiring_answer_is_a_funnel():
    assert vet([_proposal(retiring_answer="")], EPISODES) == []
    assert vet([_proposal(question="")], EPISODES) == []


def test_causal_or_prescriptive_wording_is_refused():
    for over in ({"relation": "Waiting for an answer causes the decision to be reconsidered"},
                 {"question": "Should you take more time before agreeing?"},
                 {"explanations": ["It means you avoid conflict", "Time pressure was shorter"]}):
        assert vet([_proposal(**over)], EPISODES) == [], over


def test_an_account_number_that_does_not_exist_does_not_count():
    assert vet([_proposal(supporting=[0, 1, 99])], EPISODES) == []


def test_no_more_than_three_survive_a_run():
    """Hundreds of pairings are available and enough of them read well."""
    kept = vet([_proposal() for _ in range(6)], EPISODES)

    assert len(kept) == MAX_CANDIDATES


# --- what is sent, and what is not -------------------------------------------------

def test_the_quotes_stay_on_the_machine():
    """The question is whether the accounts share a shape, which the summaries
    answer. The sentences that make each account true are not needed for it."""
    rendered = render(EPISODES)

    assert "said yes before I had thought about it" not in rendered
    assert "[0] area: work" in rendered
    assert "followed: it was reconsidered later" in rendered


def test_a_pass_that_cannot_be_read_proposes_nothing():
    class Nonsense:
        def chat(self, messages, system_prompt, **kwargs):
            return "not json"

    kept, counts = propose(EPISODES, Nonsense())
    assert kept == [] and counts["comparable"] == 4


def test_too_few_accounts_are_not_sent_at_all():
    class Watching:
        asked = 0

        def chat(self, messages, system_prompt, **kwargs):
            Watching.asked += 1
            return json.dumps({"relationships": []})

    kept, counts = propose(EPISODES[:2], Watching())
    assert kept == [] and Watching.asked == 0, "nothing to compare, nothing sent"
    assert counts["comparable"] == 2


def test_the_counts_say_what_was_proposed_and_what_was_kept():
    class Model:
        def chat(self, messages, system_prompt, **kwargs):
            return json.dumps({"relationships": [_proposal(), _proposal(supporting=[0, 1])]})

    kept, counts = propose(EPISODES, Model())

    assert len(kept) == 1
    assert counts["proposed"] == 2 and counts["kept"] == 1
    assert counts["areas"] == 3


def test_a_candidate_carries_everything_needed_to_disbelieve_it():
    candidate = vet([_proposal()], EPISODES)[0]
    body = candidate.as_dict()

    assert isinstance(candidate, Candidate)
    assert len(body["supporting"]) == 3 and body["contrast"]
    assert len(body["explanations"]) >= 2
    assert body["question"] and body["retiringAnswer"]


# --- what the first real run taught ------------------------------------------------

def test_a_condition_made_of_several_conditions_is_not_one():
    """The weakest proposal of the first run against the real archive joined
    three unrelated conditions with "or" under one good outcome. The owner read
    it as good behaviour marked rather than as a pattern, and was right."""
    listed = _proposal(condition="a clear signal appeared, or the body said something, "
                                 "or a concrete next step was there")

    assert vet([listed], EPISODES) == []


def test_one_or_is_a_phrase_rather_than_a_list():
    joined = _proposal(condition="someone was waiting for an answer or standing there")

    assert len(vet([joined], EPISODES)) == 1


def test_a_condition_that_holds_in_most_accounts_describes_the_archive():
    """A condition shared by most accounts is not a pattern in a life; it is a
    description of what its owner writes down."""
    many = [_episode("work") for _ in range(8)] + [_episode("home", outcome="it stood")]
    everywhere = _proposal(supporting=list(range(8)), contrast=8)

    assert vet([everywhere], many) == []


def test_a_contrast_has_to_say_what_it_contrasts():
    """Either the condition held and something else followed, or what followed
    appeared without the condition. Which one is the whole information."""
    assert vet([_proposal(contrast_kind="")], EPISODES) == []
    assert vet([_proposal(contrast_kind="it is just different")], EPISODES) == []

    kept = vet([_proposal(contrast_kind="outcome_without_condition")], EPISODES)
    assert kept[0].contrast_kind == "outcome_without_condition"


def test_the_condition_and_what_followed_are_kept_apart():
    candidate = vet([_proposal()], EPISODES)[0]

    assert candidate.condition == "someone was waiting for an answer"
    assert candidate.followed == "the decision was reconsidered later"
