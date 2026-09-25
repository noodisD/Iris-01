"""Owner-triggered reading, review, and critique of intellectual positions."""

from __future__ import annotations

import json
import logging
from typing import Any

from agent.config import settings
from agent import intelligence
from agent.intelligence import Intelligence
from agent.database import db
from agent.observations import chunk_entries, interleave

from . import reader, store
from .models import (
    IDEA_DOMAINS,
    IDEA_POSITIONS,
    IDEA_REFERENCE_BATCH_SIZE,
    content_hash,
    quote_hash,
    empty_dropped,
    idea_citation,
    idea_critique,
    idea_link,
    idea_run,
    idea_summary,
    statement_key,
)
from .reader import (
    CRITIQUE_PROMPT_VERSION,
    DISCOVERY_PROMPT_VERSION,
    IDEA_MEANING_PROMPT,
    LINK_PROMPT_VERSION,
    MEANING_PROMPT_VERSION,
    ReplyError,
)

logger = logging.getLogger(__name__)

#: Ideas compared in one call. Pairs are only found within a call, so this is
#: kept well above the size of the owner's framework rather than small.
MEANING_BATCH_SIZE = 150

IDEA_NOT_FOUND = "Idea not found"
IDEA_CONFLICT = "This idea or its sources changed. Reload before deciding."
LINK_NOT_FOUND = "Idea link not found"
LINK_CONFLICT = "This link or its ideas changed. Reload before deciding."
ANALYSIS_FAILED = "Ideas analysis could not finish. Review the last run."
CRITIQUE_FAILED = "Iris could not produce a critique. No critique was saved."


class IdeaNotFound(Exception):
    pass


class IdeaConflict(Exception):
    pass


class IdeaUnavailable(Exception):
    pass


class _Tally:
    def __init__(self) -> None:
        self.dropped = empty_dropped()
        self.passes_completed = 0
        self.proposed = 0
        self.stage_failed = False
        self.error: str | None = None

    def bump(self, key: str, count: int = 1) -> None:
        self.dropped[key] = self.dropped.get(key, 0) + count

    def fail(self, kind: str) -> None:
        self.stage_failed = True
        if kind == "model_failed":
            self.error = "model_failed"
        elif self.error is None:
            self.error = "malformed"


def _status(tally: _Tally, passes_planned: int) -> str:
    if passes_planned and tally.passes_completed == 0:
        return "failed"
    if tally.stage_failed:
        return "partial"
    return "complete"


def _batches(rows: list[dict[str, Any]], size: int = IDEA_REFERENCE_BATCH_SIZE) -> list[list[dict[str, Any]]]:
    return [rows[index:index + size] for index in range(0, len(rows), size)]


def _citation_sort(row: dict[str, Any]) -> tuple[int, Any, int, int]:
    undated = row.get("entry_date") is None
    return (1 if undated else 0, row.get("entry_date") or "", int(row["reflection_id"]), int(row["id"]))


def _link_sort(row: dict[str, Any]) -> tuple[int, int, str, int]:
    return (int(row["from_idea_id"]), int(row["to_idea_id"]), row["kind"], int(row["id"]))


def _idea_sort(row: dict[str, Any]) -> tuple[str, str, int]:
    return (row["domain"], row["statement"].casefold(), int(row["id"]))


