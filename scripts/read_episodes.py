#!/usr/bin/env python3
"""Read the archive once for accounts of occasions, and report counts.

This answers the question that decides whether comparing episodes is worth
building: how many of the owner's entries contain an occasion at all — a
situation, what it demanded, what came in, what they did, what followed — and
how many of those are their own, actually happened, and have every part stated.
Two accounts are needed before any shape can be shared; if the count comes back
in single figures, a comparison pass has nothing to compare.

It prints counts, never an account and never a quote. The accounts themselves
are written only to the local cache described below.

It sends entries to the model, exactly as discovery does, so it runs when the
owner asks and at no other time.

The accounts are kept in data/ — gitignored, on this machine, never sent
anywhere — so the archive is read once and every later experiment runs against
that reading instead of paying for another. The cache records the extraction
version; a change to the frame or the prompt makes an old cache unusable rather
than silently mixed with a new one.

    uv run python scripts/read_episodes.py --dry-run      # what would be read
    uv run python scripts/read_episodes.py                # one pass, cached
    uv run python scripts/read_episodes.py --reuse        # counts from the cache, free
    uv run python scripts/read_episodes.py --limit 40     # a cheaper first look
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time

# The reader logs what it refuses, and what it refuses is the owner's writing.
logging.disable(logging.CRITICAL)

from pathlib import Path  # noqa: E402

from agent.database import db  # noqa: E402
from agent.episodes import EXTRACTION_VERSION, Episode, EpisodeReader, tally  # noqa: E402
from agent.intelligence import Intelligence  # noqa: E402
from agent.observations import chunk_entries, interleave  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user", type=int, default=1)
    ap.add_argument("--limit", type=int, default=100_000,
                    help="how many entries to read, newest first")
    ap.add_argument("--no-staged", action="store_true",
                    help="skip undated recordings, which can describe an occasion "
                         "but can never say when it happened")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be read and how many passes it takes, "
                         "without sending anything to the model")
    ap.add_argument("--reuse", action="store_true",
                    help="read the cached accounts instead of the archive")
    ap.add_argument("--cache", default="data/episodes.json",
                    help="where the accounts are kept; gitignored and local")
    args = ap.parse_args()

    cache = Path(args.cache)
    if args.reuse:
        if not cache.exists():
            print(f"no cache at {cache}: run without --reuse first.")
            return 1
        body = json.loads(cache.read_text())
        if body.get("version") != EXTRACTION_VERSION:
            print(f"cache was made by extraction version {body.get('version')}, "
                  f"this is {EXTRACTION_VERSION}: read again.")
            return 1
        episodes = [Episode.from_dict(e) for e in body["episodes"]]
        print(json.dumps({**tally(episodes), "from_cache": str(cache),
                          "read_at": body.get("readAt")}, indent=1))
        return 0

    entries = list(db.get_entries_for_reading(args.user, limit=args.limit))
    if not args.no_staged:
        from agent.constants import OBSERVATION_MIN_STAGED_CHARS
        entries += db.get_staged_for_reading(args.user, OBSERVATION_MIN_STAGED_CHARS)

    chunks = chunk_entries(interleave(entries))
    print(f"entries: {len(entries)}  passes: {len(chunks)}")
    if args.dry_run:
        print("dry run: nothing was sent to the model.")
        return 0

    started = time.time()
    episodes = EpisodeReader(args.user, intelligence=Intelligence()).read(entries)
    counts = tally(episodes)
    counts["entries_read"] = len(entries)
    counts["passes"] = len(chunks)
    counts["seconds"] = round(time.time() - started)
    # Which entries yielded one, as a count of entries rather than of episodes:
    # a single long entry can carry several, and "half the archive describes
    # occasions" is a different fact from "there are eighty episodes".
    counts["entries_with_an_episode"] = len(
        {c.key for e in episodes for c in e.citations})

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({
        "version": EXTRACTION_VERSION,
        "readAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "user": args.user,
        "entriesRead": len(entries),
        "episodes": [e.as_dict() for e in episodes],
    }, indent=1))
    counts["cached_at"] = str(cache)

    print(json.dumps(counts, indent=1))
    if counts["comparable"] < 2:
        print("\nFewer than two comparable occasions: there is nothing to compare "
              "shapes between yet. The honest surface is the account itself and "
              "the owner's own connection to it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
