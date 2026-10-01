#!/usr/bin/env python3
"""Read eligible journal sources into a local, neutral v4 diagnostic cache.

    uv run python scripts/read_episodes.py --dry-run
    uv run python scripts/read_episodes.py --reuse
    uv run python scripts/read_episodes.py --limit 40

This cache is diagnostic, never imported into the live discovery tables.
Only eligible original reflections are included; unaccepted staged/import-only
material is excluded. The prior data/episodes.json is historical and untouched.
Counts print to the terminal, never accounts or passages.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

if __name__ == "__main__":
    logging.disable(logging.CRITICAL)

from agent.config import settings
from agent.database import db
from agent.discovery_worker import verify_reading
from agent.episodes import EXTRACTION_VERSION, Episode, EpisodeReader, ReadUnavailable, tally
from agent.intelligence import Intelligence
from agent.observations import chunk_entries, interleave
from agent.reading_version import VERIFIED_READER_VERSION

DEFAULT_CACHE = "data/episodes-v4.json"
HISTORICAL_CACHE = Path("data/episodes.json").resolve()


def load_cache(path: Path, user_id: int) -> tuple[list[Episode], dict]:
    body = json.loads(path.read_text())
    if (not isinstance(body, dict) or body.get("version") != EXTRACTION_VERSION or
            body.get("readerVersion") != VERIFIED_READER_VERSION or
            body.get("includesStaged") is not False or
            body.get("user") != user_id or
            not isinstance(body.get("episodes"), list) or
            not isinstance(body.get("sourceRevisions"), dict) or
            any(not key.isdigit() or type(value) is not int or value < 1
                for key, value in body["sourceRevisions"].items())):
        raise ValueError("cache is not a neutral current v4 reading for this owner")
    episodes = [Episode.from_dict(row) for row in body["episodes"]]
    if (not isinstance(body.get("entriesRead"), int) or
            body["entriesRead"] != len(body["sourceRevisions"]) or
            any(str(c.entry_id) not in body["sourceRevisions"]
                for episode in episodes for c in episode.citations)):
        raise ValueError("cached accounts do not match the recorded source manifest")
    return episodes, body


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user", type=int, default=1)
    ap.add_argument("--limit", type=int, default=100_000,
                    help="eligible original entries to read, newest first")
    ap.add_argument("--dry-run", action="store_true", help="count without contacting a provider")
    ap.add_argument("--reuse", action="store_true", help="validate and count an existing v4 cache")
    ap.add_argument("--cache", default=DEFAULT_CACHE, help="new local owner-only cache")
    ap.add_argument("--readable", default="data/readable.json",
                    help="optional punctuated copies; citations resolve against original entries")
    args = ap.parse_args(argv)
    if args.limit <= 0 or args.user <= 0 or (args.dry_run and args.reuse):
        print("Select a positive owner/limit and at most one of --dry-run or --reuse.")
        return 1
    cache = Path(args.cache)
    if args.reuse:
        try:
            episodes, body = load_cache(cache, args.user)
        except (OSError, ValueError, KeyError, TypeError):
            print("No usable current v4 cache; read eligible sources into a new cache.")
            return 1
        print(json.dumps({**tally(episodes), "from_cache": str(cache),
                          "read_at": body.get("readAt")}, indent=1))
        return 0

    entries = db.get_entries_for_reading(args.user, limit=args.limit)
    source_revisions = {str(row["id"]): row["discovery_revision"] for row in entries}
    chunks = chunk_entries(interleave(entries))
    print(f"eligible entries: {len(entries)}  passes: {len(chunks)}")
    if args.dry_run:
        print("dry run: no provider call or cache write.")
        return 0
    if cache.resolve() == HISTORICAL_CACHE or cache.exists():
        print("Refusing to overwrite an old or existing cache; choose a new --cache path.")
        return 1
    copies = {}
    readable = Path(args.readable)
    if readable.exists():
        body = json.loads(readable.read_text())
        copies = body.get("copies", {})
        if not isinstance(copies, dict):
            raise ValueError("invalid readable copy format")

    started = time.time()
    model = Intelligence(model=settings.OPENAI_WORKER_MODEL) if entries else None
    reader = EpisodeReader(args.user, intelligence=model)
    try:
        extracted = reader.read(entries, copies)
        episodes, dropped, omitted = verify_reading(extracted, model)
    except (ReadUnavailable, ValueError):
        print("reading unavailable: no diagnostic cache was written.", file=sys.stderr)
        return 1
    counts = tally(episodes)
    counts.update({
        "entries_read": len(entries), "passes": len(chunks),
        "seconds": round(time.time() - started),
        "omitted_accounts": reader.omitted_accounts + dropped,
        "omitted_fields": reader.omitted_fields + omitted,
        "entries_with_an_account": len({c.entry_id for e in episodes for c in e.citations}),
    })
    payload = {"version": EXTRACTION_VERSION, "readerVersion": VERIFIED_READER_VERSION,
               "readAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "user": args.user,
               "entriesRead": len(entries), "sourceRevisions": source_revisions,
               "includesStaged": False, "omittedAccounts": counts["omitted_accounts"],
               "omittedFields": counts["omitted_fields"],
               "episodes": [e.as_dict() for e in episodes]}
    cache.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(cache, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(payload, output, indent=1)
    except FileExistsError:
        print("Another cache was written first; refusing to overwrite it.")
        return 1
    print(json.dumps({**counts, "cached_at": str(cache)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
