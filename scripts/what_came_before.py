#!/usr/bin/env python3
"""What was true just before each occasion of a pattern the owner already knows.

Knowing that you do something is not the same as knowing when. The owner can
name their own most costly pattern; what a record can add is the conditions it
tends to arrive in, which memory smooths over: whether it came in the days
after a loss, while money was needed for something specific, tired, or on the
back of a big win.

This gathers what the writing says about each of those, per occasion, and puts
it in front of the owner to confirm. It suggests. It does not decide: a loss
three days before is a reason to ask whether the two were connected, not proof
that they were.

The evidence comes from three places, each shown with where it came from:

- labels already on the same account (a library pattern such as carrying on
  after a setback, or doing something demanding while depleted);
- the owner's own dated occasions in the days before, and how they went;
- words in the account itself that name money needed or being tired.

The labels are keyed by position in `comparable()` — the list they were made
against — and are read through that list. Reading them against the full cache
would quietly attach every label to the wrong account.

    uv run python scripts/what_came_before.py build --pattern <id>
    uv run python scripts/what_came_before.py read

Counts to the terminal. The sheet and answers stay in data/.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.episodes import Episode, comparable  # noqa: E402
from agent.reference_evaluation import account_fingerprint, account_key  # noqa: E402

FORMAT = "what-came-before-1"
WINDOW_DAYS = 14

#: The conditions asked about, in the owner's terms. Each is answered yes or
#: no by the owner; the evidence below only decides what is suggested.
CONDITIONS = {
    "setback": "a loss or setback in the days before",
    "money": "money needed for something specific: a date, spending, a debt",
    "tired": "tired, drained, or short of sleep",
    "win": "a big win in the days before",
}
_BEFORE = re.compile(r"^(none|unsure|(setback|money|tired|win)(\s*,\s*(setback|money|tired|win))*)$")
_IS_IT = ("yes", "no", "unsure")

#: Labels on the same account that speak to a condition.
SAME_ACCOUNT = {
    "setback": ("continuing-after-a-setback",),
    "tired": ("finishing-while-depleted", "short-sleep-before"),
}

#: Words in the account's own text. Deliberately short lists of plain words:
#: they only raise a question, so a missed synonym costs a suggestion, while a
#: loose pattern would suggest a condition on every account.
WORDS = {
    "money": re.compile(r"\b(vacation|holiday|rent|bills?|credit|loan|borrow\w*|debt|"
                        r"spending|deadline|salary|need(?:ed)? (?:the )?money)\b", re.I),
    "tired": re.compile(r"\b(tired|exhausted|sleepy|sleep|fatigue\w*|drained|foggy)\b", re.I),
    "setback": re.compile(r"\b(lost|loss|losses|setback|burn(?:ed|t))\b", re.I),
}


def usable(episodes: list[dict]) -> list[int]:
    """Positions in the full cache of the accounts the labels were made against.

    Uses `comparable()` itself rather than restating its rule, so the two
    cannot drift apart. It filters the objects it is given, so identity maps
    each one back to its position.
    """
    eps = [Episode.from_dict(x) for x in episodes]
    chosen = {id(e) for e in comparable(eps)}
    return [i for i, e in enumerate(eps) if id(e) in chosen]


def occasions(episodes: list[dict], labels: dict, pattern: str) -> list[tuple[int, dict]]:
    """(full-cache index, label) for every labelled occasion of the pattern."""
    positions = usable(episodes)
    rows = labels["labels"].get(pattern, {})
    if labels.get("accounts") not in (None, len(positions)):
        raise ValueError("Labels were made against a different set of accounts; relabel first.")
    return sorted(((positions[int(k)], v) for k, v in rows.items()), key=lambda t: t[0])


def _labels_by_account(episodes: list[dict], labels: dict) -> dict[int, dict[str, dict]]:
    positions = usable(episodes)
    out: dict[int, dict[str, dict]] = {}
    for pid, rows in labels["labels"].items():
        for k, v in rows.items():
            out.setdefault(positions[int(k)], {})[pid] = v
    return out


def _day(e: dict) -> date | None:
    return date.fromisoformat(e["occurredOn"]) if e.get("occurredOn") else None


def evidence(episodes: list[dict], labels: dict, index: int,
             by_account: dict[int, dict[str, dict]] | None = None) -> dict[str, list[str]]:
    """What the writing offers for each condition around one occasion."""
    if by_account is None:
        by_account = _labels_by_account(episodes, labels)
    e, found = episodes[index], {c: [] for c in CONDITIONS}

    for condition, pids in SAME_ACCOUNT.items():
        for pid in pids:
            if pid in by_account.get(index, {}):
                found[condition].append(f"same account is labelled `{pid}`")

    text = " ".join(e.get(f) or "" for f in ("situation", "demand", "response", "explanation"))
    for condition, words in WORDS.items():
        hits = sorted({m.group(0).lower() for m in words.finditer(text)})
        if hits:
            found[condition].append(f"the account says: {', '.join(hits)}")

    here = _day(e)
    if here:
        for j, other in enumerate(episodes):
            there = _day(other)
            if (j == index or not there or other.get("actor") != "self"
                    or other.get("modality") != "happened"):
                continue
            gap = (here - there).days
            if not 0 < gap <= WINDOW_DAYS:
                continue
            for pid, label in by_account.get(j, {}).items():
                if label.get("tone") == "worse":
                    found["setback"].append(f"#{j}, {gap} day(s) before, went worse (`{pid}`)")
                    break
            for pid, label in by_account.get(j, {}).items():
                if label.get("tone") == "better" and label.get("size") == "large":
                    found["win"].append(f"#{j}, {gap} day(s) before, a large gain (`{pid}`)")
                    break
    return found


def sheet(episodes: list[dict], labels: dict, pattern: str, name: str) -> str:
    lines = [
        f"# What came before: {name}",
        "",
        f"<!-- format: {FORMAT} -->",
        f"<!-- pattern: {pattern} -->",
        "",
        "Two questions for each occasion below. Write your answers on the lines.",
        "",
        f"1. `is_it:` Is this an occasion of \"{name}\"? Write `yes`, `no`, or `unsure`.",
        "2. `before:` What was true just before it? Write any of these, separated",
        "   by commas, or `none`, or `unsure`:",
        "",
    ]
    lines += [f"   - `{c}`: {meaning}" for c, meaning in CONDITIONS.items()]
    lines += ["", "The evidence listed is only what the writing offers. It suggests;",
              "you decide. `note:` is optional.", "", "---", ""]
    by_account = _labels_by_account(episodes, labels)
    for index, label in occasions(episodes, labels, pattern):
        e = episodes[index]
        lines += [f"## occasion #{index}  ·  key `{account_key(e)}`",
                  f"<!-- fingerprint: {account_fingerprint(e)} -->", "",
                  f"written {e.get('occurredOn') or 'undated'} · went "
                  f"**{label.get('tone')}** ({label.get('size')}), as labelled", ""]
        for field in ("situation", "response", "outcome"):
            if e.get(field):
                lines.append(f"- {field}: {e[field]}")
        lines += ["", "What the writing offers:", ""]
        found = evidence(episodes, labels, index, by_account)
        for condition in CONDITIONS:
            for item in found[condition] or ["nothing"]:
                lines.append(f"- `{condition}`: {item}")
        lines += ["", "`is_it:` ", "", "`before:` ", "", "`note:` ", "", "---", ""]
    return "\n".join(lines) + "\n"


def read(text: str, episodes: list[dict]) -> dict:
    """The owner's answers, bound to the content they were given about."""
    if f"<!-- format: {FORMAT} -->" not in text.splitlines():
        raise ValueError("Not a sheet this version can read.")
    pattern = re.search(r"^<!-- pattern: ([a-z0-9-]+) -->$", text, re.M)
    out = {}
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        head = re.match(r"occasion #(\d+)\s+·\s+key `([0-9a-f]{12})`", block)
        if not head:
            continue
        index, key = int(head.group(1)), head.group(2)
        found = re.search(r"^<!-- fingerprint: ([0-9a-f]{64}) -->$", block, re.M)
        if index >= len(episodes) or account_key(episodes[index]) != key:
            raise ValueError(f"Occasion #{index} is not in this cache any more.")
        if not found or found.group(1) != account_fingerprint(episodes[index]):
            raise ValueError(f"Occasion #{index} has changed since the sheet was made.")

        def line(name: str) -> str:
            m = re.search(rf"^`{name}:`[ \t]*(.*?)[ \t]*$", block, re.M)
            return (m.group(1) if m else "").strip()

        is_it, before, note = line("is_it"), line("before").lower(), line("note")
        if is_it and is_it not in _IS_IT:
            raise ValueError(f"Occasion #{index}: {is_it!r} is not yes, no or unsure.")
        if before and not _BEFORE.match(before):
            raise ValueError(f"Occasion #{index}: {before!r} is not a list of the conditions.")
        conditions = ([] if before in ("", "none", "unsure")
                      else [c.strip() for c in before.split(",")])
        out[key] = {"index": index, "is_it": is_it or None,
                    "before": conditions if before not in ("", "unsure") else None,
                    "note": note or None}
    return {"format": FORMAT, "pattern": pattern.group(1) if pattern else None,
            "occasions": out}


