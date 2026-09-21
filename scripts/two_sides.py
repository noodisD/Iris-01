#!/usr/bin/env python3
"""One pattern's occasions, split by how they went, with what else was true.

A pattern says a circumstance recurs and how its occasions turned out. This
asks the question after that: on the ones that went well, what did you do and
what else was true at the time — and on the ones that did not.

It costs nothing: the labels were collected by label_accounts.py and the rest
is arithmetic. A pattern present on one side and absent from the other is not a
cause and is not advice. It is a difference between two sets of occasions, put
in front of you so you can read both and say whether it means anything.

    uv run python scripts/two_sides.py --pattern more-than-can-be-taken-back
    uv run python scripts/two_sides.py --pattern <id> --minimum 3
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time

logging.disable(logging.CRITICAL)

from collections import Counter  # noqa: E402
from pathlib import Path  # noqa: E402

from agent.alternatives import compare, distinctive  # noqa: E402
from agent.episodes import EXTRACTION_VERSION, Episode, comparable  # noqa: E402
from agent.library import load  # noqa: E402

SIDE_TITLES = {"better": "What followed read as welcome",
               "worse": "What followed read as unwelcome"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pattern", required=True)
    ap.add_argument("--cache", default="data/episodes.json")
    ap.add_argument("--labels", default="data/labels.json")
    ap.add_argument("--library", default=None)
    ap.add_argument("--minimum", type=int, default=2,
                    help="how large a difference has to be before it is shown")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cache, store = Path(args.cache), Path(args.labels)
    if not cache.exists() or not store.exists():
        print("run scripts/read_episodes.py and scripts/label_accounts.py first.")
        return 1
    body = json.loads(cache.read_text())
    if body.get("version") != EXTRACTION_VERSION:
        print("the accounts were made by another extraction version; read again.")
        return 1
    labels = json.loads(store.read_text())
    if labels.get("readAt") != body.get("readAt"):
        print("the labels were made against different accounts; label again.")
        return 1

    patterns = {p.id: p for p in load(Path(args.library) if args.library else None)}
    if args.pattern not in patterns:
        print(f"no pattern {args.pattern}. Known: {', '.join(sorted(patterns))}")
        return 1
    pattern = patterns[args.pattern]

    episodes = comparable([Episode.from_dict(e) for e in body["episodes"]])
    by_pattern = {pid: {int(i): answer for i, answer in rows.items()}
                  for pid, rows in labels["labels"].items()}
    sides = compare(by_pattern, args.pattern, episodes)
    rows = distinctive(sides, minimum=args.minimum)

    print(f"{pattern.name}: {len(sides['better'].episodes)} welcome, "
          f"{len(sides['worse'].episodes)} unwelcome")
    for other, better, worse in rows:
        print(f"  {other}: {better} welcome / {worse} unwelcome")

    out = [f"# {pattern.name}", "", f"*{pattern.statement}*", "",
           f"{len(sides['better'].episodes)} occasions where what followed read as "
           f"welcome, {len(sides['worse'].episodes)} where it did not.", ""]
    if rows:
        out += ["## What else was true", "",
                "Patterns that sit on one side of these occasions more than the other. "
                "A difference between two sets, not a cause and not a suggestion — the "
                "occasions are below, and what they mean is yours to say.", "",
                "| also present | welcome | unwelcome |", "|---|---|---|"]
        for other, better, worse in rows:
            name = patterns[other].name if other in patterns else other
            out.append(f"| {name} | {better} | {worse} |")
        out.append("")
    for side in ("better", "worse"):
        here = sides[side]
        if not here.episodes:
            continue
        out += [f"## {SIDE_TITLES[side]} — {len(here.episodes)}", ""]
        for response, times in Counter(here.responses).most_common():
            out.append(f"- {response}" + (f" ({times}×)" if times > 1 else ""))
        out.append("")
        for e in here.episodes:
            when = e.occurred_on.isoformat() if e.occurred_on else "undated"
            out += [f"### {when} · {e.domain or 'unstated'}",
                    f"- **Then:** {e.situation}",
                    f"- **You:** {e.response}",
                    f"- **What followed:** {e.outcome}"]
            if e.explanation:
                out.append(f"- **You said why:** {e.explanation}")
            for cite in e.citations:
                out.append(f"  > {cite.text}")
            out.append("")
    out += [f"**A question that could retire this pattern:** {pattern.question}",
            f"  (An answer of: {pattern.retiring_answer})", ""]

    path = Path(args.out or f"data/sides-{args.pattern}-{time.strftime('%Y%m%d-%H%M')}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out))
    print(f"\nreport: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
