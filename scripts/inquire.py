#!/usr/bin/env python3
"""A conversation about one pattern: one question at a time, your answers lead.

Where weigh_pattern.py counts, this asks — and listens. The shape is fixed
(clarify, the evidence, the exception, what it adds up to, what would make it
worth it) so the inquiry cannot quietly become a case being built; the wording
of each question comes from the model, and every question after the first sees
what you said to the ones before.

It ends with a summary of what *you* said, which may use no number that is not
in your own counts, and which is allowed to conclude that the pattern did not
survive your answers.

    uv run python scripts/inquire.py --condition "..."

Type your answer and press enter. Empty answer or "stop" ends it early; the
summary is written from whatever was said. The transcript is yours and stays in
data/.
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
from agent.episodes import EXTRACTION_VERSION, Episode  # noqa: E402
from agent.inquiry import STAGES, Turn, next_question, synthesis  # noqa: E402
from agent.intelligence import Intelligence  # noqa: E402

TONE_WORDS = {"better": "welcome", "worse": "unwelcome", "mixed": "both"}


def _table(counts: dict) -> list[str]:
    lines = ["| | small | moderate | large |", "|---|---|---|---|"]
    for tone in TONES:
        row = [str(counts.get(f"{tone}_{size}", 0)) for size in MAGNITUDES]
        lines.append(f"| {TONE_WORDS[tone]} | {' | '.join(row)} |")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--condition", required=True)
    ap.add_argument("--cache", default="data/episodes.json")
    ap.add_argument("--counts", default=None,
                    help="a saved counts file; otherwise the accounts are weighed first")
    ap.add_argument("--out", default=None)
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

    model = Intelligence()
    if args.counts and Path(args.counts).exists():
        counts = json.loads(Path(args.counts).read_text())
    else:
        episodes = [Episode.from_dict(e) for e in body["episodes"]]
        print("weighing your accounts…")
        _, counts = weigh(args.condition, episodes, model)

    print(f"\n{args.condition}")
    print(f"{counts.get('held', 0)} of {counts.get('comparable', 0)} accounts describe this.\n")
    print("\n".join(_table(counts)))
    print("\nFive questions, one at a time. Empty answer or 'stop' ends it.\n")

    turns: list[Turn] = []
    for stage, instruction in STAGES:
        question = next_question(stage, instruction, args.condition, counts, turns, model)
        if question is None:
            print(f"[no usable question for '{stage}' — skipping it]\n")
            continue
        print(f"— {question}")
        try:
            answer = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not answer or answer.lower() in ("stop", "quit", "exit"):
            break
        turns.append(Turn(stage, question, answer))
        print()

    summary = synthesis(args.condition, counts, turns, model)
    lines = [f"# {args.condition}", "", *_table(counts), ""]
    if summary:
        lines += ["## What you said, and what it leaves", "", summary, ""]
    lines += ["## The conversation", ""]
    for turn in turns:
        lines += [f"**{turn.stage}** — {turn.question}", "", f"> {turn.answer}", ""]

    out = Path(args.out or f"data/inquiry-{time.strftime('%Y%m%d-%H%M')}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))

    if summary:
        print(f"\n{summary}\n")
    else:
        print("\n[no summary: nothing was said, or what came back broke a rule]\n")
    print(f"transcript: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
