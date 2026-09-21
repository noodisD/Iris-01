"""Proposing that two accounts from different parts of a life share a shape.

This is the inference step, and it is the first thing in IRIS that is allowed
to say something the owner did not write. The ingredients stay grounded — every
episode behind a candidate is one the archive supported, quote by quote — while
the relationship between them may be IRIS's. That is a deliberate departure
from the non-interpretive contract everything else here keeps, and it is why
this module proposes and never stores, and why the rules below are enforced in
code rather than asked for in a prompt.

What a candidate must survive, all checked after the model answers:

- Three or more supporting episodes, from two or more areas. Two accounts that
  rhyme are a coincidence; a shape needs repetition, and a shape found only
  inside one area is a topic. On the owner's archive this rule is weak and
  should be read as such: 62 comparable accounts carried 44 coarse areas
  between them, so almost any three accounts span two. What actually does the
  work here is the count, the contrast and the competing explanations.
- A contrast: an episode where the stated condition held and something else
  followed, or where the outcome appeared without it. A candidate that cannot
  name one has not been tested against the archive, only drawn from it.
- One condition, not a list of them, and one that does not hold in most of the
  accounts. Both rules come from the first real run: its weakest proposal
  joined three unrelated conditions with "or" under a good outcome, which the
  owner read — correctly — as good behaviour marked rather than as a pattern.
- Two or more competing explanations, kept side by side. The evidence here
  cannot choose between them, and presenting one is asserting what was not
  established.
- A question whose answer could retire the candidate, and the answer that
  would. Guided discovery is questions that can change the asker's mind;
  without a retiring answer a question is a funnel, however it is worded
  (Padesky, *Socratic Questioning: Changing Minds or Guiding Discovery?*).
- No causal or prescriptive wording, by the same firewall every other sentence
  passes (`agent/narrative_policy.py`). A shared condition may be described;
  what it does to the owner may not.

Novelty is reported, never assumed: if an episode's own `explanation` already
states the relationship, the candidate is marked as one the owner has drawn
themselves. Not finding it stated proves nothing about what they know — only
they can say that.

At most MAX_CANDIDATES survive a run. With a few dozen episodes there are
hundreds of possible pairings, and enough of them will read well: a cap is the
difference between a proposal and a generator of plausible stories.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from .constants import OBSERVATION_MAX_TOKENS
from .episodes import Episode, areas, coarse_area, comparable
from .narrative_policy import FORBIDDEN_REGEX
from .observations import _normalized, _strip_fence

logger = logging.getLogger(__name__)

MAX_CANDIDATES = 3
MIN_SUPPORTING = 3
MIN_DOMAINS = 2
MIN_EXPLANATIONS = 2

#: A condition may name one thing. The first real run proposed "a market signal,
#: a body-or-mind signal, or a concrete next step appeared, and it was acted on"
#: — three conditions joined by "or" under one good outcome, which the owner
#: read as "good behaviour marked" rather than as a pattern. One "or" is a
#: phrase; two is a list of separate conditions wearing one sentence.
MAX_DISJUNCTIONS = 1

#: A condition that holds in most accounts is a description of the archive
#: rather than something that distinguishes one occasion from another.
MAX_SUPPORT_SHARE = 0.5

SYSTEM_PROMPT = """You are given numbered accounts of occasions from one person's life, each with the area of life it happened in.

Find relationships that hold across accounts from DIFFERENT areas. A relationship is a shared condition and what followed it — not a shared subject. "Both about work" is not a relationship. "Whenever a decision was made while someone was waiting for an answer, it was reconsidered later" is.

For each relationship you propose, give:
- "condition": the ONE thing that was true on those occasions, in a few words. Not a list. If you need "or" to join two different conditions, they are two different relationships — choose one, or do not propose it.
- "followed": what followed on those occasions, in a few words.
- "relation": one sentence joining them, in plain words. Do not say why it happens and do not give advice.
- "supporting": the numbers of the accounts it holds in, at least 3, from at least 2 different areas.
- "contrast": the number of one account where the condition held and something else followed, or where what followed appeared without the condition. If there is none, do not propose the relationship.
- "contrast_kind": "condition_without_outcome" or "outcome_without_condition", saying which of those the contrasting account is.
- "explanations": at least two different accounts of why this might be so, each one sentence, neither presented as established.
- "question": one question to the person whose life this is, whose answer could show the relationship is wrong.
- "retiring_answer": what answer to that question would mean the relationship does not hold.
- "already_stated": true if one of the accounts' own explanations already says this relationship, false otherwise.

Propose at most 3, and fewer if fewer hold. An empty list is a good answer when the accounts share no relationship.

