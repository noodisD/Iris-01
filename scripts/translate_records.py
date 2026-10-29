#!/usr/bin/env python3
"""Give records already in IRIS their English versions (ADR-0036, migration 0057).

New records in another language are translated as they are processed. This
catches up the ones that came before:

    uv run python scripts/translate_records.py           # what it would do, and cost; sends nothing
    uv run python scripts/translate_records.py --apply   # translate, then re-index and re-read them

--apply translates each with the worker model, then queues it to be indexed
again (its recall passages and vector, now from the English) and read again
(its accounts, now quoting the English), which sets off one pattern update.
Counts only: no text is printed.
"""

from __future__ import annotations

import argparse
import logging
import sys

if __name__ == "__main__":
    logging.disable(logging.CRITICAL)

from agent.config import settings  # noqa: E402
from agent.database import db  # noqa: E402
from agent.intelligence import Intelligence  # noqa: E402
from agent.translation import current, ensure, needed  # noqa: E402


def _records(user_id: int) -> list[dict]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id, source, content, content_format, translation, translation_hash
                         FROM reflections
                        WHERE user_id = %s AND length(btrim(coalesce(content, ''))) > 0
                        ORDER BY id""", (user_id,))
        keys = ("id", "source", "content", "content_format", "translation", "translation_hash")
        rows = [dict(zip(keys, row)) for row in cur.fetchall()]
    return [r for r in rows if needed(r["content"], r["content_format"])]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user", type=int, default=1)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    records = _records(args.user)
    missing = [r for r in records if not current(r["content"], r["translation"], r["translation_hash"])]
    chars = sum(len(r["content"]) for r in missing)
    worker = settings.OPENAI_WORKER_MODEL
    listed = ", ".join(f"{r['id']} {r['source']}" for r in missing) or "none"
    print(f"records in another language: {len(records)}  without a current English version: {len(missing)} "
          f"({listed})")
    print(f"  translating them: {Intelligence.estimate(worker, chars // 3, chars // 3)}")
    if not args.apply:
        return 0

    model = Intelligence(model=worker, service_tier=settings.OPENAI_WORKER_SERVICE_TIER or None)
    made = []
    for r in missing:
        english = ensure(r["id"], r["content"], r["content_format"], model=model)
        print(f"  {r['id']} {r['source']}: {'translated' if english else 'NOT translated (read as before)'}",
              flush=True)
        if english:
            made.append(r["id"])
    with db.connection() as conn, conn.cursor() as cur:
        for reflection_id in made:
            cur.execute("UPDATE reflections SET processing_status = 'pending' WHERE id = %s", (reflection_id,))
            db._queue(cur, args.user, "reflection", reflection_id)
        conn.commit()
    print(f"re-indexing {len(made)}; re-reading {db.reread_entries(args.user, made)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
