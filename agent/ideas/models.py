"""Domain values and wire shapes for the owner's idea framework.

An idea is a proposition, not a measured theme. These names are the contract
shared by SQL checks, request validation, and the web client.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Any

from agent.observations import _normalized

IDEA_STATUSES = ("candidate", "active", "rejected")
IDEA_POSITIONS = ("exploring", "endorsed", "opposed")
CITATION_STANCES = ("endorsed", "questioned", "opposed")
STANCE_ANSWERS = (*CITATION_STANCES, "not_stated")
IDEA_DOMAINS = ("philosophy", "economics", "trading", "politics", "ethics", "other")
LINK_KINDS = ("supports", "contradicts", "refines", "depends_on")
REVIEW_STATUSES = ("candidate", "accepted", "rejected")
RUN_KINDS = ("discovery", "links")
RUN_STATUSES = ("running", "complete", "partial", "failed")
DROP_KEYS = (
    "invalid_quote",
    "not_stated",
    "unchecked",
    "malformed",
    "already_decided",
    "duplicate",
    "source_changed",
)
STATEMENT_LIMIT = 600
RATIONALE_LIMIT = 1200
NAME_LIMIT = 120
CRITIQUE_TEXT_LIMIT = 1200
IDEA_REFERENCE_BATCH_SIZE = 24


def statement_key(statement: str) -> str:
    """Identity of a proposition's wording, not of its display casing."""
    return hashlib.sha256(_normalized(statement).casefold().encode("utf-8")).hexdigest()


def content_hash(text: str) -> str:
    """SHA-256 hex of the original UTF-8 bytes. Whitespace is part of a source."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def quote_hash(quote: str) -> str:
    """Identity of a normalized quotation."""
    return content_hash(_normalized(quote))


def empty_dropped() -> dict[str, int]:
    return dict.fromkeys(DROP_KEYS, 0)


def dropped_counts(raw: dict[str, Any] | None) -> dict[str, int]:
    body = raw or {}
    return {key: int(body.get(key) or 0) for key in DROP_KEYS}


def _iso_date(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def _iso_time(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def idea_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "statement": row["statement"],
        "domain": row["domain"],
        "status": row["status"],
        "position": row["position"],
        "citationCount": int(row["citation_count"]),
        "pendingCitationCount": int(row["pending_citation_count"]),
        "firstWrittenOn": _iso_date(row.get("first_written_on")),
        "lastWrittenOn": _iso_date(row.get("last_written_on")),
        "undatedCount": int(row["undated_count"]),
        "needsEvidence": bool(row["needs_evidence"]),
    }


def idea_citation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "entryId": str(row["reflection_id"]),
        "entryDate": _iso_date(row.get("entry_date")),
        "text": row["quote"],
        "stance": row["stance"],
        "status": row["status"],
    }


def idea_link(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "fromIdeaId": str(row["from_idea_id"]),
        "toIdeaId": str(row["to_idea_id"]),
        "kind": row["kind"],
        "rationale": row["rationale"],
        "status": row["status"],
        "fromStatement": row["from_statement"],
        "toStatement": row["to_statement"],
    }


def idea_run(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": str(row["id"]),
        "kind": row["kind"],
        "status": row["status"],
        "startedAt": _iso_time(row["started_at"]),
        "finishedAt": _iso_time(row.get("finished_at")),
        "itemsRead": int(row["items_read"]),
        "passesPlanned": int(row["passes_planned"]),
        "passesCompleted": int(row["passes_completed"]),
        "proposed": int(row["proposed"]),
        "dropped": dropped_counts(row.get("dropped")),
        "error": row.get("error"),
    }


def idea_critique(row: dict[str, Any], *, is_current: bool) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "origin": "iris",
        "createdAt": _iso_time(row["created_at"]),
        "model": row["model"],
        "promptVersion": row["prompt_version"],
        "basis": row["basis"],
        "content": row["content"],
        "isCurrent": is_current,
    }