Return JSON only:
{"relationships": [{"condition": "...", "followed": "...", "relation": "...", "supporting": [0, 4, 9], "contrast": 7, "contrast_kind": "condition_without_outcome", "explanations": ["...", "..."], "question": "...", "retiring_answer": "...", "already_stated": false}]}"""


@dataclass(frozen=True)
class Candidate:
    """A proposed relationship, with everything needed to disbelieve it."""

    relation: str
    condition: str
    followed: str
    supporting: tuple[Episode, ...]
    contrast: Episode
    contrast_kind: str
    explanations: tuple[str, ...]
    question: str
    retiring_answer: str
    already_stated: bool
    domains: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "relation": self.relation,
            "condition": self.condition,
            "followed": self.followed,
            "contrastKind": self.contrast_kind,
            "domains": list(self.domains),
            "supporting": [e.as_dict() for e in self.supporting],
            "contrast": self.contrast.as_dict(),
            "explanations": list(self.explanations),
            "question": self.question,
            "retiringAnswer": self.retiring_answer,
            "alreadyStated": self.already_stated,
        }


def _clean(value) -> str:
    return _normalized(str(value or ""))


def _indexes(value, count: int) -> list[int]:
    """The account numbers a reply refers to, as positions that exist."""
    out = []
    for raw in value if isinstance(value, list) else [value]:
        try:
            i = int(raw)
        except (TypeError, ValueError):
            continue
        if 0 <= i < count and i not in out:
            out.append(i)
    return out


def vet(raw: list, episodes: list[Episode]) -> list[Candidate]:
    """The proposals that meet every rule, in the order they were made.

    Nothing here is repaired. A proposal missing a contrast is not a proposal
    with a small gap in it: it is one that was never tested against the
    accounts it did not come from.
    """
    kept: list[Candidate] = []
    for item in raw or []:
        if not isinstance(item, dict) or len(kept) >= MAX_CANDIDATES:
            continue
        relation = _clean(item.get("relation"))
        condition = _clean(item.get("condition"))
        followed = _clean(item.get("followed"))
        contrast_kind = _clean(item.get("contrast_kind"))
        question = _clean(item.get("question"))
        retiring = _clean(item.get("retiring_answer"))
        explanations = tuple(_clean(e) for e in (item.get("explanations") or []) if _clean(e))
        if not relation or not question or not retiring or not condition or not followed:
            logger.info("Candidate refused: a relation, condition, outcome, question "
                        "or retiring answer was missing")
            continue
        if condition.lower().count(" or ") > MAX_DISJUNCTIONS:
            logger.info("Candidate refused: the condition is a list of conditions")
            continue
        if contrast_kind not in ("condition_without_outcome", "outcome_without_condition"):
            logger.info("Candidate refused: the contrast does not say what it contrasts")
            continue
        if any(FORBIDDEN_REGEX.search(t) for t in (relation, question, *explanations)):
            logger.info("Candidate refused: causal or prescriptive wording")
            continue
        if len(explanations) < MIN_EXPLANATIONS:
            logger.info("Candidate refused: fewer than two competing explanations")
            continue

        supporting = _indexes(item.get("supporting"), len(episodes))
        contrast = _indexes(item.get("contrast"), len(episodes))
        if len(supporting) < MIN_SUPPORTING:
            logger.info(f"Candidate refused: {len(supporting)} supporting account(s)")
            continue
        if not contrast or contrast[0] in supporting:
            logger.info("Candidate refused: no contrasting account")
            continue

        if len(supporting) > max(MIN_SUPPORTING, int(len(episodes) * MAX_SUPPORT_SHARE)):
            logger.info(f"Candidate refused: holds in {len(supporting)} of {len(episodes)} "
                        "accounts, which describes the archive rather than a condition in it")
            continue

        episodes_for = tuple(episodes[i] for i in supporting)
        # Coarse areas, not the reader's labels: it names an area in the
        # writing's own terms, which on the real archive meant a different
        # label almost every time — "two different areas" would then be true
        # of any pair at all.
        domains = tuple(sorted({coarse_area(e.domain) for e in episodes_for} - {"unstated"}))
        if len(domains) < MIN_DOMAINS:
            logger.info(f"Candidate refused: {len(domains)} domain(s)")
            continue

        kept.append(Candidate(
            relation=relation, condition=condition, followed=followed,
            supporting=episodes_for, contrast=episodes[contrast[0]],
            contrast_kind=contrast_kind, explanations=explanations, question=question,
            retiring_answer=retiring, already_stated=bool(item.get("already_stated")),
            domains=domains))
    return kept


def render(episodes: list[Episode]) -> str:
    """The accounts as the model sees them: numbered, flat, no quotes.

    The quotes stay here. They are what makes each account true, and the
    question being asked is only whether the accounts have a shape in common —
    which the summaries answer. Less of the owner's writing leaves the machine
    for this than for the reading that produced the accounts.
    """
    lines = []
    for i, e in enumerate(episodes):
        parts = [f"[{i}] area: {e.domain or 'unstated'}", f"situation: {e.situation}"]
        if e.demand:
            parts.append(f"taking effort: {e.demand}")
        if e.information:
            parts.append(f"came in: {e.information}")
        parts.append(f"response: {e.response}")
        parts.append(f"followed: {e.outcome}")
        if e.explanation:
            parts.append(f"their own explanation: {e.explanation}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def propose(episodes: list[Episode], intelligence) -> tuple[list[Candidate], dict]:
    """Ask once, then keep only what survives the rules. Returns (kept, counts)."""
    usable = comparable(episodes)
    counts = {"episodes": len(episodes), "comparable": len(usable),
              "areas": len(areas(usable)), "proposed": 0, "kept": 0}
    if len(usable) < MIN_SUPPORTING or intelligence is None:
        return [], counts
    try:
        reply = intelligence.chat(
            messages=[{"role": "user", "content": render(usable)}],
            system_prompt=SYSTEM_PROMPT,
            max_tokens=OBSERVATION_MAX_TOKENS,
        )
    except Exception as e:
        logger.error(f"Connection pass failed: {e}")
        return [], counts
    try:
        body = json.loads(_strip_fence(reply))
        raw = body.get("relationships") or body.get("candidates") or []
    except (ValueError, AttributeError) as e:
        logger.warning(f"Connection pass did not return JSON: {e}")
        return [], counts

    counts["proposed"] = len(raw)
    kept = vet(raw, usable)
    counts["kept"] = len(kept)
    counts["already_stated"] = sum(1 for c in kept if c.already_stated)
    return kept, counts
