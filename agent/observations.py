"""Reading the entries themselves.

Everything else IRIS knows is counted: how often a theme occurs, whether its
rate rose or fell, whether two themes appear on the same days. None of that can
notice the kind of thing the owner actually asked for — a habit of mind rather
than a topic — because that is not a frequency. It is
something a reader sees in the writing, and nothing here had ever read the
writing.

So this engine reads entries and reports what recurs across them. It is made
almost entirely of refusals, because a model reading someone's journal will
produce fluent, plausible, unfalsifiable statements about them unless it is
stopped:

- It runs only when asked. Nothing in the pipeline calls it, no background job
  reaches it, and the archive is never sent anywhere without the owner acting.
- It reads only what the owner deliberately logged, and only what still counts
  as evidence (ADR-0003). Chat is never read — conversation informs recall, not
  proof. Entries marked memory-only are never read and never quoted.
- Every claim it keeps is backed by quotes checked character for character
  against the stored entry. A quote the model invented, or attributed to the
  wrong entry, drops the whole observation. Nothing is repaired: a citation that
  needed fixing was not a citation.
- A claim resting on a single entry is an anecdote, and is dropped.
- Causal and prescriptive wording is dropped (agent/narrative_policy.py). The
  firewall's `raise` mode is for IRIS's own templates, where a forbidden word is
  a bug in code we wrote; a model producing one is expected, so the claim is
  discarded and the rest of the batch survives.
- Every observation carries the span of writing it was drawn from, and is
  phrased about that span. It never claims the present, so it never needs the
  coverage gate to tell it not to.

What comes back is not stored. An observation is something IRIS noticed while
reading, offered to the owner with its receipts — not a new fact about them
filed away to be counted later.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date

from .constants import (
    OBSERVATION_HIGH_ENTRIES,
    OBSERVATION_HIGH_SPAN_DAYS,
    OBSERVATION_MAX_ENTRIES_READ,
    OBSERVATION_MEDIUM_ENTRIES,
    OBSERVATION_MIN_CITATIONS,
    OBSERVATION_MIN_ENTRIES_CITED,
    OBSERVATION_MIN_QUOTE_CHARS,
)
from .database import db
from .intelligence import Intelligence
from .narrative_policy import FORBIDDEN_REGEX
from .preferences import UserPreferencesService

logger = logging.getLogger(__name__)

ENGINE_NAME = "observations"

SYSTEM_PROMPT = """You are reading a person's own journal entries and reporting what recurs across them.

Report only what is visible in the entries themselves. You have no other information about this person.

Each observation must:
- describe something that appears in at least two different entries;
- quote the entries word for word, copying the text exactly as it appears, including its spelling;
- be phrased as description of what the entries show, not as advice, diagnosis, or a claim about what one thing did to another;
- avoid these words entirely: cause, should, recommend, means, implies, indicates, suggests, fix, improve, solve, help, trigger, led to, results in, because, due to.

Write about the period the entries cover, in the past tense. Do not describe how the person is now.

Return JSON only, in this exact shape:
{"observations": [{"claim": "...", "quotes": [{"entryId": 12, "text": "exact words from that entry"}]}]}

If nothing recurs across entries, return {"observations": []}. An empty answer is a good answer."""


def _normalized(text: str) -> str:
    """Whitespace is layout, not wording.

    A model reflowing a quoted line is not misquoting; changing a word is. This
    is the only difference tolerated between a quote and the stored entry.
    """
    return " ".join((text or "").split())


@dataclass(frozen=True)
class Citation:
    """A quote that was found, verbatim, in the entry it was attributed to."""

    entry_id: int
    entry_date: date | None
    text: str

    def as_dict(self) -> dict:
        return {
            "entryId": str(self.entry_id),
            "entryDate": self.entry_date.isoformat() if self.entry_date else None,
            "text": self.text,
        }


@dataclass(frozen=True)
class Observation:
    """Something that recurred, with the writing it was read from."""

    claim: str
    citations: tuple[Citation, ...]
    span_start: date | None
    span_end: date | None
    entries_read: int
    confidence_level: str

    def as_dict(self) -> dict:
        return {
            "engine": ENGINE_NAME,
            "claim": self.claim,
            "citations": [c.as_dict() for c in self.citations],
            "spanStart": self.span_start.isoformat() if self.span_start else None,
            "spanEnd": self.span_end.isoformat() if self.span_end else None,
            "entriesRead": self.entries_read,
            "confidenceLevel": self.confidence_level,
        }


def _parse_reply(reply: str) -> list:
    """The model's answer, or nothing. A half-understood answer is nothing."""
    text = (reply or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text).rsplit("```", 1)[0]
    try:
        data = json.loads(text)
    except ValueError as e:
        logger.warning(f"Observation reply was not JSON, discarding: {e}")
        return []
    if isinstance(data, dict):
        data = data.get("observations") or []
    return data if isinstance(data, list) else []


