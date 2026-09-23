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

from agent.reference_evaluation import (
    CHECKED,
    account_fingerprint,
    account_key,
)

REFERENCE_VERSION = 2

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
    if len(set(wanted)) != len(wanted) or any(i < 0 or i >= len(episodes) for i in wanted):
        raise ValueError("Selected accounts must be unique and present in the cache.")
    cohort = [account_key(episodes[i]) for i in wanted
              if any(isinstance(episodes[i].get(f), str) and episodes[i][f].strip()
                     for f in CHECKED)]
    if len(set(cohort)) != len(cohort):
        raise ValueError("Selected accounts have ambiguous identities.")
    lines = [
        "# Reference judgments — one field at a time",
        "",
        f"<!-- reference-format: {REFERENCE_VERSION} -->",
        f"<!-- reference-cohort: {','.join(cohort)} -->",
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
        fields = [f for f in CHECKED if isinstance(e.get(f), str) and e[f].strip()]
        if not fields:
            continue
        lines += [
            f"## account #{i}  ·  key `{account_key(e)}`",
            "",
            f"<!-- fingerprint: {account_fingerprint(e)} -->",
            "",
            f"The account says this is **{e.get('modality')}**, by "
            f"**{e.get('actor')}**.",
            "",
            "The passages, as the writing has them:",
            "",
        ]
        for c in e.get("citations", []):
            lines += [f"> {line}" for line in (c.get("text") or "").splitlines()]
            lines += [">",
                      f"> — {c.get('sourceType', 'reflection')} "
                      f"{c.get('entryId')}, written "
                      f"{c.get('entryDate') or 'undated'}", ""]
        for field in fields:
            lines += [
                f"**{field}** — the account says:",
                *[f"> {line}" for line in e[field].splitlines()],
                "",
                f"`{field}:` ",
                "",
            ]
        lines += ["---", ""]
    return "\n".join(lines)


def _read_verdicts(block: str, index: int) -> dict[str, str]:
    verdicts = {}
    seen = set()
    for field, raw_value in re.findall(r"^`([^`\n]+):`[ \t]*([^\n]*)$", block, re.M):
        if field not in CHECKED or field in seen:
            raise ValueError(f"Unknown or duplicate field marker for account #{index}.")
        seen.add(field)
        value = raw_value.strip()
        if not value:
            continue
        if value not in VERDICTS:
            raise ValueError(f"Invalid verdict for account #{index}, field {field}.")
        verdicts[field] = value
    return verdicts


def read(text: str) -> dict:
    """Parse explicit labels without guessing, silently dropping, or overwriting."""
    marker = f"<!-- reference-format: {REFERENCE_VERSION} -->"
    if text.splitlines().count(marker) != 1:
        raise ValueError(
            "This sheet has no supported content fingerprints. Build a new sheet "
            "at a different path; keep the old sheet and judgments unchanged."
        )
    cohorts = re.findall(r"^<!-- reference-cohort: ([0-9a-f,]*) -->$", text, re.M)
    if len(cohorts) != 1:
        raise ValueError("Missing or duplicate reference cohort; rebuild the sheet.")
    cohort = cohorts[0].split(",") if cohorts[0] else []
    out: dict[str, dict] = {}
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        head = block.splitlines()[0] if block.splitlines() else ""
        m = re.fullmatch(r"account #(\d+)[ \t]+·[ \t]+key `([0-9a-f]{12})`", head)
        if not m:
            raise ValueError("Malformed account heading in reference sheet.")
        index, key = int(m.group(1)), m.group(2)
        if key in out:
            raise ValueError(f"Duplicate account key at account #{index}.")
        fingerprints = re.findall(r"^<!-- fingerprint: ([0-9a-f]{64}) -->$", block, re.M)
        if len(fingerprints) != 1:
            raise ValueError(f"Missing or duplicate fingerprint for account #{index}.")
        out[key] = {"index": index, "fingerprint": fingerprints[0],
                    "verdicts": _read_verdicts(block, index)}
    return {"version": REFERENCE_VERSION, "cohort": cohort, "accounts": out}


def _validate_account(row: dict, episode: dict, index: int) -> int:
    """Return the number of definite labels on an unchanged, fully judged account."""
    if not isinstance(row, dict) or not isinstance(row.get("verdicts"), dict):
        raise ValueError("Malformed account in reference judgments.")
    if row.get("fingerprint") != account_fingerprint(episode):
        raise ValueError(f"Reference content is stale for account #{index}; review it again.")
    fields = {f for f in CHECKED if isinstance(episode.get(f), str) and episode[f].strip()}
    verdicts = row["verdicts"]
    if not fields or set(verdicts) != fields:
        raise ValueError(f"Incomplete or unexpected field judgments for account #{index}.")
    for field, verdict in verdicts.items():
        if not isinstance(verdict, str) or verdict not in VERDICTS:
            raise ValueError(f"Invalid verdict for account #{index}, field {field}.")
    return sum(verdict != "unsure" for verdict in verdicts.values())


def validate_reference(reference: dict, episodes: list[dict]) -> list[int]:
    """Require complete, current judgments before writing labels or making calls.

    `unsure` is a completed judgment, not an unanswered field. At least one
    definite label is still required for a scored evaluation. Indices are only
    display hints: matching is by account identity AND content fingerprint.
    """
    if not isinstance(reference, dict) or reference.get("version") != REFERENCE_VERSION:
        raise ValueError("Unsupported reference format; rebuild a fingerprinted sheet.")
    accounts = reference.get("accounts")
    if not isinstance(accounts, dict) or not accounts:
        raise ValueError("No reference judgments; fill and parse the reference sheet first.")
    cohort = reference.get("cohort")
    if (not isinstance(cohort, list)
            or any(not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{12}", key)
                   for key in cohort)
            or len(set(cohort)) != len(cohort)
            or set(cohort) != set(accounts)):
        raise ValueError("Reference accounts do not match the complete recorded cohort.")
    by_key: dict[str, list[int]] = {}
    for i, episode in enumerate(episodes):
        by_key.setdefault(account_key(episode), []).append(i)
    wanted = []
    scorable = 0
    for key, row in accounts.items():
        matches = by_key.get(key, [])
        if len(matches) != 1:
            raise ValueError("A reference account is missing or ambiguous in this cache.")
        i = matches[0]
        scorable += _validate_account(row, episodes[i], i)
        wanted.append(i)
    if not scorable:
        raise ValueError("All reference judgments are unsure; no fields can be scored.")
    return sorted(wanted)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("what", choices=("build", "read"))
    ap.add_argument("--cache", default="data/episodes.json")
    ap.add_argument("--sheet", default="data/reference-labels.md")
    ap.add_argument("--out", default="data/reference-labels.json")
    args = ap.parse_args(argv)

    out = Path(args.out)
    if args.what == "read" and any(
        out.resolve() == source.resolve()
        or (out.exists() and source.exists() and out.samefile(source))
        for source in (Path(args.cache), Path(args.sheet))
    ):
        print("Refusing to overwrite the cache or sheet with parsed labels.")
        return 1
    try:
        episodes = json.loads(Path(args.cache).read_text())["episodes"]
        if not isinstance(episodes, list) or any(not isinstance(e, dict) for e in episodes):
            raise ValueError("Malformed episode cache.")
    except (OSError, ValueError, KeyError, TypeError):
        print("Could not read the episode cache.")
        return 1
    path = Path(args.sheet)

    if args.what == "build":
        if path.exists():
            print(f"Refusing to overwrite {path}; choose a new --sheet path.")
            return 1
        try:
            rendered = sheet(episodes, REVIEWED)
            with path.open("x") as output:
                output.write(rendered)
        except (OSError, ValueError):
            print("Could not build the sheet; check its path and selected accounts.")
            return 1
        asked = sum(1 for i in REVIEWED
                    for f in CHECKED
                    if isinstance(episodes[i].get(f), str) and episodes[i][f].strip())
        print(f"{len(REVIEWED)} accounts, {asked} fields to judge")
        print(f"written to {path}")
        return 0

    if not path.exists():
        print(f"no sheet at {path}: run `build` first.")
        return 1
    try:
        labels = read(path.read_text())
        validate_reference(labels, episodes)
    except (OSError, ValueError) as exc:
        print(f"Reference not ready: {exc}")
        return 1
    accounts = labels["accounts"]
    filled = sum(len(v["verdicts"]) for v in accounts.values())
    counts = Counter(v for row in accounts.values() for v in row["verdicts"].values())
    out.write_text(json.dumps(labels, indent=1))
    print(f"{len(accounts)} accounts, {filled} field(s) judged")
    for name, count in counts.items():
        print(f"  {name:<16} {count:>3}")
    print(f"\nwritten to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
