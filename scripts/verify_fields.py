#!/usr/bin/env python3
"""Check whether an account's response and outcome are stated by its quotes.

Run against the reviewed accounts first. A checker that has not been measured
against known answers is a second opinion, not a check, and the ten accounts
the owner went through by hand are the only known answers this system has.

    uv run python scripts/verify_fields.py --reviewed   # measure it, ~10 calls
    uv run python scripts/verify_fields.py              # the whole cache
    uv run python scripts/verify_fields.py --dry-run    # what would be asked

Counts to the terminal, never an account and never a quote. The result is
written to data/, keyed by a hash of each account rather than its position, so
it can be read back after anything has been filtered.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

logging.disable(logging.CRITICAL)

from agent.field_support import (  # noqa: E402
    CHECKED, VERIFICATION_VERSION, account_key, check, tally)
from agent.intelligence import Intelligence  # noqa: E402

#: Reference judgments live in a file the owner fills in, not in this script.
#: The first attempt hardcoded their words here and mapped "no" to not_stated,
#: which ran together a passage that says nothing, one that says the opposite,
#: and one that supports an intention the account reports as a deed.
REFERENCE = "data/reference-labels.json"

#: A reference verdict meaning the field should NOT have been admitted. Kept as
#: a set rather than "anything but supported", so `unsure` stays unscored.
FAILING = ("not_stated", "contradicted", "wrong_modality", "wrong_actor")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", default="data/episodes.json")
    ap.add_argument("--reviewed", action="store_true",
                    help="only the accounts the owner checked by hand, scored "
                         "against what they said")
    ap.add_argument("--limit", type=int, default=100_000)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    episodes = json.loads(Path(args.cache).read_text())["episodes"]
    if args.reviewed:
        # Whichever accounts the reference file holds, rather than a list kept
        # in step by hand: the reference is the only thing that says which
        # accounts have known answers.
        reference = json.loads(Path(REFERENCE).read_text()) if Path(REFERENCE).exists() else {}
        by_key = {account_key(e): i for i, e in enumerate(episodes)}
        wanted = sorted(by_key[k] for k in reference if k in by_key)
        if not wanted:
            print(f"No reference judgments at {REFERENCE}. Build and fill "
                  "data/reference-labels.md, then `reference_labels.py read`.")
            return 1
    else:
        wanted = range(len(episodes))
    wanted = list(wanted)[:args.limit]
    askable = [i for i in wanted if any(episodes[i].get(f) for f in CHECKED)]

    print(f"{len(episodes)} accounts in the cache, {len(askable)} to ask about")
    if args.dry_run:
        print("dry run: nothing was sent to the model.")
        return 0

    intelligence = Intelligence()
    results = []
    started = time.time()
    for i in askable:
        verdicts = check(episodes[i], intelligence)
        results.append({"index": i, "key": account_key(episodes[i]),
                        "verdicts": verdicts})

    counts = tally(results)
    print(f"\nasked about {len(results)} account(s) in {round(time.time() - started)}s\n")
    print(f"{'field':<10} {'supported':>10} {'not_stated':>11} {'contradicted':>13} {'unavailable':>12}")
    for field, row in counts.items():
        print(f"{field:<10} {row['supported']:>10} {row['not_stated']:>11} "
              f"{row['contradicted']:>13} {row['unavailable']:>12}")

    if args.reviewed:
        ref_path = Path(REFERENCE)
        if not ref_path.exists():
            print(f"\nNo reference judgments at {ref_path}. Build and fill "
                  "data/reference-labels.md, then `reference_labels.py read`. "
                  "Nothing is scored against guesses.")
            return 1
        reference = json.loads(ref_path.read_text())

        caught = missed = rejected = kept = abstained = unscored = 0
        print("\nAgainst the reference judgments:\n")
        print(f"{'account':<9} {'field':<10} {'reference':<16} {'checker':<13}")
        print("-" * 52)
        for row in results:
            ref = reference.get(row["key"], {}).get("verdicts", {})
            for field, verdict in row["verdicts"].items():
                expected = ref.get(field)
                print(f"#{row['index']:<8} {field:<10} {expected or '—':<16} {verdict:<13}")
                if expected is None or expected == "unsure":
                    unscored += 1
                elif verdict == "unavailable":
                    abstained += 1
                elif expected in FAILING:
                    caught += verdict != "supported"
                    missed += verdict == "supported"
                else:
                    kept += verdict == "supported"
                    rejected += verdict != "supported"

        errors = caught + missed
        correct = kept + rejected
        print(f"\nerrors caught          {caught} of {errors}"
              + (f"  ({caught / errors:.0%})" if errors else ""))
        print(f"correct fields rejected {rejected} of {correct}"
              + (f"  ({rejected / correct:.0%})" if correct else ""))
        print(f"abstained (unavailable) {abstained}")
        print(f"not scored              {unscored}  (ambiguous or unjudged)")
        print("\nA checker that answered \"supported\" every time would catch "
              f"0 of {errors} and reject 0 of {correct}. Anything that does not "
              "beat that on the first number is not checking anything.")
        return 0

    out = Path(args.cache).parent / "field-support.json"
    out.write_text(json.dumps({
        "version": VERIFICATION_VERSION,
        "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "fields": list(CHECKED),
        "results": results,
    }, indent=1))
    print(f"\nwritten to {out}")
    print("No account was changed. The original cache is untouched, and every "
          "label or report made before this run is unvalidated until rechecked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
