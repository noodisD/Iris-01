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

- Every quote must also *support* the claim, not merely exist: a quote that
  contradicts it drops the finding, and one that only mentions the subject is
  not counted as evidence (`check_support`).

What a quick read (`read`) returns is not stored. What a discovery run
(`read_archive`) finds is stored as a proposal — a candidate the engines cannot
see, anchored in the owner's own sentences — and counted only once the owner
confirms it (ADR-0016).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date

from .constants import (
    OBSERVATION_CHARS_PER_TOKEN,
    OBSERVATION_CHUNK_TOKENS,
    OBSERVATION_HIGH_ENTRIES,
    OBSERVATION_HIGH_SPAN_DAYS,
    OBSERVATION_MAX_ENTRIES_READ,
    OBSERVATION_MAX_TOKENS,
    OBSERVATION_MEDIUM_ENTRIES,
    OBSERVATION_MIN_CITATIONS,
    OBSERVATION_MIN_ENTRIES_CITED,
    OBSERVATION_MIN_QUOTE_CHARS,
    OBSERVATION_MIN_STAGED_CHARS,
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

Each entry is labelled with an id and a source. Quote it back with both, exactly as given — two entries from different sources can share an id, so the source is what says which piece of writing you mean.

Return JSON only, in this exact shape:
{"observations": [{"claim": "...", "quotes": [{"entryId": 12, "sourceType": "reflection", "text": "exact words from that entry"}]}]}

If nothing recurs across entries, return {"observations": []}. An empty answer is a good answer."""


#: Which prompt produced a reading, derived from the prompt itself rather than
#: a number somebody has to remember to increment. It changes when the wording
#: changes, and cannot claim a version the text does not match.
PROMPT_VERSION = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:12]


def _normalized(text: str) -> str:
    """Whitespace is layout, not wording.

    A model reflowing a quoted line is not misquoting; changing a word is. This
    is the only difference tolerated between a quote and the stored entry.
    """
    return " ".join((text or "").split())


@dataclass(frozen=True)
class Citation:
    """A quote that was found, verbatim, in the entry it was attributed to.

    `source_type` is not decoration. Committed reflections and staged import
    items are separate tables with separate id sequences that overlap — on the
    real archive 15 staged ids also name a reflection — so an id alone does not
    identify a piece of writing. Verifying a quote against whichever row
    happened to share the number would let a fabricated citation pass by
    coincidence, which is the one failure this engine exists to prevent.
    """

    entry_id: int
    entry_date: date | None
    text: str
    source_type: str = "reflection"

    @property
    def key(self) -> tuple:
        return (self.source_type, self.entry_id)

    def as_dict(self) -> dict:
        return {
            "entryId": str(self.entry_id),
            "entryDate": self.entry_date.isoformat() if self.entry_date else None,
            "text": self.text,
            "sourceType": self.source_type,
            # A staged recording has no date, so it can be quoted but can never
            # become an occurrence: an occurrence needs a day it happened on.
            "citable": self.source_type == "reflection",
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
    #: The claims this was merged from, when a synthesis pass judged them the
    #: same finding. Empty for a finding that was never merged, so "one claim"
    #: and "several claims a model called equivalent" stay distinguishable.
    merged_from: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "engine": ENGINE_NAME,
            "claim": self.claim,
            "mergedFrom": list(self.merged_from),
            "citations": [c.as_dict() for c in self.citations],
            "spanStart": self.span_start.isoformat() if self.span_start else None,
            "spanEnd": self.span_end.isoformat() if self.span_end else None,
            "entriesRead": self.entries_read,
            "confidenceLevel": self.confidence_level,
        }


def _strip_fence(reply: str) -> str:
    """The JSON inside a model's answer, fenced or not."""
    text = (reply or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text).rsplit("```", 1)[0]
    return text


def _parse_reply(reply: str) -> list:
    """The model's answer, or nothing. A half-understood answer is nothing."""
    text = _strip_fence(reply)
    try:
        data = json.loads(text)
    except ValueError as e:
        logger.warning(f"Observation reply was not JSON, discarding: {e}")
        return []
    if isinstance(data, dict):
        data = data.get("observations") or []
    return data if isinstance(data, list) else []


def _tag(claim: str) -> str:
    """A short, stable handle for a claim, for logs.

    The claim itself is the owner's life read back to them. It was written to
    the log at INFO on every drop, so using the archive from the browser put
    claims about the owner into a file that outlives the run and is read by
    whoever reads logs. The tag is enough to follow one finding through a run
    and useless to anyone else.
    """
    return hashlib.sha256(_claim_key(claim).encode()).hexdigest()[:8]


def _span(citations) -> tuple:
    """The stretch of time a claim's own evidence covers.

    Every caller computes this from the citations that are actually behind the
    claim. `_verified` used to take the span of the whole reading pass instead,
    so four supporting entries from one September day, read alongside one
    unrelated entry from 2023, produced a finding "spanning" three years — and
    a span is half of what makes a finding high confidence.
    """
    dates = [c.entry_date for c in citations if getattr(c, "entry_date", None)]
    if not dates:
        return None, None, 0
    return min(dates), max(dates), (max(dates) - min(dates)).days


def _confidence(citations: tuple[Citation, ...], span_days: int) -> str:
    entries = {c.key for c in citations}
    if len(entries) >= OBSERVATION_HIGH_ENTRIES and span_days >= OBSERVATION_HIGH_SPAN_DAYS:
        return "high"
    if len(entries) >= OBSERVATION_MEDIUM_ENTRIES:
        return "medium"
    return "low"


SYNTHESIS_PROMPT = """You are given findings drawn from different parts of one person's journal.

Some may be the same finding, noticed separately and worded differently. Say which.

For each pair you believe describes the same thing, give a relationship:
- "equivalent" — the same finding, restated. Anyone who accepted one would accept the other.
- "narrower" / "broader" — one is a special case of the other. NOT the same finding.
- "contradictory" — they cannot both be true of the same person.
- "related" — connected in subject, but making different claims.

Only "equivalent" will be acted on. If you are unsure, say "related".

Return JSON only:
{"pairs": [{"a": 0, "b": 2, "relationship": "equivalent"}]}

An empty list is a good answer when nothing restates anything else."""


def synthesise(observations: list[Observation], intelligence) -> list[Observation]:
    """Merge findings that are the same finding in different words.

    Reading in passes means one pattern can be noticed several times over, and
    passes are disjoint — they share no citations — so citation overlap cannot
    reach across them. Wording can, but only carefully: opposite and nested
    claims share vocabulary freely, and a merge that swallowed a narrower claim
    into a broader one would put the narrower claim's evidence behind a
    statement it never supported.

    So this asks rather than assumes, and acts on one answer only. A surviving
    claim is always one of the originals, never a new sentence synthesised from
    them: a merged finding must be something the model already said and the
    citations already backed. What was merged is recorded on the result, so the
    owner sees it and it can be taken apart again.
    """
    if len(observations) < 2 or intelligence is None:
        return observations

    # Ordered by claim so the model sees the same list however the passes
    # finished, and so indices mean the same thing on a rerun.
    ordered = sorted(observations, key=lambda o: _claim_key(o.claim))
    listing = "\n".join(f"[{i}] {o.claim}" for i, o in enumerate(ordered))

    try:
        reply = intelligence.chat(
            messages=[{"role": "user", "content": listing}],
            system_prompt=SYNTHESIS_PROMPT,
            max_tokens=OBSERVATION_MAX_TOKENS,
        )
    except Exception as e:
        # Failing to merge leaves restatements standing, which is visible and
        # harmless. Failing open into a wrong merge would not be.
        logger.error(f"Synthesis pass failed, leaving findings unmerged: {e}")
        return observations

    try:
        pairs = json.loads(_strip_fence(reply)).get("pairs") or []
    except (ValueError, AttributeError) as e:
        logger.warning(f"Synthesis reply was not JSON, leaving findings unmerged: {e}")
        return observations

    parent = list(range(len(ordered)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    merged_any = False
    for pair in pairs:
        if not isinstance(pair, dict) or pair.get("relationship") != "equivalent":
            continue
        try:
            a, b = int(pair["a"]), int(pair["b"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= a < len(ordered) and 0 <= b < len(ordered)) or a == b:
            continue
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
            merged_any = True

    if not merged_any:
        return observations

    groups: dict[int, list[int]] = {}
    for i in range(len(ordered)):
        groups.setdefault(find(i), []).append(i)

    out: list[Observation] = []
    for members in groups.values():
        if len(members) == 1:
            out.append(ordered[members[0]])
            continue
        out.append(_pool([ordered[i] for i in members], merged=True))
    logger.info(f"Synthesis merged {len(ordered)} finding(s) into {len(out)}")
    return out


#: Why a finding read from the archive did not become a proposal, as recorded on
#: its run. `already_decided` and `not_embedded` are added by constructs.discover.
DROP_REASONS = ("merged_away", "unchecked", "incomplete", "denied", "too_few_supporting")

SUPPORT_PROMPT = """You are checking one claim about a person's journal against quotes from it.

The quotes are real: each was found word for word in the entry it came from. The
question is only what each one says about the claim.

For each quote, give one verdict:
- "supports" — the quote is an instance of what the claim describes.
- "denies" — the quote says the opposite, or says it did not happen.
- "mentions" — the quote touches the subject but is not an instance of the claim.

If you are unsure, say "mentions".

Return JSON only:
{"quotes": [{"i": 0, "verdict": "supports"}]}"""


def check_support(observations: list[Observation], intelligence,
                  tally: Counter | None = None) -> list[Observation]:
    """Keep a finding only if its quotes are instances of it.

    A quote found verbatim proves the words exist, not that they support the
    claim. Two authentic quotes that *deny* a behaviour passed every check
    here and came out as evidence for it — so nothing could be allowed to claim
    a behaviour, and confirming one was refused outright.

    So each finding is put to one narrow question about quotes already verified:
    does this one support the claim, deny it, or merely mention the subject? A
    single denial drops the finding. A quote that only mentions the subject is
    not evidence for it and is removed; what remains must still meet the same
    minimums as before. This is not a second reader grading the journal — it
    judges nothing except the relation between a sentence it is shown and a
    claim it is shown.

    It fails closed. A finding whose support could not be checked is dropped:
    unlike an unmerged restatement, an unchecked claim on screen is not harmless.

    `tally`, when given, counts every drop by reason, so a run that lost its
    findings to a model's broken replies can be told from an archive with
    nothing to say. Counts only; the claims stay in the log.
    """
    tally = tally if tally is not None else Counter()
    if intelligence is None:
        tally["unchecked"] += len(observations)
        return []
    kept: list[Observation] = []
    for obs in observations:
        listing = "\n".join(f"[{i}] {c.text}" for i, c in enumerate(obs.citations))
        try:
            reply = intelligence.chat(
                messages=[{"role": "user", "content": f"Claim: {obs.claim}\n\nQuotes:\n{listing}"}],
                system_prompt=SUPPORT_PROMPT,
                max_tokens=OBSERVATION_MAX_TOKENS,
            )
        except Exception as e:
            logger.warning(f"Support could not be checked, finding {_tag(obs.claim)} dropped ({e})")
            tally["unchecked"] += 1
            continue
        # Asked and answered badly is a different failure from never answered:
        # one is the provider, the other is the prompt or the model.
        try:
            verdicts = {int(v["i"]): str(v["verdict"])
                        for v in json.loads(_strip_fence(reply)).get("quotes") or []
                        if isinstance(v, dict)}
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.info(f"Support check reply unreadable, finding {_tag(obs.claim)} dropped ({e})")
            tally["incomplete"] += 1
            continue

        if len(verdicts) != len(obs.citations) or not all(
                verdicts.get(i) in ("supports", "denies", "mentions")
                for i in range(len(obs.citations))):
            logger.info(f"Support check answered incompletely, finding {_tag(obs.claim)} dropped")
            tally["incomplete"] += 1
            continue
        if any(v == "denies" for v in verdicts.values()):
            logger.info(f"A quote denies the claim, finding {_tag(obs.claim)} dropped")
            tally["denied"] += 1
            continue

        supporting = tuple(c for i, c in enumerate(obs.citations) if verdicts[i] == "supports")
        if (len(supporting) < OBSERVATION_MIN_CITATIONS
                or len({c.key for c in supporting}) < OBSERVATION_MIN_ENTRIES_CITED):
            logger.info(f"Too few quotes support the claim, finding {_tag(obs.claim)} dropped")
            tally["too_few_supporting"] += 1
            continue

        # The span belongs to the quotes that survived. Keeping the old one let
        # a claim report a reach its remaining evidence no longer had — and
        # span is half of what makes a finding high confidence.
        span_start, span_end, span_days = _span(supporting)
        kept.append(Observation(
            claim=obs.claim, citations=supporting, span_start=span_start,
            span_end=span_end, entries_read=obs.entries_read,
            confidence_level=_confidence(supporting, span_days), merged_from=obs.merged_from))
    return kept


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
                max_tokens=OBSERVATION_MAX_TOKENS,
            )
        except Exception as e:
            logger.error(f"Observation read failed for user {self.user_id}: {e}")
            return []

        return check_support(self._verified(_parse_reply(reply), entries), self.intelligence)

    def read_archive(self, include_staged: bool = True) -> tuple[list[Observation], int | None]:
        """Read everything, in passes, and record what the reading covered.

        This is the whole-archive path. `read()` remains the single-pass one
        that the endpoint uses for a quick look; this is what a full discovery
        run calls. Staged recordings are read but can never become occurrences,
        because an occurrence needs a day and they have none (ADR-0013).

        Returns the findings and the id of the run that produced them. The run
        is recorded because a read that found nothing and a read that half
        failed are indistinguishable from their output, and because the raw
        pre-merge observations are kept — so a change to consolidation can be
        tried against them instead of paying to read private writing again.
        """
        entries = list(db.get_entries_for_reading(self.user_id, limit=100_000))
        if include_staged:
            entries += db.get_staged_for_reading(self.user_id, OBSERVATION_MIN_STAGED_CHARS)
        if len(entries) < OBSERVATION_MIN_ENTRIES_CITED:
            logger.info(f"Not enough readable entries for user {self.user_id}: {len(entries)}")
            return [], None

        entries = interleave(entries)
        chunks = chunk_entries(entries)
        model = getattr(self.intelligence, "model", None) or "unknown"
        run_id = db.create_observation_run(
            user_id=self.user_id, model=model, prompt_version=PROMPT_VERSION,
            entries_read=len(entries), passes_planned=len(chunks))

        found: list[Observation] = []
        completed = 0
        failures: list[str] = []
        logger.info(f"Run {run_id}: reading {len(entries)} entries in {len(chunks)} pass(es)")
        for i, chunk in enumerate(chunks, 1):
            try:
                reply = self.intelligence.chat(
                    messages=[{"role": "user", "content": self._render(chunk)}],
                    system_prompt=SYSTEM_PROMPT,
                    max_tokens=OBSERVATION_MAX_TOKENS,
                )
            except Exception as e:
                # One failed pass is not a failed read. The rest still stands —
                # but the run says so, rather than letting a half-read archive
                # look like a complete one that found little.
                logger.error(f"Run {run_id}: pass {i} of {len(chunks)} failed: {e}")
                failures.append(f"pass {i}: {e}")
                continue
            # Verified against this chunk's entries only, so a quote cannot be
            # attributed to writing that was not in front of the model.
            found.extend(self._verified(_parse_reply(reply), chunk))
            completed += 1

        # Kept before anything is joined, so merging can be judged later without
        # another read.
        raw = [o.as_dict() for o in found]

        joined = synthesise(consolidate(found), self.intelligence)
        dropped: Counter = Counter(dict.fromkeys(DROP_REASONS, 0))
        dropped["merged_away"] = len(found) - len(joined)
        merged = check_support(joined, self.intelligence, tally=dropped)

        if completed == 0:
            status = "failed"
        elif completed < len(chunks):
            status = "partial"
        else:
            status = "complete"
        db.finish_observation_run(
            run_id=run_id, status=status, passes_completed=completed,
            raw_observations=raw, error="; ".join(failures) or None,
            dropped=dict(dropped))
        logger.info(
            f"Run {run_id}: {status}, {completed}/{len(chunks)} passes, "
            f"{len(found)} raw finding(s) -> {len(merged)} after merging and the "
            f"support check; dropped {dict(dropped)}")
        return merged, run_id

    # --- prompt ------------------------------------------------------------

    @staticmethod
    def _render(entries: list[dict]) -> str:
        """The entries, each labelled with what a quote must be attributed to.

        The source travels with the id because the two stores' ids overlap: on
        the real archive 15 staged items share a number with a reflection, so an
        id alone does not identify a piece of writing.
        """
        parts = ["Here are the entries, newest first.\n"]
        for e in entries:
            when = e["date"].isoformat() if e.get("date") else "undated"
            source = e.get("source_type", "reflection")
            parts.append(f"[entryId {e['id']} · sourceType {source} · {when}]\n{e['content']}\n")
        return "\n".join(parts)

    # --- verification ------------------------------------------------------

    def _verified(self, raw: list, entries: list[dict]) -> list[Observation]:
        by_id = {(e.get("source_type", "reflection"), e["id"]): e for e in entries}

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
                logger.info(f"Observation {_tag(claim)} discarded for causal or prescriptive wording")
                continue

            citations = self._citations(item.get("quotes") or [], by_id)
            if citations is None:
                logger.info(f"Observation {_tag(claim)} discarded, a citation failed verification")
                continue
            if len(citations) < OBSERVATION_MIN_CITATIONS:
                logger.info(f"Observation {_tag(claim)} discarded, {len(citations)} verified quote(s)")
                continue
            if len({c.key for c in citations}) < OBSERVATION_MIN_ENTRIES_CITED:
                logger.info(f"Observation {_tag(claim)} discarded, all quotes from one entry")
                continue

            span_start, span_end, span_days = _span(citations)
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
    def _citations(quotes: list, by_id: dict) -> tuple[Citation, ...] | None:
        """Every quote verified, or nothing.

        Returns None when any quote cannot be verified, which drops the whole
        observation. This used to skip bad quotes individually and keep the rest,
        so two real quotes plus one invented one produced an observation that
        looked fully verified — while the module promised the opposite, and while
        a surviving citation can seed an occurrence by construction.

        A model that fabricated one quote was not careful about the others. The
        expensive half of this pipeline is deciding what to believe, so the cheap
        answer to a bad citation is to disbelieve the claim carrying it.
        """
        found: list[Citation] = []
        for q in quotes:
            if not isinstance(q, dict):
                logger.info("Citation was not an object, observation refused")
                return None
            try:
                entry_id = int(q.get("entryId"))
            except (TypeError, ValueError):
                logger.info("Citation had no usable entry id, observation refused")
                return None
            source_type = str(q.get("sourceType") or "reflection")
            entry = by_id.get((source_type, entry_id))
            if entry is None:
                # Either invented, or attributed to something that was not read.
                logger.info(f"Citation names {source_type} {entry_id}, which was not read; refused")
                return None
            quote = _normalized(str(q.get("text") or ""))
            if len(quote) < OBSERVATION_MIN_QUOTE_CHARS:
                logger.info("Citation too short to identify a passage, observation refused")
                return None
            if quote not in _normalized(entry["content"]):
                logger.info(f"Quote not found verbatim in {source_type} {entry_id}, observation refused")
                return None
            found.append(Citation(entry_id=entry_id, entry_date=entry.get("date"),
                                  text=quote, source_type=entry.get("source_type", "reflection")))
        return tuple(found)


def interleave(entries: list[dict]) -> list[dict]:
    """The archive in reading order: dated entries as they were written, with
    undated ones spread evenly between them.

    Passes are cut from this order, so the order decides what can be seen
    together. It used to be the order the rows arrived in — reflections newest
    first, staged recordings appended at the end — which put every recording
    into the last passes and every journal entry into the others. A pattern
    that ran through both could not be noticed by any single pass, because no
    pass held both. Once undated recordings were committed as reflections they
    sorted to the *front* instead, with the same effect. An undated entry has no
    place in time, so it is given none: it is spread through the whole record,
    and every pass reads some of each.
    """
    dated = sorted((e for e in entries if e.get("date")),
                   key=lambda e: (e["date"], e.get("source_type", ""), e["id"]))
    undated = sorted((e for e in entries if not e.get("date")),
                     key=lambda e: (e.get("source_type", ""), e["id"]))
    if not dated or not undated:
        return dated + undated
    slots: dict[int, list[dict]] = {}
    for k, entry in enumerate(undated):
        slots.setdefault(round((k + 1) * len(dated) / (len(undated) + 1)), []).append(entry)
    ordered: list[dict] = []
    for i, entry in enumerate(dated):
        ordered.extend(slots.get(i, []))
        ordered.append(entry)
    ordered.extend(slots.get(len(dated), []))
    return ordered


def chunk_entries(entries: list[dict],
                  budget_tokens: int = OBSERVATION_CHUNK_TOKENS) -> list[list[dict]]:
    """Split the archive into passes small enough to be read closely.

    One pass over the whole archive produces generalities: the owner's is about
    110K tokens, and a model asked to find patterns across all of it at once
    answers about the average of a life rather than about what recurs in it.

    Chunks accumulate to a token budget rather than a fixed entry count because
    the months are wildly uneven — two of them hold 50 of 135 entries while four
    hold one each — so a fixed count would split the dense stretches and pad the
    sparse ones. An entry larger than the budget on its own still gets its own
    chunk rather than being dropped.
    """
    chunks: list[list[dict]] = []
    current: list[dict] = []
    size = 0
    for entry in entries:
        cost = max(1, len(entry.get("content") or "") // OBSERVATION_CHARS_PER_TOKEN)
        if current and size + cost > budget_tokens:
            chunks.append(current)
            current, size = [], 0
        current.append(entry)
        size += cost
    if current:
        chunks.append(current)
    return chunks


def _claim_key(claim: str) -> str:
    """A claim stripped to its wording, for recognising a literal restatement.

    Two passes describing one pattern in the same words are one finding, and
    saying so needs no judgement about meaning — only that the sentences match
    once case and punctuation are set aside. Anything less certain than that is
    left to `synthesise`, which asks rather than assumes.
    """
    return re.sub(r"[^a-z0-9 ]+", "", (claim or "").lower()).strip()


def consolidate(observations: list[Observation]) -> list[Observation]:
    """Merge a finding restated word for word, and nothing else.

    Reading in passes means one pattern can be noticed several times over, in
    slightly different words. Left alone that is exactly how the earlier system
    produced thirteen near-identical "breakthroughs" in two days — a screen full
    of restatement reading as a screen full of findings.

    This used to also merge findings that cited enough of the same entries
    (OBSERVATION_MERGE_OVERLAP, as a Jaccard ratio). Document overlap is not
    claim equivalence: "coffee appeared in the mornings" and "evening walks
    appeared after work" can quote different passages of the same two long
    entries, and the rule silently kept whichever sentence was longer and
    dropped the other — no record, no way back, and the support check later
    stripping the survivor's quotes could not bring the lost finding back.

    So citations no longer merge anything by themselves. Identical wording
    still does, because two identical sentences are the same sentence rather
    than a judgement about meaning; everything else is left to `synthesise`,
    which asks, acts only on "equivalent", and records what it merged.
    """
    # Connected components, not first-match-wins. The previous loop joined an
    # observation to the first group it happened to touch and stopped, so a
    # bridging observation did not unite the groups it connected: keys A={1,2},
    # B={2,3}, C={3,4} gave one group in the order A,B,C and two in the order
    # A,C,B. The partition depended on which pass finished first, which is not a
    # property of the writing.
    parent: dict[int, int] = {}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for i in range(len(observations)):
        parent[i] = i

    # Disjoint passes share no citations, so a finding noticed twice stayed two
    # findings however identically it was worded. Matching the wording is not a
    # semantic judgement: it is the same sentence.
    by_claim: dict[str, int] = {}
    for i, observation in enumerate(observations):
        claim_key = _claim_key(observation.claim)
        if claim_key:
            if claim_key in by_claim:
                union(i, by_claim[claim_key])
            else:
                by_claim[claim_key] = i

    groups: dict[int, list] = {}
    for i, observation in enumerate(observations):
        groups.setdefault(find(i), []).append(observation)
    merged = [{"observations": members} for members in groups.values()]

    return [_pool(group["observations"]) for group in merged]


def _pool(members: list[Observation], merged: bool = False) -> Observation:
    """One finding from several, keeping all of the evidence.

    The surviving claim is always one of the originals — the longest, which says
    most — and never a new sentence written to cover them. A merged finding has
    to be something that was actually said and actually cited; inventing a
    broader statement would put every member's evidence behind a claim none of
    them made.
    """
    if len(members) == 1:
        return members[0]

    best = max(members, key=lambda o: len(o.claim))
    citations: list[Citation] = []
    seen: set = set()
    for member in members:
        for citation in member.citations:
            if (citation.key, citation.text) in seen:
                continue
            seen.add((citation.key, citation.text))
            citations.append(citation)

    span_start, span_end, span_days = _span(citations)
    if span_start is None:
        span_start, span_end = best.span_start, best.span_end
    return Observation(
        claim=best.claim,
        citations=tuple(citations),
        span_start=span_start,
        span_end=span_end,
        # Distinct writing read, not the sum of each member's pass size. Two
        # observations from one five-entry pass reported ten entries read, which
        # overstated the evidence behind a merged claim.
        entries_read=max((m.entries_read for m in members), default=0),
        confidence_level=_confidence(tuple(citations), span_days),
        # What this was made from, so a merge is visible and can be undone. Only
        # recorded for the synthesis pass, where the judgement was a model's
        # rather than an identity of citations or of wording.
        merged_from=tuple(m.claim for m in members) if merged else (),
    )


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

    # The same two functions the gates call, not a third copy of them. Coverage,
    # conflict and ranking do not apply: an observation describes a span, and
    # it is reviewed and confirmed rather than ranked against other findings.
    from .pipeline_orchestrator import engine_enabled, meets_floor

    if not engine_enabled(ENGINE_NAME, prefs):
        return []
    return [o for o in observations if meets_floor(o.confidence_level, prefs)]
