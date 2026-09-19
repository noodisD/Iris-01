"""The weekly letter, held to the rules the rest of IRIS keeps.

It was the one place IRIS wrote freely: an unconstrained prompt for "2-3 warm,
grounded paragraphs", no firewall on the result, no check on anything it
quoted, and a count of "wins" defined as entries with energy of 7 or more — a
score, in a product whose rule is that it does not score the owner.

The letter stays, and says only what it can support:

- The model is given facts computed here and the findings the shared admission
  let through, rendered by the same templates chat uses. It is not given the
  owner's entries — no more of their writing leaves the machine for a letter
  than did before.
- Every sentence it writes passes the narrative firewall or is dropped.
- Anything it puts in quotation marks must appear word for word in the week's
  entries, or the sentence is dropped. It never saw the entries, so a quote it
  produces is invented unless it happens to match.
- If the call fails, or nothing survives, the letter is the facts themselves.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .narrative_policy import FORBIDDEN_REGEX

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are writing a short weekly note to one person about their own week. "
    "Write two short paragraphs in second person using only the facts and "
    "observations you are given. Do not add facts, do not interpret them, do not "
    "say what caused anything, do not give advice, and do not quote anything. "
    "No bullet points, no headings."
)

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_QUOTED = re.compile(r"[\"“]([^\"”]+)[\"”]")


def _normalized(text: str) -> str:
    return " ".join((text or "").split())


def hold_to_the_rules(text: str, week_entries: list[str]) -> str:
    """The model's letter, minus every sentence that breaks a rule."""
    source = _normalized(" \n ".join(week_entries))
    paragraphs = []
    for paragraph in (text or "").split("\n\n"):
        kept = []
        for sentence in _SENTENCE.split(paragraph.strip()):
            if not sentence:
                continue
            if FORBIDDEN_REGEX.search(sentence):
                logger.info("Letter sentence dropped: causal or prescriptive wording")
                continue
            if any(_normalized(q) not in source for q in _QUOTED.findall(sentence)):
                logger.info("Letter sentence dropped: a quote not found in the week's entries")
                continue
            kept.append(sentence)
        if kept:
            paragraphs.append(" ".join(kept))
    return "\n\n".join(paragraphs)


def facts_letter(facts: list[str], findings: list[str]) -> str:
    """The letter with no model at all: what is known, in the order it is known."""
    parts = [" ".join(facts)] if facts else []
    if findings:
        parts.append(" ".join(findings))
    return "\n\n".join(parts)


def compose(facts: list[str], findings: list[str], week_entries: list[str],
            intelligence: Any) -> str:
    """Write the letter, or fall back to the facts."""
    if not week_entries or intelligence is None:
        return facts_letter(facts, findings)
    prompt = ("Facts about the week:\n" + "\n".join(f"- {f}" for f in facts)
              + "\n\nWhat IRIS noticed:\n"
              + ("\n".join(f"- {f}" for f in findings) if findings else "- nothing new"))
    try:
        written = intelligence.chat(messages=[{"role": "user", "content": prompt}],
                                    system_prompt=SYSTEM_PROMPT)
    except Exception as e:
        logger.warning(f"Letter could not be written, using the facts: {e}")
        return facts_letter(facts, findings)
    held = hold_to_the_rules(written, week_entries)
    return held or facts_letter(facts, findings)
