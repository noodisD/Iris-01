"""Conservative differences between confirmed day measurements and check-ins.

No journal words or coordinates enter this module. A permutation result is a
showing threshold, not a causal claim; only the owner can judge a comparison.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from datetime import date
from statistics import mean, median
from typing import Any, TypedDict

from agent.database import db
from agent.discovery import period_bounds
from agent.days.recompute import list_days

class DayResults(TypedDict):
    differences: list[dict]
    diagnostics: dict[str, Any]
    _details: dict[tuple[str, str], dict]


OUTCOMES = ("energy", "mood", "sleep_quality", "stress", "focus")
SPLITS = ("office_home", "commute", "steps", "screen_time", "social_share", "sleep")
VERDICTS = ("rings_true", "does_not", "unsure")
MIN_SIDE_DAYS = 5
MIN_GAP = 1.0
MAX_P = 0.01
SHUFFLES = 2000
MIN_LOCATION_COVERAGE = 0.5

OUTCOME_LABELS = {
    "energy": "Energy", "mood": "Mood", "sleep_quality": "Sleep quality",
    "stress": "Stress", "focus": "Focus",
}
SPLIT_LABELS = {
    "office_home": ("office days", "home days"),
    "commute": ("days above your median commute", "days below your median commute"),
    "steps": ("days above your median steps", "days below your median steps"),
    "screen_time": ("days above your median screen time", "days below your median screen time"),
    "social_share": ("days above your median social/video/game share",
                     "days below your median social/video/game share"),
    "sleep": ("days above your median sleep time", "days below your median sleep time"),
}


def scores_from_rows(rows: list[tuple[date, int | None, dict | None]]) -> dict[str, dict[str, float]]:
    """One self-report score per day, never one vote per journal entry."""
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for day, energy, metrics in rows:
        if day is None:
            continue
        values = grouped[day.isoformat()]
        if type(energy) is int and 1 <= energy <= 10:
            values["energy"].append(float(energy))
        if not isinstance(metrics, dict):
            continue
        for outcome in OUTCOMES[1:]:
            item = metrics.get(outcome)
            if not isinstance(item, dict) or item.get("source") != "checkin":
                continue
            value = item.get("value")
            if type(value) is int and 1 <= value <= 10:
                values[outcome].append(float(value))
    return {
        day: {outcome: mean(values) for outcome, values in outcomes.items()}
        for day, outcomes in grouped.items() if outcomes
    }


def _measurement(row: dict[str, Any], split: str) -> float | None:
    if split == "commute":
        return float(row["commuteMinutes"]) if row["locationCoverage"] >= MIN_LOCATION_COVERAGE else None
    if split == "steps":
        count = row["steps"]
        return float(count) if count is not None and row["stepsFullDay"] else None
    if split == "screen_time":
        return float(row["screenMinutes"]) if row["screenByCategory"] else None
    if split == "social_share":
        minutes = row["screenMinutes"]
        if not minutes or not row["screenByCategory"]:
            return None
        categories = row["screenByCategory"]
        return float(sum(categories.get(key, 0) for key in ("social", "video", "game")) / minutes)
    if split == "sleep":
        minutes = row["sleepMinutes"]
        return float(minutes) if minutes is not None else None
    return None


def permutation_p(left: list[float], right: list[float], seed: int) -> float:
    """Two-sided, add-one p-value from exactly 2,000 reproducible shuffles."""
    left_count, right_count = len(left), len(right)
    pool = [*left, *right]
    total = sum(pool)
    observed = abs(sum(left) / left_count - sum(right) / right_count)
    rng = random.Random(seed)
    extreme = 0
    for _ in range(SHUFFLES):
        rng.shuffle(pool)
        left_sum = 0.0
        for index in range(left_count):
            left_sum += pool[index]
        gap = abs(left_sum / left_count - (total - left_sum) / right_count)
        if gap >= observed - 1e-12:
            extreme += 1
    return (extreme + 1) / (SHUFFLES + 1)


def _seed(outcome: str, split: str) -> int:
    digest = hashlib.sha256(f"{outcome}:{split}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _sides(features: list[dict], split: str) -> dict[str, str]:
    """Assign only measured days, with median ties left out altogether."""
    if split == "office_home":
        return {
            row["day"]: "left" if row["dayKind"] == "office" else "right"
            for row in features
            if row["locationCoverage"] >= MIN_LOCATION_COVERAGE
            and row["dayKind"] in ("office", "home")
        }
    values = [(row["day"], value) for row in features
              if (value := _measurement(row, split)) is not None]
    if not values:
        return {}
    middle = median(value for _day, value in values)
    return {day: "left" if value > middle else "right"
            for day, value in values if value != middle}


def calculate(features: list[dict], scores: dict[str, dict[str, float]]) -> list[dict]:
    """Only qualifying comparisons. `features` is coordinate-free /api/days data."""
    result = []
    for split in SPLITS:
        side_by_day = _sides(features, split)
        if not side_by_day:
            continue
        for outcome in OUTCOMES:
            left = [values[outcome] for day, values in scores.items()
                    if side_by_day.get(day) == "left" and outcome in values]
            right = [values[outcome] for day, values in scores.items()
                     if side_by_day.get(day) == "right" and outcome in values]
            if len(left) < MIN_SIDE_DAYS or len(right) < MIN_SIDE_DAYS:
                continue
            left_mean, right_mean = mean(left), mean(right)
            if abs(left_mean - right_mean) < MIN_GAP:
                continue
            p = permutation_p(left, right, _seed(outcome, split))
            if p > MAX_P:
                continue
            left_label, right_label = SPLIT_LABELS[split]
            sentence = (f"{OUTCOME_LABELS[outcome]} averaged {left_mean:.1f} on {left_label} "
                        f"({len(left)} days) and {right_mean:.1f} on {right_label} "
                        f"({len(right)} days).")
            result.append({
                "outcome": outcome, "split": split, "sentence": sentence,
                "leftCount": len(left), "rightCount": len(right),
                "leftMean": round(left_mean, 1), "rightMean": round(right_mean, 1),
                "pValue": round(p, 4), "verdict": None,
            })
    return result

def _exclusions(features: list[dict], scores: dict[str, dict[str, float]],
                outcome: str, split: str) -> dict[str, int]:
    """One first-applicable exclusion reason per scored or measured day."""
    by_day = {row["day"]: row for row in features}
    sides = _sides(features, split)
    values = [v for row in features if (v := _measurement(row, split)) is not None]
    threshold = median(values) if values and split != "office_home" else None
    excluded = dict.fromkeys(("missingScore", "missingMeasurement", "lowCoverage",
                              "partialSteps", "medianTies"), 0)
    for day in by_day.keys() | scores.keys():
        row = by_day.get(day)
        if outcome not in scores.get(day, {}):
            reason = "missingScore"
        elif row is None:
            reason = "missingMeasurement"
        elif split in ("office_home", "commute") and row["locationCoverage"] < MIN_LOCATION_COVERAGE:
            reason = "lowCoverage"
        elif split == "steps" and row["steps"] is not None and not row["stepsFullDay"]:
            reason = "partialSteps"
        elif split != "office_home" and _measurement(row, split) is None:
            reason = "missingMeasurement"
        elif split == "office_home" and row["dayKind"] not in ("office", "home"):
            reason = "missingMeasurement"
        elif threshold is not None and _measurement(row, split) == threshold:
            reason = "medianTies"
        elif day not in sides:
            reason = "missingMeasurement"
        else:
            continue
        excluded[reason] += 1
    return excluded


def _read_inputs(user_id: int, period: str) -> tuple[list[dict], dict, dict, date]:
    start, as_of = period_bounds(period)
    features = list_days(user_id)
    if start is not None:
        lower, upper = start.isoformat(), as_of.isoformat()
        features = [row for row in features if lower <= row["day"] <= upper]
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id, reflection_date, energy_level, metrics FROM reflections
                WHERE user_id = %s AND reflection_date IS NOT NULL
                  AND (energy_level IS NOT NULL OR metrics IS NOT NULL)
                  AND (%s::date IS NULL OR reflection_date >= %s::date)
                  AND (%s::date IS NULL OR reflection_date <= %s::date)
                ORDER BY reflection_date, id""",
            (user_id, start, start, as_of if period != "all" else None,
             as_of if period != "all" else None))
        rows = cur.fetchall()
    scores = scores_from_rows([(day, energy, metrics) for _id, day, energy, metrics in rows])
    entry_ids: dict[tuple[str, str], list[str]] = defaultdict(list)
    for entry_id, day, energy, metrics in rows:
        valid = scores_from_rows([(day, energy, metrics)])
        for outcome in valid.get(day.isoformat(), {}):
            entry_ids[(day.isoformat(), outcome)].append(str(entry_id))
    return features, scores, entry_ids, as_of


