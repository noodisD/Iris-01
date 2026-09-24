#!/usr/bin/env python3
"""Plans, and whether anything followed them.

Checking accounts by hand, the owner noticed something no account names: a thing
planned and never carried out. The material was already there, since the reader
records `modality: planned`. Nothing looked across accounts for a plan with no
occasion after it.

What this cannot do is decide that a plan was never carried out. A journal is
not a record of everything that happened. No later account resembling a plan
means only that nothing resembling it was written down, and "absent from the
writing" is exactly the inference this project refuses to make on its own.

So it retrieves and the owner answers. For each plan it finds the owner's own
later occasions that most resemble it, lays them beside it, and asks one
question with the answers written in. What the answers add up to (how many plans
were carried out, in which areas, what happened instead) is counted only from
what the owner said.

The resemblance is by words, from the situation and the response. A plan rarely
has an outcome, so the shape comparison used elsewhere does not fit. Words find
candidates; they settle nothing. A plan to call someone and an occasion of
calling them share words, and so do a plan and an occasion that merely took
place in the same kitchen. Hence the owner.

    uv run python scripts/plans_followed.py build   # write the sheet
    uv run python scripts/plans_followed.py read    # count the answers

Counts to the terminal. The sheet and the answers stay in data/, which holds the
owner's writing and never leaves the machine.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.reference_evaluation import account_fingerprint, account_key  # noqa: E402

FORMAT = "plans-followed-1"

#: The one question, and every answer it accepts. Written into the sheet
#: verbatim: the first hand-check asked a two-clause question with a negation in
#: it, got "its not", and the answer was read backwards.
QUESTION = "Was this plan carried out?"
ANSWERS = {
    "yes #N": "yes, and account #N below is when",
    "yes": "yes, but none of the accounts below is it",
    "partly": "some of it was done",
    "no": "no, it was not carried out",
    "unsure": "you cannot say",
}
_ANSWER = re.compile(r"^(yes #(\d+)|yes|partly|no|unsure)$")

#: Words too common to mean two accounts are about the same thing.
_COMMON = frozenset(
    "a an and as at be been but by for from had has have he her his i if in is "
    "it its me my not of on or she so that the their them then there they this "
    "to up was we were what when which who will with would you your going want "
    "wanted plan planned try tried get got make made do did".split())

#: Below this share of the smaller account's words, a candidate is noise.
MIN_OVERLAP = 0.2
MIN_SHARED = 2
CANDIDATES = 3


def _words(e: dict) -> set[str]:
    text = " ".join((e.get(f) or "") for f in ("situation", "response", "demand"))
    return {w for w in re.findall(r"[a-z']+", text.lower())
            if w not in _COMMON and len(w) > 2}


def plans(episodes: list[dict]) -> list[int]:
    """The owner's own plans, by position in the cache."""
    return [i for i, e in enumerate(episodes)
            if e.get("modality") == "planned" and e.get("actor") == "self"]


def candidates(episodes: list[dict], plan: int) -> list[tuple[float, int, str]]:
    """Later occasions that most resemble a plan: (overlap, index, order).

    `order` is "after" when both are dated and the occasion is on or after the
    plan's day; "unknown" when either is undated. An occasion dated before the
    plan is never offered: it cannot be the plan carried out. The dates are the
    days the writing was made, which for a plan is the day it was planned.
    """
    p = episodes[plan]
    mine = _words(p)
    found = []
    for i, e in enumerate(episodes):
        if i == plan or e.get("modality") != "happened" or e.get("actor") != "self":
            continue
        pd, ed = p.get("occurredOn"), e.get("occurredOn")
        if pd and ed and ed < pd:
            continue
        theirs = _words(e)
        shared = mine & theirs
        if len(shared) < MIN_SHARED or not mine or not theirs:
            continue
        overlap = len(shared) / min(len(mine), len(theirs))
        if overlap >= MIN_OVERLAP:
            found.append((round(overlap, 2), i, "after" if pd and ed else "unknown"))
    found.sort(key=lambda t: (-t[0], t[1]))
    return found[:CANDIDATES]


def _account(e: dict, label: str) -> list[str]:
    sources = ", ".join(f"{c.get('sourceType', 'reflection')} {c.get('entryId')}"
                        for c in e.get("citations", []))
    lines = [f"{label} — written {e.get('occurredOn') or 'undated'} — {sources}", ""]
    for field in ("situation", "demand", "response", "outcome"):
        if e.get(field):
            lines.append(f"- {field}: {e[field]}")
    return lines + [""]


