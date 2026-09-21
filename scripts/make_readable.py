#!/usr/bin/env python3
"""Make a reading copy of each entry: same words, punctuated.

Dictated entries arrive as one long breath, and a model reads them worse than
it reads the same words laid out properly. This asks for punctuation, capitals
and paragraph breaks — and refuses any copy that changed, added or lost a
single word, because every quote this system shows the owner has to exist in
what they actually wrote.

The copies are a reading aid. They are cached beside the accounts in data/,
they never replace an entry, and quotes taken from them are resolved back to
the owner's own text before anything is stored or shown.

    uv run python scripts/make_readable.py --dry-run
    uv run python scripts/make_readable.py --limit 20     # a cheap first look
    uv run python scripts/make_readable.py

Counts to the terminal: how many were tidied, and how many were refused for
changing a word — which is the number worth watching.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time

logging.disable(logging.CRITICAL)

from pathlib import Path  # noqa: E402

from agent.database import db  # noqa: E402
from agent.intelligence import Intelligence  # noqa: E402
from agent.readable import needs_tidying, readable, words  # noqa: E402

VERSION = 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user", type=int, default=1)
    ap.add_argument("--limit", type=int, default=100_000)
    ap.add_argument("--cache", default="data/readable.json")
    ap.add_argument("--all", action="store_true",
                    help="tidy every entry, not only the ones read as one breath")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    entries = list(db.get_entries_for_reading(args.user, limit=args.limit))
    cache = Path(args.cache)
    done = {}
    if cache.exists():
        body = json.loads(cache.read_text())
        if body.get("version") == VERSION:
            done = body.get("copies", {})

    wanted = [e for e in entries if args.all or needs_tidying(e["content"])]
    todo = [e for e in wanted if str(e["id"]) not in done]
    print(f"entries: {len(entries)}  read as one breath: {len(wanted)}  "
          f"already tidied: {len(done)}  to do: {len(todo)}")
    if args.dry_run:
        print("dry run: nothing was sent to the model.")
        return 0

    started = time.time()
    model = Intelligence()
    why: dict[str, int] = {}
    for entry in todo:
        copy, reason = readable(entry["content"], model)
        why[reason] = why.get(reason, 0) + 1
        if copy is not None:
            done[str(entry["id"])] = copy
        elif reason == "unavailable":
            # No point asking two hundred more times.
            print("the model could not be reached; stopping.")
            break

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"version": VERSION, "user": args.user,
                                 "madeAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                 "copies": done}, indent=1))

    print(json.dumps({
        "tidied": why.get("ok", 0),
        "refused_for_changing_a_word": why.get("changed_words", 0),
        "unusable_answer": why.get("unusable_answer", 0),
        "model_unavailable": why.get("unavailable", 0),
        "cached": len(done),
        "words_unchanged": all(words(e["content"]) == words(done[str(e["id"])])
                               for e in entries if str(e["id"]) in done),
        "seconds": round(time.time() - started),
        "cache": str(cache),
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
