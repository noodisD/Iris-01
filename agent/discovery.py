"""Occasions, the library patterns they are instances of, and the owner's verdicts.

The reader turns writing into occasions: accounts of something that happened,
with the passages they rest on. A labelling pass says which library patterns
each occasion is an instance of, and how it went. This module stores both and
answers the one question the Patterns screen asks of them: for a pattern, which
occasions went better and which went worse, and what else was true on each side.

It computes nothing a model has to be trusted for. The occasions and labels are
what earlier passes produced; the two sides are arithmetic over them; what a
difference means is the owner's to say. An occasion the owner says is not an
instance of a pattern leaves every count for that pattern, but is kept, so the
verdict can be seen and changed.

Labels are stored with what produced them, because labellers err in both
directions. Checked against the owner's verdicts on one pattern, one labeller
included every candidate, non-instances and all, while another missed some real
occasions and wrongly included one. So neither a full pattern nor an empty one is
settled by its labels. The owner's verdicts are the check, and a bigger model is
not: one measured more conservative, and no more accurate.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

from psycopg2.extras import Json

from .alternatives import SIDES, Side, distinctive
from .constants import OBSERVATION_MIN_QUOTE_CHARS
from .database import db
from .episodes import ACTORS, MODALITIES, EXTRACTION_VERSION, Episode, comparable
from .evidence_ref import (
    CoLabelRef,
    DayRef,
    EvidenceChanged,
    EvidenceNotCurrent,
    EvidenceNotFound,
    PatternRef,
    parse_ref,
)
from .library import Pattern, library_hash as current_library_hash, load as load_library
from .readable import locate
from .reference_evaluation import account_fingerprint

TONES = ("better", "worse", "mixed")
OCCASION_VERDICTS = ("yes", "no", "unsure")
PATTERN_VERDICTS = ("rings_true", "does_not", "unsure")

_OCCASION_FIELDS = ("actor", "modality", "domain", "situation", "demand", "information",
                    "response", "outcome", "explanation")


def period_bounds(period: str, today: date | None = None) -> tuple[date | None, date]:
    """Inclusive bounds on the recorded entry date; undated writing is all-time only."""
    as_of = today if today is not None else datetime.now().astimezone().date()
    if period == "all":
        return None, as_of
    if period == "30d":
        return as_of - timedelta(days=29), as_of
    if period == "90d":
        return as_of - timedelta(days=89), as_of
    raise ValueError("Unknown writing range.")


def comparable_positions(episodes: list[dict]) -> list[int]:
    """Positions in the full reading of the occasions labels were made against.

    Labels are keyed by position in `comparable()`, not in the full reading.
    Reading them against the full list attaches every label to the wrong
    occasion, so this uses `comparable()` itself rather than restating it.
    """
    eps = [Episode.from_dict(e) for e in episodes]
    chosen = {id(e) for e in comparable(eps)}
    return [i for i, e in enumerate(eps) if id(e) in chosen]


def _source_rows(cur, user_id: int, source_revisions: dict[int, int]) -> dict[int, dict]:
    """Lock all proposed sources before touching any discovery evidence."""
    if (not isinstance(source_revisions, dict)
            or any(type(k) is not int or type(v) is not int or k <= 0 or v <= 0
                   for k, v in source_revisions.items())):
        raise ValueError("Reading source revisions are invalid.")
    sources = {}
    for source_id in sorted(source_revisions):
        cur.execute(
            """SELECT user_id, reflection_date, content, evidence_eligible, discovery_revision
                 FROM reflections WHERE id = %s FOR UPDATE""", (source_id,))
        row = cur.fetchone()
        if (row is None or row[0] != user_id or not row[3]
                or not (row[2] or "").strip() or row[4] != source_revisions[source_id]):
            raise ValueError("Reading source is missing, ineligible, or changed.")
        sources[source_id] = {"date": row[1], "content": row[2]}
    return sources


def _validate_citation(citation: dict, sources: dict[int, dict]) -> date | None:
    if not isinstance(citation, dict) or citation.get("sourceType") != "reflection":
        raise ValueError("Reading citation is not a reflection.")
    raw_id = citation.get("entryId")
    if type(raw_id) is int and raw_id > 0:
        entry_id = raw_id
    elif (isinstance(raw_id, str) and raw_id.isascii()
          and raw_id.isdecimal() and int(raw_id) > 0
          and str(int(raw_id)) == raw_id):
        entry_id = int(raw_id)
    else:
        raise ValueError("Reading citation source is invalid.")
    source = sources.get(entry_id)
    if source is None or not isinstance(citation.get("text"), str):
        raise ValueError("Reading citation has no matching source.")
    if len(citation["text"].strip()) < OBSERVATION_MIN_QUOTE_CHARS:
        raise ValueError("Reading citation is too short to identify a passage.")
    if locate(source["content"], citation["text"]) != citation["text"]:
        raise ValueError("Reading citation does not match source text.")
    recorded = source["date"]
    if citation.get("entryDate") != (recorded.isoformat() if recorded else None):
        raise ValueError("Reading citation date has changed.")
    return recorded


def _validate_account(account: dict, sources: dict[int, dict]) -> None:
    if (not isinstance(account, dict) or account.get("actor") not in ACTORS
            or account.get("modality") not in MODALITIES):
        raise ValueError("Reading account classification is invalid.")
    citations = account.get("citations")
    if not isinstance(citations, list) or not citations:
        raise ValueError("Reading account has no source citations.")
    dates = [recorded for citation in citations
             if (recorded := _validate_citation(citation, sources)) is not None]
    if account.get("occurredOn") != (min(dates).isoformat() if dates else None):
        raise ValueError("Reading recorded date does not match its sources.")
    if not account.get("situation") or not account.get("response"):
        raise ValueError("Reading account has no situation or response.")
    for field in ("situation", "demand", "information", "response", "outcome", "explanation"):
        value = account.get(field)
        if value is not None and (not isinstance(value, str)
                                  or not any(locate(c["text"], value) == value for c in citations)):
            raise ValueError("Reading account has an unsupported passage.")


def _prepare_labels(labels: dict, positions: list[int], expected: set[str]) -> list[tuple]:
    prepared = []
    for pattern_id, rows in labels["labels"].items():
        if pattern_id not in expected or not isinstance(rows, dict):
            raise ValueError("Reading pattern label is invalid.")
        seen_positions: set[int] = set()
        for position, label in rows.items():
            try:
                index = int(position)
            except (ValueError, TypeError) as exc:
                raise ValueError("Reading label index is invalid.") from exc
            if (str(index) != str(position) or index < 0 or index >= len(positions)
                    or index in seen_positions or not isinstance(label, dict)
                    or label.get("tone") not in TONES
                    or label.get("size") not in ("small", "moderate", "large")):
                raise ValueError("Reading label classification is invalid.")
            seen_positions.add(index)
            prepared.append((pattern_id, positions[index], label["tone"], label["size"],
                             labels["by"].get(pattern_id)))
    return prepared


def _validate_reading(episodes: list[dict], labels: dict, sources: dict[int, dict],
                      *, extraction_version: int, library_hash: str) -> tuple[list[int], list[tuple]]:
    """Validate complete, source-backed results before the first evidence write."""
    if (type(extraction_version) is not int or extraction_version != EXTRACTION_VERSION
            or not isinstance(library_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", library_hash)):
        raise ValueError("Reading version or library hash is invalid.")
    patterns = load_library()
    if library_hash != current_library_hash(patterns):
        raise ValueError("Reading library has changed.")
    if not isinstance(episodes, list) or not isinstance(labels, dict):
        raise ValueError("Reading accounts or labels are invalid.")
    try:
        positions = comparable_positions(episodes)
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("Reading account structure is invalid.") from exc
    if (labels.get("extractionVersion") != extraction_version
            or labels.get("libraryHash") != library_hash
            or labels.get("accounts") != len(positions)
            or not isinstance(labels.get("labels"), dict)
            or not isinstance(labels.get("by"), dict)):
        raise ValueError("Reading labels or metadata are missing or mismatched.")
    expected = {p.id for p in patterns}
    if positions and set(labels["labels"]) != expected:
        raise ValueError("Reading labels are incomplete.")
    if not positions and labels["labels"]:
        raise ValueError("Reading has labels without comparable accounts.")
    for account in episodes:
        _validate_account(account, sources)
    return positions, _prepare_labels(labels, positions, expected)


def _store_reading(cur, user_id: int, episodes: list[dict], labels: dict, *,
                   source_revisions: dict[int, int], extraction_version: int,
                   library_hash: str, omitted_accounts: int = 0,
                   locked_sources: dict[int, dict] | None = None) -> dict[str, int]:
    """Publish a complete reading inside the caller's transaction and source locks."""
    if (not isinstance(source_revisions, dict) or not source_revisions
            or type(omitted_accounts) is not int or omitted_accounts < 0):
        raise ValueError("Reading sources or omitted count are invalid.")
    sources = locked_sources if locked_sources is not None else _source_rows(cur, user_id, source_revisions)
    _, prepared = _validate_reading(episodes, labels, sources,
                                    extraction_version=extraction_version, library_hash=library_hash)
    ids: dict[int, int] = {}
    counts = Counter()
    source_ids = sorted(source_revisions)
    cur.execute(
        """UPDATE occasions SET is_current = FALSE
             WHERE id IN (SELECT occasion_id FROM occasion_sources
                          WHERE reflection_id = ANY(%s))""", (source_ids,))
    cur.execute(
        """UPDATE pattern_labels SET is_current = FALSE
             WHERE occasion_id IN (SELECT occasion_id FROM occasion_sources
                                    WHERE reflection_id = ANY(%s))""", (source_ids,))
    cur.execute("DELETE FROM occasion_sources WHERE reflection_id = ANY(%s)", (source_ids,))
    for index, e in enumerate(episodes):
        fingerprint = account_fingerprint(e)
        cur.execute(
            f"""INSERT INTO occasions (user_id, fingerprint, {", ".join(_OCCASION_FIELDS)},
                                       occurred_on, citations, extraction_version, is_current)
                VALUES (%s, %s, {", ".join(["%s"] * len(_OCCASION_FIELDS))}, %s, %s, %s, TRUE)
                ON CONFLICT (user_id, fingerprint) DO UPDATE
                   SET extraction_version = EXCLUDED.extraction_version, is_current = TRUE
                RETURNING id, (xmax = 0)""",
            (user_id, fingerprint, *[e.get(f) for f in _OCCASION_FIELDS],
             e.get("occurredOn"), Json(e["citations"]), extraction_version))
        occasion_id, added = cur.fetchone()
        ids[index] = occasion_id
        counts["occasions_added" if added else "occasions_already_there"] += 1
        for source_id in sorted({int(c["entryId"]) for c in e["citations"]}):
            cur.execute(
                """INSERT INTO occasion_sources (occasion_id, reflection_id, source_revision)
                   VALUES (%s, %s, %s) ON CONFLICT (occasion_id, reflection_id)
                   DO UPDATE SET source_revision = EXCLUDED.source_revision""",
                (occasion_id, source_id, source_revisions[source_id]))
    for pattern_id, index, tone, size, model in prepared:
        cur.execute(
            """INSERT INTO pattern_labels (occasion_id, pattern_id, tone, size, labelled_by, is_current)
               VALUES (%s, %s, %s, %s, %s, TRUE)
               ON CONFLICT (occasion_id, pattern_id) DO UPDATE
                  SET tone = EXCLUDED.tone, size = EXCLUDED.size,
                      labelled_by = EXCLUDED.labelled_by, is_current = TRUE
               RETURNING (xmax = 0)""",
            (ids[index], pattern_id, tone, size, model))
        counts["labels_added" if cur.fetchone()[0] else "labels_updated"] += 1
    for source_id, revision in sorted(source_revisions.items()):
        cur.execute(
            """INSERT INTO discovery_reads (reflection_id, source_revision, extraction_version,
                                             library_hash, completed_at, omitted_accounts)
               VALUES (%s, %s, %s, %s, NOW(), %s)
               ON CONFLICT (reflection_id) DO UPDATE
                  SET source_revision = EXCLUDED.source_revision,
                      extraction_version = EXCLUDED.extraction_version,
                      library_hash = EXCLUDED.library_hash, completed_at = EXCLUDED.completed_at,
                      omitted_accounts = EXCLUDED.omitted_accounts""",
            (source_id, revision, extraction_version, library_hash, omitted_accounts))
    return dict(counts)


