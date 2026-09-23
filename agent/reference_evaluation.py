"""Pure reference identity and scoring; no database, settings, or model calls."""

from __future__ import annotations

import hashlib
import json
import re

CHECKED = ("response", "outcome")
FAILING = ("not_stated", "contradicted", "wrong_modality", "wrong_actor")
REFERENCE_VERDICTS = ("supported", *FAILING, "unsure")
CHECKER_VERDICTS = ("supported", "not_stated", "contradicted", "unavailable")


def account_key(episode: dict) -> str:
    """Legacy account locator, NOT a version of its claims or evidence."""
    parts = [(episode.get("situation") or ""), (episode.get("response") or "")]
    parts += sorted(f"{c.get('sourceType', 'reflection')}:{c.get('entryId')}"
                    for c in episode.get("citations", []))
    return hashlib.sha1("\u0000".join(parts).encode()).hexdigest()[:12]


def account_fingerprint(episode: dict) -> str:
    """Bind judgments to all cached account content, independent of citation order.

    Keep the locator separate: outcome, actor and modality edits do not change
    its legacy key. They MUST invalidate the associated judgments. Including
    every field also covers evidence dates and future extraction metadata.
    """
    def canonical(value: object) -> str:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    content = {key: value for key, value in episode.items() if key != "citations"}
    content["citations"] = sorted(episode.get("citations", []), key=canonical)
    payload = {"fingerprint_version": 1, "account": content}
    return hashlib.sha256(canonical(payload).encode()).hexdigest()


def _class_counts() -> dict:
    return {name: dict.fromkeys(("total", *CHECKER_VERDICTS, "rejected"), 0)
            for name in ("correct", "known_error", "unsure")}


def _index_results(reference: dict, results: list[dict]) -> tuple[dict, dict]:
    """Reject stale or ambiguous results before scoring; count unjudged output."""
    for ref in reference.values():
        fingerprint = ref.get("fingerprint")
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise ValueError("Reference content fingerprint is missing or malformed.")
    indexed = {}
    missing = {"accounts": 0, "fields": 0}
    for row in results:
        key = row["key"]
        if key in indexed:
            raise ValueError("Duplicate account in checker results.")
        indexed[key] = row
        if key not in reference:
            missing["accounts"] += 1
            missing["fields"] += len(row.get("verdicts", {}))
            continue
        if row.get("fingerprint") != reference[key].get("fingerprint"):
            raise ValueError("Checker result does not match the reference content.")
        missing["fields"] += len(set(row.get("verdicts", {}))
                                 - set(reference[key]["verdicts"]))
    return indexed, missing


def score_results(reference: dict, results: list[dict]) -> dict:
    """Score against fixed reference totals, not just successful model answers.

    Missing results/fields are unavailable, not a negative semantic judgment.
    `unsure` has its own distribution. Unjudged outputs are reported separately.
    Mismatched content, duplicate results and invalid verdicts fail explicitly.
    """
    indexed, missing = _index_results(reference, results)
    overall = _class_counts()
    by_field = {field: _class_counts() for field in CHECKED}
    for key, ref in reference.items():
        verdicts = indexed.get(key, {}).get("verdicts", {})
        for field, expected in ref["verdicts"].items():
            if field not in CHECKED or expected not in REFERENCE_VERDICTS:
                raise ValueError("Invalid reference field or verdict.")
            verdict = verdicts.get(field, "unavailable")
            if verdict not in CHECKER_VERDICTS:
                raise ValueError("Invalid checker verdict.")
            category = ("correct" if expected == "supported" else
                        "unsure" if expected == "unsure" else "known_error")
            for group in (overall, by_field[field]):
                counts = group[category]
                counts["total"] += 1
                counts[verdict] += 1
                counts["rejected"] += verdict in ("not_stated", "contradicted")

    baselines = {}
    for name, verdict in (("constant_supported", "supported"),
                          ("constant_reject", "not_stated")):
        baseline = _class_counts()
        for category, counts in overall.items():
            total = counts["total"]
            baseline[category]["total"] = total
            baseline[category][verdict] = total
            baseline[category]["rejected"] = total if verdict == "not_stated" else 0
        baselines[name] = baseline
    return {"overall": overall, "by_field": by_field,
            "missing_reference": missing, "baselines": baselines}
