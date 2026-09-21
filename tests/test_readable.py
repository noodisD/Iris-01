"""A reading copy may change punctuation. It may not change a word.

Dictated entries arrive as one long breath, and a model reads them worse than
it reads the same words laid out properly. Tidying them is worth doing and is
the most dangerous edit available here: everything in this product stands on
quotes existing word for word in what the owner wrote, so a copy that improves
the grammar has quietly replaced the evidence with prose nobody wrote.

Every passage below is invented.
"""

from __future__ import annotations

import json

from agent.episodes import verified_episodes
from agent.readable import locate, needs_tidying, readable, same_words, words

RAW = ("so today i went to the pottery class again and the wheel kept wobbling "
       "and i couldnt centre the clay at all then near the end it just worked "
       "and i got a bowl out of it")
TIDY = ("So today I went to the pottery class again, and the wheel kept wobbling, "
        "and I couldnt centre the clay at all. Then near the end it just worked, and "
        "I got a bowl out of it.")


class Model:
    """Says where the sentences end, which is all the model is asked for."""

    def __init__(self, *ends):
        self.ends = list(ends)

    def chat(self, messages, system_prompt, **kwargs):
        return json.dumps({"sentence_ends": self.ends})


# --- the rule -------------------------------------------------------------------

def test_the_marks_go_in_and_the_words_do_not_change():
    copy, why = readable(RAW, Model("and the wheel kept wobbling", "centre the clay at all"))
    assert why == "ok"

    assert same_words(RAW, copy)
    assert copy.count(".") == 3, "two sentence ends, and the close of the passage"
    assert copy.startswith("So today I went")


def test_a_model_that_cannot_be_trusted_with_text_is_not_given_text():
    """Asked for a tidied passage, the model rewrote one of every three entries
    in this archive — and every single dictated one. It is asked where the
    sentences end instead, and the marks are inserted here, so the worst a bad
    answer can do is put a full stop in an odd place."""
    copy, _ = readable(RAW, Model("a phrase that is not in the passage at all"))

    assert same_words(RAW, copy), "an ending nobody wrote changes nothing"


def test_an_ending_that_appears_twice_does_not_cut_the_same_place_twice():
    text = "i went for a walk and it was fine i went for a walk and it was fine"
    copy, _ = readable(text, Model("and it was fine", "and it was fine"))

    assert same_words(text, copy)
    assert copy.count(".") == 2


def test_nothing_comes_back_without_a_model_or_an_answer():
    assert readable(RAW, None) == (None, "not_needed")
    assert readable("", Model("anything")) == (None, "not_needed")
    assert readable(RAW, Model()) == (None, "unusable_answer"), "no endings, no copy"


# --- quotes resolve to the owner's own text ----------------------------------------

def test_a_quote_from_the_tidy_copy_is_returned_as_the_owner_wrote_it():
    found = locate(RAW, "I couldnt centre the clay at all.")

    assert found == "i couldnt centre the clay at all"


def test_a_quote_with_words_that_are_not_there_is_not_found():
    assert locate(RAW, "I could not centre the clay") is None
    assert locate(RAW, "") is None


def test_an_episode_read_from_the_copy_cites_the_original():
    """The model is shown punctuation the owner never typed. What is stored,
    and what they are shown back, is their own text."""
    entries = [{"id": 1, "date": None, "content": RAW, "source_type": "reflection"}]
    raw = [{"actor": "self", "modality": "happened", "domain": "pottery",
            "situation": "a pottery class where the wheel wobbled",
            "response": "kept going until the end",
            "outcome": "a bowl came out of it",
            "quotes": [{"entryId": 1, "sourceType": "reflection",
                        "text": "Then near the end it just worked, and I got a bowl out of it."}]}]

    kept = verified_episodes(raw, entries)

    assert len(kept) == 1
    assert kept[0].citations[0].text == "then near the end it just worked and i got a bowl out of it"


def test_an_invented_quote_still_fails_however_it_is_punctuated():
    entries = [{"id": 1, "date": None, "content": RAW, "source_type": "reflection"}]
    raw = [{"actor": "self", "modality": "happened", "domain": "pottery",
            "situation": "a pottery class", "response": "kept going",
            "outcome": "a bowl",
            "quotes": [{"entryId": 1, "sourceType": "reflection",
                        "text": "I was pleased with how it turned out."}]}]

    assert verified_episodes(raw, entries) == []


def test_words_ignores_case_and_punctuation_only():
    assert words("Don't, stop!") == ["don't", "stop"]
    assert words("DON'T STOP") == ["don't", "stop"]


# --- only what needs it ------------------------------------------------------------

def test_a_dictated_breath_needs_tidying():
    """No sentence marks at all, and long enough that the lack shows."""
    assert needs_tidying(RAW + " " + RAW)


def test_writing_that_is_already_punctuated_is_left_alone():
    """Most entries do not need this, and a copy is the one edit here that
    could break a citation — so it is spent only where it buys something."""
    ordinary = ("Slept badly again. The morning was slow but the afternoon went fine, "
                "and I finished the piece I had been avoiding. Tomorrow: the accounts, "
                "then a walk if the weather holds. It was a reasonable day on balance.")

    assert not needs_tidying(ordinary)


def test_a_short_note_is_never_worth_a_copy():
    assert not needs_tidying("went for a walk no phone")


def test_a_provider_failure_is_not_a_model_that_rewrites():
    """A run with no credits left counted every failed call as a copy that had
    changed a word, and read as "the model rewrites everything". Two different
    things, counted apart."""
    class Down:
        def chat(self, messages, system_prompt, **kwargs):
            raise RuntimeError("no credits remaining")

    assert readable(RAW, Down()) == (None, "unavailable")
