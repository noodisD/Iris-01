"""Reading an entry as an account of something that happened.

Nothing here is registered with any engine, surface or queue. It is a reader
built to answer one question before anything is designed around it: how much of
this archive is made of *episodes* — a situation, what it demanded, what came
in, what the owner did, and what they reported followed — rather than of
subjects that recur. `scripts/read_episodes.py` runs it once and reports counts.

Why a frame at all. The existing reader produces claims with quotations, which
is enough to say "this subject keeps coming up" and not enough to say "these two
accounts have the same shape". Comparing shapes is the point: an account of
missing half an instruction while concentrating on an unfamiliar action has the
same relation in it as an account from a completely different subject, and no
amount of topical similarity will put them together (Gentner and Markman on
structure mapping).

What this does not do, deliberately:

- It does not decide that two episodes are the same shape. This pass extracts
  and verifies; comparison is a separate question, and asking it before knowing
  how many comparable episodes exist would be building on a guess.
- It does not write anything. No table, no candidate, no card.
- It does not soften any existing rule. Every quote is verified verbatim against
  the entry it is attributed to, and an episode whose parts cannot be supported
  is dropped whole — the same fail-closed treatment `check_support` gives a
  claim, and for the same reason: an unverifiable account of what someone did is
  worse than no account.

The one thing it adds is what ADR-0016 named as missing before a claim about
behaviour could ever be confirmed: an actor, an event identity, a modality
(happened, planned, or imagined) and a time. A frame with those four is the
proof that refusal is waiting for. Until it is measured, it stays a prototype.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date

from .constants import OBSERVATION_MAX_TOKENS
from .narrative_policy import FORBIDDEN_REGEX
from .observations import (
    Citation,
    ObservationEngine,
    _normalized,
    _strip_fence,
    chunk_entries,
    interleave,
)

logger = logging.getLogger(__name__)

#: Whether the writing says this happened, was intended, or was imagined. An
#: account of a plan is not an event, and counting one as the other is how a
#: record of intentions becomes a record of behaviour.
MODALITIES = ("happened", "planned", "hypothetical")

#: Who the account is about. A friend's experience, retold, is not the owner's.
ACTORS = ("self", "other")

#: The parts of an episode. `situation` and `response` are required: without
#: them there is no account, only a remark. The rest may be absent, and absent
#: is recorded as absent rather than filled in.
PARTS = ("situation", "demand", "information", "response", "outcome")

SYSTEM_PROMPT = """You are reading someone's journal entries and extracting accounts of particular occasions.

An account is one occasion, not a habit or a summary. Extract only what the writing states.

For each account, give:
- "actor": "self" if the writer is describing their own experience, "other" if it is someone else's.
- "modality": "happened" if the writing says it did, "planned" if it was intended, "hypothetical" if it is imagined or a comparison.
- "situation": what was going on.
- "demand": what was taking effort or attention, if the writing says.
- "information": what came in — something said, seen, noticed — if the writing says.
- "response": what the person did.
- "outcome": what the writing says followed. Omit if it does not say.
- "quotes": the passages this rests on, each {"entryId": N, "sourceType": "reflection", "text": "..."} quoted word for word.

Rules:
- Every part must come from the entry. Do not complete an account from what usually happens.
- Do not explain why anything happened, and do not say what anyone should do.
- If the same occasion is described twice, extract it once.
- An entry may contain no accounts. An empty list is a good answer.

