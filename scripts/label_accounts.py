#!/usr/bin/env python3
"""Put every pattern in the library to every account, and keep the answers.

One call per pattern, and then the comparisons are arithmetic: which patterns
were also present on the occasions one of them went well, what was done on each
side, how any of it changed since last time. Counting and throwing the answers
away meant paying for the archive again to ask a second question about it.

    uv run python scripts/label_accounts.py --dry-run
    uv run python scripts/label_accounts.py
    uv run python scripts/label_accounts.py --library data/patterns/markets.json

The labels are cached beside the accounts in data/. A run that cannot reach the
model stops and keeps what it has.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time

logging.disable(logging.CRITICAL)

from pathlib import Path  # noqa: E402

from agent.connections import label_many, render  # noqa: E402
from agent.episodes import EXTRACTION_VERSION, Episode, comparable  # noqa: E402
from agent.intelligence import Intelligence  # noqa: E402
from agent.library import load  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", default="data/episodes.json")
    ap.add_argument("--labels", default="data/labels.json")
    ap.add_argument("--library", default=None)
    ap.add_argument("--again", action="store_true", help="relabel patterns already done")
    ap.add_argument("--batch", type=int, default=5,
                    help="how many patterns share a call. The accounts are the "
                         "expensive part of the prompt and go once per call; a "
                         "larger batch costs less and loses more when a reply "
                         "cannot be read")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cache = Path(args.cache)
    if not cache.exists():
        print(f"no accounts at {cache}: run scripts/read_episodes.py first.")
        return 1
    body = json.loads(cache.read_text())
    if body.get("version") != EXTRACTION_VERSION:
        print(f"cache is extraction version {body.get('version')}, this is "
              f"{EXTRACTION_VERSION}: read the archive again.")
        return 1

    episodes = [Episode.from_dict(e) for e in body["episodes"]]
    usable = comparable(episodes)
    patterns = load(Path(args.library) if args.library else None)

    store = Path(args.labels)
    kept = {}
    if store.exists():
        previous = json.loads(store.read_text())
        if previous.get("readAt") == body.get("readAt"):
            kept = previous.get("labels", {})
        else:
            print("the accounts changed since the last labelling; starting again")
    todo = [p for p in patterns if args.again or p.id not in kept]
    batches = [todo[i:i + args.batch] for i in range(0, len(todo), args.batch)]
    # The accounts dominate the prompt, so the cost of a run is roughly the
    # accounts times the number of calls. Said before anything is sent.
    per_call = len(render(usable)) // 4
    print(f"accounts: {len(usable)}  patterns: {len(patterns)}  to label: {len(todo)}")
    print(f"{len(batches)} call(s), about {per_call:,} tokens of accounts each "
          f"≈ {len(batches) * per_call // 1000}k tokens in. One call per pattern "
          f"would be {len(todo) * per_call // 1000}k.")
    if args.dry_run:
        print("dry run: nothing was sent.")
        return 0

    started = time.time()
    model = Intelligence()
    for batch in batches:
        labels, counts = label_many(
            [(p.id, p.statement, p.markers) for p in batch], episodes, model)
        if not counts["asked"]:
            print(f"  the model could not be asked — stopping, {len(kept)} pattern(s) kept.")
            break
        for pattern in batch:
            rows = labels.get(pattern.id)
            if rows is None:
                print(f"  {pattern.id}: no answer in the batch — not recorded")
                continue
            kept[pattern.id] = {str(i): answer for i, answer in rows.items()}
            print(f"  {pattern.id}: {len(rows)} accounts")
        # Written after each batch: a run that stops keeps what it paid for.
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text(json.dumps({"readAt": body.get("readAt"),
                                     "accounts": len(usable),
                                     "labelledAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                     "labels": kept}, indent=1))

    print(json.dumps({"patterns_labelled": len(kept), "accounts": len(usable),
                      "seconds": round(time.time() - started), "labels": str(store)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
