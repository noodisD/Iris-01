#!/usr/bin/env python3
"""The whole archive, mapped: every circumstance that recurs, weighed.

A proposal run answers "what relationship holds here" three times. This asks
what the accounts are made of — the circumstances that come round again — and
then weighs each one the way a single pattern was weighed by hand: how often
it held, what followed, and how large what followed was, in the writing's own
words.

Nothing here says a circumstance matters. It says it recurs, and then shows
the shape of what followed, which is the part a count of occasions hides.

    uv run python scripts/survey.py --dry-run
    uv run python scripts/survey.py --limit 6

One call to find the circumstances, then one per circumstance. Counts to the
terminal; the map, with your own words under each row, to a local report.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time

logging.disable(logging.CRITICAL)

from pathlib import Path  # noqa: E402

from agent.connections import MAGNITUDES, TONES, survey_conditions, weigh  # noqa: E402
from agent.episodes import EXTRACTION_VERSION, Episode, comparable  # noqa: E402
from agent.intelligence import Intelligence  # noqa: E402

TONE_WORDS = {"better": "welcome", "worse": "unwelcome", "mixed": "both"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", default="data/episodes.json")
    ap.add_argument("--limit", type=int, default=8, help="how many circumstances to weigh")
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
    usable = comparable(episodes)
    print(f"accounts: {len(episodes)}  comparable: {len(usable)}")
    if args.dry_run:
        print(f"dry run: one call to find circumstances, then up to {args.limit} "
              "to weigh them. Nothing was sent.")
        return 0

    started = time.time()
    model = Intelligence()
    conditions, found = survey_conditions(episodes, model, limit=args.limit)
    print(f"circumstances proposed: {found['proposed']}  kept: {found['kept']}")

    rows = []
    sections = []
    for n, item in enumerate(conditions, 1):
        condition = item["condition"]
        grid, counts = weigh(condition, episodes, model)
        rows.append({"condition": condition, "held": counts["held"],
                     **{f"{t}_{s}": counts.get(f"{t}_{s}", 0)
                        for t in TONES for s in MAGNITUDES}})
        print(f"  {n}. held in {counts['held']}")

        sections += [f"## {n}. {condition}", "",
                     f"Described in {counts['held']} of {len(usable)} accounts.", "",
                     "| | small | moderate | large |", "|---|---|---|---|"]
        for tone in TONES:
            cells = [str(counts.get(f"{tone}_{size}", 0)) for size in MAGNITUDES]
            sections.append(f"| {TONE_WORDS[tone]} | {' | '.join(cells)} |")
        sections.append("")
        for tone in TONES:
            for size in MAGNITUDES:
                here = grid.get((tone, size), [])
                if not here:
                    continue
                sections += [f"**{TONE_WORDS[tone].capitalize()}, {size}**", ""]
                for e in here:
                    when = e.occurred_on.isoformat() if e.occurred_on else "undated"
                    sections += [f"- *{when}, {e.domain or 'unstated'}* — {e.situation}; "
                                 f"you {e.response}; {e.outcome}"]
                    for cite in e.citations:
                        sections.append(f"  > {cite.text}")
                sections.append("")

    report = ["# What your accounts are made of", "",
              f"{len(usable)} accounts of your own that say what followed, out of "
              f"{len(episodes)} read on {time.strftime('%Y-%m-%d')}.", "",
              "Each row is a circumstance that recurs, and how the occasions it held on "
              "turned out — welcome or not, and how large, in your own words. The table "
              "says nothing about which circumstances matter, or what to do about them.",
              "", "| circumstance | held | welcome (s/m/l) | unwelcome (s/m/l) |",
              "|---|---|---|---|"]
    for row in rows:
        welcome = "/".join(str(row[f"better_{s}"]) for s in MAGNITUDES)
        unwelcome = "/".join(str(row[f"worse_{s}"]) for s in MAGNITUDES)
        report.append(f"| {row['condition']} | {row['held']} | {welcome} | {unwelcome} |")
    report += ["", *sections]

    out = Path(args.out or f"data/survey-{time.strftime('%Y%m%d-%H%M')}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(report))
    print(json.dumps({"comparable": len(usable), "circumstances": len(conditions),
                      "seconds": round(time.time() - started), "report": str(out)}, indent=1))
    print("\nThe report is for you to read; this prints counts only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
