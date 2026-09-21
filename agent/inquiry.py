"""An inquiry into a pattern: one question at a time, and the answers matter.

A list of questions is not an inquiry. The first attempt at this produced three
questions in one breath, each restating the same table, none of them able to
use what the owner said — which is a questionnaire with a table on top.

What makes questioning Socratic is not the wording of any one question. It is
that the asker does not know the answer, listens to it, says back what they
heard, and lets it change where the questioning goes (Padesky, *Socratic
Questioning: Changing Minds or Guiding Discovery?*). So the *shape* is fixed
here, in code, and only the wording comes from the model:

1. **clarify** — what the condition actually means in the owner's terms. A
   pattern named by a machine from summaries may not be the thing they live.
2. **evidence** — what makes them say the welcome occasions were welcome.
3. **exception** — an occasion where the condition held and what followed was
   different. An inquiry that never looks for the case that breaks the pattern
   is a case being built.
4. **consequence** — what the next run of occasions adds up to if nothing
   changes. This is the question the owner asked for, and the one a count
   cannot answer: the record holds what happened, not what it would cost.
5. **weigh** — what would make the rare large welcome occasion worth the
   unwelcome ones. Their judgement, about their life.

Then a synthesis, which is the part most likely to go wrong. It may contain no
number that is not in the counts, must pass the narrative firewall, and is
built from what the owner said rather than from what IRIS proposed — including,
when their answers went that way, that the pattern did not survive them. An
inquiry whose conclusion is fixed before it starts is an interrogation.

Nothing here is stored in the database. The transcript is the owner's, on their
machine.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from .connections import _ADVICE_OPENERS, _clean
from .constants import OBSERVATION_MAX_TOKENS
from .narrative_policy import FORBIDDEN_REGEX
from .observations import _strip_fence

logger = logging.getLogger(__name__)

#: What each turn is for. The model writes the question; it does not choose
#: which question is being asked.
STAGES: tuple[tuple[str, str], ...] = (
    ("clarify",
     "Ask what this circumstance actually looks like for them, in their own terms. "
     "You have only summaries of their writing; they have the occasions."),
    ("evidence",
     "Ask what made the occasions that went well feel welcome to them — what "
     "specifically was gained. Do not assume it was the obvious thing."),
    ("exception",
     "Ask for an occasion where this circumstance held and what followed was "
     "different from the pattern, and what was different about it."),
    ("consequence",
     "Ask what the next run of occasions like these would add up to for them if "
     "nothing changed. The counts say what happened; they cannot say what it "
     "would cost."),
    ("weigh",
     "Ask what would have to be true for the rare large welcome occasion to be "
     "worth the unwelcome ones. This is their judgement, not yours."),
)

QUESTION_PROMPT = """You are asking one person about a pattern in occasions they wrote down.

Ask ONE question, and nothing else. No preamble, no summary, no second question.

The question must:
- be answerable only by them — about what they mean, expect, weigh or remember;
- follow from what they have already said in this conversation;
- leave open whether the pattern holds at all. You do not know the answer.

Do not give advice, do not say what would be wise, do not name a feeling they have not named, and do not ask anything whose answer you have already decided.

Return JSON only: {"question": "..."}"""

SYNTHESIS_PROMPT = """You are closing a short conversation with one person about a pattern in occasions they wrote down.

Write at most six sentences:
- what they said, in their terms, attributed to them;
- what is still unresolved;
- whether what they said leaves the pattern standing, narrowed to some conditions, or not standing at all.

Use no number that does not appear in the counts you were given. Do not say what caused anything, do not give advice, do not tell them what they feel, and do not claim the pattern holds if their answers did not support it.

Return JSON only: {"summary": "..."}"""

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


@dataclass
class Turn:
    """One question and what the owner said back."""

    stage: str
    question: str
    answer: str


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".").rstrip("0").rstrip(".") or "0" for n in _NUMBER.findall(text)}


def _acceptable(question: str) -> bool:
    """One question, no advice, and a question at all."""
    if not question.endswith("?") or question.count("?") != 1:
        return False
    if FORBIDDEN_REGEX.search(question):
        return False
    return not any(question.lower().lstrip().startswith(o) for o in _ADVICE_OPENERS)


def _transcript(turns: list[Turn]) -> str:
    return "\n".join(f"Q: {t.question}\nThey said: {t.answer}" for t in turns)


def next_question(stage: str, instruction: str, condition: str, counts: dict,
                  turns: list[Turn], intelligence) -> str | None:
    """The question for this stage, or None if nothing usable came back.

    Refused rather than repaired: a question that arrives as two questions, or
    as advice with a question mark, is not trimmed into shape — the stage is
    skipped and the inquiry says so. A malformed question is a cheap thing to
    lose and an expensive thing to ask.
    """
    if intelligence is None:
        return None
    asked = (f"The circumstance: {condition}\n"
             f"What their own accounts show: {json.dumps(counts)}\n\n"
             f"This question is for: {instruction}\n\n"
             + (f"So far:\n{_transcript(turns)}" if turns else "Nothing has been asked yet."))
    try:
        reply = intelligence.chat(messages=[{"role": "user", "content": asked}],
                                  system_prompt=QUESTION_PROMPT,
                                  max_tokens=OBSERVATION_MAX_TOKENS)
        question = _clean(json.loads(_strip_fence(reply)).get("question"))
    except Exception as e:
        logger.error(f"No question for stage {stage}: {e}")
        return None
    if not _acceptable(question):
        logger.info(f"Question refused at stage {stage}")
        return None
    return question


def synthesis(condition: str, counts: dict, turns: list[Turn], intelligence) -> str:
    """What the owner said, and what it leaves standing.

    Held to the rule the weekly letter learned: every number in it must be one
    it was given. An inquiry that ends by inventing a count has undone the
    point of counting.
    """
    if not turns or intelligence is None:
        return ""
    allowed = _numbers(json.dumps(counts))
    asked = (f"The circumstance: {condition}\n"
             f"Counts from their own accounts: {json.dumps(counts)}\n\n"
             f"The conversation:\n{_transcript(turns)}")
    try:
        reply = intelligence.chat(messages=[{"role": "user", "content": asked}],
                                  system_prompt=SYNTHESIS_PROMPT,
                                  max_tokens=OBSERVATION_MAX_TOKENS)
        summary = _clean(json.loads(_strip_fence(reply)).get("summary"))
    except Exception as e:
        logger.error(f"No synthesis: {e}")
        return ""
    if FORBIDDEN_REGEX.search(summary):
        logger.info("Synthesis refused: causal or prescriptive wording")
        return ""
    if not _numbers(summary) <= allowed:
        logger.info("Synthesis refused: a number it was not given")
        return ""
    return summary
