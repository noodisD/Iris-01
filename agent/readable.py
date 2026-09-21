"""A reading copy of an entry: the same words, easier to parse.

Dictated writing arrives as one long breath — no sentence breaks, no capitals,
"um" and false starts, punctuation wherever the transcriber guessed. A model
reading it does worse than it would on the same words laid out properly, and
the owner is not going to punctuate two hundred entries by hand.

The rule that makes this safe is narrow and checked rather than trusted:

    a reading copy may change punctuation, casing and line breaks.
    it may not change a single word.

Everything in this product stands on quotes existing word for word in what the
owner wrote. Rewrite the words and a citation is no longer a citation, the
support check is checking prose nobody wrote, and a construct is anchored in a
sentence its author never said. So `same_words` compares the two texts as
sequences of words with case and punctuation stripped, and a copy that fails is
thrown away rather than repaired.

What this deliberately cannot fix: a transcriber that heard the wrong word.
That needs the owner, or an uncertain span kept as uncertain — not a model's
guess at what they meant, which is the same failure wearing a helpful face.

`locate` is the other half. A quote taken from the reading copy carries its
punctuation, so it is looked up in the original by words alone and returned as
the original wrote it. What the owner is shown is always their own text.
"""

from __future__ import annotations

import json
import logging
import re

from .constants import OBSERVATION_MAX_TOKENS
from .observations import _strip_fence

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are given a passage of someone's journal, dictated in one breath and without punctuation.

Say where the sentences end. For each sentence, give the last three or four words of it, exactly as they appear in the passage.

Do not rewrite anything. Do not correct, drop or add words. You are marking where full stops belong, nothing else.

Return JSON only: {"sentence_ends": ["...", "..."]}"""

_WORD = re.compile(r"[\w']+", re.UNICODE)
_SENTENCE_END = re.compile(r"[.!?]")

#: Above roughly this many words per sentence-ending mark, a passage is being
#: read as one breath. Ordinary writing sits near 15-25; a dictated entry with
#: no punctuation at all has no marks in hundreds of words.
WORDS_PER_SENTENCE_LIMIT = 45


def words(text: str) -> list[str]:
    """The text as lowercase words, without punctuation."""
    return [w.lower() for w in _WORD.findall(text or "")]


def same_words(original: str, copy: str) -> bool:
    """Whether the copy is the original with only its punctuation changed."""
    return words(original) == words(copy)


def locate(original: str, quote: str) -> str | None:
    """The quote as the original wrote it, found by words alone.

    A quote taken from a reading copy carries that copy's punctuation and
    capitals. Verifying it against the original by string comparison would fail
    on a comma, and storing it as the copy wrote it would show the owner a
    sentence they did not punctuate. This finds the same run of words in the
    original and returns exactly that span of their text.
    """
    hay, needle = words(original), words(quote)
    if not needle or len(needle) > len(hay):
        return None
    for start in range(len(hay) - len(needle) + 1):
        if hay[start:start + len(needle)] == needle:
            spans = [m.span() for m in _WORD.finditer(original)]
            return original[spans[start][0]:spans[start + len(needle) - 1][1]]
    return None


def needs_tidying(text: str) -> bool:
    """Whether this passage is hard to read for want of punctuation.

    Most entries do not need a reading copy, and asking for one is the
    expensive, risky half of this: on the first twenty entries, a third of the
    copies came back with a word changed and were thrown away. Spending that
    only on the passages that are actually one long breath costs less and puts
    fewer entries near the edit that would break a citation.
    """
    counted = words(text)
    if len(counted) < WORDS_PER_SENTENCE_LIMIT:
        return False
    marks = len(_SENTENCE_END.findall(text or ""))
    return marks == 0 or len(counted) / marks > WORDS_PER_SENTENCE_LIMIT


def punctuate(text: str, ends: list[str]) -> str:
    """The passage with a full stop after each of those endings, and nothing else.

    The marks are inserted into the original string, so the words cannot change
    however wrong the endings are: the worst a bad ending can do is put a stop
    in an odd place. Asking a model for the tidied *text* instead failed on
    every one of the 32 dictated entries in this archive — each copy came back
    with a word dropped, a filler removed or a repetition merged, which is the
    one edit that would break a citation.
    """
    spans = [m.span() for m in _WORD.finditer(text)]
    if not spans:
        return text
    hay = words(text)
    cuts: set[int] = set()
    searched = 0
    for ending in ends or []:
        needle = words(str(ending))
        if not needle:
            continue
        for start in range(searched, len(hay) - len(needle) + 1):
            if hay[start:start + len(needle)] == needle:
                cuts.add(start + len(needle) - 1)
                searched = start + len(needle)
                break

    out = []
    for i, (begin, end) in enumerate(spans):
        word = text[begin:end]
        gap = text[spans[i - 1][1]:begin] if i else text[:begin]
        if i and (i - 1) in cuts:
            out.append("." + ("\n\n" if gap.strip() else " "))
            word = word[:1].upper() + word[1:]
        else:
            out.append(gap)
            if not i:
                word = word[:1].upper() + word[1:]
        # A lone "i" is the same word in either case, and the lowercase one is
        # the single thing that makes dictated text look unread.
        out.append("I" if word == "i" else word)
    tail = text[spans[-1][1]:].strip()
    return "".join(out) + (tail if tail else ".")


#: Why a reading copy was not made. "unavailable" is the provider failing and
#: is not a judgement about the answer — counting the two together is how a run
#: with no credits left came out looking like a model that rewrites everything.
REASONS = ("ok", "not_needed", "unavailable", "unusable_answer", "changed_words")


def readable(text: str, intelligence) -> tuple[str | None, str]:
    """A reading copy of one entry, and why, if there is none.

    The model is asked only where the sentences end; the marks are put in here.
    `same_words` still runs, because a rule this load-bearing is worth checking
    even when the construction makes it true.
    """
    if not text or not text.strip() or intelligence is None:
        return None, "not_needed"
    try:
        reply = intelligence.chat(messages=[{"role": "user", "content": text}],
                                  system_prompt=SYSTEM_PROMPT,
                                  max_tokens=OBSERVATION_MAX_TOKENS)
    except Exception as e:
        logger.error(f"The model could not be asked: {e}")
        return None, "unavailable"
    try:
        ends = json.loads(_strip_fence(reply)).get("sentence_ends") or []
    except (ValueError, AttributeError):
        return None, "unusable_answer"
    if not isinstance(ends, list) or not ends:
        return None, "unusable_answer"
    copy = punctuate(text, ends)
    if not same_words(text, copy):  # pragma: no cover - construction forbids it
        logger.error("Reading copy refused: the words are not the same words")
        return None, "changed_words"
    return copy, "ok"
