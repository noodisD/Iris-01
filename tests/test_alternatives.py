"""What else was true when a pattern's occasions went one way or the other.

The owner's question after the first library run: what were the behaviours on
the good occasions and the bad ones, and what might be done differently. The
part a system can honestly answer is the first half — what they did, and what
else was true at the time — by arithmetic over labels it already has.

The part it must not answer is the second: nothing here ranks a response,
recommends one, or says a pattern could be swapped for another.

Every account below is invented.
"""

from __future__ import annotations

from datetime import date

from collections import Counter

from agent.alternatives import Side, compare, distinctive
from agent.episodes import Citation, Episode


def _episode(response, domain="work"):
    return Episode(
        actor="self", modality="happened", domain=domain,
        situation="a decision was needed", response=response,
        demand=None, information=None, outcome="it went one way or the other",
        explanation=None, occurred_on=date(2026, 3, 1),
        citations=(Citation(entry_id=1, entry_date=date(2026, 3, 1), text="a sentence"),))


EPISODES = [_episode("decided at once"), _episode("decided at once"),
            _episode("waited a day"), _episode("waited a day"), _episode("asked someone")]

LABELS = {
    "the-pattern": {0: {"tone": "worse", "size": "large"},
                    1: {"tone": "worse", "size": "moderate"},
                    2: {"tone": "better", "size": "moderate"},
                    3: {"tone": "better", "size": "small"}},
    "settled-in-advance": {2: {"tone": "better", "size": "moderate"},
                           3: {"tone": "better", "size": "small"}},
    "someone-was-waiting": {0: {"tone": "worse", "size": "large"},
                            1: {"tone": "worse", "size": "moderate"},
                            2: {"tone": "better", "size": "moderate"}},
    "unrelated": {4: {"tone": "better", "size": "small"}},
}


def test_the_occasions_split_by_how_they_went():
    sides = compare(LABELS, "the-pattern", EPISODES)

    assert len(sides["better"].episodes) == 2
    assert len(sides["worse"].episodes) == 2
    assert sides["better"].responses == ["waited a day", "waited a day"]


def test_what_else_was_true_is_counted_on_each_side():
    sides = compare(LABELS, "the-pattern", EPISODES)

    assert sides["better"].others["settled-in-advance"] == 2
    assert sides["worse"].others["settled-in-advance"] == 0
    assert sides["worse"].others["someone-was-waiting"] == 2
    assert "the-pattern" not in sides["better"].others, "a pattern is not its own company"


def test_both_sides_need_three_accounts_even_with_large_count_gap():
    sides = compare(LABELS, "the-pattern", EPISODES)
    assert distinctive(sides, {"better": 2, "worse": 2}) == []
    assert distinctive(sides, {"better": 2, "worse": 2}, minimum=1) == []


def test_equal_rates_do_not_qualify_and_exact_quarter_gap_does():
    sides = {"better": Side(others=Counter({"equal": 4, "quarter": 2})),
             "worse": Side(others=Counter({"equal": 8, "quarter": 4}))}
    # 4/5 and 8/10 are equal, despite a count gap of four.
    assert distinctive(sides, {"better": 5, "worse": 10}) == []
    sides["better"].others["quarter"] = 1
    # 1/4 and 4/8: exactly 25 percentage points with a count gap of three.
    assert distinctive(sides, {"better": 4, "worse": 8}) == [("quarter", 1, 4)]


def test_cli_count_override_does_not_remove_proportion_gate():
    sides = {"better": Side(others=Counter({"near": 2})),
             "worse": Side(others=Counter({"near": 1}))}
    assert distinctive(sides, {"better": 6, "worse": 4}, minimum=1) == []
    sides["worse"].others["near"] = 0
    assert distinctive(sides, {"better": 6, "worse": 4}, minimum=1) == [("near", 2, 0)]


def test_an_unlabelled_pattern_has_no_occasions():
    sides = compare(LABELS, "never-matched", EPISODES)

    assert sides["better"].episodes == [] and sides["worse"].episodes == []
