#!/usr/bin/env python3
"""Recover per-account labels from a library report that only kept the counts.

The first library run threw its labels away and wrote a report. Re-asking is
paying twice for an answer already given, and asking a different model gives a
different answer, so the labels are read back out of the report instead: each
account is listed under the cell it fell in, with the same words the accounts
hold, and matching them back is arithmetic.

An account that cannot be matched is reported rather than guessed at.

    uv run python scripts/labels_from_report.py data/library-20260921-1617.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from agent.episodes import EXTRACTION_VERSION, Episode, comparable
from agent.library import load

CELL = re.compile(r"^\*\*(Welcome|Unwelcome|Both), (small|moderate|large)\*\*", re.M)
TONES = {"welcome": "better", "unwelcome": "worse", "both": "mixed"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("report")
    ap.add_argument("--cache", default="data/episodes.json")
    ap.add_argument("--labels", default="data/labels.json")
    ap.add_argument("--library", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    body = json.loads(Path(args.cache).read_text())
    if body.get("version") != EXTRACTION_VERSION:
        print("the accounts were made by another extraction version.")
        return 1
    usable = comparable([Episode.from_dict(e) for e in body["episodes"]])
    by_line = {f"{e.situation}; you {e.response}; {e.outcome}": i
               for i, e in enumerate(usable)}
    names = {p.name: p.id for p in load(Path(args.library) if args.library else None)}

    text = Path(args.report).read_text()
    found: dict[str, dict[str, dict]] = {}
    missed = 0
    pattern_id, tone, size = None, None, None
    for line in text.splitlines():
        if line.startswith("## "):
            pattern_id = names.get(line[3:].strip())
            tone = size = None
        elif (cell := CELL.match(line)):
            tone, size = TONES[cell.group(1).lower()], cell.group(2)
        elif line.startswith("- *") and pattern_id and tone:
            said = line.split("— ", 1)[-1].strip()
            position = by_line.get(said)
            if position is None:
                missed += 1
                continue
            found.setdefault(pattern_id, {})[str(position)] = {"tone": tone, "size": size}

    total = sum(len(v) for v in found.values())
    print(f"patterns: {len(found)}  accounts matched: {total}  unmatched: {missed}")
    for pid, rows in found.items():
        print(f"  {pid}: {len(rows)}")
    if args.dry_run:
        print("dry run: nothing written.")
        return 0

    store = Path(args.labels)
    existing = json.loads(store.read_text()) if store.exists() else {}
    same = existing.get("readAt") == body.get("readAt")
    labels = existing.get("labels", {}) if same else {}
    by = existing.get("by", {}) if same else {}
    labels.update(found)
    # Which model said so. Counts from two models are not comparable, and a
    # store that does not say which is which invites exactly that comparison.
    by.update(dict.fromkeys(found, f"recovered from {Path(args.report).name}"))
    store.write_text(json.dumps({"readAt": body.get("readAt"), "accounts": len(usable),
                                 "labelledAt": "recovered from " + Path(args.report).name,
                                 "by": by, "labels": labels}, indent=1))
    print(f"labels: {store} ({len(labels)} patterns)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
