"""Read source-grounded accounts of particular occasions in journal entries.

The reader selects quoted passages for the situation, response, and any other
populated part. All passages must resolve within verified source citations;
actor, modality, and domain remain provisional classifications. The date is
the citation's recorded entry date, not a separately established event date.
Storage and comparison of accounts belong to the discovery pipeline.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date

from .constants import OBSERVATION_MAX_TOKENS, OBSERVATION_MIN_QUOTE_CHARS
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
EXTRACTION_VERSION = 3

class ReadUnavailable(RuntimeError):
    """An episode or label pass could not complete reliably."""


SYSTEM_PROMPT = """You are reading someone's journal entries and extracting accounts of particular occasions.

An account is one occasion, not a habit or a summary. Extract only what the writing states.

For each account, give:
- "actor": "self" if the writer is describing their own experience, "other" if it is someone else's.
- "modality": "happened" if the writing says it did, "planned" if it was intended, "hypothetical" if it is imagined or a comparison.
- "situation": a passage showing what was going on.
- "demand": a passage showing what took effort or attention, if stated.
- "information": a passage showing what came in — something said, seen, noticed — if stated.
- "response": a passage showing what the person did.
- "outcome": a passage showing what followed, only if stated.
- "domain": an optional, provisional two- or three-word area of life.
- "explanation": a passage containing the writer's own explanation, only if stated.
- "quotes": the source passages this account rests on, each {"entryId": N, "sourceType": "reflection", "text": "..."}.

Every populated situation, demand, information, response, outcome and explanation MUST be a contiguous passage of words from one of this account's quotes. Select the writing's actual words, not a summary or paraphrase. Include enough source quotations to support every populated passage. Do not invent an outcome or explanation when absent. Actor, modality and domain are provisional interpretations, not verified facts. If the same occasion is described twice, extract it once. An entry may contain no accounts; an empty list is a good answer.

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
            logger.info("Episode refused: citation source not read")
            return None
        quote = str(q.get("text") or "")
        if len(quote.strip()) < OBSERVATION_MIN_QUOTE_CHARS:
            return None
        # Against the owner's text, never the reading copy: the copy is a way
        # of reading the entry, not a second version of what they wrote.
        original = locate(entry["content"], quote)
        if original is None:
            logger.info("Episode refused: citation passage not found")
            return None
        found.append(Citation(entry_id=entry_id, entry_date=entry.get("date"),
                              text=original,
                              source_type=entry.get("source_type", "reflection")))
    return tuple(found)


def _verified_episodes(raw: list, entries: list[dict]) -> tuple[list[Episode], int]:
    """Keep only accounts whose every populated source passage is locatable."""
    by_id = {(e.get("source_type", "reflection"), e["id"]): e for e in entries}
    kept: list[Episode] = []
    omitted = 0
    for item in raw:
        if not isinstance(item, dict):
            omitted += 1
            logger.info("Episode refused: invalid account")
            continue
        actor = _clean(item.get("actor"))
        modality = _clean(item.get("modality"))
        if actor not in ACTORS or modality not in MODALITIES:
            omitted += 1
            logger.info("Episode refused: actor or modality not stated")
            continue

        fields = {part: _clean(item.get(part)) for part in (*PARTS, "explanation")}
        if not fields["situation"] or not fields["response"]:
            omitted += 1
            logger.info("Episode refused: no situation or no response")
            continue

        quotes = item.get("quotes")
        citations = _citations(quotes, by_id) if isinstance(quotes, list) else None
        if not citations:
            omitted += 1
            logger.info("Episode refused: its quotes could not be verified")
            continue

        # Resolve against the verified citations rather than the entire entry:
        # a passage in an uncited part of the source cannot support this account.
        resolved = {
            part: next((original for citation in citations
                        if (original := locate(citation.text, value)) is not None), None)
            if value else None
            for part, value in fields.items()
        }
        if any(fields[part] and resolved[part] is None for part in fields):
            omitted += 1
            logger.info("Episode refused: unsupported source passage")
            continue
        dates = [c.entry_date for c in citations if c.entry_date]
        kept.append(Episode(
            actor=actor, modality=modality,
            situation=resolved["situation"], response=resolved["response"],
            demand=resolved["demand"], information=resolved["information"],
            outcome=resolved["outcome"],
            domain=_clean(item.get("domain")),
            explanation=resolved["explanation"],
            citations=citations,
            # This is the recorded entry date, not an independently dated event.
            occurred_on=min(dates) if dates else None,
        ))
    return kept, omitted


def verified_episodes(raw: list, entries: list[dict]) -> list[Episode]:
    """Return supported accounts; omit valid-but-unusable account candidates."""
    return _verified_episodes(raw, entries)[0]


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
        self.omitted_accounts = 0

    def read(self, entries: list[dict], readable: dict | None = None) -> list[Episode]:
        """Every episode these entries support, in one pass per chunk.

        `readable` maps an entry's id to a punctuated copy of it, which is what
        the model is shown. Quotes still resolve against the owner's own text
        (`_citations`), so a reading copy can make an entry easier to parse and
        can never become the thing that gets cited.
        """
        self.omitted_accounts = 0
        if not entries:
            return []
        if self.intelligence is None:
            logger.error("Episode pass unavailable: no provider")
            raise ReadUnavailable("Episode pass unavailable: no provider")
        from .markdown_text import for_model
        prepared = []
        for entry in entries:
            if entry.get("content_format") == "markdown":
                prepared.append({
                    **entry,
                    "content": for_model(entry.get("content"), "markdown"),
                    "_original": entry.get("_original", entry.get("content")),
                })
            else:
                prepared.append(entry)
        entries = prepared
        found: list[Episode] = []
        if readable:
            entries = [{**e, "content": readable.get(str(e["id"]), e["content"]),
                        "_original": e.get("_original", e["content"])} for e in entries]
        chunks = chunk_entries(interleave(entries))
        for i, chunk in enumerate(chunks, 1):
            try:
                reply = self.intelligence.chat(
                    messages=[{"role": "user", "content": self.engine._render(chunk)}],
                    system_prompt=SYSTEM_PROMPT,
                    max_tokens=OBSERVATION_MAX_TOKENS,
                )
            except Exception as exc:
                logger.error("Episode pass unavailable: provider failure (chunk %s of %s)", i, len(chunks))
                raise ReadUnavailable("Episode pass unavailable: provider failure") from exc
            try:
                document = json.loads(_strip_fence(reply))
            except (ValueError, TypeError, AttributeError) as exc:
                logger.error("Episode pass unavailable: malformed JSON (chunk %s of %s)", i, len(chunks))
                raise ReadUnavailable("Episode pass unavailable: malformed JSON") from exc
            if not isinstance(document, dict) or not isinstance(document.get("episodes"), list):
                logger.error("Episode pass unavailable: invalid schema (chunk %s of %s)", i, len(chunks))
                raise ReadUnavailable("Episode pass unavailable: invalid schema")
            originals = [{**e, "content": e.get("_original", e["content"])} for e in chunk]
            valid, omitted = _verified_episodes(document["episodes"], originals)
            found.extend(valid)
            self.omitted_accounts += omitted
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
