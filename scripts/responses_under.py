#!/usr/bin/env python3
"""One circumstance, and what was done about it on each occasion.

A relationship between a circumstance and a feeling can be true and useless:
"when something wanted was blocked, it was difficult" holds for everyone alive.
What distinguishes one occasion from another is what was done next, which the
accounts already carry — a response and an outcome are two of the parts an
episode must have to be comparable at all.

This asks the model only what it can read from the writing — was this that
circumstance, and did what followed read as welcome — and groups the responses
here, unranked. Which of them is worth repeating is the owner's to decide.

    uv run python scripts/responses_under.py --condition "a wanted action was blocked"

Counts to the terminal, the responses and their outcomes to a local report.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time

logging.disable(logging.CRITICAL)

from pathlib import Path  # noqa: E402

from agent.connections import TONES, responses_under  # noqa: E402
from agent.episodes import EXTRACTION_VERSION, Episode  # noqa: E402
from agent.intelligence import Intelligence  # noqa: E402

TITLES = {"better": "What followed read as welcome",
          "worse": "What followed read as unwelcome",
          "mixed": "What followed read as both"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--condition", required=True)
    ap.add_argument("--cache", default="data/episodes.json")
    ap.add_argument("--out", default=None)
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
    if args.dry_run:
        print(f"accounts: {len(episodes)}. dry run: nothing was sent.")
        return 0

    started = time.time()
    groups, counts = responses_under(args.condition, episodes, Intelligence())

    lines = [f"# {args.condition}", "",
             f"Of {counts['comparable']} accounts, {counts['held']} describe this. "
             f"What you did on each occasion, and what followed — in your own words, "
             f"grouped by how the account reads and ranked by nobody.", ""]
    for tone in TONES:
        if not groups[tone]:
            continue
        lines += [f"## {TITLES[tone]} — {len(groups[tone])}", ""]
        for e in groups[tone]:
            when = e.occurred_on.isoformat() if e.occurred_on else "undated"
            lines += [f"### {when} · {e.domain or 'unstated'}",
                      f"- **Then:** {e.situation}",
                      f"- **You:** {e.response}",
                      f"- **What followed:** {e.outcome}"]
            if e.explanation:
                lines.append(f"- **You said why:** {e.explanation}")
            for cite in e.citations:
                lines.append(f"  > {cite.text}")
            lines.append("")

    out = Path(args.out or f"data/responses-{time.strftime('%Y%m%d-%H%M')}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    print(json.dumps({**counts, "seconds": round(time.time() - started),
                      "report": str(out)}, indent=1))
    print("\nThe report is for you to read; this prints counts only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
