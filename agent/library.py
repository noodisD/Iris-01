"""A library of general patterns, and how an account is matched against one.

Asking a model to name the circumstances in an archive produced, twice, a
result that could not be used. Told to stay concrete it named the one corner of
a life with enough repetition to clear a "recurs three times" test — 66
accounts over 48 areas, only three of which held three or more, so the report
was about that corner and nothing else. Told to abstract, it produced sentences
that matched nothing: of twelve field-neutral circumstances, eight were found
in no account at all when each account was put to them one at a time, and one
was found in more than half.

A fixed library answers both. Each pattern is written once, in words that fit
any area of life, with what it looks like, what it is not, and the question
whose answer would retire it. Matching then has something stable to recognise,
the same patterns can be counted again next month, and an archive weighted
towards one activity does not decide what gets looked for.

What a pattern is not: a type, a trait, a diagnosis, or a verdict. It is a
question asked of an account — does this describe that — and the answer is
counted, never assigned to the person.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .narrative_policy import FORBIDDEN_REGEX

logger = logging.getLogger(__name__)

LIBRARY_PATH = Path(__file__).resolve().parent.parent / "patterns" / "library.json"

REQUIRED = ("id", "name", "statement", "holds_when", "not_when", "question",
            "retiring_answer")


@dataclass(frozen=True)
class Pattern:
    """One general pattern, with what would show it and what would not."""

    id: str
    name: str
    statement: str
    holds_when: tuple[str, ...]
    not_when: tuple[str, ...]
    question: str
    retiring_answer: str

    @property
    def markers(self) -> str:
        """The pattern as the matching pass is shown it."""
        return ("It holds when:\n" + "\n".join(f"- {h}" for h in self.holds_when)
                + "\nIt does not hold when:\n" + "\n".join(f"- {n}" for n in self.not_when))


def load(path: Path | None = None) -> list[Pattern]:
    """Every pattern in the library, refused whole if one of them is malformed.

    A library with a pattern that advises, explains a cause, or leaves out what
    would *not* show it is worse than no library: it is a lens that decides
    what it finds. Checked on load rather than trusted to review.
    """
    body = json.loads((path or LIBRARY_PATH).read_text())
    out: list[Pattern] = []
    seen: set[str] = set()
    for item in body.get("patterns", []):
        missing = [f for f in REQUIRED if not item.get(f)]
        if missing:
            raise ValueError(f"pattern {item.get('id', '?')} is missing {missing}")
        if item["id"] in seen:
            raise ValueError(f"pattern {item['id']} appears twice")
        text = " ".join([item["statement"], item["question"], *item["holds_when"],
                         *item["not_when"]])
        if FORBIDDEN_REGEX.search(text):
            raise ValueError(f"pattern {item['id']} explains or advises")
        seen.add(item["id"])
        out.append(Pattern(
            id=item["id"], name=item["name"], statement=item["statement"],
            holds_when=tuple(item["holds_when"]), not_when=tuple(item["not_when"]),
            question=item["question"], retiring_answer=item["retiring_answer"]))
    if not out:
        raise ValueError("the library is empty")
    return out
