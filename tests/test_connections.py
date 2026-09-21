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


# --- testing a claim against the accounts ------------------------------------------

def _labels(*pairs):
    class Model:
        def chat(self, messages, system_prompt, **kwargs):
            return json.dumps({"accounts": [
                {"i": i, "condition": c, "followed": f} for i, (c, f) in enumerate(pairs)]})
    return Model()


def test_a_claim_is_counted_in_four_corners():
    """Whether a claim holds is arithmetic, and it stays here: a model asked
    "does this hold?" answers agreeably."""
    from agent.connections import examine

    cells, counts = examine("someone was waiting", "it was reconsidered", EPISODES,
                            _labels(("yes", "yes"), ("yes", "no"),
                                    ("no", "yes"), ("no", "no")))

    assert counts["supports"] == 1 and counts["contradicts"] == 1
    assert counts["outcome_without_condition"] == 1 and counts["neither"] == 1
    assert cells["contradicts"][0] is EPISODES[1]
    assert counts["labelled"] == 4 and counts["unclear"] == 0


def test_an_account_that_says_neither_is_unclear_rather_than_counted():
    from agent.connections import examine

    _, counts = examine("someone was waiting", "it was reconsidered", EPISODES,
                        _labels(("yes", "unclear"), ("unclear", "yes"),
                                ("yes", "yes"), ("no", "no")))

    assert counts["unclear"] == 2
    assert counts["supports"] == 1


def test_an_examination_that_fails_labels_nothing():
    from agent.connections import examine

    class Broken:
        def chat(self, messages, system_prompt, **kwargs):
            raise RuntimeError("provider went away")

    cells, counts = examine("a", "b", EPISODES, Broken())
    assert counts["labelled"] == 0 and all(not v for v in cells.values())


def test_a_second_run_is_told_what_has_already_been_judged():
    """The same accounts asked the same question give the same few answers.
    Repeating them is not more discovery."""
    seen = {}

    class Model:
        def chat(self, messages, system_prompt, **kwargs):
            seen["asked"] = messages[0]["content"]
            return json.dumps({"relationships": []})

    propose(EPISODES, Model(), avoid=["Something already judged"])

    assert "already been considered" in seen["asked"]
    assert "Something already judged" in seen["asked"]


# --- the same circumstance, different responses -------------------------------------

def test_responses_are_grouped_by_how_what_followed_read():
    """"When something wanted was blocked, it was difficult" is true of everyone
    alive. What distinguishes one occasion from another is what was done next,
    and the accounts already carry it."""
    from agent.connections import responses_under

    class Model:
        def chat(self, messages, system_prompt, **kwargs):
            return json.dumps({"accounts": [
                {"i": 0, "held": "yes", "went": "worse"},
                {"i": 1, "held": "yes", "went": "better"},
                {"i": 2, "held": "no", "went": "better"},
                {"i": 3, "held": "yes", "went": "unclear"},
            ]})

    groups, counts = responses_under("a wanted action was blocked", EPISODES, Model())

    assert counts["held"] == 3, "the account where it did not hold is not counted"
    assert counts["better"] == 1 and counts["worse"] == 1
    assert counts["unclear"] == 1
    assert groups["better"][0] is EPISODES[1]


def test_the_responses_are_not_ranked_for_the_owner():
    """Which response is worth repeating is advice, and this does not give it:
    the groups are what happened, in the writing's own terms."""
    import inspect

    from agent import connections

    source = inspect.getsource(connections.responses_under)
    for word in ("best", "recommend", "should", "better strategy"):
        assert word not in source.lower().replace("better if", "")


def test_a_circumstance_nothing_describes_returns_empty_groups():
    from agent.connections import responses_under

    class Nothing:
        def chat(self, messages, system_prompt, **kwargs):
            return json.dumps({"accounts": [{"i": i, "held": "no", "went": "unclear"}
                                            for i in range(4)]})

    groups, counts = responses_under("something that never happened", EPISODES, Nothing())

    assert counts["held"] == 0
    assert all(not g for g in groups.values())


# --- weighing a behaviour that sometimes pays ---------------------------------------

def _weighing(*rows):
    class Model:
        def chat(self, messages, system_prompt, **kwargs):
            return json.dumps({"accounts": [
                {"i": i, "held": h, "went": w, "size": s} for i, (h, w, s) in enumerate(rows)]})
    return Model()


def test_occasions_are_placed_by_how_they_went_and_how_large_they_were():
    """Counting welcome against unwelcome hides the shape that matters for a
    behaviour that sometimes pays: a run of small wins beside one large loss."""
    from agent.connections import weigh

    grid, counts = weigh("more was committed than could be held", EPISODES,
                         _weighing(("yes", "better", "small"), ("yes", "better", "small"),
                                   ("yes", "worse", "large"), ("no", "worse", "large")))

    assert counts["held"] == 3
    assert counts["better_small"] == 2 and counts["worse_large"] == 1
    assert counts["better_large"] == 0
    assert len(grid[("worse", "large")]) == 1


def test_an_occasion_whose_size_is_not_stated_is_not_given_one():
    from agent.connections import weigh

    _, counts = weigh("a circumstance", EPISODES,
                      _weighing(("yes", "worse", "unclear"), ("yes", "unclear", "large"),
                                ("yes", "better", "small"), ("no", "worse", "small")))

    assert counts["unclear"] == 2 and counts["better_small"] == 1


def test_a_question_that_is_an_instruction_is_refused():
    """The easiest place in this system to smuggle in advice is a question."""
    from agent.connections import reflective_questions

    class Model:
        def chat(self, messages, system_prompt, **kwargs):
            return json.dumps({"questions": [
                "Should you take smaller positions in future?",
                "What would the largest of these outcomes mean if it happened twice more?",
                "Have you considered stopping?",
                "This is not a question.",
                "What would make one of the welcome outcomes worth the largest unwelcome one?",
            ]})

    kept = reflective_questions("a circumstance", {"held": 5, "better_small": 3,
                                                   "worse_large": 2}, Model())

    assert len(kept) == 2
    assert all(q.endswith("?") for q in kept)
    assert not any(q.lower().startswith(("should", "have you considered")) for q in kept)


def test_no_questions_without_a_model():
    from agent.connections import reflective_questions

    assert reflective_questions("a circumstance", {"held": 3}, None) == []
