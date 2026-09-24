#!/usr/bin/env python3
"""Bring a reading of the archive, its pattern labels, and the owner's answers into the app.

The reader and the labeller have so far written to files under data/, and the
owner has answered questions about them in markdown sheets. This loads all of
it into the tables the Patterns screen reads, so none of that work has to be
done again. It sends nothing anywhere and makes no model calls.

Loading twice changes nothing: occasions are keyed by their content and labels
by occasion and pattern. A reload never overwrites a verdict given in the app;
answers from a sheet fill only verdicts that are still empty.

    uv run python scripts/load_discovery.py                # the default files
    uv run python scripts/load_discovery.py --dry-run      # counts only

Counts to the terminal, never an occasion's text.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import discovery  # noqa: E402
from agent.database import db  # noqa: E402


def answers_from_sheet(path: Path) -> tuple[str | None, list[tuple[int, str, str | None]]]:
    """(pattern, [(reading index, is_it, note)]) from a parsed what-came-before sheet."""
    if not path.exists():
        return None, []
    body = json.loads(path.read_text())
    rows = [(r["index"], r["is_it"], r.get("note"))
            for r in body.get("occasions", {}).values() if r.get("is_it")]
    return body.get("pattern"), rows


def main() -> int:
    # Log lines here could carry an occasion's text, so logging is off while
    # this runs, and only while it runs. Switching it off at import silenced
    # every log in any process that merely imported this module, the test
    # suite included.
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        return _run()
    finally:
        logging.disable(previous)


def _run() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user", type=int, default=0, help="defaults to the local user")
    ap.add_argument("--cache", default="data/episodes.json")
    ap.add_argument("--labels", default="data/labels.json")
    ap.add_argument("--answers", default="data/what-came-before.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    episodes = json.loads(Path(args.cache).read_text())["episodes"]
    labels = json.loads(Path(args.labels).read_text())
    pattern, answers = answers_from_sheet(Path(args.answers))
    n_labels = sum(len(rows) for rows in labels.get("labels", {}).values())
    print(f"reading: {len(episodes)} occasions, {n_labels} labels across "
          f"{len(labels.get('labels', {}))} patterns; {len(answers)} answers from the sheet")
    if args.dry_run:
        print("dry run: nothing was written.")
        return 0

    # No name passed: the same rule the app uses (IRIS_DEFAULT_USER, else
    # "local"), so this cannot load everything under a user the app never shows.
    user_id = args.user or db.local_user_id()
    counts = discovery.load_reading(user_id, episodes, labels)
    print("loaded:", ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))

    applied = skipped = 0
    for index, is_it, note in answers:
        occasion_id = discovery.occasion_id_for(user_id, episodes[index])
        if occasion_id is None:
            skipped += 1
            continue
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT owner_verdict FROM pattern_labels
                    WHERE occasion_id = %s AND pattern_id = %s""", (occasion_id, pattern))
            row = cur.fetchone()
        if row is None or row[0] is not None:
            skipped += 1  # no such label, or the owner has already answered in the app
            continue
        discovery.set_occasion_verdict(user_id, pattern, occasion_id, is_it, note)
        applied += 1
    if answers:
        print(f"answers from the sheet: {applied} applied, {skipped} left as they were")
    return 0


if __name__ == "__main__":
    sys.exit(main())
