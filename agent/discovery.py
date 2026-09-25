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

from collections import Counter
from typing import Any

from psycopg2.extras import Json

from .alternatives import SIDES, Side, distinctive
from .database import db
from .episodes import Episode, comparable
from .library import Pattern
from .reference_evaluation import account_fingerprint

TONES = ("better", "worse", "mixed")
OCCASION_VERDICTS = ("yes", "no", "unsure")
PATTERN_VERDICTS = ("rings_true", "does_not", "unsure")

_OCCASION_FIELDS = ("actor", "modality", "domain", "situation", "demand", "information",
                    "response", "outcome", "explanation")


def comparable_positions(episodes: list[dict]) -> list[int]:
    """Positions in the full reading of the occasions labels were made against.

    Labels are keyed by position in `comparable()`, not in the full reading.
    Reading them against the full list attaches every label to the wrong
    occasion, so this uses `comparable()` itself rather than restating it.
    """
    eps = [Episode.from_dict(e) for e in episodes]
    chosen = {id(e) for e in comparable(eps)}
    return [i for i, e in enumerate(eps) if id(e) in chosen]


def load_reading(user_id: int, episodes: list[dict], labels: dict) -> dict[str, int]:
    """Store a reading and its labels. Loading the same reading again changes
    nothing: occasions are keyed by their content, labels by occasion and
    pattern, and a reload never touches a verdict the owner has given."""
    positions = comparable_positions(episodes)
    if labels.get("accounts") not in (None, len(positions)):
        raise ValueError("These labels were made against a different reading; relabel it first.")
    by = labels.get("by", {})
    counts = Counter()
    with db.connection() as conn, conn.cursor() as cur:
        ids: dict[int, int] = {}
        for index, e in enumerate(episodes):
            cur.execute(
                f"""INSERT INTO occasions (user_id, fingerprint, {", ".join(_OCCASION_FIELDS)},
                                           occurred_on, citations)
                    VALUES (%s, %s, {", ".join(["%s"] * len(_OCCASION_FIELDS))}, %s, %s)
                    ON CONFLICT (user_id, fingerprint) DO NOTHING
                    RETURNING id;""",
                (user_id, account_fingerprint(e), *[e.get(f) for f in _OCCASION_FIELDS],
                 e.get("occurredOn"), Json(e.get("citations", []))))
            row = cur.fetchone()
            if row:
                counts["occasions_added"] += 1
            else:
                cur.execute("SELECT id FROM occasions WHERE user_id = %s AND fingerprint = %s",
                            (user_id, account_fingerprint(e)))
                row = cur.fetchone()
                counts["occasions_already_there"] += 1
            ids[index] = row[0]

        for pattern_id, rows in labels.get("labels", {}).items():
            for position, label in rows.items():
                occasion_id = ids[positions[int(position)]]
                cur.execute(
                    """INSERT INTO pattern_labels (occasion_id, pattern_id, tone, size, labelled_by)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (occasion_id, pattern_id) DO UPDATE
                          SET tone = EXCLUDED.tone, size = EXCLUDED.size,
                              labelled_by = EXCLUDED.labelled_by
                       RETURNING (xmax = 0);""",
                    (occasion_id, pattern_id, label["tone"], label.get("size"), by.get(pattern_id)))
                counts["labels_added" if cur.fetchone()[0] else "labels_updated"] += 1
        conn.commit()
    return dict(counts)


def occasion_id_for(user_id: int, episode: dict) -> int | None:
    """The stored occasion for one account of a reading, found by its content."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM occasions WHERE user_id = %s AND fingerprint = %s",
                    (user_id, account_fingerprint(episode)))
        row = cur.fetchone()
        return row[0] if row else None


def _labels(user_id: int) -> list[dict[str, Any]]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT l.occasion_id, l.pattern_id, l.tone, l.size, l.labelled_by,
                      l.owner_verdict, l.verdict_note
                 FROM pattern_labels l JOIN occasions o ON o.id = l.occasion_id
                WHERE o.user_id = %s""", (user_id,))
        keys = ("occasion_id", "pattern_id", "tone", "size", "labelled_by", "owner_verdict", "verdict_note")
        return [dict(zip(keys, r, strict=True)) for r in cur.fetchall()]


def _pattern_verdicts(user_id: int) -> dict[str, dict[str, Any]]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT pattern_id, verdict, note FROM pattern_verdicts WHERE user_id = %s",
                    (user_id,))
        return {p: {"verdict": v, "note": n} for p, v, n in cur.fetchall()}