class IdeaService:
    def __init__(self, user_id: int, intelligence: Any | None = None) -> None:
        self.user_id = user_id
        self.intelligence = intelligence

    def _client(self) -> Any:
        if self.intelligence is None:
            try:
                self.intelligence = Intelligence()
            except Exception:
                logger.error("idea model client unavailable")
                raise ReplyError("model_failed") from None
        return self.intelligence

    def discover(self) -> dict[str, Any]:
        entries = db.get_entries_for_reading(self.user_id, limit=None)
        model = settings.OPENAI_MODEL
        if not entries:
            run_id = store.start_run(
                self.user_id, "discovery", model, DISCOVERY_PROMPT_VERSION, 0, 0,
            )
            store.finish_run(
                run_id, self.user_id, status="complete", passes_completed=0,
                proposed=0, dropped=empty_dropped(), error=None,
            )
            return {"run": idea_run(store.get_run(run_id, self.user_id))}

        chunks = chunk_entries(interleave(entries))
        run_id = store.start_run(
            self.user_id, "discovery", model, DISCOVERY_PROMPT_VERSION,
            len(entries), len(chunks),
        )
        tally = _Tally()
        try:
            client = self._client()
            registry = store.list_registry(self.user_id)
            for chunk in chunks:
                by_id = {("reflection", entry["id"]): entry for entry in chunk}
                try:
                    drafts, malformed = reader.extract_ideas(client, chunk)
                except ReplyError as exc:
                    tally.fail(exc.kind)
                    if exc.kind == "malformed":
                        tally.bump("malformed")
                    continue
                tally.passes_completed += 1
                tally.bump("malformed", malformed)
                for draft in drafts:
                    self._stage_draft(draft, by_id, client, run_id, tally, registry)
        except Exception:
            logger.error("idea discovery failed for user %s run %s", self.user_id, run_id)
            tally.fail("model_failed")
        finally:
            status = _status(tally, len(chunks))
            store.finish_run(
                run_id, self.user_id, status=status, passes_completed=tally.passes_completed,
                proposed=tally.proposed, dropped=tally.dropped,
                error=tally.error if status != "complete" else None,
            )
        return {"run": idea_run(store.get_run(run_id, self.user_id))}

    def _stage_draft(
        self,
        draft: Any,
        by_id: dict[tuple[str, int], dict[str, Any]],
        client: Any,
        run_id: int,
        tally: _Tally,
        registry: list[dict[str, Any]],
    ) -> None:
        verified = reader.verify_draft(draft.quotes, by_id)
        if not verified:
            tally.bump("invalid_quote")
            return
        try:
            stances = reader.check_stances(client, draft.statement, verified, by_id)
        except ReplyError as exc:
            tally.bump("unchecked")
            tally.fail(exc.kind)
            return
        kept = []
        for citation, stance in zip(verified, stances, strict=True):
            if stance == "not_stated":
                tally.bump("not_stated")
                continue
            kept.append((citation, stance))
        if not kept:
            return
        matched = self._match(draft.statement, client, tally, registry)
        if matched == "unchecked":
            return
        if matched == "rejected":
            tally.bump("already_decided")
            return
        citations = [
            {
                "reflection_id": citation.entry_id,
                "quote": citation.text,
                "quote_hash": quote_hash(citation.text),
                "source_hash": content_hash(by_id[(citation.source_type, citation.entry_id)]["content"]),
                "stance": stance,
            }
            for citation, stance in kept
        ]
        outcome = store.stage_citations(
            self.user_id, run_id, statement=draft.statement, domain=draft.domain,
            citations=citations, matched_id=None if matched is None else int(matched),
        )
        tally.proposed += outcome["created"]
        for key in ("already_decided", "duplicate", "source_changed"):
            tally.bump(key, outcome[key])
        if matched is None and outcome["source_changed"] == 0 and outcome["already_decided"] == 0:
            registry[:] = store.list_registry(self.user_id)

    def _match(
        self,
        statement: str,
        client: Any,
        tally: _Tally,
        registry: list[dict[str, Any]],
    ) -> int | str | None:
        key = statement_key(statement)
        exact = [row for row in registry if row["statement_key"] == key]
        if exact:
            row = min(exact, key=lambda item: int(item["id"]))
            return "rejected" if row["status"] == "rejected" else int(row["id"])
        found: list[int] = []
        for batch in _batches(sorted(registry, key=lambda row: int(row["id"]))):
            try:
                match = reader.match_idea(client, statement, batch)
            except ReplyError as exc:
                tally.bump("unchecked")
                tally.fail(exc.kind)
                return "unchecked"
            if match is not None:
                found.append(match)
        if not found:
            return None
        chosen = min(found)
        row = next(item for item in registry if int(item["id"]) == chosen)
        return "rejected" if row["status"] == "rejected" else chosen

    def discover_links(self, idea_id: int) -> dict[str, Any]:
        graph = store.load_graph(self.user_id)
        subject = graph["by_id"].get(idea_id)
        if subject is None or subject["status"] == "rejected":
            raise IdeaNotFound
        if not subject["anchored"]:
            raise IdeaConflict
        neighbours = [
            idea for idea in graph["ideas"]
            if idea["anchored"] and int(idea["id"]) != idea_id
        ]
        neighbours.sort(key=lambda row: int(row["id"]))
        batches = _batches(neighbours)
        run_id = store.start_run(
            self.user_id, "links", settings.OPENAI_MODEL, LINK_PROMPT_VERSION,
            len(neighbours), len(batches),
        )
        tally = _Tally()
        try:
            if batches:
                client = self._client()
                for batch in batches:
                    try:
                        proposals, malformed = reader.propose_links(client, subject, batch)
                    except ReplyError as exc:
                        tally.fail(exc.kind)
                        if exc.kind == "malformed":
                            tally.bump("malformed")
                        continue
                    tally.passes_completed += 1
                    tally.bump("malformed", malformed)
                    outcome = store.stage_links(
                        self.user_id, run_id, idea_id,
                        [
                            {
                                "from_idea_id": link.fromIdeaId,
                                "to_idea_id": link.toIdeaId,
                                "kind": link.kind,
                                "rationale": link.rationale,
                            }
                            for link in proposals
                        ],
                    )
                    tally.proposed += outcome["created"]
                    for key in ("already_decided", "duplicate", "source_changed", "malformed"):
                        tally.bump(key, outcome[key])
        except Exception:
            logger.error("idea link discovery failed for user %s idea %s", self.user_id, idea_id)
            tally.fail("model_failed")
        finally:
            status = _status(tally, len(batches))
            store.finish_run(
                run_id, self.user_id, status=status, passes_completed=tally.passes_completed,
                proposed=tally.proposed, dropped=tally.dropped,
                error=tally.error if status != "complete" else None,
            )
        return {"run": idea_run(store.get_run(run_id, self.user_id))}

    def _meaning_batches(self) -> list[list[dict[str, Any]]]:
        graph = store.load_graph(self.user_id)
        ideas = sorted((idea for idea in graph["ideas"]
                        if idea["status"] == "active" and idea["anchored"]), key=lambda row: int(row["id"]))
        return _batches(ideas, MEANING_BATCH_SIZE) if len(ideas) >= 2 else []

    def meaning_estimate(self) -> dict[str, Any]:
        """What a same-meaning pass would send and cost, before anything is sent.

        Only the accepted idea statements are sent, never journal text.
        """
        batches = self._meaning_batches()
        ideas = sum(len(batch) for batch in batches)
        characters = sum(len(row["statement"]) for batch in batches for row in batch)
        # About four characters a token, plus the instructions once per call and
        # a reply budget of a few pairs per call.
        tokens_in = characters // 4 + len(batches) * (len(IDEA_MEANING_PROMPT) // 4 + 50)
        tokens_out = len(batches) * 800
        return {"ideas": ideas, "calls": len(batches), "tokensIn": tokens_in,
                # The price table, not a client: an estimate never makes one.
                "estimate": intelligence.Intelligence.estimate(settings.OPENAI_MODEL, tokens_in, tokens_out)}

    def discover_meanings(self) -> dict[str, Any]:
        """Propose pairs of accepted ideas that share one essential meaning.

        Owner-triggered. Proposals are candidates for the owner to accept or
        dismiss in Review; nothing is linked by this alone.
        """
        batches = self._meaning_batches()
        run_id = store.start_run(
            self.user_id, "meaning", settings.OPENAI_MODEL, MEANING_PROMPT_VERSION,
            sum(len(batch) for batch in batches), len(batches),
        )
        tally = _Tally()
        try:
            if batches:
                client = self._client()
                for batch in batches:
                    try:
                        pairs, malformed = reader.propose_same_meaning(client, batch)
                    except ReplyError as exc:
                        tally.fail(exc.kind)
                        if exc.kind == "malformed":
                            tally.bump("malformed")
                        continue
                    tally.passes_completed += 1
                    tally.bump("malformed", malformed)
                    outcome = store.stage_links(
                        self.user_id, run_id, None,
                        [{"from_idea_id": pair.a, "to_idea_id": pair.b, "kind": "same_meaning",
                          "rationale": pair.rationale} for pair in pairs],
                    )
                    tally.proposed += outcome["created"]
                    for key in ("already_decided", "duplicate", "source_changed", "malformed"):
                        tally.bump(key, outcome[key])
        except Exception:
            logger.error("same-meaning discovery failed for user %s", self.user_id)
            tally.fail("model_failed")
        finally:
            status = _status(tally, len(batches))
            store.finish_run(
                run_id, self.user_id, status=status, passes_completed=tally.passes_completed,
                proposed=tally.proposed, dropped=tally.dropped,
                error=tally.error if status != "complete" else None,
            )
        return {"run": idea_run(store.get_run(run_id, self.user_id))}

    def confirm(self, idea_id: int, citation_ids: list[int], position: str, domain: str) -> dict[str, str]:
        if position not in IDEA_POSITIONS or domain not in IDEA_DOMAINS:
            raise IdeaConflict
        outcome = store.confirm_idea(self.user_id, idea_id, citation_ids, position, domain)
        if outcome == "missing":
            raise IdeaNotFound
        if outcome != "ok":
            raise IdeaConflict
        return {"id": str(idea_id), "status": "active"}

    def reject(self, idea_id: int) -> dict[str, str]:
        outcome = store.reject_idea(self.user_id, idea_id)
        if outcome == "missing":
            raise IdeaNotFound
        if outcome != "ok":
            raise IdeaConflict
        return {"id": str(idea_id), "status": "rejected"}

    def reject_citations(self, idea_id: int, citation_ids: list[int]) -> dict[str, Any]:
        outcome = store.reject_citations(self.user_id, idea_id, citation_ids)
        if outcome == "missing":
            raise IdeaNotFound
        if outcome == "conflict":
            raise IdeaConflict
        return {"id": str(idea_id), "rejected": int(outcome)}

    def update(
        self,
        idea_id: int,
        *,
        position: str | None = None,
        domain: str | None = None,
    ) -> dict[str, Any]:
        if position is not None and position not in IDEA_POSITIONS:
            raise IdeaConflict
        if domain is not None and domain not in IDEA_DOMAINS:
            raise IdeaConflict
        outcome = store.update_idea(self.user_id, idea_id, position=position, domain=domain)
        if outcome == "missing":
            raise IdeaNotFound
        if outcome != "ok":
            raise IdeaConflict
        return self._summary(idea_id)

    def confirm_link(self, link_id: int) -> dict[str, str]:
        outcome = store.decide_link(self.user_id, link_id, "accepted")
        if outcome == "missing":
            raise IdeaNotFound
        if outcome != "ok":
            raise IdeaConflict
        return {"id": str(link_id), "status": "accepted"}

    def reject_link(self, link_id: int) -> dict[str, str]:
        outcome = store.decide_link(self.user_id, link_id, "rejected")
        if outcome == "missing":
            raise IdeaNotFound
        if outcome != "ok":
            raise IdeaConflict
        return {"id": str(link_id), "status": "rejected"}

    def critique(self, idea_id: int) -> dict[str, Any]:
        basis = self._basis(idea_id)
        if basis is None:
            graph = store.load_graph(self.user_id)
            if idea_id not in graph["by_id"] or graph["by_id"][idea_id]["status"] == "rejected":
                raise IdeaNotFound
            raise IdeaConflict
        digest = _basis_hash(basis)
        try:
            client = self._client()
            content = reader.critique(client, basis)
        except ReplyError:
            raise IdeaUnavailable from None
        current = self._basis(idea_id)
        if current is None or _basis_hash(current) != digest:
            raise IdeaConflict
        row = store.insert_critique(
            self.user_id, idea_id,
            model=getattr(client, "model", None) or settings.OPENAI_MODEL,
            prompt_version=CRITIQUE_PROMPT_VERSION,
            input_hash=digest,
            basis=basis,
            content=content,
        )
        return {"critique": idea_critique(row, is_current=True)}

    def framework(self) -> dict[str, Any]:
        graph = store.load_graph(self.user_id)
        ideas = [idea for idea in graph["ideas"] if idea["status"] == "active"]
        ideas.sort(key=_idea_sort)
        anchored = {int(idea["id"]) for idea in ideas if idea["anchored"]}
        links = [
            link for link in graph["links"]
            if link["status"] == "accepted"
            and int(link["from_idea_id"]) in anchored
            and int(link["to_idea_id"]) in anchored
        ]
        links.sort(key=_link_sort)
        by_id = {int(idea["id"]): idea for idea in ideas}
        tensions = sorted(
            int(link["id"]) for link in links
            if link["kind"] == "contradicts"
            and by_id[int(link["from_idea_id"])]["position"] == "endorsed"
            and by_id[int(link["to_idea_id"])]["position"] == "endorsed"
        )
        foundations = sorted({
            int(link["to_idea_id"]) for link in links if link["kind"] == "depends_on"
        })
        connected = {
            int(link["from_idea_id"]) for link in links
        } | {int(link["to_idea_id"]) for link in links}
        unconnected = sorted(anchored - connected)
        return {
            "ideas": [idea_summary(idea) for idea in ideas],
            "links": [idea_link(link) for link in links],
            "tensionIds": [str(item) for item in tensions],
            "foundationIds": [str(item) for item in foundations],
            "unconnectedIds": [str(item) for item in unconnected],
            "lastRun": idea_run(store.latest_run(self.user_id)),
        }

    def review(self) -> dict[str, Any]:
        graph = store.load_graph(self.user_id)
        cards = []
        for idea in sorted(graph["ideas"], key=_idea_sort):
            pending = _visible_citations(graph["citations"], idea, pending_only=True)
            if idea["status"] == "candidate" or (idea["status"] == "active" and pending):
                cards.append({
                    "idea": idea_summary(idea),
                    "citations": [idea_citation(row) for row in pending],
                })
        anchored = {int(idea["id"]) for idea in graph["ideas"] if idea["anchored"]}
        links = [
            link for link in graph["links"]
            if link["status"] == "candidate"
            and int(link["from_idea_id"]) in anchored
            and int(link["to_idea_id"]) in anchored
        ]
        links.sort(key=_link_sort)
        return {
            "ideas": cards,
            "links": [idea_link(link) for link in links],
            "lastRun": idea_run(store.latest_run(self.user_id)),
        }

    def detail(self, idea_id: int) -> dict[str, Any]:
        graph = store.load_graph(self.user_id)
        idea = graph["by_id"].get(idea_id)
        if idea is None or idea["status"] == "rejected":
            raise IdeaNotFound
        citations = _visible_citations(graph["citations"], idea, pending_only=False)
        anchored = {int(row["id"]) for row in graph["ideas"] if row["anchored"]}
        links = [
            link for link in graph["links"]
            if link["status"] in ("accepted", "candidate")
            and int(link["from_idea_id"]) in anchored
            and int(link["to_idea_id"]) in anchored
            and idea_id in (int(link["from_idea_id"]), int(link["to_idea_id"]))
        ]
        links.sort(key=_link_sort)
        current = _basis_hash(self._basis(idea_id) or {})
        critiques = [
            idea_critique(
                row,
                is_current=idea["anchored"] and str(row["input_hash"]).strip() == current,
            )
            for row in graph["critiques"]
            if int(row["idea_id"]) == idea_id
        ]
        return {
            "idea": idea_summary(idea),
            "citations": [idea_citation(row) for row in citations],
            "links": [idea_link(link) for link in links],
            "critiques": critiques,
        }

    def _summary(self, idea_id: int) -> dict[str, Any]:
        graph = store.load_graph(self.user_id)
        idea = graph["by_id"].get(idea_id)
        if idea is None:
            raise IdeaNotFound
        return idea_summary(idea)

    def _basis(self, idea_id: int) -> dict[str, Any] | None:
        graph = store.load_graph(self.user_id)
        idea = graph["by_id"].get(idea_id)
        if idea is None or not idea["anchored"]:
            return None
        neighbours = []
        for link in graph["links"]:
            if link["status"] != "accepted":
                continue
            ends = {int(link["from_idea_id"]), int(link["to_idea_id"])}
            if idea_id not in ends:
                continue
            other_id = (ends - {idea_id}).pop()
            other = graph["by_id"].get(other_id)
            if other is None or not other["anchored"]:
                continue
            if link["kind"] == "contradicts":
                direction = "symmetric"
            elif int(link["from_idea_id"]) == idea_id:
                direction = "outgoing"
            else:
                direction = "incoming"
            neighbours.append({
                "id": str(other_id),
                "statement": other["statement"],
                "position": other["position"],
                "kind": link["kind"],
                "direction": direction,
            })
        neighbours.sort(key=lambda row: (int(row["id"]), row["kind"], row["direction"]))
        return {
            "idea": {
                "id": str(idea_id),
                "statement": idea["statement"],
                "position": idea["position"],
                "domain": idea["domain"],
            },
            "neighbours": neighbours,
        }


def _basis_hash(basis: dict[str, Any]) -> str:
    payload = json.dumps(basis, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return content_hash(payload)


def _visible_citations(
    citations: list[dict[str, Any]],
    idea: dict[str, Any],
    *,
    pending_only: bool,
) -> list[dict[str, Any]]:
    wanted = {"candidate"} if pending_only else {"accepted", "candidate"}
    rows = [
        row for row in citations
        if row["idea_id"] == idea["id"] and row["valid"] and row["status"] in wanted
    ]
    rows.sort(key=_citation_sort)
    return rows

