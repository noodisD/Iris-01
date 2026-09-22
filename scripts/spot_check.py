#!/usr/bin/env python3
"""Pick a handful of accounts to check by hand, and lay them out for checking.

Every count above the extraction inherits one unverified claim: that an account
says what the writing it cites says. The reader proves a quote appears word for
word in the entry it names. It does not prove the account *follows* from that
quote — that the actor is right, that it happened rather than being planned,
that two accounts are two occasions rather than one told twice.

So this takes no view on whether the extraction is good. It chooses the sample
most likely to expose an error and writes it out beside the writing it came
from, with a blank verdict against each question, for the owner to fill in.

The sample is stratified rather than random, because the rare cases are where
the errors would be: the single account attributed to anyone else is worth more
than twenty ordinary ones, and an undated account is where a date could have
been filled in from the wrong place.

Counts to the terminal; the sheet itself is written to data/, gitignored, and
holds the owner's own writing.

    uv run python scripts/spot_check.py            # ten accounts
    uv run python scripts/spot_check.py --count 20
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

#: What is being asked of each account, and why it can be wrong despite a quote
#: that verifies. These are the questions a verified citation does not answer.
QUESTIONS = (
    ("actor", "Is this the owner's own occasion, or someone else's?"),
    ("modality", "Did it happen, or was it planned, imagined or feared?"),
    ("identity", "Is this one occasion, or the same one told again elsewhere?"),
    ("situation", "Does the situation follow from the quotes, without additions?"),
    ("response", "Is the response what they actually did?"),
    ("outcome", "Is the outcome stated in the writing, not inferred?"),
    ("date", "Did the occasion happen on this day, or is this the day it was written?"),
    ("reading", "Does any field interpret rather than report?"),
)


def strata(episodes: list[dict]) -> list[tuple[str, list[int]]]:
    """Groups worth sampling from, rarest first.

    Order matters: `choose` takes one from each in turn, so the rarest kinds are
    reached before the sample is full and ordinary dated accounts fill whatever
    is left. An account can belong to several of these; it is checked once, and
    listed under the first kind that claimed it.
    """
    def where(test) -> list[int]:
        return [i for i, e in enumerate(episodes) if test(e)]

    seen_text = Counter(
        (e.get("situation") or "")[:40].lower() for e in episodes)

    return [
        ("attributed to someone else", where(lambda e: e.get("actor") != "self")),
        ("planned, not done", where(lambda e: e.get("modality") == "planned")),
        ("undated", where(lambda e: not e.get("occurredOn"))),
        ("possible retelling", where(
            lambda e: seen_text[(e.get("situation") or "")[:40].lower()] > 1)),
        ("carries an explanation", where(lambda e: e.get("explanation"))),
        ("cites more than one entry", where(
            lambda e: len({c.get("entryId") for c in e.get("citations", [])}) > 1)),
        ("ordinary, dated", where(
            lambda e: e.get("occurredOn") and e.get("modality") == "happened")),
    ]


def choose(episodes: list[dict], count: int) -> list[tuple[int, str]]:
    """Indices to check, each with the reason it was chosen."""
    picked: dict[int, str] = {}
    pools = [(label, list(members)) for label, members in strata(episodes)]
    # One from each kind in turn, rarest first, rather than draining the first
    # pool: filling greedily gave nine planned accounts and nothing undated,
    # which is a sample of one question rather than of the extraction.
    while len(picked) < count and any(members for _, members in pools):
        for label, members in pools:
            while members:
                i = members.pop(0)
                if i not in picked:
                    picked[i] = label
                    break
            if len(picked) >= count:
                break
    return sorted(picked.items())


def sheet(episodes: list[dict], chosen: list[tuple[int, str]]) -> str:
    lines = [
        "# Spot-check of extracted accounts",
        "",
        "Ten accounts is a diagnostic, not a validation of all of them. Where a",
        "field is wrong, say so and the check widens to the rest of that kind.",
        "",
        "Write `ok`, `wrong`, or `unsure` after each question. `unsure` is a real",
        "answer and more useful than a guess.",
        "",
    ]
    for n, (i, reason) in enumerate(chosen, 1):
        e = episodes[i]
        lines += [
            f"## {n}. account #{i} — chosen as: {reason}",
            "",
            f"- actor: **{e.get('actor')}**    modality: **{e.get('modality')}**"
            f"    domain: {e.get('domain') or '—'}",
            f"- occurred on: **{e.get('occurredOn') or 'undated'}**",
            "",
            "| field | what the account says |",
            "|---|---|",
        ]
        for field in ("situation", "demand", "information", "response",
                      "outcome", "explanation"):
            value = (e.get(field) or "—").replace("|", "\\|")
            lines.append(f"| {field} | {value} |")
        lines += ["", "What it cites, as the entry has it:", ""]
        for c in e.get("citations", []):
            where = f"{c.get('sourceType', 'reflection')} {c.get('entryId')}"
            when = c.get("entryDate") or "undated"
            lines.append(f"> {c.get('text')}")
            lines.append(">")
            lines.append(f"> — {where}, written {when}")
            lines.append("")
        lines += ["", "| question | | verdict |", "|---|---|---|"]
        for key, question in QUESTIONS:
            lines.append(f"| {key} | {question} | |")
        lines += ["", "Notes:", "", "---", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache", default="data/episodes.json")
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    cache = Path(args.cache)
    if not cache.exists():
        print(f"no accounts at {cache}: run read_episodes.py first.")
        return 1
    episodes = json.loads(cache.read_text())["episodes"]

    chosen = choose(episodes, args.count)
    out = Path(args.out) if args.out else cache.parent / "spot-check.md"
    out.write_text(sheet(episodes, chosen))

    print(f"{len(episodes)} accounts, {len(chosen)} chosen")
    for label, members in strata(episodes):
        taken = sum(1 for i, r in chosen if r == label)
        print(f"  {label:<28} {len(members):>3} available, {taken} chosen")
    print(f"\nwritten to {out}")
    print("Nothing was sent anywhere, and no account was changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