def load_reading(user_id: int, episodes: list[dict], labels: dict, *,
                 source_revisions: dict[int, int], extraction_version: int,
                 library_hash: str) -> dict[str, int]:
    """Import a versioned reading after locking and validating every cited source."""
    with db.connection() as conn, conn.cursor() as cur:
        result = _store_reading(cur, user_id, episodes, labels,
                                source_revisions=source_revisions,
                                extraction_version=extraction_version, library_hash=library_hash)
        conn.commit()
        return result


def occasion_id_for(user_id: int, episode: dict) -> int | None:
    """The stored occasion for one account of a reading, found by its content."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM occasions WHERE user_id = %s AND fingerprint = %s",
                    (user_id, account_fingerprint(episode)))
        row = cur.fetchone()
        return row[0] if row else None


_CURRENT_SOURCES_SQL = """
    AND EXISTS (SELECT 1 FROM occasion_sources os WHERE os.occasion_id = o.id)
    AND NOT EXISTS (
        SELECT 1 FROM occasion_sources os
        LEFT JOIN reflections r ON r.id = os.reflection_id
        LEFT JOIN discovery_reads dr ON dr.reflection_id = r.id
        WHERE os.occasion_id = o.id
          AND (r.id IS NULL OR r.user_id <> o.user_id
               OR NOT r.evidence_eligible OR r.content IS NULL
               OR length(trim(r.content)) = 0
               OR r.discovery_revision <> os.source_revision
               OR dr.source_revision IS DISTINCT FROM os.source_revision
               OR dr.extraction_version IS DISTINCT FROM %s
               OR dr.library_hash IS DISTINCT FROM %s))"""


def _labels(user_id: int, *, period: str = "all", today: date | None = None) -> list[dict[str, Any]]:
    start, as_of = period_bounds(period, today)
    current_hash = current_library_hash(load_library())
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""SELECT l.occasion_id, l.pattern_id, COALESCE(l.owner_tone, l.tone),
                      l.tone, l.owner_tone, l.size, l.labelled_by, l.owner_verdict,
                      l.verdict_note, o.fingerprint, o.occurred_on, o.citations,
                      {", ".join("o." + field for field in _OCCASION_FIELDS)}
                 FROM pattern_labels l JOIN occasions o ON o.id = l.occasion_id
                WHERE o.user_id = %s AND o.is_current AND o.extraction_version = %s
                  AND l.is_current
                  AND (%s = 'all' OR o.occurred_on BETWEEN %s AND %s)
                  {_CURRENT_SOURCES_SQL}""",
            (user_id, EXTRACTION_VERSION, period, start, as_of,
             EXTRACTION_VERSION, current_hash))
        keys = ("occasion_id", "pattern_id", "tone", "suggested_tone", "owner_tone",
                "size", "labelled_by", "owner_verdict", "verdict_note",
                "fingerprint", "occurred_on", "citations", *_OCCASION_FIELDS)
        return [dict(zip(keys, row, strict=True)) for row in cur.fetchall()]


