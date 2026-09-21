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

from .constants import OBSERVATION_MAX_TOKENS, OBSERVATION_MIN_QUOTE_CHARS
from .narrative_policy import FORBIDDEN_REGEX
from .readable import locate
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

#: What an account needs before it can be set beside another and compared on
#: its shape. Requiring all five parts was too strict: `information` — what
#: arrived while attention was occupied — is the heart of one shape and
#: irrelevant to others ("preparation against live decisions" has no incoming
#: cue at all). On this archive that test admitted 19 of 86 accounts; this one
#: admits the 46 that say what followed.
SHAPE = ("situation", "response", "outcome")

#: Bumped whenever the frame or the prompt changes, so a cached extraction is
#: never silently mixed with one made by different rules.
EXTRACTION_VERSION = 2

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
- "domain": two or three words for the area of life this happened in, in the writing's own terms.
- "explanation": the writer's own account of why it went that way, if they give one. Theirs, not yours. Omit if they do not.
- "quotes": the passages this rests on, each {"entryId": N, "sourceType": "reflection", "text": "..."} quoted word for word.

Rules:
- Every part must come from the entry. Do not complete an account from what usually happens.
- Do not explain why anything happened, and do not say what anyone should do.
- If the same occasion is described twice, extract it once.
- An entry may contain no accounts. An empty list is a good answer.