def summary(answers: dict, labels: dict, episodes: list[dict]) -> dict:
    """Counts only from what the owner confirmed, split by how each went."""
    tones = {i: v.get("tone") for i, v in occasions(episodes, labels, answers["pattern"])}
    confirmed = [r for r in answers["occasions"].values() if r["is_it"] == "yes"]
    answered = [r for r in confirmed if r["before"] is not None]
    by_tone: dict[str, Counter] = {}
    for r in answered:
        tally = by_tone.setdefault(tones.get(r["index"]) or "unlabelled", Counter())
        tally["occasions"] += 1
        tally.update(r["before"] or ["none"])
    return {"confirmed": len(confirmed), "with_conditions_answered": len(answered),
            "not_this_pattern": sum(1 for r in answers["occasions"].values() if r["is_it"] == "no"),
            "by_tone": {t: dict(c) for t, c in by_tone.items()}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("what", choices=("build", "read"))
    ap.add_argument("--pattern", default="")
    ap.add_argument("--cache", default="data/episodes.json")
    ap.add_argument("--labels", default="data/labels.json")
    ap.add_argument("--library", default="patterns/library.json")
    ap.add_argument("--sheet", default="data/what-came-before.md")
    ap.add_argument("--out", default="data/what-came-before.json")
    args = ap.parse_args()

    episodes = json.loads(Path(args.cache).read_text())["episodes"]
    labels = json.loads(Path(args.labels).read_text())
    path = Path(args.sheet)

    if args.what == "build":
        if path.exists():
            print(f"Refusing to overwrite {path}: it may hold answers.")
            return 1
        library = {p["id"]: p for p in json.loads(Path(args.library).read_text())["patterns"]}
        if args.pattern not in library:
            print(f"No pattern {args.pattern!r} in the library.")
            return 1
        path.write_text(sheet(episodes, labels, args.pattern, library[args.pattern]["name"]))
        found = [evidence(episodes, labels, i) for i, _ in occasions(episodes, labels, args.pattern)]
        print(f"{len(found)} occasions")
        for c in CONDITIONS:
            print(f"  with something to suggest `{c}`: {sum(1 for f in found if f[c])}")
        print(f"written to {path}")
        return 0

    answers = read(path.read_text(), episodes)
    Path(args.out).write_text(json.dumps(answers, indent=1))
    s = summary(answers, labels, episodes)
    print(f"confirmed occasions: {s['confirmed']} (answered 'before': "
          f"{s['with_conditions_answered']}; not this pattern: {s['not_this_pattern']})")
    for tone, counts in s["by_tone"].items():
        n = counts.pop("occasions")
        print(f"  went {tone}: {n}  " + "  ".join(f"{c} {counts.get(c, 0)}" for c in (*CONDITIONS, "none")))
    print(f"\nwritten to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
