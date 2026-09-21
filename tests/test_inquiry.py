"""What makes questioning an inquiry rather than a questionnaire.

The first attempt produced three questions in one breath, each restating the
same table, none able to use what the owner said. That is a form with a table
on top. What makes questioning Socratic is that the asker does not know the
answer, hears it, and lets it change where the questioning goes — so the shape
is fixed in code and only the wording comes from the model, and a question that
arrives as advice, or as two questions, is refused rather than trimmed.

Every answer below is invented.
"""

from __future__ import annotations

import json

from agent.inquiry import STAGES, Turn, next_question, synthesis

CONDITION = "more was committed than could comfortably be held"
COUNTS = {"held": 17, "better_large": 3, "worse_large": 6, "worse_moderate": 2}


class Model:
    """Answers with whatever the test scripts, and records what it was asked."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.asked: list[str] = []

    def chat(self, messages, system_prompt, **kwargs):
        self.asked.append(messages[0]["content"])
        reply = self.replies.pop(0) if self.replies else {"question": "And then what?"}
        return json.dumps(reply)


def test_the_shape_of_the_inquiry_is_not_the_models_to_choose():
    """Clarify, then the evidence, then the exception, then what it adds up to,
    then what would make it worth it. An inquiry that never looks for the case
    that breaks the pattern is a case being built."""
    assert [name for name, _ in STAGES] == [
        "clarify", "evidence", "exception", "consequence", "weigh"]


def test_each_question_sees_what_was_already_said():
    model = Model({"question": "What does that look like on an ordinary week?"})
    turns = [Turn("clarify", "What does this look like for you?",
                  "Usually it is money, sometimes it is promising my time twice over.")]

    next_question("evidence", STAGES[1][1], CONDITION, COUNTS, turns, model)

    assert "promising my time twice over" in model.asked[0], "the answer is in the prompt"
    assert "What does this look like for you?" in model.asked[0]


def test_two_questions_in_one_are_refused_rather_than_trimmed():
    model = Model({"question": "What was gained there? And what did it cost?"})

    assert next_question("evidence", STAGES[1][1], CONDITION, COUNTS, [], model) is None


def test_advice_with_a_question_mark_is_refused():
    for bad in ("Should you set a limit before you start?",
                "Have you considered committing less?",
                "What would help you stop doing this?"):
        model = Model({"question": bad})
        assert next_question("weigh", STAGES[4][1], CONDITION, COUNTS, [], model) is None, bad


def test_a_question_that_is_a_question_survives():
    model = Model({"question": "What was different about the one that went another way?"})

    question = next_question("exception", STAGES[2][1], CONDITION, COUNTS, [], model)

    assert question == "What was different about the one that went another way?"


def test_the_synthesis_may_use_no_number_it_was_not_given():
    """The inquiry that ends by inventing a count has undone the point of
    counting."""
    turns = [Turn("clarify", "What does it look like?", "Usually money.")]
    invented = Model({"summary": "You described 40 occasions of this, mostly in one year."})

    assert synthesis(CONDITION, COUNTS, turns, invented) == ""

    honest = Model({"summary": "You said it is usually money. Of the 17 occasions here, "
                               "what made the 3 welcome ones worth it is still open."})
    assert synthesis(CONDITION, COUNTS, turns, honest).startswith("You said")


def test_the_synthesis_cannot_explain_or_advise():
    turns = [Turn("clarify", "What does it look like?", "Usually money.")]
    causal = Model({"summary": "The pressure caused you to commit more than you could hold."})

    assert synthesis(CONDITION, COUNTS, turns, causal) == ""


def test_nothing_is_said_when_nothing_was_asked():
    assert synthesis(CONDITION, COUNTS, [], Model()) == ""
    assert next_question("clarify", STAGES[0][1], CONDITION, COUNTS, [], None) is None


def test_the_synthesis_is_allowed_to_end_the_pattern():
    """The conclusion is not fixed before the questions are asked: an answer
    that undoes the pattern has to be able to say so."""
    turns = [Turn("exception", "Was there an occasion that went differently?",
                  "Most of them did, I only write down the bad ones.")]
    model = Model({"summary": "You said you mostly write down the occasions that went "
                              "badly, so what these accounts hold is not the pattern of "
                              "the occasions themselves."})

    assert "not the pattern" in synthesis(CONDITION, COUNTS, turns, model)