Return JSON only:
{"episodes": [{"actor": "self", "modality": "happened", "situation": "...", "demand": "...", "information": "...", "response": "...", "outcome": "...", "quotes": [...]}]}"""


@dataclass(frozen=True)
class Episode:
    """One occasion, as the writing describes it, with the writing attached."""

    actor: str
    modality: str
    situation: str
    response: str
    demand: str | None
    information: str | None
    outcome: str | None
    citations: tuple[Citation, ...]
    occurred_on: date | None

    @property
    def is_complete(self) -> bool:
        """Whether every part of the frame is present.

        Only a complete episode can be compared with another on its shape: two
        accounts with no stated outcome have nothing to agree or disagree
        about. Counting these is the point of the first pass.
        """
        return all(getattr(self, part) for part in PARTS)

    def as_claim(self) -> str:
        """The episode as one sentence, for the support check.

        Deliberately flat and in the writing's own terms: the check asks
        whether the quotes show this occasion, and a sentence that explained
        or interpreted it would be asking something else.
        """
        parts = [f"On one occasion: {self.situation}"]
        if self.demand:
            parts.append(f"while {self.demand}")
        if self.information:
            parts.append(f"with {self.information}")
        parts.append(f"the writer {self.response}")
        if self.outcome:
            parts.append(f"and reported {self.outcome}")
        return ", ".join(parts) + "."

    def as_dict(self) -> dict:
        return {
            "actor": self.actor,
            "modality": self.modality,
            **{part: getattr(self, part) for part in PARTS},
            "occurredOn": self.occurred_on.isoformat() if self.occurred_on else None,
            "citations": [c.as_dict() for c in self.citations],
            "complete": self.is_complete,
        }


def _clean(value) -> str | None:
    text = _normalized(str(value or ""))
    return text or None


def verified_episodes(raw: list, entries: list[dict]) -> list[Episode]:
    """The episodes a reply describes that the entries actually support.

    Refuses, rather than repairs, in every case the existing reader refuses:
    an unusable actor or modality, a missing situation or response, a quote
    that cannot be found word for word in the entry it names, and any wording
    that explains or prescribes (`narrative_policy`). An account of what
    someone did is the most consequential thing this system can hold, so it is
    held to the strictest rule already in the codebase rather than a new one.
    """
    by_id = {(e.get("source_type", "reflection"), e["id"]): e for e in entries}
    kept: list[Episode] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        actor = _clean(item.get("actor"))
        modality = _clean(item.get("modality"))
        if actor not in ACTORS or modality not in MODALITIES:
            logger.info("Episode refused: actor or modality not stated")
            continue

        fields = {part: _clean(item.get(part)) for part in PARTS}
        if not fields["situation"] or not fields["response"]:
            logger.info("Episode refused: no situation or no response")
            continue
        if any(FORBIDDEN_REGEX.search(v) for v in fields.values() if v):
            logger.info("Episode refused: causal or prescriptive wording")
            continue

        citations = ObservationEngine._citations(item.get("quotes") or [], by_id)
        if not citations:
            logger.info("Episode refused: its quotes could not be verified")
            continue

        dates = [c.entry_date for c in citations if c.entry_date]
        kept.append(Episode(
            actor=actor, modality=modality,
            situation=fields["situation"], response=fields["response"],
            demand=fields["demand"], information=fields["information"],
            outcome=fields["outcome"],
            citations=citations,
            # The occasion's own day, where the writing that carries it has
            # one. An undated recording can describe an episode; it cannot say
            # when it happened, and nothing here fills that in.
            occurred_on=min(dates) if dates else None,
        ))
    return kept


class EpisodeReader:
    """Reads an archive and returns the occasions it can support."""

    def __init__(self, user_id: int, intelligence=None):
        self.user_id = user_id
        # The model is whatever the caller passed, and nothing otherwise. The
        # observation engine builds one lazily when asked, which is right for a
        # surface the owner pressed a button on and wrong for a prototype: a
        # test that passed None would have read the archive for real.
        self.intelligence = intelligence
        self.engine = ObservationEngine(user_id, intelligence=intelligence)

    def read(self, entries: list[dict]) -> list[Episode]:
        """Every episode these entries support, in one pass per chunk."""
        if not entries or self.intelligence is None:
            return []
        found: list[Episode] = []
        chunks = chunk_entries(interleave(entries))
        for i, chunk in enumerate(chunks, 1):
            try:
                reply = self.intelligence.chat(
                    messages=[{"role": "user", "content": self.engine._render(chunk)}],
                    system_prompt=SYSTEM_PROMPT,
                    max_tokens=OBSERVATION_MAX_TOKENS,
                )
            except Exception as e:
                logger.error(f"Episode pass {i} of {len(chunks)} failed: {e}")
                continue
            try:
                raw = json.loads(_strip_fence(reply)).get("episodes") or []
            except (ValueError, AttributeError) as e:
                logger.warning(f"Episode pass {i} did not return JSON: {e}")
                continue
            found.extend(verified_episodes(raw, chunk))
        return found


def tally(episodes: list[Episode]) -> dict:
    """What a read found, as counts. Never an account, never a quote."""
    return {
        "episodes": len(episodes),
        "self": sum(1 for e in episodes if e.actor == "self"),
        "other": sum(1 for e in episodes if e.actor == "other"),
        **{m: sum(1 for e in episodes if e.modality == m) for m in MODALITIES},
        "with_outcome": sum(1 for e in episodes if e.outcome),
        "complete": sum(1 for e in episodes if e.is_complete),
        "dated": sum(1 for e in episodes if e.occurred_on),
        # The only ones a comparison pass could ever put side by side: the
        # owner's own occasions, that actually happened, with every part
        # present. If this number is small, comparing shapes is premature.
        "comparable": sum(1 for e in episodes
                          if e.is_complete and e.actor == "self" and e.modality == "happened"),
    }
