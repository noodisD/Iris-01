#!/usr/bin/env python3
"""Prepare new owner judgments of v4 extracted fields against original passages.

    uv run python scripts/reference_labels.py build --count 10
    uv run python scripts/reference_labels.py read

Old reference sheets are historical; no array position or old verdict is
transferred to a newly extracted account. Both artifacts remain owner-only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

from agent.episodes import Episode, GROUNDED_FIELDS
from agent.reference_evaluation import CHECKED, account_fingerprint
from scripts.read_episodes import DEFAULT_CACHE, load_cache
from scripts.spot_check import choose

REFERENCE_VERSION = 3
VERDICTS = {
    "supported": "the original passage says this about this actor, event or report",
    "not_stated": "the passage does not state this, in either direction",
    "contradicted": "the original passage says something incompatible",
    "wrong_modality": "it supports a plan/hypothetical rather than an event, or vice versa",
    "wrong_actor": "the statement belongs to someone other than this account's actor",
    "unsure": "the original passage does not settle the question",
}


def sheet(episodes: list[dict], wanted: tuple[int, ...]) -> str:
    if len(set(wanted)) != len(wanted) or any(index < 0 or index >= len(episodes) for index in wanted):
        raise ValueError("selected accounts must be unique and in the v4 cache")
    rows = [Episode.from_dict(row) for row in episodes]
    cohort = [account_fingerprint(episodes[index]) for index in wanted
              if any(getattr(rows[index], field) is not None for field in CHECKED)]
    if len(set(cohort)) != len(cohort) or not cohort:
        raise ValueError("selected accounts have duplicate or empty field identities")
    lines = ["# New v4 reference judgments — one grounded field at a time", "",
             f"<!-- reference-format: {REFERENCE_VERSION} -->",
             f"<!-- reference-cohort: {','.join(cohort)} -->", "",
             "For each extracted field judge its original passage, actor, negation",
             "and record kind. An original quote's presence is not contextual support.",
             "Write one complete verdict after each marker below, without copying old labels.",
             "", *[f"- `{name}` — {meaning}" for name, meaning in VERDICTS.items()], "", "---", ""]
    for index in wanted:
        account = rows[index]
        fields = [field for field in CHECKED if getattr(account, field) is not None]
        if not fields:
            continue
        key = account_fingerprint(episodes[index])
        lines += [f"## account #{index} · fingerprint `{key}`", "",
                  f"Owner actor: **{account.actor}** · record kind: **{account.record_kind}**",
                  "Written on: " + (account.recorded_on.isoformat() if account.recorded_on else "undated"),
                  "", "Original cited passages:", ""]
        for citation in account.citations:
            lines += [*[f"> {line}" for line in citation.text.splitlines()], ">",
                      f"> — {citation.source_type} {citation.entry_id}, "
                      f"written {citation.entry_date or 'undated'}", ""]
        for field in fields:
            lines += [f"**{field}** — extracted:", *[f"> {line}" for line in getattr(account, field).splitlines()],
                      "", f"`{field}:` ", ""]
        lines += ["---", ""]
    return "\n".join(lines)


def read(text: str) -> dict:
    marker = f"<!-- reference-format: {REFERENCE_VERSION} -->"
    if text.splitlines().count(marker) != 1:
        raise ValueError("unsupported reference format; build a new v4 sheet")
    cohorts = re.findall(r"^<!-- reference-cohort: ([0-9a-f,]*) -->$", text, re.M)
    if len(cohorts) != 1:
        raise ValueError("reference cohort missing or duplicated")
    cohort = cohorts[0].split(",") if cohorts[0] else []
    if len(cohort) != len(set(cohort)) or any(not re.fullmatch(r"[0-9a-f]{64}", key) for key in cohort):
        raise ValueError("reference cohort has ambiguous account identity")
    out = {}
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        heading = block.splitlines()[0] if block.splitlines() else ""
        match = re.fullmatch(r"account #(\d+) · fingerprint `([0-9a-f]{64})`", heading)
        if match is None:
            raise ValueError("malformed account heading")
        index, key = int(match.group(1)), match.group(2)
        if key in out:
            raise ValueError("duplicate reference fingerprint")
        verdicts = {}
        for field, raw in re.findall(r"^`([^`\n]+):`[ \t]*([^\n]*)$", block, re.M):
            if field not in CHECKED or field in verdicts:
                raise ValueError("unknown or duplicate field marker")
            value = raw.strip()
            if value and value not in VERDICTS:
                raise ValueError("invalid field verdict")
            if value:
                verdicts[field] = value
            else:
                verdicts[field] = None
        out[key] = {"index": index, "fingerprint": key, "verdicts": verdicts}
    if set(out) != set(cohort):
        raise ValueError("reference sheet omits or adds an account")
    return {"version": REFERENCE_VERSION, "cohort": cohort, "accounts": out}


def validate_reference(reference: dict, episodes: list[dict]) -> list[int]:
    if not isinstance(reference, dict) or reference.get("version") != REFERENCE_VERSION:
        raise ValueError("unsupported reference version")
    accounts, cohort = reference.get("accounts"), reference.get("cohort")
    if (not isinstance(accounts, dict) or not accounts or not isinstance(cohort, list)
            or len(cohort) != len(set(cohort)) or set(cohort) != set(accounts)):
        raise ValueError("incomplete reference cohort")
    fingerprints = {}
    for index, row in enumerate(episodes):
        account = Episode.from_dict(row)
        key = account_fingerprint(row)
        if key in fingerprints:
            raise ValueError("duplicate account identity in v4 cache")
        fingerprints[key] = (index, account)
    wanted = []
    scored = 0
    for key, reference_row in accounts.items():
        if (not re.fullmatch(r"[0-9a-f]{64}", key) or
                not isinstance(reference_row, dict) or
                reference_row.get("fingerprint") != key or
                key not in fingerprints):
            raise ValueError("reference fingerprint does not match current v4 content")
        index, account = fingerprints[key]
        expected = {field for field in GROUNDED_FIELDS if getattr(account, field) is not None}
        verdicts = reference_row.get("verdicts")
        if (not isinstance(verdicts, dict) or set(verdicts) != expected
                or any(value not in VERDICTS for value in verdicts.values())):
            raise ValueError("incomplete current field judgments")
        wanted.append(index)
        scored += sum(value != "unsure" for value in verdicts.values())
    if not scored:
        raise ValueError("all reference judgments are unsure")
    return sorted(wanted)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("what", choices=("build", "read"))
    parser.add_argument("--cache", default=DEFAULT_CACHE)
    parser.add_argument("--user", type=int, default=1)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--sheet", default="data/reference-labels-v4.md")
    parser.add_argument("--out", default="data/reference-labels-v4.json")
    args = parser.parse_args(argv)
    if args.user <= 0 or args.count <= 0:
        print("Owner and count must be positive.")
        return 1
    try:
        rows, _ = load_cache(Path(args.cache), args.user)
    except (OSError, ValueError, KeyError, TypeError):
        print("Could not read a current neutral v4 cache.")
        return 1
    episodes = [row.as_dict() for row in rows]
    path = Path(args.sheet)
    out = Path(args.out)
    if args.what == "build":
        if path.exists() or path.resolve() == Path(args.cache).resolve():
            print("Refusing to overwrite an earlier review sheet or cache.")
            return 1
        wanted = tuple(index for index, _ in choose(episodes, args.count))
        try:
            content = sheet(episodes, wanted)
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                file.write(content)
        except (OSError, ValueError):
            print("Could not build a new review sheet.")
            return 1
        print(f"{len(wanted)} current v4 accounts need new owner judgments at {path}")
        return 0
    if (out.exists() or out.resolve() in {path.resolve(), Path(args.cache).resolve()}):
        print("Refusing to overwrite a previous reference, sheet or cache.")
        return 1
    try:
        reference = read(path.read_text())
        validate_reference(reference, episodes)
        out.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(reference, file, indent=1)
    except (OSError, ValueError):
        print("Reference incomplete or stale; no labels were written.")
        return 1
    counts = Counter(verdict for row in reference["accounts"].values()
                     for verdict in row["verdicts"].values())
    print(f"{len(reference['accounts'])} accounts, {sum(counts.values())} judged fields at {out}")
    for name, count in counts.items():
        print(f"  {name:<16} {count:>3}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
