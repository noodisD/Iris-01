#!/usr/bin/env python3
"""Build a source-linked manual review sheet for v4 account extraction.

    uv run python scripts/spot_check.py --count 10

The v4 cache must have the current reader hash and contain only accepted,
eligible journal sources. The sheet is owner-only and never overwrites an
earlier spot-check or the historical v3 cache.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from scripts.read_episodes import DEFAULT_CACHE, load_cache

QUESTIONS = (
    ("actor", "Whose words and action does the original passage describe?"),
    ("recordKind", "Did it happen, was it a general self-description, or only intended/imagined?"),
    ("identity", "Is this a separate event, or the same one retold in another entry?"),
    ("situation", "Is this particular situation stated for this actor and occasion?"),
    ("response", "Is this what they actually did, not what they meant to do?"),
    ("immediateOutcome", "Is an immediate result explicitly stated for this same occasion?"),
    ("laterOutcome", "Is a separate later result explicitly stated, not inferred from a later entry date?"),
    ("feeling", "Is the feeling theirs and explicitly stated?"),
    ("concern", "Is this stated as their want, worry, value or stake?"),
    ("explanation", "If supplied, is this what the owner wrote, rather than Iris's hypothesis?"),
    ("recordedOn", "Does this date record the entry, without asserting when the event happened?"),
)
_COMMON = frozenset(
    "a an and as at be been but by for from had has have he her his i if in is "
    "it its me my not of on or she so that the their them then there they this "
    "to up was we were what when which who will with would you your".split())


def strata(episodes: list[dict]) -> list[tuple[str, list[int]]]:
    """Choose rare epistemic boundaries before ordinary dated self-events."""
    def where(predicate) -> list[int]:
        return [index for index, row in enumerate(episodes) if predicate(row)]

    return [
        ("other or unclear actor", where(lambda e: e["actor"] != "self")),
        ("intended or imagined", where(lambda e: e["recordKind"] in {"intention", "hypothetical"})),
        ("general owner report", where(lambda e: e["recordKind"] == "self_report")),
        ("undated writing", where(lambda e: e["recordedOn"] is None)),
        ("no stated outcome", where(lambda e: e["immediateOutcome"] is None
                                    and e["laterOutcome"] is None)),
        ("owner explanation", where(lambda e: e["explanation"] is not None)),
        ("dated self-event", where(lambda e: e["actor"] == "self"
                                  and e["recordKind"] == "event"
                                  and e["recordedOn"] is not None)),
    ]


def _shape_words(account: dict) -> set[str]:
    text = " ".join(account.get(name) or "" for name in (
        "situation", "response", "immediateOutcome", "laterOutcome"))
    return {word for word in re.findall(r"[a-z']+", text.lower())
            if word not in _COMMON and len(word) > 2}


def retellings(episodes: list[dict], limit: int = 3,
               threshold: float = 0.5) -> list[tuple[float, int, int]]:
    """Retrieve possible retellings; shared words are not event identity."""
    words = [_shape_words(row) for row in episodes]
    scored = []
    for left in range(len(words)):
        if len(words[left]) < 4:
            continue
        for right in range(left + 1, len(words)):
            if len(words[right]) < 4:
                continue
            overlap = len(words[left] & words[right]) / min(len(words[left]), len(words[right]))
            if overlap >= threshold:
                scored.append((round(overlap, 2), left, right))
    scored.sort(reverse=True)
    return scored[:limit]


def choose(episodes: list[dict], count: int) -> list[tuple[int, str]]:
    selected: dict[int, str] = {}
    pools = [(label, list(indices)) for label, indices in strata(episodes)]
    while len(selected) < count and any(indices for _, indices in pools):
        for label, indices in pools:
            while indices:
                index = indices.pop(0)
                if index not in selected:
                    selected[index] = label
                    break
            if len(selected) >= count:
                break
    return sorted(selected.items())


def sheet(episodes: list[dict], chosen: list[tuple[int, str]]) -> str:
    lines = [
        "# Manual spot-check of neutral v4 accounts",
        "",
        "This sample does not validate all writing. Mark each question ok, wrong",
        "or unsure; a located passage is not proof of who acted or what resulted.",
        "",
    ]
    for number, (index, reason) in enumerate(chosen, 1):
        account = episodes[index]
        lines += [
            f"## {number}. account #{index} — {reason}",
            "",
            f"- actor: **{account['actor']}** · record kind: **{account['recordKind']}**"
            f" · domain: {account['domain'] or '—'}",
            f"- written on: **{account['recordedOn'] or 'undated'}** (not event time)",
            "",
            "| field | extracted original wording |",
            "|---|---|",
        ]
        for field in ("situation", "demand", "information", "response", "feeling", "concern",
                      "immediateOutcome", "laterOutcome", "explanation", "selfReport"):
            value = (account[field] or "Not recorded").replace("|", "\\|")
            lines.append(f"| {field} | {value} |")
        lines += ["", "Original cited context:", ""]
        for citation in account["citations"]:
            lines.extend(f"> {line}" for line in citation["text"].splitlines())
            lines += [">", f"> — {citation['sourceType']} {citation['entryId']}, "
                      f"written {citation['entryDate'] or 'undated'}", ""]
        lines += ["| question | verdict (ok / wrong / unsure) |", "|---|---|"]
        lines += [f"| {key}: {question} | |" for key, question in QUESTIONS]
        lines += ["", "Notes:", "", "---", ""]

    pairs = retellings(episodes)
    if pairs:
        lines += ["# Possible retellings, not merged or counted as one event",
                  "", "For each pair, ask whether both passages describe one event, two, or are unclear.", ""]
        for overlap, left, right in pairs:
            lines += [f"## accounts #{left} and #{right} — {overlap:.0%} words in common", ""]
            for index in (left, right):
                row = episodes[index]
                sources = ", ".join(
                    f"{c['sourceType']} {c['entryId']} ({c['entryDate'] or 'undated'})"
                    for c in row["citations"])
                lines += [
                    f"**#{index}** — recorded {row['recordedOn'] or 'undated'} — {sources}",
                    "",
                    f"- situation: {row['situation'] or 'Not recorded'}",
                    f"- response: {row['response'] or 'Not recorded'}",
                    f"- immediate outcome: {row['immediateOutcome'] or 'Not recorded'}",
                    f"- later outcome: {row['laterOutcome'] or 'Not recorded'}",
                    "",
                ]
            lines += ["Verdict (one event / two events / unsure):", "", "---", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", default=DEFAULT_CACHE)
    parser.add_argument("--user", type=int, default=1)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    if args.count <= 0 or args.user <= 0:
        print("Select a positive owner and count.")
        return 1
    cache = Path(args.cache)
    try:
        rows, _ = load_cache(cache, args.user)
    except (OSError, ValueError, KeyError, TypeError):
        print("No current neutral v4 cache; run read_episodes.py first.")
        return 1
    accounts = [episode.as_dict() for episode in rows]
    selected = choose(accounts, args.count)
    out = Path(args.out) if args.out else cache.parent / "spot-check-v4.md"
    if out.exists() or out.resolve() == cache.resolve():
        print("Refusing to overwrite a cache or earlier owner review.")
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(sheet(accounts, selected))
    except FileExistsError:
        print("Another review sheet was written first; refusing to overwrite it.")
        return 1
    print(f"{len(accounts)} accounts, {len(selected)} chosen")
    for label, indices in strata(accounts):
        print(f"  {label:<28} {len(indices):>3} available")
    print(f"  {len(retellings(accounts))} possible retelling pairs offered for review")
    print(f"written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
