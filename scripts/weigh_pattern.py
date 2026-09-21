#!/usr/bin/env python3
"""What a behaviour has actually cost and paid, and what only you can weigh.

Counting welcome occasions against unwelcome ones is the wrong summary for a
behaviour that sometimes pays. The occasions that went well are the ones that
keep it going, and a tally hides whether the two sides are the same size: a run
of small gains beside one large loss counts as "mostly fine" and is not.

So each occasion is placed twice — welcome or not, and small, moderate or large
as your own account describes it — and then you are asked the questions the
counts cannot answer. Those questions are about what you expect and what you
would accept. IRIS does not answer them, and does not decide which side of the
table matters.

    uv run python scripts/weigh_pattern.py --condition "..."
    uv run python scripts/weigh_pattern.py --condition "..." --note "your own reading"

Counts to the terminal, the occasions and the questions to a local report.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time

logging.disable(logging.CRITICAL)

from pathlib import Path  # noqa: E402

from agent.connections import MAGNITUDES, TONES, reflective_questions, weigh  # noqa: E402
from agent.episodes import EXTRACTION_VERSION, Episode  # noqa: E402
from agent.intelligence import Intelligence  # noqa: E402

TONE_WORDS = {"better": "welcome", "worse": "unwelcome", "mixed": "both"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--condition", required=True)
    ap.add_argument("--note", default=None, help="your own reading, kept as yours")
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
    model = Intelligence()
    grid, counts = weigh(args.condition, episodes, model)
    questions = reflective_questions(args.condition, counts, model)

    lines = [f"# {args.condition}", "",
             f"Of {counts['comparable']} accounts, {counts['held']} describe this.",
             "", "| | small | moderate | large |", "|---|---|---|---|"]
    for tone in TONES:
        row = [str(counts.get(f"{tone}_{size}", 0)) for size in MAGNITUDES]
        lines.append(f"| {TONE_WORDS[tone]} | {' | '.join(row)} |")
    lines += ["", "The table is what your accounts say, counted. It does not say which "
              "side should weigh more — a rare large outcome against a run of small ones "
              "is a judgement about your life, not a fact about your writing.", ""]
    if args.note:
        lines += ["## Your reading", "", f"> {args.note}", ""]
    if questions:
        lines += ["## Questions the counts cannot answer", ""]
        lines += [f"{i}. {q}" for i, q in enumerate(questions, 1)]
        lines.append("")

    for tone in TONES:
        for size in MAGNITUDES:
            here = grid.get((tone, size), [])
            if not here:
                continue
            lines += [f"## {TONE_WORDS[tone].capitalize()}, {size} — {len(here)}", ""]
            for e in here:
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

    out = Path(args.out or f"data/weighed-{time.strftime('%Y%m%d-%H%M')}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    print(json.dumps({**counts, "questions": len(questions),
                      "seconds": round(time.time() - started), "report": str(out)}, indent=1))
    print("\nThe report is for you to read; this prints counts only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
