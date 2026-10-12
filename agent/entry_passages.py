"""A long journal entry cut into passages for recall.

Chat finds what to remember by embedding. One vector for a four-thousand-word
entry is the average of everything in it, so it matches every question a
little and none well, and what chat was then shown was a 300-character window
picked by shared words, which misses an inflected form and fails outright on
an entry with no sentence breaks. A long entry is instead cut into runs of
whole sentences, each embedded on its own; the passage that matched is the
passage shown. A dictated entry is cut from its reading copy, whose words are
the entry's words, so a passage is always the owner's own text.

Short entries are recalled whole, as before.
"""

from __future__ import annotations

import re

#: Entries at or under this many words are recalled whole.
MIN_WORDS = 250
#: A passage closes once it reaches this many words...
TARGET_WORDS = 150
#: ...and never grows past this, so a sentence that long is cut at words.
MAX_WORDS = 250
#: A last run this short joins the one before it.
TAIL_WORDS = 40

_SENTENCE = re.compile(r"(?<=[.!?…])\s+")


def _count(text: str) -> int:
    return len(text.split())


def _units(text: str) -> list[tuple[str, bool]]:
    """Sentences in order, each with whether it closes a paragraph."""
    units: list[tuple[str, bool]] = []
    for paragraph in re.split(r"\n\s*\n", text or ""):
        sentences = [s for s in _SENTENCE.split(" ".join(paragraph.split())) if s]
        for k, sentence in enumerate(sentences):
            words = sentence.split()
            pieces = [" ".join(words[i:i + MAX_WORDS]) for i in range(0, len(words), MAX_WORDS)]
            for p, piece in enumerate(pieces):
                units.append((piece, k == len(sentences) - 1 and p == len(pieces) - 1))
    return units


def cut(text: str) -> list[str]:
    """The passages of a long entry, or nothing for one recalled whole."""
    if _count(text or "") <= MIN_WORDS:
        return []
    passages: list[str] = []
    current: list[str] = []
    size = 0
    for sentence, ends_paragraph in _units(text):
        n = _count(sentence)
        if current and size + n > MAX_WORDS:
            passages.append(" ".join(current))
            current, size = [], 0
        current.append(sentence)
        size += n
        if size >= TARGET_WORDS or (ends_paragraph and size >= TARGET_WORDS * 0.6):
            passages.append(" ".join(current))
            current, size = [], 0
    if current:
        if passages and size < TAIL_WORDS and _count(passages[-1]) + size <= MAX_WORDS + TAIL_WORDS:
            passages[-1] = f"{passages[-1]} {' '.join(current)}"
        else:
            passages.append(" ".join(current))
    return passages
