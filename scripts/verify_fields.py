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

#: What the owner said about each field, from data/spot-check.md, in their
#: words. Mapped to an expected verdict only where the wording is unambiguous;
#: a hedge is kept as a hedge rather than rounded into agreement.
REVIEWED: dict[int, dict[str, str]] = {
    0:  {"response": "no", "outcome": "inferred"},
    1:  {"response": "yeh kind of but not exeactly", "outcome": "its not I guess"},
    2:  {"response": "no", "outcome": "its not looks ok"},
    3:  {"response": "yes", "outcome": "its not a good outcome"},
    4:  {"response": "yes", "outcome": "its absent"},
    9:  {"response": "yes", "outcome": "its not"},
    10: {"response": "no it is not accurate", "outcome": "its not"},
    48: {"response": "yes", "outcome": "yes"},
    61: {"response": "kind of", "outcome": "absent"},
    72: {"response": "yes", "outcome": "yes"},
}

#: Only the wordings that plainly mean one thing. "its not a good outcome"
#: judges the occasion, not the extraction, and "kind of" is a hedge: both are
#: excluded from scoring rather than guessed at, and reported as excluded.
EXPECTED = {
    "yes": "supported",
    "no": "not_stated",
    "no it is not accurate": "not_stated",
    "its not": "not_stated",
    "its not I guess": "not_stated",
    "inferred": "not_stated",
}


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
    wanted = sorted(REVIEWED) if args.reviewed else range(len(episodes))
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
        print("\nAgainst what the owner said:\n")
        print(f"{'account':<9} {'field':<10} {'owner':<30} {'checker':<13} agrees")
        print("-" * 78)
        agreed = scored = skipped = 0
        for row in results:
            for field, verdict in row["verdicts"].items():
                said = REVIEWED[row["index"]].get(field, "")
                expected = EXPECTED.get(said)
                if expected is None:
                    skipped += 1
                    mark = "(not scored)"
                else:
                    scored += 1
                    ok = expected == verdict
                    agreed += ok
                    mark = "yes" if ok else "NO"
                print(f"#{row['index']:<8} {field:<10} {said[:29]:<30} {verdict:<13} {mark}")
        if scored:
            print(f"\nagreed on {agreed} of {scored} scorable verdicts "
                  f"({agreed / scored:.0%}); {skipped} not scored because the "
                  "owner's wording was a hedge or judged the occasion rather "
                  "than the extraction")
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
