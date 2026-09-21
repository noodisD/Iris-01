#!/usr/bin/env python3
"""Test a condition-and-outcome claim against the accounts already extracted.

Where `compare_episodes.py` proposes, this checks: every comparable account is
labelled on two axes — did the condition hold, did what the claim says follow
actually follow — and the four corners are counted here rather than by the
model. Whether a claim holds is arithmetic; a model asked that question answers
it agreeably.

The claims come from a file, so the owner's own refinements can be tested as
easily as IRIS's proposals:

    data/hypotheses.json
    [{"label": "small stake", "condition": "...", "followed": "..."}]

    uv run python scripts/examine_connection.py --dry-run
    uv run python scripts/examine_connection.py
    uv run python scripts/examine_connection.py --condition "..." --followed "..."

Counts to the terminal, the accounts in each corner to a local report.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time

logging.disable(logging.CRITICAL)

from pathlib import Path  # noqa: E402

from agent.connections import CELLS, examine  # noqa: E402
from agent.episodes import EXTRACTION_VERSION, Episode, comparable  # noqa: E402
from agent.config import settings  # noqa: E402
from agent.intelligence import Intelligence  # noqa: E402

CORNER_TITLES = {
    "supports": "The condition held, and what the claim says followed did",
    "contradicts": "The condition held, and something else followed",
    "outcome_without_condition": "What the claim describes happened without the condition",
    "neither": "Neither the condition nor what it describes",
}


def _section(title: str, episodes) -> list[str]:
    lines = [f"### {title} — {len(episodes)}", ""]
    for e in episodes:
        when = e.occurred_on.isoformat() if e.occurred_on else "undated"
        lines.append(f"- *{when}, {e.domain or 'unstated'}* — {e.situation}; "
                     f"you {e.response}; {e.outcome}")
        for cite in e.citations:
            lines.append(f"  > {cite.text}")
    return [*lines, ""]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", default="data/episodes.json")
    ap.add_argument("--hypotheses", default="data/hypotheses.json")
    ap.add_argument("--condition", help="test one claim instead of the file")
    ap.add_argument("--followed", help="what the claim says followed")
    ap.add_argument("--out", default=None)
    ap.add_argument("--model", default=None,
                    help="which model does the work; the cheap worker model by "
                         "default, since these passes classify and count")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    model_name = args.model or settings.OPENAI_WORKER_MODEL

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

    if args.condition:
        claims = [{"label": "given on the command line",
                   "condition": args.condition, "followed": args.followed or ""}]
    else:
        path = Path(args.hypotheses)
        if not path.exists():
            print(f"no claims at {path}, and no --condition given.")
            return 1
        claims = json.loads(path.read_text())

    usable = comparable(episodes)
    print(f"claims: {len(claims)}  accounts: {len(usable)}")
    if args.dry_run:
        print("dry run: nothing was sent to the model.")
        return 0

    started = time.time()
    report = ["# Claims tested against the accounts", "",
              f"{len(usable)} accounts of your own, read on {time.strftime('%Y-%m-%d')}.",
              "", "Each claim was put to every account separately: did the condition "
              "hold, and did what the claim says follow actually follow. The counting "
              "is done here, not by the model.", ""]
    summary = []
    for claim in claims:
        cells, counts = examine(claim["condition"], claim.get("followed", ""),
                                episodes, Intelligence(model=model_name))
        summary.append({"label": claim.get("label", claim["condition"][:40]),
                        **{k: counts[k] for k in CELLS},
                        "unclear": counts["unclear"]})
        report += [f"## {claim.get('label', 'a claim')}", "",
                   f"**When:** {claim['condition']}  →  **what followed:** "
                   f"{claim.get('followed', '')}", "",
                   f"Supported by {counts['supports']}, contradicted by "
                   f"{counts['contradicts']}, what it describes happened without the "
                   f"condition in {counts['outcome_without_condition']}, "
                   f"{counts['unclear']} accounts could not be labelled.", ""]
        for corner in CELLS:
            if cells[corner]:
                report += _section(CORNER_TITLES[corner], cells[corner])

    out = Path(args.out or f"data/claims-{time.strftime('%Y%m%d-%H%M')}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(report))
    print(json.dumps({"claims": summary, "seconds": round(time.time() - started),
                      "report": str(out)}, indent=1))
    print("\nThe report is for you to read; this prints counts only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
