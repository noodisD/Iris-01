"""What else was true on the occasions a pattern went one way or the other.

A pattern on its own says a circumstance recurs and how its occasions turned
out. The question after that — the one the owner asked — is what was different
about the ones that went well: what they did, and what else was true at the
time. That is answerable from labels already collected, by arithmetic, without
asking a model to explain anything.

For one pattern, the occasions split into welcome and unwelcome. On each side
this reports which *other* patterns from the library were also present, and
what the owner did. A pattern present on the welcome side and absent from the
unwelcome one is not a cause and is not advice: it is a difference between two
sets of occasions, offered so the owner can look at both and say whether it
means anything.

Nothing here ranks responses, recommends one, or says a pattern could be
swapped for another. The evidence available cannot carry that, and a sentence
that carried it would be the system telling someone how to live from thirty
summaries of their own writing.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .episodes import Episode

#: How what followed read, as the labelling pass judged it.
SIDES = ("better", "worse")


@dataclass
class Side:
    """One side of a pattern's occasions: what happened, and what else held."""

    episodes: list[Episode] = field(default_factory=list)
    others: Counter = field(default_factory=Counter)

    @property
    def responses(self) -> list[str]:
        return [e.response for e in self.episodes]


def compare(labels: dict[str, dict[int, dict]], pattern_id: str,
            episodes: list[Episode]) -> dict[str, Side]:
    """The pattern's welcome and unwelcome occasions, with what else was true.

    `labels` is {pattern id: {account position: {"tone", "size"}}} — what a
    labelling run produced for each pattern over the same accounts, so the
    positions mean the same thing throughout.
    """
    mine = labels.get(pattern_id) or {}
    sides = {name: Side() for name in SIDES}
    for position, answer in mine.items():
        side = sides.get(answer.get("tone"))
        if side is None or position >= len(episodes):
            continue
        side.episodes.append(episodes[position])
        for other_id, other in labels.items():
            if other_id != pattern_id and position in other:
                side.others[other_id] += 1
    return sides


def distinctive(sides: dict[str, Side], minimum: int = 2) -> list[tuple[str, int, int]]:
    """Patterns that sit on one side of a pattern's occasions and not the other.

    `minimum` is the size of the difference, not of the larger side: two
    occasions against one is a difference of one, which on this much evidence
    is two occasions and a coincidence. Sorted by that difference, largest
    first.
    """
    ids = set(sides["better"].others) | set(sides["worse"].others)
    out = []
    for other in ids:
        better = sides["better"].others.get(other, 0)
        worse = sides["worse"].others.get(other, 0)
        if abs(better - worse) >= minimum:
            out.append((other, better, worse))
    return sorted(out, key=lambda row: abs(row[1] - row[2]), reverse=True)