def _pattern_verdicts(user_id: int) -> dict[str, dict[str, Any]]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT pattern_id, verdict, note FROM pattern_verdicts WHERE user_id = %s",
                    (user_id,))
        return {p: {"verdict": v, "note": n} for p, v, n in cur.fetchall()}



def _coverage(labels: list[dict[str, Any]], period: str, as_of: date) -> dict[str, Any]:
    accepted = {label["occasion_id"]: label for label in labels if label["owner_verdict"] != "no"}
    dated = [label["occurred_on"] for label in accepted.values() if label["occurred_on"]]
    source_ids = {
        int(c["entryId"]) for label in accepted.values() for c in label["citations"]
        if c.get("sourceType") == "reflection"
    }
    return {
        "range": period, "asOf": as_of.isoformat(),
        "recordedFrom": min(dated).isoformat() if dated else None,
        "recordedTo": max(dated).isoformat() if dated else None,
        "entryCount": len(source_ids), "accountCount": len(accepted),
        "undatedAccountCount": len(accepted) - len(dated),
    }


def _snapshot(labels: list[dict[str, Any]], period: str, *,
              feedback: Any = None) -> str:
    """Stable change token over all relevant evidence, including rejected accounts."""
    records = sorted(
        ((label["pattern_id"], label["fingerprint"], label["tone"],
          label["suggested_tone"], label["owner_tone"], label["size"],
          label["labelled_by"], label["owner_verdict"], label["verdict_note"])
         for label in labels),
        key=lambda record: (record[0], record[1]),
    )
    payload = json.dumps([period, records, feedback], separators=(",", ":"),
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _occasion(label: dict[str, Any]) -> dict[str, Any]:
    return {"id": label["occasion_id"], **{field: label[field] for field in _OCCASION_FIELDS},
            "occurred_on": label["occurred_on"], "citations": label["citations"], "label": label}


def _newest(label: dict[str, Any]) -> tuple:
    return (label["occurred_on"] is not None, label["occurred_on"] or date.min,
            label["occasion_id"])


def summaries_with_coverage(user_id: int, library: list[Pattern], *,
                            period: str = "all") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _, as_of = period_bounds(period)
    labels = _labels(user_id, period=period, today=as_of)
    verdicts = _pattern_verdicts(user_id)
    by_pattern: dict[str, list[dict[str, Any]]] = {}
    for label in labels:
        by_pattern.setdefault(label["pattern_id"], []).append(label)
    out = []
    for p in library:
        mine = by_pattern.get(p.id, [])
        counted = [label for label in mine if label["owner_verdict"] != "no"]
        tones = Counter(label["tone"] for label in counted)
        newest = sorted(counted, key=_newest, reverse=True)
        better = next((label for label in newest if label["tone"] == "better"), None)
        worse = next((label for label in newest if label["tone"] == "worse"), None)
        examples = [better, worse] if better and worse else newest[:2]
        examples = sorted(examples, key=_newest, reverse=True)
        coverage = _coverage(mine, period, as_of)
        out.append({
            "pattern": p, "occasions": len(counted),
            "tones": {tone: tones.get(tone, 0) for tone in TONES},
            "reviewed": sum(label["owner_verdict"] is not None for label in mine),
            "rejected": len(mine) - len(counted),
            "labelledBy": sorted({label["labelled_by"] for label in mine if label["labelled_by"]}),
            "verdict": verdicts.get(p.id), "entryCount": coverage["entryCount"],
            "recordedFrom": coverage["recordedFrom"], "recordedTo": coverage["recordedTo"],
            "undatedAccountCount": coverage["undatedAccountCount"],
            "examples": [_occasion(label) for label in examples],
            "question": p.question,
            "snapshot": _snapshot(mine, period, feedback=verdicts.get(p.id)),
            "coverage": coverage,
        })
    out.sort(key=lambda item: (
        item["tones"]["better"] == 0 or item["tones"]["worse"] == 0,
        -(date.fromisoformat(item["recordedTo"]).toordinal() if item["recordedTo"] else 0),
        -item["entryCount"], item["pattern"].id))
    return out, _coverage(labels, period, as_of)


def summaries(user_id: int, library: list[Pattern], *, period: str = "all") -> list[dict[str, Any]]:
    """Every library lens, with accepted current evidence for this recorded period."""
    return summaries_with_coverage(user_id, library, period=period)[0]


def _sides(labels: list[dict[str, Any]], pattern_id: str) -> tuple[dict[str, Side], Counter]:
    """A pattern's better and worse occasions: what else held on each, and how many."""
    by_occasion: dict[int, list[dict]] = {}
    for label in labels:
        if label["owner_verdict"] != "no":
            by_occasion.setdefault(label["occasion_id"], []).append(label)
    sides = {name: Side() for name in SIDES}
    totals: Counter = Counter()
    for label in labels:
        if label["pattern_id"] != pattern_id or label["owner_verdict"] == "no":
            continue
        side = sides.get(label["tone"])
        if side is None:
            continue
        totals[label["tone"]] += 1
        for other in by_occasion.get(label["occasion_id"], []):
            if other["pattern_id"] != pattern_id:
                side.others[other["pattern_id"]] += 1
    return sides, totals


def detail(user_id: int, pattern: Pattern, *, period: str = "all") -> dict[str, Any]:
    """One lens with every current labelled account, including rejected ones."""
    _, as_of = period_bounds(period)
    labels = _labels(user_id, period=period, today=as_of)
    mine = [label for label in labels if label["pattern_id"] == pattern.id]
    sides, totals = _sides(labels, pattern.id)
    verdict = _pattern_verdicts(user_id).get(pattern.id)
    return {
        "pattern": pattern,
        "occasions": [_occasion(label) for label in sorted(mine, key=_newest, reverse=True)],
        "distinctive": [
            {"patternId": other, "better": better, "worse": worse,
             "betterTotal": totals["better"], "worseTotal": totals["worse"],
             "betterRate": better / totals["better"], "worseRate": worse / totals["worse"]}
            for other, better, worse in distinctive(sides, totals)],
        "verdict": verdict,
        "coverage": _coverage(mine, period, as_of),
        "snapshot": _snapshot(mine, period, feedback=verdict),
    }


def differences(user_id: int, library: list[Pattern], *, period: str = "all") -> list[dict[str, Any]]:
    """Conservative, denominator-aware co-label comparisons."""
    _, as_of = period_bounds(period)
    labels = _labels(user_id, period=period, today=as_of)
    return _differences_for_labels(user_id, library, labels, period, as_of)


def _differences_for_labels(user_id: int, library: list[Pattern], labels: list[dict[str, Any]],
                            period: str, as_of: date) -> list[dict[str, Any]]:
    """Keep counts and snapshots tied to the same account reading as the detail."""
    names = {p.id: p.name for p in library}
    pattern_verdicts = _pattern_verdicts(user_id)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT pattern_id, other_pattern_id, verdict, note
                         FROM difference_verdicts WHERE user_id = %s""", (user_id,))
        verdicts = {(p, o): {"verdict": v, "note": n} for p, o, v, n in cur.fetchall()}
    out = []
    for p in library:
        sides, totals = _sides(labels, p.id)
        if min(totals["better"], totals["worse"]) < 3:
            continue
        primary = [label for label in labels if label["pattern_id"] == p.id]
        primary_ids = {label["occasion_id"] for label in primary}
        for other, better, worse in distinctive(sides, totals):
            relevant = [label for label in labels
                        if label["occasion_id"] in primary_ids
                        and label["pattern_id"] in (p.id, other)]
            out.append({
                "patternId": p.id, "patternName": p.name,
                "otherId": other, "otherName": names.get(other, other),
                "worse": worse, "worseTotal": totals["worse"],
                "better": better, "betterTotal": totals["better"],
                "verdict": verdicts.get((p.id, other)),
                "patternVerdict": pattern_verdicts.get(p.id),
                "betterRate": better / totals["better"],
                "worseRate": worse / totals["worse"],
                "rateGap": abs(better / totals["better"] - worse / totals["worse"]),
                "sampleLabel": "exploratory",
                "dismissed": any((v or {}).get("verdict") == "does_not" for v in (
                    verdicts.get((p.id, other)), pattern_verdicts.get(p.id),
                    pattern_verdicts.get(other))),
                "coverage": _coverage(primary, period, as_of),
                "snapshot": _snapshot(
                    relevant, period, feedback={
                        "pair": verdicts.get((p.id, other)),
                        "primary": pattern_verdicts.get(p.id),
                        "other": pattern_verdicts.get(other),
                    }),
            })
    return sorted(one_per_pair(out), key=lambda d: (
        -d["rateGap"], min(d["betterTotal"], d["worseTotal"]) * -1,
        -(date.fromisoformat(d["coverage"]["recordedTo"]).toordinal()
          if d["coverage"]["recordedTo"] else 0),
        d["patternId"], d["otherId"]))


def outcome_pairs(user_id: int, library: list[Pattern], *,
                  period: str = "all") -> list[dict[str, Any]]:
    """Juxtapose two accounts from different entries without claiming a trend."""
    _, as_of = period_bounds(period)
    labels = _labels(user_id, period=period, today=as_of)
    opinions = _pattern_verdicts(user_id)
    out = []
    for pattern in library:
        opinion = opinions.get(pattern.id)
        if (opinion or {}).get("verdict") == "does_not":
            continue
        mine = [row for row in labels if row["pattern_id"] == pattern.id]
        accepted = [row for row in mine if row["owner_verdict"] != "no"]
        better = sorted((row for row in accepted if row["tone"] == "better"),
                        key=_newest, reverse=True)
        worse = sorted((row for row in accepted if row["tone"] == "worse"),
                       key=_newest, reverse=True)
        pair = next(((b, w) for b in better for w in worse
                     if {str(c["entryId"]) for c in b["citations"]}.isdisjoint(
                         str(c["entryId"]) for c in w["citations"])), None)
        if pair is None:
            continue
        b, w = pair
        out.append({
            "kind": "outcome_pair", "patternId": pattern.id,
            "patternName": pattern.name, "question": pattern.question,
            "better": _occasion(b), "worse": _occasion(w),
            "betterTotal": len(better), "worseTotal": len(worse),
            "mixedTotal": sum(row["tone"] == "mixed" for row in accepted),
            "verdict": opinion, "coverage": _coverage(mine, period, as_of),
            "snapshot": _snapshot(mine, period, feedback=opinion),
        })
    return sorted(out, key=lambda pair: (
        -max(pair["better"]["occurred_on"] or date.min,
             pair["worse"]["occurred_on"] or date.min).toordinal(),
        pair["patternId"]))


def difference_detail(user_id: int, library: list[Pattern], pattern_id: str,
                      other_id: str, *, period: str = "all") -> dict[str, Any] | None:
    """All accepted denominator accounts partitioned by accepted co-label."""
    _, as_of = period_bounds(period)
    labels = _labels(user_id, period=period, today=as_of)
    difference = next((row for row in _differences_for_labels(
        user_id, library, labels, period, as_of)
        if row["patternId"] == pattern_id and row["otherId"] == other_id), None)
    if difference is None:
        return None
    other_ids = {row["occasion_id"] for row in labels
                 if row["pattern_id"] == other_id and row["owner_verdict"] != "no"}
    groups: dict[str, list[dict[str, Any]]] = {
        "betterWith": [], "betterWithout": [], "worseWith": [], "worseWithout": []}
    mixed = 0
    for row in labels:
        if row["pattern_id"] != pattern_id or row["owner_verdict"] == "no":
            continue
        if row["tone"] == "mixed":
            mixed += 1
        elif row["tone"] in ("better", "worse"):
            key = row["tone"] + ("With" if row["occasion_id"] in other_ids else "Without")
            groups[key].append(_occasion(row))
    for group in groups.values():
        group.sort(key=lambda row: (row["occurred_on"] is not None,
                                   row["occurred_on"] or date.min, row["id"]), reverse=True)
    return {"difference": difference, "groups": groups, "mixedExcluded": mixed}


def resolve_discussion(user_id: int, reference: str | dict, *,
                       require_snapshot: bool = False) -> dict[str, Any]:
    """Resolve only this owner's currently source-backed record; never trust supplied quotes."""
    ref = parse_ref(reference)
    library = {p.id: p for p in load_library()}
    if isinstance(ref, PatternRef):
        pattern = library.get(ref.patternId)
        if pattern is None:
            raise EvidenceNotFound("No such selected pattern.")
        if ref.kind == "pattern":
            evidence = detail(user_id, pattern, period=ref.range)
            if not any(o["label"]["owner_verdict"] != "no" for o in evidence["occasions"]):
                raise EvidenceNotFound("No current source-backed account for this pattern.")
            title, question = pattern.name, pattern.question
        else:
            evidence = next((pair for pair in outcome_pairs(
                user_id, list(library.values()), period=ref.range)
                if pair["patternId"] == pattern.id), None)
            if evidence is None:
                raise EvidenceNotCurrent("This comparison has changed.")
            title = f"Two situations: {pattern.name}"
            question = evidence["question"]
    elif isinstance(ref, CoLabelRef):
        if (ref.patternId not in library or ref.otherId not in library
                or ref.patternId == ref.otherId):
            raise EvidenceNotFound("No such selected comparison.")
        evidence = difference_detail(user_id, list(library.values()), ref.patternId,
                                     ref.otherId, period=ref.range)
        if evidence is None:
            raise EvidenceNotCurrent("This comparison has changed.")
        title = f"{library[ref.patternId].name} and {library[ref.otherId].name}"
        question = "What might explain this difference, and what does this evidence leave uncertain?"
    elif isinstance(ref, DayRef):
        from .day_differences import detail_for_user  # noqa: PLC0415 - period_bounds imports this module

        evidence = detail_for_user(user_id, ref.outcome, ref.split, period=ref.range)
        if evidence is None:
            raise EvidenceNotCurrent("This comparison has changed.")
        title = f"{ref.outcome.replace('_', ' ').title()} by {ref.split.replace('_', ' ')}"
        question = "What might explain this difference, and what does this evidence leave uncertain?"
    else:
        raise EvidenceNotFound("No such selected evidence.")
    current = evidence["difference"]["snapshot"] if isinstance(ref, (CoLabelRef, DayRef)) else evidence["snapshot"]
    changed = current != ref.snapshot
    if changed and require_snapshot:
        raise EvidenceChanged()
    return {"ref": ref.model_copy(update={"snapshot": current}), "title": title,
            "question": question, "evidence": evidence, "changed": changed}


def writing_coverage(user_id: int, *, period: str = "all") -> dict[str, Any]:
    """Overall contributing writing for the selected recorded period."""
    _, as_of = period_bounds(period)
    return _coverage(_labels(user_id, period=period, today=as_of), period, as_of)

def writing_snapshot(user_id: int, *, period: str = "all") -> str:
    """Change token for all period-selected discovery accounts and corrections."""
    return _snapshot(_labels(user_id, period=period), period,
                     feedback=_pattern_verdicts(user_id))


def _contrast(d: dict[str, Any]) -> float:
    """How far apart the two sides are, as shares of each side's occasions."""
    return abs(d["worse"] / d["worseTotal"] - d["better"] / d["betterTotal"])


def one_per_pair(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One difference for each pair of patterns.

    Each pattern is compared with the others from its own side, so a pair that
    differs both ways was listed twice: "when A came up, B was there" and "when
    B came up, A was there", the same finding seen from each end. The direction
    the owner has judged stands (a note by itself is not a judgment); otherwise
    one whose sides are further apart.
    """
    best: dict[frozenset[str], dict[str, Any]] = {}
    for d in rows:
        key = frozenset((d["patternId"], d["otherId"]))
        rank = ((d["verdict"] or {}).get("verdict") is not None, _contrast(d),
                min(d["betterTotal"], d["worseTotal"]), d["patternId"])
        held = best.get(key)
        if held is None or rank > (((held["verdict"] or {}).get("verdict") is not None),
                                   _contrast(held), min(held["betterTotal"], held["worseTotal"]),
                                   held["patternId"]):
            best[key] = d
    return list(best.values())


def set_difference_verdict(user_id: int, pattern_id: str, other_pattern_id: str,
                           verdict: str | None, note: str | None = None) -> None:
    """Replace the owner's judgment and note, preserving note-only feedback."""
    note = (note or "").strip() or None
    with db.connection() as conn, conn.cursor() as cur:
        if verdict is None and note is None:
            cur.execute(
                """DELETE FROM difference_verdicts
                    WHERE user_id = %s AND pattern_id = %s AND other_pattern_id = %s""",
                (user_id, pattern_id, other_pattern_id))
        else:
            cur.execute(
                """INSERT INTO difference_verdicts (user_id, pattern_id, other_pattern_id, verdict, note)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (user_id, pattern_id, other_pattern_id) DO UPDATE
                      SET verdict = EXCLUDED.verdict, note = EXCLUDED.note, updated_at = now()""",
                (user_id, pattern_id, other_pattern_id, verdict, note))
        conn.commit()


_UNSET = object()


def set_occasion_verdict(user_id: int, pattern_id: str, occasion_id: int,
                         verdict: str | None, note: str | None = None,
                         *, owner_tone: str | None | object = _UNSET) -> bool:
    """Replace feedback; an absent tone leaves its override intact."""
    if owner_tone is not _UNSET and owner_tone is not None and owner_tone not in TONES:
        raise ValueError("Invalid owner tone.")
    with db.connection() as conn, conn.cursor() as cur:
        tone_clause = ", owner_tone = %s" if owner_tone is not _UNSET else ""
        params = [verdict, (note or "").strip() or None]
        if owner_tone is not _UNSET:
            params.append(owner_tone)
        cur.execute(
            f"""UPDATE pattern_labels l SET owner_verdict = %s, verdict_note = %s{tone_clause}
                  FROM occasions o
                 WHERE l.occasion_id = o.id AND o.user_id = %s AND o.is_current
                   AND o.extraction_version = %s AND l.is_current
                   AND l.occasion_id = %s AND l.pattern_id = %s
                   {_CURRENT_SOURCES_SQL}""",
            (*params, user_id, EXTRACTION_VERSION, occasion_id, pattern_id,
             EXTRACTION_VERSION, current_library_hash(load_library())))
        changed = cur.rowcount == 1
        conn.commit()
        return changed


def set_pattern_verdict(user_id: int, pattern_id: str,
                        verdict: str | None, note: str | None = None) -> None:
    """Replace judgment and note; remove the record only if both are clear."""
    note = (note or "").strip() or None
    with db.connection() as conn, conn.cursor() as cur:
        if verdict is None and note is None:
            cur.execute("DELETE FROM pattern_verdicts WHERE user_id = %s AND pattern_id = %s",
                        (user_id, pattern_id))
        else:
            cur.execute(
                """INSERT INTO pattern_verdicts (user_id, pattern_id, verdict, note)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (user_id, pattern_id) DO UPDATE
                      SET verdict = EXCLUDED.verdict, note = EXCLUDED.note, updated_at = now()""",
                (user_id, pattern_id, verdict, note))
        conn.commit()