def summaries(user_id: int, library: list[Pattern]) -> list[dict[str, Any]]:
    """Every library pattern with how many occasions it has, by how they went."""
    labels = _labels(user_id)
    verdicts = _pattern_verdicts(user_id)
    out = []
    for p in library:
        mine = [label for label in labels if label["pattern_id"] == p.id]
        counted = [label for label in mine if label["owner_verdict"] != "no"]
        tones = Counter(label["tone"] for label in counted)
        out.append({
            "pattern": p, "occasions": len(counted),
            "tones": {t: tones.get(t, 0) for t in TONES},
            "reviewed": sum(1 for label in mine if label["owner_verdict"] is not None),
            "rejected": sum(1 for label in mine if label["owner_verdict"] == "no"),
            "labelledBy": sorted({label["labelled_by"] for label in mine if label["labelled_by"]}),
            "verdict": verdicts.get(p.id),
        })
    return out


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


def detail(user_id: int, pattern: Pattern) -> dict[str, Any]:
    """One pattern's occasions on both sides, and what else was true on each."""
    labels = _labels(user_id)
    mine = {label["occasion_id"]: label for label in labels if label["pattern_id"] == pattern.id}
    sides, _ = _sides(labels, pattern.id)

    occasions = []
    if mine:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""SELECT id, {", ".join(_OCCASION_FIELDS)}, occurred_on, citations
                      FROM occasions WHERE user_id = %s AND id = ANY(%s)
                     ORDER BY occurred_on DESC NULLS LAST, id DESC""",
                (user_id, list(mine)))
            keys = ("id", *_OCCASION_FIELDS, "occurred_on", "citations")
            for row in cur.fetchall():
                o = dict(zip(keys, row, strict=True))
                o["label"] = mine[o["id"]]
                occasions.append(o)

    return {
        "pattern": pattern,
        "occasions": occasions,
        "alsoTrue": {name: dict(side.others) for name, side in sides.items()},
        "distinctive": distinctive(sides),
        "verdict": _pattern_verdicts(user_id).get(pattern.id),
    }


def differences(user_id: int, library: list[Pattern]) -> list[dict[str, Any]]:
    """Every difference in outcome across the library: the Insights screen.

    For each pattern with occasions on both sides, each other pattern that sits
    on one side at least two occasions more than the other. A side with no
    occasions compares nothing, so a pattern needs both. Largest difference
    first. Arithmetic over the labels, as on the Patterns screen; what it means
    is the owner's verdict.
    """
    labels = _labels(user_id)
    names = {p.id: p.name for p in library}
    pattern_verdicts = _pattern_verdicts(user_id)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT pattern_id, other_pattern_id, verdict, note
                         FROM difference_verdicts WHERE user_id = %s""", (user_id,))
        verdicts = {(p, o): {"verdict": v, "note": n} for p, o, v, n in cur.fetchall()}
    out = []
    for p in library:
        sides, totals = _sides(labels, p.id)
        if not totals["better"] or not totals["worse"]:
            continue
        for other, better, worse in distinctive(sides):
            out.append({
                "patternId": p.id, "patternName": p.name,
                "otherId": other, "otherName": names.get(other, other),
                "worse": worse, "worseTotal": totals["worse"],
                "better": better, "betterTotal": totals["better"],
                "verdict": verdicts.get((p.id, other)),
                "patternVerdict": pattern_verdicts.get(p.id),
            })
    return sorted(out, key=lambda d: (-abs(d["worse"] - d["better"]), d["patternName"], d["otherName"]))


def set_difference_verdict(user_id: int, pattern_id: str, other_pattern_id: str,
                           verdict: str, note: str | None = None) -> None:
    """Whether a difference in outcome rings true to the owner."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO difference_verdicts (user_id, pattern_id, other_pattern_id, verdict, note)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (user_id, pattern_id, other_pattern_id) DO UPDATE
                  SET verdict = EXCLUDED.verdict, note = EXCLUDED.note, updated_at = now()""",
            (user_id, pattern_id, other_pattern_id, verdict, (note or "").strip() or None))
        conn.commit()


def set_occasion_verdict(user_id: int, pattern_id: str, occasion_id: int,
                         verdict: str | None, note: str | None = None) -> bool:
    """Whether this occasion is really an instance of the pattern. None clears it."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE pattern_labels l SET owner_verdict = %s, verdict_note = %s
                 FROM occasions o
                WHERE l.occasion_id = o.id AND o.user_id = %s
                  AND l.occasion_id = %s AND l.pattern_id = %s""",
            (verdict, (note or "").strip() or None, user_id, occasion_id, pattern_id))
        changed = cur.rowcount == 1
        conn.commit()
        return changed


def set_pattern_verdict(user_id: int, pattern_id: str, verdict: str, note: str | None = None) -> None:
    """Whether the pattern rings true to the owner at all."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO pattern_verdicts (user_id, pattern_id, verdict, note)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (user_id, pattern_id) DO UPDATE
                  SET verdict = EXCLUDED.verdict, note = EXCLUDED.note, updated_at = now()""",
            (user_id, pattern_id, verdict, (note or "").strip() or None))
        conn.commit()