def _confidence(citations: tuple[Citation, ...], span_days: int) -> str:
    entries = {c.entry_id for c in citations}
    if len(entries) >= OBSERVATION_HIGH_ENTRIES and span_days >= OBSERVATION_HIGH_SPAN_DAYS:
        return "high"
    if len(entries) >= OBSERVATION_MEDIUM_ENTRIES:
        return "medium"
    return "low"


class ObservationEngine:
    """Reads entries on request and reports what it can prove it read."""

    def __init__(self, user_id: int, intelligence=None):
        self.user_id = user_id
        # Injected in tests. Built lazily otherwise, so importing this module
        # never requires an API key and never constructs a client.
        self._intelligence = intelligence

    @property
    def intelligence(self):
        if self._intelligence is None:
            self._intelligence = Intelligence()
        return self._intelligence

    def read(self, limit: int = OBSERVATION_MAX_ENTRIES_READ, since=None) -> list[Observation]:
        """Read the owner's entries and return what survives verification."""
        entries = db.get_entries_for_reading(self.user_id, limit=limit, since=since)
        if len(entries) < OBSERVATION_MIN_ENTRIES_CITED:
            logger.info(f"Not enough readable entries for user {self.user_id}: {len(entries)}")
            return []

        try:
            reply = self.intelligence.chat(
                messages=[{"role": "user", "content": self._render(entries)}],
                system_prompt=SYSTEM_PROMPT,
                max_tokens=1500,
            )
        except Exception as e:
            logger.error(f"Observation read failed for user {self.user_id}: {e}")
            return []

        return self._verified(_parse_reply(reply), entries)

    # --- prompt ------------------------------------------------------------

    @staticmethod
    def _render(entries: list[dict]) -> str:
        """The entries, each labelled with the id a quote must be attributed to."""
        parts = ["Here are the entries, newest first.\n"]
        for e in entries:
            when = e["date"].isoformat() if e.get("date") else "undated"
            parts.append(f"[entryId {e['id']} · {when}]\n{e['content']}\n")
        return "\n".join(parts)

    # --- verification ------------------------------------------------------

    def _verified(self, raw: list, entries: list[dict]) -> list[Observation]:
        by_id = {e["id"]: e for e in entries}
        dates = [e["date"] for e in entries if e.get("date")]
        span_start, span_end = (min(dates), max(dates)) if dates else (None, None)
        span_days = (span_end - span_start).days if span_start and span_end else 0

        out: list[Observation] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            claim = str(item.get("claim") or "").strip()
            if not claim:
                continue

            if FORBIDDEN_REGEX.search(claim):
                # Not a system error — a model saying "because" is ordinary. The
                # claim goes, the batch stays.
                logger.info(f"Observation discarded for causal or prescriptive wording: {claim[:60]}")
                continue

            citations = self._citations(item.get("quotes") or [], by_id)
            if len(citations) < OBSERVATION_MIN_CITATIONS:
                logger.info(f"Observation discarded, {len(citations)} verified quote(s): {claim[:60]}")
                continue
            if len({c.entry_id for c in citations}) < OBSERVATION_MIN_ENTRIES_CITED:
                logger.info(f"Observation discarded, all quotes from one entry: {claim[:60]}")
                continue

            out.append(Observation(
                claim=claim,
                citations=citations,
                span_start=span_start,
                span_end=span_end,
                entries_read=len(entries),
                confidence_level=_confidence(citations, span_days),
            ))
        return out

    @staticmethod
    def _citations(quotes: list, by_id: dict) -> tuple[Citation, ...]:
        found: list[Citation] = []
        for q in quotes:
            if not isinstance(q, dict):
                continue
            try:
                entry_id = int(q.get("entryId"))
            except (TypeError, ValueError):
                continue
            entry = by_id.get(entry_id)
            if entry is None:
                # Either invented, or attributed to an entry that was not read.
                continue
            quote = _normalized(str(q.get("text") or ""))
            if len(quote) < OBSERVATION_MIN_QUOTE_CHARS:
                continue
            if quote not in _normalized(entry["content"]):
                logger.info(f"Quote not found verbatim in entry {entry_id}, refused")
                continue
            found.append(Citation(entry_id=entry_id, entry_date=entry.get("date"), text=quote))
        return tuple(found)


def apply_preferences(observations: list[Observation], user_id: int) -> list[Observation]:
    """The same admission policy every other finding passes through (ADR-0007).

    A new surface does not get its own thresholds: if the owner set their
    confidence floor to high, that governs here too.
    """
    try:
        prefs = UserPreferencesService(user_id).get_prefs()
    except Exception as e:
        logger.error(f"Preferences unavailable for user {user_id}, withholding: {e}")
        return []

    enabled = prefs.get("enabled_engines")
    if enabled is not None and ENGINE_NAME not in enabled:
        return []

    levels = {"low": 0, "medium": 1, "high": 2}
    minimum = levels.get(prefs.get("min_confidence", "medium"), 1)
    return [o for o in observations if levels.get(o.confidence_level, 0) >= minimum]
