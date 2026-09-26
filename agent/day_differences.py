"""Conservative differences between confirmed day measurements and check-ins.

No journal words or coordinates enter this module. A permutation result is a
showing threshold, not a causal claim; only the owner can judge a comparison.
"""

from __future__ import annotations

import hashlib
import random
from collections import defaultdict
from datetime import date
from statistics import mean, median
from typing import Any

from agent.database import db
from agent.days.recompute import list_days

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


def for_user(user_id: int) -> list[dict]:
    """Read confirmed day cache and self-report numbers, not journal words."""
    features = list_days(user_id)
    if not features:
        return []
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT reflection_date, energy_level, metrics FROM reflections
                WHERE user_id = %s AND reflection_date IS NOT NULL
                  AND (energy_level IS NOT NULL OR metrics IS NOT NULL)
                ORDER BY reflection_date, id""",
            (user_id,),
        )
        scores = scores_from_rows(cur.fetchall())
        differences = calculate(features, scores)
        if not differences:
            return []
        cur.execute(
            """SELECT outcome, split, verdict, note FROM day_difference_verdicts
                WHERE user_id = %s""", (user_id,),
        )
        verdicts = {(outcome, split): {"verdict": verdict, "note": note}
                    for outcome, split, verdict, note in cur.fetchall()}
    for item in differences:
        item["verdict"] = verdicts.get((item["outcome"], item["split"]))
    return differences


def set_verdict(user_id: int, outcome: str, split: str, verdict: str,
                note: str | None = None) -> None:
    """Store a verdict independently of today's comparison eligibility."""
    if outcome not in OUTCOMES or split not in SPLITS or verdict not in VERDICTS:
        raise ValueError("No such day comparison or verdict")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO day_difference_verdicts (user_id, outcome, split, verdict, note)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (user_id, outcome, split) DO UPDATE
                   SET verdict = EXCLUDED.verdict, note = EXCLUDED.note, updated_at = now()""",
            (user_id, outcome, split, verdict, (note or "").strip() or None),
        )
        conn.commit()
