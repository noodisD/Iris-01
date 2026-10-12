"""Fixing what the transcriber mis-heard, against a second hearing (ADR-0030).

A session's words come from local Whisper; the diarizing transcriber heard the
same audio independently. Where the two disagree, a model sees both for that
stretch of time and may fix a word only when it is plainly a mis-hearing,
preferring what the other hearing says there. It may not summarise, smooth
the speech, or move words between speakers, and a span neither hearing makes
sense of is marked unclear rather than guessed. `readable.py` explains why a
guess is worse than a gap: a session's owner turns are quoted back as evidence.

Checked, not trusted: a turn whose length moves by more than a fifth keeps
Whisper's words, every word change is logged for the owner, and a request the
provider fails leaves its turns as they were.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from .config import settings
from .observations import _strip_fence

if TYPE_CHECKING:
    from .session_voices import Heard

logger = logging.getLogger(__name__)

#: Turns per request, with the second hearing for the same stretch of time.
CHUNK = 20
#: A turn's word count may move this much before the fix is refused.
DRIFT = (0.8, 1.25)
#: Measured on a 56-minute session: $0.31 on the chat model.
DOLLARS_PER_MINUTE = 0.0055
UNCLEAR = {"pl": "niezrozumiałe"}

PROMPT = """You correct an automatic transcript of a recorded conversation in language "{language}".
You get one stretch of it in two versions of the same audio:
- MAIN: numbered turns (from Whisper). This is the one you correct.
- SECOND: an independent transcript of the same stretch of time by another model. It can repeat itself and has errors of its own.

Rules:
1. Fix only plain speech-recognition errors: mis-heard words, words that make no sense in context, words split apart, punctuation and capitals. Where SECOND has a sensible word in that place, use it.
2. Do not summarise, do not smooth spoken style, do not add content, and do not remove repetitions or asides that were really said. Keep colloquial speech as it is. Write in the transcript's language.
3. If a span cannot be settled from either version, keep it and mark it as [{unclear}: <the original words>]. Do not guess.
4. Keep the number of turns and their numbers. Do not move text between turns.
5. For every changed word give an entry in "changes" (from, to, a short why). Leave punctuation-only changes out of "changes".

Reply with JSON only: {{"turns":[{{"n":<number>,"text":"<corrected text>","changes":[{{"from":"...","to":"...","why":"..."}}]}}]}}"""


def _words(text: str) -> int:
    return len(re.findall(r"\w+", text))


def _request(turns: list[Heard], second: list[Heard], first: int) -> str:
    lo = turns[0].start - 5
    hi = turns[-1].end + 5
    main = "\n".join(f"[{first + k}] {t.speaker}: {t.text}" for k, t in enumerate(turns))
    other = "\n".join(f"{h.speaker}: {h.text}" for h in second if lo <= h.start < hi and h.text)
    return f"MAIN:\n{main}\n\nSECOND:\n{other}"


def tidy(turns: list[Heard], second: list[Heard], language: str | None,
         intelligence: Any = None) -> tuple[list[Heard], dict]:
    """The turns with mis-hearings fixed, and a report of every change made or refused."""
    from dataclasses import replace

    if not turns:
        return turns, {"changes": [], "refused": 0, "unavailable": 0, "unclear": 0}
    if intelligence is None:
        from .intelligence import Intelligence
        intelligence = Intelligence()
    marker = UNCLEAR.get(language or "", "unclear")
    system = PROMPT.format(language=language or "unknown", unclear=marker)
    fixed = list(turns)
    changes: list[dict] = []
    refused = unavailable = 0
    for first in range(0, len(turns), CHUNK):
        part = turns[first:first + CHUNK]
        try:
            reply = intelligence.chat(messages=[{"role": "user", "content": _request(part, second, first)}],
                                      system_prompt=system, temperature=None, max_tokens=16000,
                                      model=settings.OPENAI_MODEL, response_format={"type": "json_object"})
            got = {int(t["n"]): t for t in json.loads(_strip_fence(reply)).get("turns", [])}
        except Exception as exc:
            logger.warning(f"Transcript check unavailable for turns {first}+ ({type(exc).__name__})")
            unavailable += len(part)
            continue
        for k, turn in enumerate(part):
            new = got.get(first + k) or {}
            text = str(new.get("text") or "").strip()
            if not text:
                continue
            before, after = _words(turn.text), _words(text)
            if before >= 4 and not DRIFT[0] <= after / before <= DRIFT[1]:
                refused += 1
                continue
            fixed[first + k] = replace(turn, text=text)
            changes += [{"at": round(turn.start), "from": str(c.get("from", "")), "to": str(c.get("to", "")),
                         "why": str(c.get("why", ""))}
                        for c in new.get("changes") or [] if isinstance(c, dict)]
    unclear = sum(t.text.count(f"[{marker}") for t in fixed)
    return fixed, {"changes": changes, "refused": refused, "unavailable": unavailable, "unclear": unclear}
