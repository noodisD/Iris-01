#!/usr/bin/env python3
"""Check whether an account's response and outcome are stated by its quotes.

Run against the reviewed accounts first. A checker that has not been measured
against known answers is a second opinion, not a check. The owner's completed,
fingerprinted labels are required; the earlier spot-check is not a substitute.

    uv run python scripts/verify_fields.py --reviewed   # measure it, ~10 calls
    uv run python scripts/verify_fields.py              # the whole cache
    uv run python scripts/verify_fields.py --dry-run    # what would be asked

Counts to the terminal, never an account and never a quote. The result is
written to data/, keyed by a hash of each account rather than its position, so
it can be read back after anything has been filtered.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.reference_evaluation import (
    CHECKED,
    account_fingerprint,
    account_key,
    score_results,
)
from scripts.reference_labels import validate_reference

#: Reference judgments live in a file the owner fills in, not in this script.
#: The first attempt hardcoded their words here and mapped "no" to not_stated,
#: which ran together a passage that says nothing, one that says the opposite,
#: and one that supports an intention the account reports as a deed.
REFERENCE = "data/reference-labels.json"


def _run_checks(episodes: list[dict], wanted: list[int]) -> tuple[list[dict], dict]:
    """Only this boundary imports the app and can contact a model.

    Reference validation and dry runs complete before reaching this function.
    Tests substitute this boundary with synthetic results, never an API client.
    """
    from agent.field_support import (  # noqa: PLC0415 -- preflight first
        SYSTEM_PROMPT,
        VERIFICATION_VERSION,
        check,
    )
    from agent.intelligence import Intelligence  # noqa: PLC0415 -- preflight first

    intelligence = Intelligence()
    results = []
    previous_logging_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        for i in wanted:
            results.append({"index": i, "key": account_key(episodes[i]),
                            "fingerprint": account_fingerprint(episodes[i]),
                            "verdicts": check(episodes[i], intelligence)})
    finally:
        logging.disable(previous_logging_level)
    return results, {"version": VERIFICATION_VERSION, "model": intelligence.model,
                     "promptHash": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()}


def _print_score(score: dict) -> None:
    errors = score["overall"]["known_error"]
    correct = score["overall"]["correct"]
    unsure = score["overall"]["unsure"]
    print("\nAgainst the reference judgments (full reference denominators):")
    print(f"errors caught           {errors['rejected']} of {errors['total']}")
    print(f"correct fields rejected {correct['rejected']} of {correct['total']}")
    print(f"unavailable on errors   {errors['unavailable']} of {errors['total']}")
    print(f"unavailable on correct  {correct['unavailable']} of {correct['total']}")
    print(f"reference unsure        {unsure['total']} (not scored)")
    print(f"  supported {unsure['supported']}, rejected {unsure['rejected']}, "
          f"unavailable {unsure['unavailable']}")
    print(f"unjudged result fields  {score['missing_reference']['fields']}")
    print("\nBaselines on the same complete reference:")
    for name, baseline in score["baselines"].items():
        err = baseline["known_error"]
        good = baseline["correct"]
        print(f"  {name}: catches {err['rejected']} of {err['total']}; "
              f"rejects {good['rejected']} of {good['total']} correct fields")
    print("Unavailable is a service/response failure, not a semantic abstention. "
          "Catching errors alone is not success; correct-field rejection and "
          "coverage matter too.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", default="data/episodes.json")
    ap.add_argument("--reviewed", action="store_true",
                    help="only the accounts the owner checked by hand, scored "
                         "against what they said")
    ap.add_argument("--limit", type=int, default=100_000)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reference", default=REFERENCE)
    ap.add_argument("--out", help="result artifact (defaults beside the cache)")
    args = ap.parse_args(argv)
    if args.limit <= 0:
        print("--limit must be positive.")
        return 1
    filename = "field-support-reviewed.json" if args.reviewed else "field-support.json"
    out = Path(args.out) if args.out else Path(args.cache).parent / filename
    protected = [Path(args.cache), Path(args.reference)]
    if any(out.resolve() == source.resolve()
           or (out.exists() and source.exists() and out.samefile(source)) for source in protected):
        print("Refusing to overwrite the cache or reference with checker results.")
        return 1
    try:
        episodes = json.loads(Path(args.cache).read_text())["episodes"]
        if not isinstance(episodes, list) or any(not isinstance(e, dict) for e in episodes):
            raise ValueError("Malformed episode cache.")
    except (OSError, ValueError, KeyError, TypeError):
        print("Could not read the episode cache.")
        return 1

    reference = None
    if args.reviewed:
        try:
            reference = json.loads(Path(args.reference).read_text())
            wanted = validate_reference(reference, episodes)[:args.limit]
            # --limit defines an explicit evaluation subset; unavailable model
            # answers must never define that subset after the fact.
            reference = {"version": reference["version"],
                         "cohort": [account_key(episodes[i]) for i in wanted], "accounts": {
                account_key(episodes[i]): reference["accounts"][account_key(episodes[i])]
                for i in wanted}}
            validate_reference(reference, episodes)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"Reference not ready: {exc}")
            print("Fill and parse a current fingerprinted sheet before evaluation.")
            return 1
    else:
        wanted = list(range(len(episodes)))[:args.limit]
    askable = [i for i in wanted if any(
        isinstance(episodes[i].get(f), str) and episodes[i][f].strip() for f in CHECKED)]

    print(f"{len(episodes)} accounts in the cache, {len(askable)} to ask about")
    if args.dry_run or not askable:
        print("Dry run or no populated fields: nothing was sent to the model.")
        return 0

    started = time.time()
    results, metadata = _run_checks(episodes, askable)

    print(f"\nasked about {len(results)} account(s) in {round(time.time() - started)}s\n")
    print(f"{'field':<10} {'supported':>10} {'not_stated':>11} {'contradicted':>13} {'unavailable':>12}")
    for field in CHECKED:
        row = Counter(result["verdicts"].get(field) for result in results)
        print(f"{field:<10} {row['supported']:>10} {row['not_stated']:>11} "
              f"{row['contradicted']:>13} {row['unavailable']:>12}")

    artifact = {
        **metadata,
        "formatVersion": 2,
        "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "fields": list(CHECKED),
        "results": results,
    }
    if reference is not None:
        score = score_results(reference["accounts"], results)
        _print_score(score)
        artifact.update({"reference": reference, "score": score})
    out.write_text(json.dumps(artifact, indent=1))
    print(f"\nwritten to {out}")
    print("No account was changed. The original cache is untouched, and every "
          "label or report made before this run is unvalidated until rechecked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