Return JSON only:
{"episodes": [{"actor": "self", "modality": "happened", "domain": "...", "situation": "...", "demand": "...", "information": "...", "response": "...", "outcome": "...", "explanation": "...", "quotes": [...]}]}"""


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
    domain: str | None = None
    #: The writer's own account of why it went that way. Kept apart from what
    #: happened, and never treated as a fact about them: it is the thing a
    #: connection might agree with, extend, or contradict — and the thing that
    #: decides whether a connection is new to them or one they already drew.
    explanation: str | None = None

    @property
    def is_complete(self) -> bool:
        """Whether every part of the frame is present, markers included."""
        return all(getattr(self, part) for part in PARTS)

    @property
    def has_shape(self) -> bool:
        """Whether there is enough here to set beside another account.

        Situation, response, and what followed. `demand` and `information` are
        markers two accounts may or may not share; requiring them of every
        account admitted only the shapes that happen to involve an incoming
        cue.
        """
        return all(getattr(self, part) for part in SHAPE)

    @property
    def markers(self) -> tuple[str, ...]:
        """The optional parts this account states, which another may share."""
        return tuple(p for p in ("demand", "information") if getattr(self, p))

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
            "domain": self.domain,
            **{part: getattr(self, part) for part in PARTS},
            "explanation": self.explanation,
            "occurredOn": self.occurred_on.isoformat() if self.occurred_on else None,
            "citations": [c.as_dict() for c in self.citations],
            "complete": self.is_complete,
            "hasShape": self.has_shape,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Episode:
        """An episode read back from a cached run, quotes and all."""
        return cls(
            actor=data["actor"], modality=data["modality"], domain=data.get("domain"),
            situation=data["situation"], response=data["response"],
            demand=data.get("demand"), information=data.get("information"),
            outcome=data.get("outcome"), explanation=data.get("explanation"),
            occurred_on=date.fromisoformat(data["occurredOn"]) if data.get("occurredOn") else None,
            citations=tuple(
                Citation(entry_id=int(c["entryId"]),
                         entry_date=date.fromisoformat(c["entryDate"]) if c.get("entryDate") else None,
                         text=c["text"], source_type=c.get("sourceType", "reflection"))
                for c in data.get("citations", [])),
        )


def _clean(value) -> str | None:
    text = _normalized(str(value or ""))
    return text or None


def _citations(quotes: list, by_id: dict) -> tuple[Citation, ...] | None:
    """Every quote found in the entry it names, or nothing.

    The same all-or-nothing rule the observation reader keeps, with one
    difference: the quote is matched by its words rather than by its exact
    characters, and what is stored is the span as the *original* entry wrote
    it. A model reading a punctuated copy of a dictated entry quotes it with
    that copy's commas; the owner never typed those commas, and showing them
    their own writing with someone else's punctuation in it is a small lie in
    the place this system can least afford one.

    A word that is not in the entry still fails, which is the whole point.
    """
    found: list[Citation] = []
    for q in quotes:
        if not isinstance(q, dict):
            return None
        try:
            entry_id = int(q.get("entryId"))
        except (TypeError, ValueError):
            return None
        source_type = str(q.get("sourceType") or "reflection")
        entry = by_id.get((source_type, entry_id))
        if entry is None:
            logger.info(f"Citation names {source_type} {entry_id}, which was not read")
            return None
        quote = str(q.get("text") or "")
        if len(quote.strip()) < OBSERVATION_MIN_QUOTE_CHARS:
            return None
        # Against the owner's text, never the reading copy: the copy is a way
        # of reading the entry, not a second version of what they wrote.
        original = locate(entry["content"], quote)
        if original is None:
            logger.info(f"Quote not found in {source_type} {entry_id}")
            return None
        found.append(Citation(entry_id=entry_id, entry_date=entry.get("date"),
                              text=original,
                              source_type=entry.get("source_type", "reflection")))
    return tuple(found)


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

        citations = _citations(item.get("quotes") or [], by_id)
        if not citations:
            logger.info("Episode refused: its quotes could not be verified")
            continue

        dates = [c.entry_date for c in citations if c.entry_date]
        kept.append(Episode(
            actor=actor, modality=modality,
            situation=fields["situation"], response=fields["response"],
            demand=fields["demand"], information=fields["information"],
            outcome=fields["outcome"],
            domain=_clean(item.get("domain")),
            explanation=_clean(item.get("explanation")),
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

    def read(self, entries: list[dict], readable: dict | None = None) -> list[Episode]:
        """Every episode these entries support, in one pass per chunk.

        `readable` maps an entry's id to a punctuated copy of it, which is what
        the model is shown. Quotes still resolve against the owner's own text
        (`_citations`), so a reading copy can make an entry easier to parse and
        can never become the thing that gets cited.
        """
        if not entries or self.intelligence is None:
            return []
        found: list[Episode] = []
        if readable:
            entries = [{**e, "content": readable.get(str(e["id"]), e["content"]),
                        "_original": e["content"]} for e in entries]
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
            # Verified against what the owner wrote, whatever was read.
            originals = [{**e, "content": e.get("_original", e["content"])} for e in chunk]
            found.extend(verified_episodes(raw, originals))
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
        "with_explanation": sum(1 for e in episodes if e.explanation),
        "labels": len({e.domain for e in episodes if e.domain}),
        "areas": len(areas(episodes)),
        # The only ones a comparison pass could ever put side by side: the
        # owner's own occasions, that actually happened, saying what followed.
        # If this number is small, comparing shapes is premature.
        "comparable": sum(1 for e in comparable(episodes)),
    }


#: Words that carry no area on their own, so "the pottery class" and "pottery"
#: are one area rather than two.
_NOT_AN_AREA = {"a", "an", "the", "my", "of", "in", "at", "on", "and", "with",
                "session", "sessions", "time", "day", "life", "general", "other",
                "personal", "daily", "routine", "activity", "activities"}


def _stem(word: str) -> str:
    """A crude stem, so "painting" and "paint" are one area rather than two."""
    for suffix in ("ing", "ers", "er", "ed", "es", "s", "e"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def coarse_area(label: str | None) -> str:
    """One word for the area an account happened in.

    The reader is asked for the area in the writing's own terms, and on this
    archive it produced 103 different labels for 116 accounts — almost an
    identifier each, which makes "from two different areas" true of any pair
    and therefore worthless as a test of cross-domain reach. This reduces a
    label to its first word that means something, which puts "pottery class",
    "pottery practice" and "pottery" together without anyone deciding in
    advance what the areas of a life are.

    A heuristic, and visible as one: the alternative is to give the reader a
    fixed vocabulary, which costs another read of the archive and decides the
    categories for the owner.
    """
    for word in (label or "").lower().replace("/", " ").replace("-", " ").split():
        word = "".join(c for c in word if c.isalnum())
        if len(word) > 2 and word not in _NOT_AN_AREA:
            return _stem(word)
    return "unstated"


def areas(episodes: list[Episode]) -> set[str]:
    """The coarse areas a set of accounts covers."""
    return {coarse_area(e.domain) for e in episodes} - {"unstated"}


def comparable(episodes: list[Episode]) -> list[Episode]:
    """The owner's own occasions, that happened, that say what followed."""
    return [e for e in episodes
            if e.has_shape and e.actor == "self" and e.modality == "happened"]
