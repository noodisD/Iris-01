"""Editorial process lenses for interpreting already-discovered personal dynamics.

The literature informs questions, not a classification or a personal match. A lens
cannot supply an occurrence, an unstated motive, or an outcome.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

LIBRARY_PATH = Path(__file__).resolve().parent.parent / "patterns" / "library.json"
FAMILIES = frozenset({"belonging", "uncertainty", "self_worth", "emotional_protection",
                      "capacity", "agency"})
LENS_FIELDS = frozenset({"id", "family", "name", "sequence", "possibleFunction",
                         "immediateReturn", "possibleLaterCost", "requires", "notWhen",
                         "alternative", "question", "sourceIds"})
SOURCE_FIELDS = frozenset({"title", "url", "kind", "scope"})
_ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    url: str
    kind: str
    scope: str


@dataclass(frozen=True)
class Lens:
    id: str
    family: str
    name: str
    sequence: str
    possible_function: str
    immediate_return: str
    possible_later_cost: str
    requires: tuple[str, str]
    not_when: str
    alternative: str
    question: str
    source_ids: tuple[str, ...]
    sources: tuple[Source, ...]


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{field} must be a nonblank, trimmed string")
    return value


def load(path: Path | None = None) -> list[Lens]:
    """Validate the whole v4 catalogue; reject any incomplete or foreign source."""
    body = json.loads((path or LIBRARY_PATH).read_text(encoding="utf-8"))
    if not isinstance(body, dict) or set(body) != {"version", "sources", "lenses"} or body["version"] != 4:
        raise ValueError("invalid v4 lens library root")
    if not isinstance(body["sources"], dict) or not body["sources"]:
        raise ValueError("lens sources must be a nonempty object")
    sources: dict[str, Source] = {}
    for key, record in body["sources"].items():
        if not isinstance(key, str) or not _ID.fullmatch(key.replace("_", "-")):
            raise ValueError(f"invalid source ID: {key}")
        if not isinstance(record, dict) or set(record) != SOURCE_FIELDS:
            raise ValueError(f"invalid source record: {key}")
        values = {field: _text(record[field], field) for field in SOURCE_FIELDS}
        if values["kind"] not in {"research_article", "theoretical_overview"}:
            raise ValueError(f"invalid source kind: {key}")
        if not values["url"].startswith("https://"):
            raise ValueError(f"invalid source URL: {key}")
        sources[key] = Source(key, **values)
    if not isinstance(body["lenses"], list) or not body["lenses"]:
        raise ValueError("the lens library is empty")
    result: list[Lens] = []
    seen: set[str] = set()
    for item in body["lenses"]:
        if not isinstance(item, dict) or set(item) != LENS_FIELDS:
            raise ValueError("invalid lens fields")
        lens_id = _text(item["id"], "id")
        if not _ID.fullmatch(lens_id):
            raise ValueError(f"invalid lens ID: {lens_id}")
        if lens_id in seen:
            raise ValueError(f"lens {lens_id} appears twice")
        seen.add(lens_id)
        fields = {key: _text(item[key], key) for key in LENS_FIELDS - {"requires", "sourceIds"}}
        if fields["family"] not in FAMILIES:
            raise ValueError(f"unknown lens family: {fields['family']}")
        if not fields["question"].endswith("?") or fields["question"].count("?") != 1:
            raise ValueError(f"invalid lens question: {lens_id}")
        requirements = item["requires"]
        if not isinstance(requirements, list) or len(requirements) != 2:
            raise ValueError(f"lens {lens_id} needs exactly two requirements")
        requirements = tuple(_text(part, "requires") for part in requirements)
        ids = item["sourceIds"]
        if (not isinstance(ids, list) or not ids or
                any(not isinstance(source_id, str) or source_id not in sources for source_id in ids) or
                len(set(ids)) != len(ids)):
            raise ValueError(f"lens {lens_id} has invalid source IDs")
        result.append(Lens(
            id=lens_id, family=fields["family"], name=fields["name"],
            sequence=fields["sequence"], possible_function=fields["possibleFunction"],
            immediate_return=fields["immediateReturn"],
            possible_later_cost=fields["possibleLaterCost"], requires=requirements,
            not_when=fields["notWhen"], alternative=fields["alternative"],
            question=fields["question"], source_ids=tuple(ids),
            sources=tuple(sources[source_id] for source_id in ids)))
    return result


def library_hash(lenses: list[Lens]) -> str:
    """Hash all display content, requirements, and bibliographic source scopes."""
    canonical = json.dumps([asdict(lens) for lens in lenses], sort_keys=True,
                           ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
