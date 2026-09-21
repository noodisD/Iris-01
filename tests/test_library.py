"""A library of patterns, and why it is checked rather than trusted.

Asking a model to name the circumstances in an archive failed twice, in
opposite directions. Concrete, it named the one corner of a life with enough
repetition to clear "recurs three times" — the owner read about their whole
archive and got a report about one activity. Abstract, it produced sentences
that matched nothing: eight of twelve were found in no account at all when each
account was put to them individually.

So the patterns are written once, in words that fit any area, and the library
is validated on load. A pattern that advises, explains a cause, or does not say
what would *not* show it is a lens that decides what it finds.
"""

from __future__ import annotations

import json

import pytest

from agent.library import LIBRARY_PATH, Pattern, load


def _write(tmp_path, patterns):
    path = tmp_path / "library.json"
    path.write_text(json.dumps({"version": 1, "patterns": patterns}))
    return path


GOOD = {
    "id": "waiting-for-an-answer",
    "name": "An answer was wanted immediately",
    "statement": "Someone was waiting while the decision was made.",
    "holds_when": ["another person was present and waiting"],
    "not_when": ["there was time to consider it alone"],
    "question": "Was there an occasion when nobody was waiting and you still decided at once?",
    "retiring_answer": "An account of deciding at once with nobody waiting",
}


# --- the library that ships --------------------------------------------------------

def test_the_library_loads_and_is_general():
    patterns = load()

    assert len(patterns) >= 6
    assert all(isinstance(p, Pattern) for p in patterns)
    assert len({p.id for p in patterns}) == len(patterns)


def test_every_pattern_says_what_would_not_show_it():
    """A pattern with only positive markers finds itself everywhere."""
    for pattern in load():
        assert pattern.not_when, pattern.id
        assert pattern.question.endswith("?"), pattern.id
        assert pattern.retiring_answer, pattern.id


def test_no_pattern_names_an_activity():
    """The point of the library is that a pattern is recognisable in a lesson,
    a conversation or a piece of work — not only where the owner writes most."""
    activities = ("trad", "market", "chess", "yoga", "driving", "money", "portfolio")
    for pattern in load():
        text = f"{pattern.name} {pattern.statement}".lower()
        assert not any(word in text for word in activities), pattern.id


# --- what a library may not contain ------------------------------------------------

def test_a_pattern_that_explains_or_advises_is_refused(tmp_path):
    for bad in ({**GOOD, "statement": "Waiting causes the decision to be rushed."},
                {**GOOD, "question": "Should you ask for more time?"},
                {**GOOD, "holds_when": ["the pressure means they cannot think"]}):
        with pytest.raises(ValueError):
            load(_write(tmp_path, [bad]))


def test_a_pattern_missing_its_parts_is_refused(tmp_path):
    for field in ("statement", "not_when", "question", "retiring_answer"):
        with pytest.raises(ValueError, match="missing"):
            load(_write(tmp_path, [{**GOOD, field: "" if field != "not_when" else []}]))


def test_the_same_pattern_twice_is_refused(tmp_path):
    with pytest.raises(ValueError, match="twice"):
        load(_write(tmp_path, [GOOD, GOOD]))


def test_an_empty_library_is_refused(tmp_path):
    with pytest.raises(ValueError, match="empty"):
        load(_write(tmp_path, []))


def test_the_markers_carry_both_sides():
    pattern = load()[0]

    assert "It holds when:" in pattern.markers
    assert "It does not hold when:" in pattern.markers


def test_the_library_lives_in_the_repository_and_holds_no_ones_writing():
    """General knowledge, kept apart from personal evidence: the library is a
    lens the owner can read, and contains nothing about them."""
    text = LIBRARY_PATH.read_text().lower()

    assert "patterns" in text
    for private in ("i ", "my ", "solana", "dax"):
        assert private not in text, private
