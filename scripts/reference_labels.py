#!/usr/bin/env python3
"""Build, and read back, the reference judgments any field-checker is measured on.

The first hand-check asked "is the response what they actually did?" — a good
question about an occasion and the wrong question about a field. It ran together
things that fail differently: a passage that says nothing, a passage that says
the opposite, a passage that supports an intention while the account reports a
deed, and a memory that disagrees with what was written at the time. Scored
against those labels, a checker that answered "supported" every time scored 54%,
and the checker that was built scored 54%.

So the labels are rebuilt to answer one question exactly:

    does this passage support this field, for this actor, at this modality,
    with this meaning?

with the ways of failing kept apart, and `unsure` preserved rather than resolved.
An ambiguous reference judgment is not a missing one: it marks a field that
cannot be scored, and a checker should be measured on what it does with those
too.

    uv run python scripts/reference_labels.py build     # write the sheet
    uv run python scripts/reference_labels.py read      # parse it back

Counts to the terminal; the sheet and the parsed labels stay in data/.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.field_support import CHECKED, account_key  # noqa: E402

#: The verdicts, and what each one means. `wrong_modality` and `wrong_actor` are
#: separate because they are the two failures a passage can produce while being
#: entirely real and entirely relevant — and they are the two the extractor is
#: most likely to make, since it chooses both from the same sentence.
VERDICTS = {
    "supported": "the passage states this, for this person, at this modality",
    "not_stated": "the passage does not say it, either way",
    "contradicted": "the passage says something that cannot be true alongside it",
    "wrong_modality": "the passage supports it as intended or imagined, and the "
                      "account reports it as done — or the reverse",
    "wrong_actor": "the passage is about someone other than the account's actor",
    "unsure": "the passage is genuinely ambiguous. Leave it here; do not resolve it",
}

#: The accounts that were checked by hand once already. Re-labelled rather than
#: re-sampled, so the old verdicts and the new ones describe the same accounts.
REVIEWED = (0, 1, 2, 3, 4, 9, 10, 48, 61, 72)


def sheet(episodes: list[dict], wanted: tuple[int, ...]) -> str:
    lines = [
        "# Reference judgments — one field at a time",
        "",
        "For each field below, the question is only this:",
        "",
        "> Does the passage support **this field**, for **this actor**, at",
        "> **this modality**, with this meaning?",
        "",
        "Not whether the occasion went well. Not whether the account is useful.",
        "Not whether you remember it differently now — if the writing says it,",
        "it is supported, even if you would put it another way today.",
        "",
        "Write one of these after each field:",
        "",
    ]
    lines += [f"- `{name}` — {meaning}" for name, meaning in VERDICTS.items()]
    lines += ["", "---", ""]

    for i in wanted:
        e = episodes[i]
        fields = [f for f in CHECKED if e.get(f)]
        if not fields:
            continue
        lines += [
            f"## account #{i}  ·  key `{account_key(e)}`",
            "",
            f"The account says this is **{e.get('modality')}**, by "
            f"**{e.get('actor')}**.",
            "",
            "The passages, as the writing has them:",
            "",
        ]
        for c in e.get("citations", []):
            lines += [f"> {c.get('text')}", ">",
                      f"> — {c.get('sourceType', 'reflection')} "
                      f"{c.get('entryId')}, written "
                      f"{c.get('entryDate') or 'undated'}", ""]
        for field in fields:
            lines += [
                f"**{field}** — the account says: {e.get(field)}",
                "",
                f"`{field}:` ",
                "",
            ]
        lines += ["---", ""]
    return "\n".join(lines)


def read(text: str) -> dict:
    """The filled sheet as labels, keyed by account rather than by position."""
    out: dict[str, dict] = {}
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        head = block.splitlines()[0]
        m = re.search(r"account #(\d+)\s+·\s+key `([0-9a-f]+)`", head)
        if not m:
            continue
        index, key = int(m.group(1)), m.group(2)
        verdicts = {}
        for field in CHECKED:
            found = re.search(rf"^`{field}:`\s*(\S.*?)\s*$", block, re.M)
            if found and found.group(1) in VERDICTS:
                verdicts[field] = found.group(1)
        out[key] = {"index": index, "verdicts": verdicts}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("what", choices=("build", "read"))
    ap.add_argument("--cache", default="data/episodes.json")
    ap.add_argument("--sheet", default="data/reference-labels.md")
    ap.add_argument("--out", default="data/reference-labels.json")
    args = ap.parse_args()

    episodes = json.loads(Path(args.cache).read_text())["episodes"]
    path = Path(args.sheet)

    if args.what == "build":
        path.write_text(sheet(episodes, REVIEWED))
        asked = sum(1 for i in REVIEWED
                    for f in CHECKED if episodes[i].get(f))
        print(f"{len(REVIEWED)} accounts, {asked} fields to judge")
        print(f"written to {path}")
        return 0

    if not path.exists():
        print(f"no sheet at {path}: run `build` first.")
        return 1
    labels = read(path.read_text())
    filled = sum(len(v["verdicts"]) for v in labels.values())
    counts = Counter(v for row in labels.values() for v in row["verdicts"].values())
    Path(args.out).write_text(json.dumps(labels, indent=1))
    print(f"{len(labels)} accounts, {filled} field(s) judged")
    for name in VERDICTS:
        if counts.get(name):
            print(f"  {name:<16} {counts[name]:>3}")
    print(f"\nwritten to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
