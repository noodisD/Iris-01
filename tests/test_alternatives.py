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

from agent.alternatives import compare, distinctive
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


def test_a_pattern_on_one_side_only_is_the_distinction():
    rows = distinctive(compare(LABELS, "the-pattern", EPISODES))

    assert rows[0] == ("settled-in-advance", 2, 0)
    assert [r[0] for r in rows] == ["settled-in-advance"], (
        "two against one is a difference of one, which is a coincidence here")


def test_one_occasion_is_not_a_difference_between_two_sets():
    thin = {"the-pattern": {0: {"tone": "better", "size": "small"},
                            1: {"tone": "worse", "size": "small"}},
            "rare": {0: {"tone": "better", "size": "small"}}}

    assert distinctive(compare(thin, "the-pattern", EPISODES)) == []
    assert distinctive(compare(thin, "the-pattern", EPISODES), minimum=1) == [("rare", 1, 0)]


def test_an_unlabelled_pattern_has_no_occasions():
    sides = compare(LABELS, "never-matched", EPISODES)

    assert sides["better"].episodes == [] and sides["worse"].episodes == []


def test_nothing_here_ranks_or_recommends():
    """The evidence cannot carry "do this instead", and a sentence that carried
    it would be the system telling someone how to live from summaries of their
    own writing."""
    import ast
    import inspect

    from agent import alternatives

    tree = ast.parse(inspect.getsource(alternatives))
    tree.body = [n for n in tree.body if not (isinstance(n, ast.Expr)
                                              and isinstance(n.value, ast.Constant))]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            node.body = [n for n in node.body if not (isinstance(n, ast.Expr)
                                                      and isinstance(n.value, ast.Constant))]
    code = ast.unparse(tree).lower()

    # The prose says what this refuses to do; the code must not do it.
    for word in ("should", "recommend", "advice", "best", "instead"):
        assert word not in code, word
