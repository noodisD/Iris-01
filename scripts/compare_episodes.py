#!/usr/bin/env python3
"""Ask once whether accounts from different parts of a life share a shape.

Runs against the accounts `read_episodes.py` already extracted, so the archive
is not read again. One call to the model, at most three candidates out, and
every rule in `agent/connections.py` applied to the answer afterwards: three
supporting accounts across two areas, a contrast that tests it, two competing
explanations, and a question whose answer could retire it.

It stores nothing. The candidates are written to a local report for the owner
to read and judge — the terminal gets counts only, because what is in the
report is their life.

    uv run python scripts/compare_episodes.py --dry-run   # what would be sent
    uv run python scripts/compare_episodes.py             # one call, report out
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time

logging.disable(logging.CRITICAL)

from pathlib import Path  # noqa: E402

from agent.connections import propose, render  # noqa: E402
from agent.episodes import EXTRACTION_VERSION, Episode, areas, comparable  # noqa: E402
from agent.intelligence import Intelligence  # noqa: E402


def _report(candidates, counts) -> str:
    lines = [
        "# Possible connections",
        "",
        f"From {counts['comparable']} accounts of your own, across "
        f"{counts['areas']} areas, read on {time.strftime('%Y-%m-%d')}.",
        "",
        "Each of these is IRIS's proposal, not something you wrote. A proposal "
        "can be wrong in a useful way: the first run's weakest one named three "
        "conditions at once, and reading it produced three sharper ones. The accounts "
        "under it are yours and were verified against your entries; the relationship "
        "between them was inferred, and the question under each one is there because "
        "its answer could show the connection is wrong.",
        "",
    ]
    if not candidates:
        lines += ["No connection met the rules this time: three accounts across two "
                  "areas, a contrasting account, two competing explanations, and a "
                  "question that could retire it.", ""]
    for n, c in enumerate(candidates, 1):
        lines += [f"## {n}. {c.relation}", "",
                  f"**When:** {c.condition}  →  **what followed:** {c.followed}", ""]
        if c.already_stated:
            lines += ["*You have already drawn this connection yourself in one of the "
                      "accounts below.*", ""]
        lines += [f"**Areas:** {', '.join(c.domains)}", "", "**Accounts this holds in:**"]
        for e in c.supporting:
            when = e.occurred_on.isoformat() if e.occurred_on else "undated"
            lines.append(f"- *{when}, {e.domain or 'unstated'}* — {e.situation}; "
                         f"you {e.response}; {e.outcome}")
            for cite in e.citations:
                lines.append(f"  > {cite.text}")
        against = ("the same condition, and something else followed"
                   if c.contrast_kind == "condition_without_outcome"
                   else "the same outcome, without the condition")
        lines += ["", f"**An account that does not fit** ({against}):",
                  f"- *{c.contrast.domain or 'unstated'}* — {c.contrast.situation}; "
                  f"you {c.contrast.response}; {c.contrast.outcome}", ""]
        lines += ["**Explanations that both fit what is here:**"]
        lines += [f"- {e}" for e in c.explanations]
        lines += ["", f"**A question that could retire this:** {c.question}",
                  f"  (An answer of: {c.retiring_answer})", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", default="data/episodes.json")
    ap.add_argument("--out", default=None, help="where to write the report")
    ap.add_argument("--dry-run", action="store_true",
                    help="say how many accounts would be sent, and send nothing")
    ap.add_argument("--max", type=int, default=3,
                    help="how many candidates may survive a run")
    ap.add_argument("--judged", default="data/judged.json",
                    help="relations already judged, which a run must not propose again")
    args = ap.parse_args()

    cache = Path(args.cache)
    if not cache.exists():
        print(f"no accounts at {cache}: run scripts/read_episodes.py first.")
        return 1
    body = json.loads(cache.read_text())
    if body.get("version") != EXTRACTION_VERSION:
        print(f"cache was made by extraction version {body.get('version')}, "
              f"this is {EXTRACTION_VERSION}: read the archive again.")
        return 1

    episodes = [Episode.from_dict(e) for e in body["episodes"]]
    usable = comparable(episodes)
    print(f"accounts: {len(episodes)}  comparable: {len(usable)}  "
          f"areas: {len(areas(usable))}  labels: {len({e.domain for e in usable if e.domain})}")
    if args.dry_run:
        print(f"dry run: {len(render(usable).splitlines())} lines would be sent, "
              "without quotes. Nothing was sent.")
        return 0

    judged_path = Path(args.judged)
    judged = json.loads(judged_path.read_text()) if judged_path.exists() else []
    avoid = [j["relation"] for j in judged if j.get("relation")]

    started = time.time()
    candidates, counts = propose(episodes, Intelligence(), avoid=avoid,
                                 max_candidates=args.max)
    counts["already_judged"] = len(avoid)
    out = Path(args.out or f"data/connections-{time.strftime('%Y%m%d-%H%M')}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_report(candidates, counts))

    # Everything proposed goes into the ledger, so the next run has to find
    # something else. What the owner thought of it is theirs to add.
    judged += [{"relation": c.relation, "condition": c.condition,
                "proposed": time.strftime("%Y-%m-%d"), "verdict": None} for c in candidates]
    judged_path.parent.mkdir(parents=True, exist_ok=True)
    judged_path.write_text(json.dumps(judged, indent=1))

    print(json.dumps({**counts, "seconds": round(time.time() - started),
                      "report": str(out), "ledger": str(judged_path)}, indent=1))
    print("\nThe report is for you to read; this prints counts only.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
