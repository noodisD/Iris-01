#!/usr/bin/env python3
"""Two labellings of the same accounts, set against each other.

Which model to use for the counting passes is a question with an answer, and
the answer is in the archive rather than in a benchmark: run the same patterns
past a second model and see where it agrees with the labelling already trusted.

Reported as recall against the reference — of the occasions the reference found
a pattern in, how many did the other find — and as agreement on how those
occasions went. A model that finds half of them is not cheaper, it is measuring
something else.

    uv run python scripts/compare_labels.py data/labels.json data/labels-luna-batch5.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("reference", help="the labelling being trusted")
    ap.add_argument("other", help="the labelling being judged")
    args = ap.parse_args()

    ref = json.loads(Path(args.reference).read_text())
    other = json.loads(Path(args.other).read_text())
    if ref.get("readAt") != other.get("readAt"):
        print("these labellings are of different accounts; not comparable.")
        return 1

    ref_labels, other_labels = ref.get("labels", {}), other.get("labels", {})
    ref_by, other_by = ref.get("by", {}), other.get("by", {})
    shared = sorted(set(ref_labels) & set(other_labels))
    # A pattern both stores took from the same run agrees with itself perfectly
    # and says nothing about either model. Only the ones that came from
    # different places are a comparison at all.
    if ref_by and other_by:
        shared = [p for p in shared if ref_by.get(p) != other_by.get(p)]
        note = "patterns whose labels came from different places"
    else:
        note = ("every pattern both stores hold — one of them records no source, "
                "so patterns copied from the same run cannot be excluded and "
                "agree with themselves")
    if not shared:
        print("no pattern was labelled by both.")
        return 1

    print(f"{len(shared)} pattern(s): {note}\n")
    print(f"{'pattern':<44} {'ref':>4} {'other':>6} {'found':>6} {'agreed':>7}")
    found_total = ref_total = agreed_total = 0
    for pid in shared:
        mine, theirs = ref_labels[pid], other_labels[pid]
        both = set(mine) & set(theirs)
        agreed = sum(1 for i in both if mine[i]["tone"] == theirs[i]["tone"])
        ref_total += len(mine)
        found_total += len(both)
        agreed_total += agreed
        print(f"{pid:<44} {len(mine):>4} {len(theirs):>6} {len(both):>6} {agreed:>7}")

    recall = found_total / ref_total if ref_total else 0
    tone = agreed_total / found_total if found_total else 0
    print(f"\nof {ref_total} occasions the reference found, the other found "
          f"{found_total} ({recall:.0%})")
    print(f"of those, they agreed on how it went {tone:.0%} of the time")
    # Who produced the compared columns, rather than every pattern in the store.
    def who(store, pids):
        named = {store.get("by", {}).get(p) for p in pids} - {None}
        return ", ".join(sorted(named)) or str(store.get("labelledAt"))
    print(f"\nreference: {who(ref, shared)}")
    print(f"other:     {who(other, shared)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