def results(user_id: int, *, period: str = "all") -> DayResults:
    """Qualifying rows plus honest missing-input diagnostics and exact day groups."""
    features, scores, entry_ids, as_of = _read_inputs(user_id, period)
    found = calculate(features, scores)
    feature_by_day = {row["day"]: row for row in features}
    eligible = 0
    for split in SPLITS:
        sides = _sides(features, split)
        for outcome in OUTCOMES:
            counts = [sum(side == name and outcome in scores.get(day, {})
                          for day, side in sides.items()) for name in ("left", "right")]
            eligible += min(counts) >= MIN_SIDE_DAYS
    overlap = feature_by_day.keys() & scores.keys()
    reason = ("no_measured_days" if not features else
              "no_checkins" if not scores else
              "no_overlap" if not overlap else
              "insufficient_groups" if not eligible else
              "no_qualifying_difference" if not found else None)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT outcome, split, verdict, note FROM day_difference_verdicts
                        WHERE user_id = %s""", (user_id,))
        opinions = {(outcome, split): {"verdict": verdict, "note": note}
                    for outcome, split, verdict, note in cur.fetchall()}
    details: dict[tuple[str, str], dict] = {}
    for item in found:
        split, outcome = item["split"], item["outcome"]
        sides = _sides(features, split)
        measurement = {row["day"]: (
            row["dayKind"] if split == "office_home" else _measurement(row, split))
            for row in features}
        grouped: dict[str, list[dict[str, Any]]] = {"left": [], "right": []}
        for day, side in sides.items():
            if outcome in scores.get(day, {}):
                grouped[side].append({"day": day, "value": scores[day][outcome],
                                      "splitValue": measurement[day],
                                      "entryIds": entry_ids.get((day, outcome), [])})
        for group in grouped.values():
            group.sort(key=lambda row: row["day"], reverse=True)
        days = sorted(row["day"] for group in grouped.values() for row in group)
        threshold_values = [value for row in features
                            if (value := _measurement(row, split)) is not None]
        item["coverage"] = {
            "range": period, "asOf": as_of.isoformat(),
            "recordedFrom": days[0], "recordedTo": days[-1],
            "measuredDays": len(features), "checkinDays": len(scores),
            "overlappingDays": len(overlap)}
        item["leftLabel"], item["rightLabel"] = SPLIT_LABELS[split]
        item["threshold"] = (median(threshold_values)
                             if split != "office_home" and threshold_values else None)
        item["verdict"] = opinions.get((outcome, split))
        payload = json.dumps([period, outcome, split, grouped, item["threshold"],
                              item["verdict"]], sort_keys=True, separators=(",", ":"))
        item["snapshot"] = hashlib.sha256(payload.encode()).hexdigest()
        details[(outcome, split)] = {
            "difference": item, "leftDays": grouped["left"], "rightDays": grouped["right"],
            "excluded": _exclusions(features, scores, outcome, split)}
    return {"differences": found, "diagnostics": {
        "measuredDays": len(features), "checkinDays": len(scores),
        "overlappingDays": len(overlap), "eligibleComparisons": eligible, "reason": reason},
        "_details": details}


def detail_for_user(user_id: int, outcome: str, split: str, *,
                    period: str = "all") -> dict | None:
    return results(user_id, period=period)["_details"].get((outcome, split))


def for_user(user_id: int, *, period: str = "all") -> list[dict]:
    """Read qualifying, source-linked comparisons in the selected period."""
    return results(user_id, period=period)["differences"]


def set_verdict(user_id: int, outcome: str, split: str, verdict: str | None,
                note: str | None = None) -> None:
    """Replace the owner's whole feedback record, including note-only feedback."""
    if outcome not in OUTCOMES or split not in SPLITS or (verdict is not None and verdict not in VERDICTS):
        raise ValueError("No such day comparison or verdict")
    cleaned_note = (note or "").strip() or None
    with db.connection() as conn, conn.cursor() as cur:
        if verdict is None and cleaned_note is None:
            cur.execute(
                """DELETE FROM day_difference_verdicts
                    WHERE user_id = %s AND outcome = %s AND split = %s""",
                (user_id, outcome, split),
            )
        else:
            cur.execute(
                """INSERT INTO day_difference_verdicts (user_id, outcome, split, verdict, note)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (user_id, outcome, split) DO UPDATE
                       SET verdict = EXCLUDED.verdict, note = EXCLUDED.note, updated_at = now()""",
                (user_id, outcome, split, verdict, cleaned_note),
            )
        conn.commit()
