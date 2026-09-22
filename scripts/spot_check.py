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

The sheet ends with pairs that share a shape. Those are retrieved, not decided:
two occasions can have the same situation, response and outcome and still be
two occasions — comparing them is the point of the rest of this work — so a
shared shape only earns the pair a question. Whether it is one occasion told
twice is the owner's answer.

Counts to the terminal; the sheet itself is written to data/, gitignored, and
holds the owner's own writing.

    uv run python scripts/spot_check.py            # ten accounts
    uv run python scripts/spot_check.py --count 20
"""

from __future__ import annotations

import argparse
import json
import re
import sys
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
    ("reading", "Does situation, demand, information, response or outcome add "
                "anything the writing does not say?"),
    ("explanation", "If there is an explanation: is it the writer's own, or "
                    "one the reader supplied?"),
)

#: Words too common in anyone's writing to mean two accounts are the same
#: occasion. Kept small deliberately: a longer list starts removing the words
#: that carry the meaning.
_COMMON = frozenset(
    "a an and as at be been but by for from had has have he her his i if in is "
    "it its me my not of on or she so that the their them then there they this "
    "to up was we were what when which who will with would you your".split())


def strata(episodes: list[dict]) -> list[tuple[str, list[int]]]:
    """Groups worth sampling from, rarest first.

    Order matters: `choose` takes one from each in turn, so the rarest kinds are
    reached before the sample is full and ordinary dated accounts fill whatever
    is left. An account can belong to several of these; it is checked once, and
    listed under the first kind that claimed it.
    """
    def where(test) -> list[int]:
        return [i for i, e in enumerate(episodes) if test(e)]

    return [
        ("attributed to someone else", where(lambda e: e.get("actor") != "self")),
        ("planned, not done", where(lambda e: e.get("modality") == "planned")),
        ("undated", where(lambda e: not e.get("occurredOn"))),
        ("carries an explanation", where(lambda e: e.get("explanation"))),
        ("cites more than one entry", where(
            lambda e: len({c.get("entryId") for c in e.get("citations", [])}) > 1)),
        ("ordinary, dated", where(
            lambda e: e.get("occurredOn") and e.get("modality") == "happened")),
    ]


def _shape_words(e: dict) -> set[str]:
    """The words that carry an account's shape, minus the ones everyone uses."""
    text = " ".join((e.get(f) or "") for f in ("situation", "response", "outcome"))
    return {w for w in re.findall(r"[a-z']+", text.lower())
            if w not in _COMMON and len(w) > 2}


def retellings(episodes: list[dict], limit: int = 3,
               threshold: float = 0.5) -> list[tuple[float, int, int]]:
    """Pairs worth asking about, found by shape and settled by the owner.

    Shared structure retrieves candidates; it decides nothing. Two occasions
    can have the same shape and still be two occasions — that is the whole
    premise of comparing across areas, so treating similarity as sameness here
    would delete the recurrence the rest of this is looking for.

    So nothing is merged, dropped or marked. The pair goes in front of the
    owner with both dates and both sources, and whether it is one occasion told
    twice is their answer, not this function's.
    """
    words = [_shape_words(e) for e in episodes]
    scored: list[tuple[float, int, int]] = []
    for i in range(len(episodes)):
        if len(words[i]) < 4:
            continue
        for j in range(i + 1, len(episodes)):
            if len(words[j]) < 4:
                continue
            shared = words[i] & words[j]
            overlap = len(shared) / min(len(words[i]), len(words[j]))
            if overlap >= threshold:
                scored.append((round(overlap, 2), i, j))
    scored.sort(reverse=True)
    return scored[:limit]


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

    pairs = retellings(episodes)
    if pairs:
        lines += [
            "# Pairs that share a shape",
            "",
            "Retrieved because they use the same words about what happened, what",
            "was done and what followed. That is a reason to look, not a finding:",
            "two occasions can share a shape and still be two occasions, which is",
            "what the comparison work is for. Nothing has been merged or dropped.",
            "",
            "For each pair: same occasion told twice, or two occasions?",
            "",
        ]
        for overlap, i, j in pairs:
            lines += [f"## accounts #{i} and #{j} — {overlap:.0%} of their words in common", ""]
            for k in (i, j):
                e = episodes[k]
                sources = ", ".join(
                    f"{c.get('sourceType', 'reflection')} {c.get('entryId')}"
                    f" ({c.get('entryDate') or 'undated'})"
                    for c in e.get("citations", []))
                lines += [
                    f"**#{k}** — {e.get('occurredOn') or 'undated'} — {sources}",
                    "",
                    f"- situation: {e.get('situation') or '—'}",
                    f"- response: {e.get('response') or '—'}",
                    f"- outcome: {e.get('outcome') or '—'}",
                    "",
                ]
            lines += ["Verdict (one occasion / two occasions / unsure):", "",
                      "---", ""]
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
    pairs = retellings(episodes)
    print(f"  {'pairs sharing a shape':<28} {len(pairs):>3} put up for comparison")
    print(f"\nwritten to {out}")
    print("Nothing was sent anywhere, and no account was changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
