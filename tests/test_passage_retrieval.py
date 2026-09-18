"""Which part of a long entry reaches the model.

An entry is retrieved because its whole embedding matched the question, and was
then handed over as its first 300 characters. 102 of the owner's 139 entries are
longer than that, so an entry found for what it says about sleep could arrive as
its opening paragraph about the office move — and the sentence that actually
matched was never shown. The model then answered from the part that had nothing
to do with the question, while appearing to cite the entry.

Every entry below is invented.
"""

from __future__ import annotations

from agent.core import _best_passage

OPENING = "The office move finally happened and the new desk is by the window. "
MIDDLE = "I was sleeping badly again and felt wrecked the whole morning. "
CLOSING = "The commute is twenty minutes longer now, which I had not planned for. "


def _long_entry() -> str:
    return (OPENING * 3) + MIDDLE + (CLOSING * 3)


def test_the_sentence_that_matches_is_the_one_shown():
    passage = _best_passage(_long_entry(), "why did I sleep so badly", limit=140)
    assert "sleeping badly" in passage


def test_a_regular_variant_of_the_word_still_matches():
    """"sleeping" and "sleep" are the same subject to the person asking."""
    assert "sleeping badly" in _best_passage(_long_entry(), "sleep", limit=140)


def test_an_irregular_form_is_not_pretended_to_match():
    """No suffix rule gets from "slept" to "sleep", and inventing one would make
    the passage choice unpredictable. The opening is returned instead, marked as
    a fragment — the same thing shown before passage retrieval existed."""
    entry = (OPENING * 3) + "I slept four hours. " + (CLOSING * 3)
    passage = _best_passage(entry, "sleep", limit=140)
    assert "slept four hours" not in passage
    assert passage.startswith("The office move") and passage.endswith("…")


def test_a_passage_taken_from_the_middle_says_so():
    passage = _best_passage(_long_entry(), "why did I sleep so badly", limit=140)
    assert passage.startswith("… "), "a fragment must not read as the start of the entry"
    assert passage.endswith("…"), "nor as the end of it"


def test_a_short_entry_is_given_whole_and_unmarked():
    entry = "Slept badly before the exam."
    assert _best_passage(entry, "sleep", limit=300) == entry


def test_an_entry_with_nothing_in_common_falls_back_to_its_opening():
    """No overlap is not a reason to pick an arbitrary middle."""
    passage = _best_passage(_long_entry(), "quantum chromodynamics", limit=120)
    assert passage.startswith("The office move")
    assert passage.endswith("…")


def test_the_passage_stays_within_its_budget():
    for query in ("sleep", "commute", "desk window", ""):
        assert len(_best_passage(_long_entry(), query, limit=120)) <= 124  # + ellipses


def test_one_enormous_sentence_is_still_cut_to_fit():
    entry = "and then " * 200
    passage = _best_passage(entry, "then", limit=100)
    assert len(passage) <= 104


def test_line_breaks_do_not_survive_as_entry_boundaries():
    """A retrieved memory is one line in the context block; a newline inside it
    would read as the start of another entry."""
    entry = "First line about sleep.\n\nSecond line about work. " + (CLOSING * 4)
    assert "\n" not in _best_passage(entry, "sleep", limit=120)


def test_the_choice_is_the_same_every_time():
    entry = _long_entry()
    first = _best_passage(entry, "sleep", limit=140)
    assert all(_best_passage(entry, "sleep", limit=140) == first for _ in range(3))
