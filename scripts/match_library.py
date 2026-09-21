#!/usr/bin/env python3
"""Your accounts, put to each pattern in the library.

Asking a model what circumstances recur in an archive failed twice: concrete,
it found only the corner of a life with the most repetition; abstract, it
produced sentences that matched nothing. The library is written once, in words
that fit any area, with what would show a pattern and what would not — so
matching has something stable to recognise, and the same patterns can be
counted again next month against the same definitions.

Each pattern is put to every comparable account: did this pattern hold, did
what followed read as welcome, and how large was it. The counting happens here.
Nothing is assigned to the owner: a pattern is a question asked of an account.

    uv run python scripts/match_library.py --dry-run
    uv run python scripts/match_library.py --only attention-taken

One call per pattern. Counts to the terminal, the map and the accounts under
each cell to a local report.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time

logging.disable(logging.CRITICAL)

from pathlib import Path  # noqa: E402

from agent.connections import MAGNITUDES, TONES, weigh  # noqa: E402
from agent.episodes import Episode, EXTRACTION_VERSION, areas, comparable  # noqa: E402
from agent.intelligence import Intelligence  # noqa: E402
from agent.library import load  # noqa: E402

TONE_WORDS = {"better": "welcome", "worse": "unwelcome", "mixed": "both"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", default="data/episodes.json")
    ap.add_argument("--library", default=None)
    ap.add_argument("--only", action="append", help="match one pattern by id")
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

    patterns = load(Path(args.library) if args.library else None)
    if args.only:
        patterns = [p for p in patterns if p.id in set(args.only)]
    episodes = [Episode.from_dict(e) for e in body["episodes"]]
    usable = comparable(episodes)
    print(f"accounts: {len(episodes)}  comparable: {len(usable)}  "
          f"areas: {len(areas(usable))}  patterns: {len(patterns)}")
    if args.dry_run:
        print("dry run: one call per pattern. Nothing was sent.")
        return 0

    started = time.time()
    model = Intelligence()
    rows, sections = [], []
    for pattern in patterns:
        grid, counts = weigh(pattern.statement, episodes, model, markers=pattern.markers)
        if not counts.get("asked"):
            print(f"  {pattern.id}: the model could not be asked — stopping. "
                  "Nothing below this line was measured.")
            break
        held = counts["held"]
        matched = [e for cell in grid.values() for e in cell]
        spread = len(areas(matched))
        rows.append({"pattern": pattern.name, "held": held, "areas": spread,
                     **{f"{t}_{s}": counts.get(f"{t}_{s}", 0)
                        for t in TONES for s in MAGNITUDES}})
        print(f"  {pattern.id}: {held} accounts, {spread} areas")

        sections += [f"## {pattern.name}", "", f"*{pattern.statement}*", "",
                     f"Found in {held} of {len(usable)} accounts, across {spread} areas.", ""]
        if held:
            sections += ["| | small | moderate | large |", "|---|---|---|---|"]
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
                        sections.append(f"- *{when}, {e.domain or 'unstated'}* — "
                                        f"{e.situation}; you {e.response}; {e.outcome}")
                        for cite in e.citations:
                            sections.append(f"  > {cite.text}")
                    sections.append("")
        sections += [f"**A question that could retire this:** {pattern.question}",
                     f"  (An answer of: {pattern.retiring_answer})", ""]

    report = ["# Your accounts, against the library", "",
              f"{len(usable)} accounts of your own that say what followed, across "
              f"{len(areas(usable))} areas, read on {time.strftime('%Y-%m-%d')}.", "",
              "The patterns are general and were written before your accounts were "
              "looked at. A pattern found in few of them is not a failing of yours or "
              "of the pattern: it is a fact about what this archive happens to record.",
              "", "| pattern | accounts | areas | welcome (s/m/l) | unwelcome (s/m/l) |",
              "|---|---|---|---|---|"]
    for row in rows:
        welcome = "/".join(str(row[f"better_{s}"]) for s in MAGNITUDES)
        unwelcome = "/".join(str(row[f"worse_{s}"]) for s in MAGNITUDES)
        report.append(f"| {row['pattern']} | {row['held']} | {row['areas']} | "
                      f"{welcome} | {unwelcome} |")
    report += ["", *sections]

    out = Path(args.out or f"data/library-{time.strftime('%Y%m%d-%H%M')}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(report))
    print(json.dumps({"patterns": len(patterns), "comparable": len(usable),
                      "seconds": round(time.time() - started), "report": str(out)}, indent=1))
    print("\nThe report is for you to read; this prints counts only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
