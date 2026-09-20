"""The weekly letter says only what it can support.

It was the one free-writing surface: an unconstrained prompt, no firewall on
the result, no check on anything quoted. It keeps its voice and loses the
licence. Every entry and sentence below is invented.
"""

from __future__ import annotations

from agent.review_letter import SYSTEM_PROMPT, compose, facts_letter, hold_to_the_rules

WEEK = ["Walked to the lake before work and the water was flat.",
        "Long day, finished the migration plan at last."]
FACTS = ["You wrote 2 entries on 2 of the 7 days."]
FINDINGS = ["The pattern 'lake walks' appeared 5 times since 2025-03-01; its occurrences were spread."]


class Model:
    def __init__(self, reply=None, fail=False):
        self.reply, self.fail, self.seen = reply, fail, []

    def chat(self, messages, system_prompt, **kwargs):
        self.seen.append((system_prompt, messages[0]["content"]))
        if self.fail:
            raise RuntimeError("provider went away")
        return self.reply


def test_a_causal_sentence_is_dropped():
    held = hold_to_the_rules(
        "You wrote twice this week. The walks caused the better mood.", WEEK)
    assert held == "You wrote twice this week."


def test_an_invented_quote_is_dropped_and_a_real_one_kept():
    held = hold_to_the_rules(
        'You wrote "the water was flat" on one morning. You also wrote "everything is fine".', WEEK)
    assert held == 'You wrote "the water was flat" on one morning.'


def test_the_model_is_never_shown_the_entries():
    """No more of the owner's writing leaves the machine for a letter than
    did before: facts and findings, never the entries themselves."""
    model = Model(reply="A calm week.")
    compose(FACTS, FINDINGS, WEEK, model)
    system, prompt = model.seen[0]
    assert system == SYSTEM_PROMPT
    assert not any(entry in prompt for entry in WEEK)


def test_a_failed_call_leaves_the_facts():
    assert compose(FACTS, FINDINGS, WEEK, Model(fail=True)) == facts_letter(FACTS, FINDINGS)


def test_when_nothing_survives_the_facts_are_the_letter():
    written = "Your walks improved everything. You should keep going."
    assert compose(FACTS, FINDINGS, WEEK, Model(reply=written)) == facts_letter(FACTS, FINDINGS)


def test_an_empty_week_is_not_sent_to_a_model_at_all():
    model = Model(reply="anything")
    assert compose(["Nothing was written this week."], [], [], model) == "Nothing was written this week."
    assert model.seen == []


def test_a_number_the_letter_was_not_given_is_not_a_fact():
    """The review's case: given "I stayed home", the letter accepted "You wrote
    97 entries and ran a marathon. Your energy averaged 10." A forbidden-word
    firewall is a wording guard. Counts are the part that can be checked, and
    the part that reads as authority."""
    held = hold_to_the_rules(
        "You wrote 97 entries and ran a marathon. Your energy averaged 10.",
        ["I stayed home"], FACTS)
    assert held == ""


def test_the_numbers_it_was_given_survive():
    held = hold_to_the_rules("You wrote 2 entries this week. It was a quiet one.", WEEK, FACTS)
    assert held == "You wrote 2 entries this week. It was a quiet one."


def test_a_finding_s_numbers_count_as_given():
    """The findings are facts too: the letter is shown both."""
    held = hold_to_the_rules("The lake walks came up 5 times since 2025-03-01.", WEEK,
                             FACTS + FINDINGS)
    assert held == "The lake walks came up 5 times since 2025-03-01."
