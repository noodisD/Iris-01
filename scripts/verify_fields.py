#!/usr/bin/env python3
"""Evaluate the production contextual field checker on current neutral v4 accounts.

    uv run python scripts/verify_fields.py --reviewed --dry-run
    uv run python scripts/verify_fields.py --reviewed

The owner creates new v4 field judgments first; historical v3 verdicts are
never mapped by array position. Unavailable and unclear are not negative facts.
No model is constructed until the cache and any reference pass preflight.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from collections import Counter
from pathlib import Path

from agent.connections import FIELD_PROMPT
from agent.episodes import GROUNDED_FIELDS
from agent.field_support import VERIFICATION_VERSION, check
from agent.reference_evaluation import CHECKED, account_fingerprint, score_results
from scripts.read_episodes import DEFAULT_CACHE, load_cache
from scripts.reference_labels import validate_reference

REFERENCE = "data/reference-labels-v4.json"


def _run_checks(episodes: list, wanted: list[int]) -> tuple[list[dict], dict]:
    """The only boundary permitted to construct the configured provider."""
    from agent.config import settings
    from agent.intelligence import Intelligence

    model = Intelligence(model=settings.OPENAI_WORKER_MODEL, service_tier=settings.OPENAI_WORKER_SERVICE_TIER or None)
    disabled = logging.root.manager.disable
    try:
        results = []
        for index in wanted:
            fingerprint = account_fingerprint(episodes[index].as_dict())
            results.append({"index": index, "key": fingerprint, "fingerprint": fingerprint,
                            "verdicts": check(episodes[index], model)})
    finally:
        logging.disable(disabled)
    return results, {"version": VERIFICATION_VERSION, "model": model.model,
                     "promptHash": hashlib.sha256(FIELD_PROMPT.encode()).hexdigest()}


def _print_score(score: dict) -> None:
    errors = score["overall"]["known_error"]
    correct = score["overall"]["correct"]
    unsure = score["overall"]["unsure"]
    print("\nAgainst the new reference, with full predeclared denominators:")
    print(f"errors caught           {errors['rejected']} of {errors['total']}")
    print(f"correct fields rejected {correct['rejected']} of {correct['total']}")
    print(f"unavailable on errors   {errors['unavailable']} of {errors['total']}")
    print(f"unavailable on correct  {correct['unavailable']} of {correct['total']}")
    print(f"reference unsure        {unsure['total']} (reported separately)")
    print(f"unjudged result fields  {score['missing_reference']['fields']}")
    for name, baseline in score["baselines"].items():
        error, good = baseline["known_error"], baseline["correct"]
        print(f"  {name}: catches {error['rejected']} of {error['total']}; "
              f"rejects {good['rejected']} of {good['total']} correct fields")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", default=DEFAULT_CACHE)
    parser.add_argument("--user", type=int, default=1)
    parser.add_argument("--reviewed", action="store_true")
    parser.add_argument("--limit", type=int, default=100_000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reference", default=REFERENCE)
    parser.add_argument("--out", help="new owner-only result artifact")
    args = parser.parse_args(argv)
    if args.limit <= 0 or args.user <= 0:
        print("Select a positive owner and limit.")
        return 1
    filename = "field-support-v4-reviewed.json" if args.reviewed else "field-support-v4.json"
    out = Path(args.out) if args.out else Path(args.cache).parent / filename
    protected = (Path(args.cache), Path(args.reference))
    if out.exists() or any(out.resolve() == path.resolve() for path in protected):
        print("Refusing to overwrite a cache, reference or previous result.")
        return 1
    try:
        episodes, _ = load_cache(Path(args.cache), args.user)
    except (OSError, ValueError, KeyError, TypeError):
        print("Could not read a current neutral v4 account cache.")
        return 1
    reference = None
    if args.reviewed:
        try:
            reference = json.loads(Path(args.reference).read_text())
            wanted = validate_reference(reference, [episode.as_dict() for episode in episodes])[:args.limit]
            keys = {account_fingerprint(episodes[index].as_dict()) for index in wanted}
            reference = {**reference, "cohort": [key for key in reference["cohort"] if key in keys],
                         "accounts": {key: row for key, row in reference["accounts"].items() if key in keys}}
            validate_reference(reference, [episode.as_dict() for episode in episodes])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"Reference not ready: {exc}")
            return 1
    else:
        wanted = list(range(min(len(episodes), args.limit)))
    askable = [index for index in wanted if any(getattr(episodes[index], field) is not None
                                               for field in GROUNDED_FIELDS)]
    print(f"{len(episodes)} v4 accounts in cache, {len(askable)} to check")
    if args.dry_run or not askable:
        print("No provider call or result file in dry-run/empty mode.")
        return 0
    started = time.time()
    results, metadata = _run_checks(episodes, askable)
    print(f"\nchecked {len(results)} account(s) in {round(time.time() - started)}s\n")
    print(f"{'field':<20} {'supported':>10} {'not_stated':>11} {'contradicted':>13}"
          f" {'unclear':>9} {'unavailable':>12}")
    for field in CHECKED:
        row = Counter(result["verdicts"].get(field) for result in results)
        print(f"{field:<20} {row['supported']:>10} {row['not_stated']:>11} "
              f"{row['contradicted']:>13} {row['unclear']:>9} {row['unavailable']:>12}")
    artifact = {**metadata, "formatVersion": 3,
                "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "fields": list(CHECKED), "results": results}
    if reference is not None:
        score = score_results(reference["accounts"], results)
        _print_score(score)
        artifact.update({"reference": reference, "score": score})
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(artifact, file, indent=1)
    except FileExistsError:
        print("Another checker result was written first; refusing to overwrite.")
        return 1
    print(f"\nwritten to {out}; source accounts and earlier judgments unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
