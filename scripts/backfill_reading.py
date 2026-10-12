#!/usr/bin/env python3
"""Give existing entries their reading copies and passages (migration 0050).

New entries get both as they are processed. This catches up the archive:

    uv run python scripts/backfill_reading.py              # what it would do, and cost; sends nothing
    uv run python scripts/backfill_reading.py --apply      # copies from data/readable.json, passages
    uv run python scripts/backfill_reading.py --reread     # read the entries with copies again

--apply stores the reading copies already made by scripts/make_readable.py
(each checked word for word against the entry as it is now), makes any missing
ones with the worker model, and cuts and embeds every long entry's passages.
--reread queues the entries that have a reading copy to be read again, which
replaces their accounts and sets off one pattern update. Counts only.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

if __name__ == "__main__":
    logging.disable(logging.CRITICAL)

from agent.config import settings  # noqa: E402
from agent.database import db  # noqa: E402
from agent.entry_passages import MIN_WORDS  # noqa: E402
from agent.intelligence import Intelligence  # noqa: E402
from agent.readable import current_copy, needs_tidying, same_words  # noqa: E402


def _entries(user_id: int) -> list[dict]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id, content, content_format, reading_copy, evidence_eligible
                         FROM reflections
                        WHERE user_id = %s AND content_format <> 'session'
                          AND length(btrim(coalesce(content, ''))) > 0
                        ORDER BY id""", (user_id,))
        keys = ("id", "content", "content_format", "reading_copy", "eligible")
        return [dict(zip(keys, row)) for row in cur.fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user", type=int, default=1)
    ap.add_argument("--cache", default="data/readable.json")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--reread", action="store_true")
    args = ap.parse_args()

    cache = Path(args.cache)
    cached = json.loads(cache.read_text()).get("copies", {}) if cache.exists() else {}
    entries = _entries(args.user)
    usable = {e["id"]: cached[str(e["id"])] for e in entries
              if str(e["id"]) in cached and same_words(e["content"], cached[str(e["id"])])}
    have = {e["id"] for e in entries if current_copy(e["content"], e["reading_copy"])}
    missing = [e for e in entries if needs_tidying(e["content"]) and e["id"] not in have | set(usable)]
    long = [e for e in entries if len(e["content"].split()) > MIN_WORDS]
    worker = settings.OPENAI_WORKER_MODEL
    chars = sum(len(e["content"]) for e in missing)
    print(f"entries: {len(entries)}  with a reading copy: {len(have)}  cached copies usable: "
          f"{len(set(usable) - have)} (stale: {len(cached) - len(usable)})  still to make: {len(missing)}")
    print(f"  making them: {Intelligence.estimate(worker, chars // 3, chars // 12)}")
    words = sum(len(e["content"].split()) for e in long)
    print(f"long entries (over {MIN_WORDS} words): {len(long)}, about {words // 150} passages; "
          f"embedding {Intelligence.estimate('text-embedding-3-small', words * 2)}")

    if args.apply:
        from agent.pipeline import _index_entry_passages

        with db.connection() as conn, conn.cursor() as cur:
            for reflection_id, copy in usable.items():
                if reflection_id not in have:
                    cur.execute("UPDATE reflections SET reading_copy = %s WHERE id = %s;", (copy, reflection_id))
            conn.commit()
        made = sum(1 for e in long if _index_entry_passages(args.user, e["id"], e["content"], e["content_format"]))
        # Short dictated entries get no passages, but still want their copy.
        from agent.readable import ensure_copy
        model = Intelligence(model=worker, service_tier=settings.OPENAI_WORKER_SERVICE_TIER or None)
        for e in missing:
            if e["id"] not in {x["id"] for x in long}:
                ensure_copy(e["id"], e["content"], None, model)
        after = _entries(args.user)
        print(f"applied: {sum(1 for e in after if current_copy(e['content'], e['reading_copy']))} entries "
              f"have a reading copy; {made} long entries cut into passages")

    if args.reread:
        targets = [e["id"] for e in _entries(args.user)
                   if e["eligible"] and current_copy(e["content"], e["reading_copy"])]
        print(f"re-reading {db.reread_entries(args.user, targets)} entries with a reading copy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