def sheet(episodes: list[dict]) -> str:
    wanted = plans(episodes)
    lines = [
        "# Plans, and whether anything followed them",
        "",
        f"<!-- format: {FORMAT} -->",
        "",
        "Each plan below is shown with the later accounts that most resemble it.",
        "Resembling is not the same as being the plan carried out. They share",
        "words, nothing more, so judge each one yourself.",
        "",
        f"Answer one question for each plan: **{QUESTION}**",
        "",
        "Write exactly one of these on the `answer:` line:",
        "",
    ]
    lines += [f"- `{a}` — {meaning}" for a, meaning in ANSWERS.items()]
    lines += ["", "The `note:` line is optional: what happened instead, or why.",
              "", "---", ""]
    for i in wanted:
        e = episodes[i]
        lines += [f"## plan #{i}  ·  key `{account_key(e)}`",
                  f"<!-- fingerprint: {account_fingerprint(e)} -->", ""]
        lines += _account(e, "**The plan**")
        found = candidates(episodes, i)
        if found:
            lines += ["Later accounts that resemble it:", ""]
            for overlap, j, order in found:
                when = "" if order == "after" else " (order unknown: one of them is undated)"
                lines += _account(episodes[j], f"**#{j}** — {overlap:.0%} of words shared{when}")
        else:
            lines += ["No later account resembles it.", ""]
        lines += ["`answer:` ", "", "`note:` ", "", "---", ""]
    return "\n".join(lines) + "\n"


def read(text: str, episodes: list[dict]) -> dict:
    """The owner's answers, bound to the content they were given about."""
    if f"<!-- format: {FORMAT} -->" not in text.splitlines():
        raise ValueError("Not a plans sheet this version can read.")
    out = {}
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        head = re.match(r"plan #(\d+)\s+·\s+key `([0-9a-f]{12})`", block)
        if not head:
            continue
        index, key = int(head.group(1)), head.group(2)
        found = re.search(r"^<!-- fingerprint: ([0-9a-f]{64}) -->$", block, re.M)
        if index >= len(episodes) or account_key(episodes[index]) != key:
            raise ValueError(f"Plan #{index} is not in this cache any more.")
        if not found or found.group(1) != account_fingerprint(episodes[index]):
            raise ValueError(f"Plan #{index} has changed since the sheet was made.")
        answer = re.search(r"^`answer:`[ \t]*(.*?)[ \t]*$", block, re.M)
        note = re.search(r"^`note:`[ \t]*(.*?)[ \t]*$", block, re.M)
        given = (answer.group(1) if answer else "").strip()
        if not given:
            out[key] = {"index": index, "answer": None}
            continue
        m = _ANSWER.match(given)
        if not m:
            raise ValueError(f"Plan #{index}: {given!r} is not one of the answers.")
        out[key] = {"index": index,
                    "answer": "yes" if given.startswith("yes") else given,
                    "carried_out_as": int(m.group(2)) if m.group(2) else None,
                    "note": (note.group(1).strip() if note else "") or None}
    return {"format": FORMAT, "plans": out}


def summary(answers: dict, episodes: list[dict]) -> dict:
    """Counts only from what the owner said; unanswered plans stay unanswered."""
    rows = answers["plans"].values()
    by_answer = Counter(r["answer"] or "unanswered" for r in rows)
    not_done = Counter((episodes[r["index"]].get("domain") or "unstated").lower()
                       for r in rows if r["answer"] == "no")
    return {"answers": dict(by_answer),
            "recorded_occasion_found": sum(1 for r in rows if r.get("carried_out_as") is not None),
            "not_carried_out_by_area": dict(not_done)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("what", choices=("build", "read"))
    ap.add_argument("--cache", default="data/episodes.json")
    ap.add_argument("--sheet", default="data/plans-followed.md")
    ap.add_argument("--out", default="data/plans-followed.json")
    args = ap.parse_args()

    episodes = json.loads(Path(args.cache).read_text())["episodes"]
    path = Path(args.sheet)

    if args.what == "build":
        if path.exists():
            print(f"Refusing to overwrite {path}: it may hold answers. "
                  "Choose another --sheet.")
            return 1
        path.write_text(sheet(episodes))
        wanted = plans(episodes)
        with_candidates = sum(1 for i in wanted if candidates(episodes, i))
        print(f"{len(wanted)} plans, {with_candidates} with a resembling later account, "
              f"{len(wanted) - with_candidates} with none")
        print(f"written to {path}")
        return 0

    answers = read(path.read_text(), episodes)
    Path(args.out).write_text(json.dumps(answers, indent=1))
    s = summary(answers, episodes)
    print(f"{len(answers['plans'])} plans")
    for name in ("yes", "partly", "no", "unsure", "unanswered"):
        if s["answers"].get(name):
            print(f"  {name:<11} {s['answers'][name]:>3}")
    print(f"  carried out and written about: {s['recorded_occasion_found']}")
    if s["not_carried_out_by_area"]:
        print(f"  not carried out, across {len(s['not_carried_out_by_area'])} area(s)")
    print(f"\nwritten to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
