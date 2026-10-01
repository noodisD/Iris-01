#!/usr/bin/env python3
"""Evaluate the predeclared synthetic personal-dynamics reference, never owner data.

Live output is a local evidence ledger, NOT model self-validation. An independent
human must map generated definitions to reference definitions and audit factual
clauses/hypotheses before the release thresholds can be declared met.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/personal_dynamics_reference.json"
# Captured from the complete reference before any provider run. Changing any
# source OR label requires a separately reviewed new reference and hash.
REFERENCE_SHA256 = "f4c271e99e66bd8d7734408b82a537721e30c4cd37e136e4bd81fb66a3666577"
LENS_IDS = frozenset((
    "yes-before-capacity", "needs-left-unsaid", "taking-over-to-feel-secure",
    "clear-ask-or-limit", "certainty-before-action", "reassurance-that-expires",
    "preparing-instead-of-starting", "small-reversible-step", "moving-finish-line",
    "rest-must-be-earned", "comparison-becomes-verdict", "repair-without-self-verdict",
    "relief-with-an-open-loop", "thinking-without-new-information",
    "distance-after-hurt", "noticing-before-responding", "sprint-then-empty",
    "too-many-open-commitments", "capacity-signals-overruled", "recovery-before-empty",
    "borrowed-standard-own-goal", "commitment-outlives-purpose",
    "waiting-for-right-feeling", "own-reason-concrete-step",
))


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def validate(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    fingerprint = hashlib.sha256(raw).hexdigest()
    if fingerprint != REFERENCE_SHA256:
        raise ValueError(f"Reference changed ({fingerprint}); fixed pre-provider fingerprint "
                         f"is {REFERENCE_SHA256}. Do not relabel against model output.")
    fixture = json.loads(raw)
    if fixture.get("schemaVersion") != 1 or set(fixture) != {
        "schemaVersion", "purpose", "acceptance", "cases", "lensCases",
        "lensDates", "lensReports"
    }:
        raise ValueError("Wrong reference schema")
    if not all(fixture["acceptance"].get(k) == v for k, v in {
        "membershipPrecision": .90, "membershipRecall": .80,
        "dynamicRecovery": .80, "factualClausePrecision": .95, "safetyErrors": 0
    }.items()):
        raise ValueError("Release thresholds are not the predeclared thresholds")
    cases = fixture["cases"]
    if {row["id"] for row in cases} != {
        "request_capacity", "outcomes_unrecorded", "report_not_events", "overtime_reasons",
        "motive_rejected", "role_order_negation", "retelling_triangle",
        "out_of_range_bridge", "shared_concern", "useful_unmapped",
        "lens_process_boundaries", "untrusted_source_and_history"
    } or len(cases) != 12:
        raise ValueError("Exactly the twelve required reference scenarios must be fixed")
    if {row["lensId"] for row in fixture["lensCases"]} != LENS_IDS or len(fixture["lensCases"]) != 24:
        raise ValueError("Each of the 24 process lenses needs exactly one linked and excluded case")
    if set(fixture["lensReports"]) != LENS_IDS or set(fixture["lensDates"]) != {
        "linkedProcess", "nearMiss", "ownerReport"
    }:
        raise ValueError("Every lens needs a predeclared owner report and three recorded dates")
    for recorded_on in fixture["lensDates"].values():
        date.fromisoformat(recorded_on)
    if any(not isinstance(text, str) or not text.strip()
           for text in fixture["lensReports"].values()):
        raise ValueError("Lens self-reports must be explicit and nonblank")
    if {c["split"] for c in cases} != {"development", "holdout"}:
        raise ValueError("A distinct development and holdout are required")
    for row in fixture["lensCases"]:
        if row["split"] not in ("development", "holdout") or not all(
            isinstance(row.get(k), str) and row[k].strip()
            for k in ("positive", "nearMiss", "exclusion")
        ) or row["positive"] == row["nearMiss"]:
            raise ValueError(f"Invalid process boundary: {row['lensId']}")
    for case in cases:
        if case["split"] not in ("development", "holdout"):
            raise ValueError(f"Invalid split: {case['id']}")
        entries = {e["key"]: e for e in case["entries"]}
        if len(entries) != len(case["entries"]):
            raise ValueError(f"Duplicate source key: {case['id']}")
        for entry in entries.values():
            if not entry["text"].strip():
                raise ValueError(f"Blank source: {case['id']} / {entry['key']}")
            date.fromisoformat(entry["recordedOn"])
        names = set()
        for expected in case["expectedDynamics"]:
            if expected["key"] in names or not expected["context"].strip() or not expected["response"].strip():
                raise ValueError(f"Invalid target definition: {case['id']}")
            names.add(expected["key"])
            for field in ("support", "exception", "responseElsewhere", "excluded", "ownerReport"):
                if not set(expected.get(field, [])).issubset(entries):
                    raise ValueError(f"Unknown {field} source in {case['id']}")
            for a, b in expected.get("sameEvent", []) + expected.get("distinctEvent", []):
                if a not in entries or b not in entries or a == b:
                    raise ValueError(f"Invalid planted event pair in {case['id']}")
            for key, passages in expected["admissiblePassages"].items():
                if key not in entries or not passages or any(p not in entries[key]["text"] for p in passages):
                    raise ValueError(f"Passage does not exist verbatim in {case['id']} / {key}")
        for key, passages in case.get("admissiblePassages", {}).items():
            if key not in entries or any(p not in entries[key]["text"] for p in passages):
                raise ValueError(f"Case-level passage missing in {case['id']} / {key}")
    seeds = [case for case in cases if case.get("seedSmoke")]
    if len(seeds) != 1 or len(seeds[0]["entries"]) != 8 or seeds[0]["id"] != "request_capacity":
        raise ValueError("Smoke case must be the fixed eight-entry request cohort")
    return fixture, fingerprint


def cohort(fixture: dict, split: str) -> list[dict]:
    return [case for case in fixture["cases"] if split == "all" or case["split"] == split]


def estimate(fixture: dict, split: str) -> dict:
    """Approximate paid work; observed account and definition counts are not yet known."""
    from agent.connections import MAX_PAIRS_PER_REPLY
    from agent.lens_matching import _MAX_ROWS
    from agent.config import settings
    from agent.intelligence import Intelligence

    selected = cohort(fixture, split)
    lens_rows = [x for x in fixture["lensCases"] if split == "all" or x["split"] == split]
    batches = [(len(c["entries"]), sum(len(e["text"]) for e in c["entries"]))
               for c in selected if c["entries"]]
    batches += [(3, len(l["positive"]) + len(l["nearMiss"]) +
                 len(fixture["lensReports"][l["lensId"]])) for l in lens_rows]
    # Each source has an extraction and contextual field check. Synthesis includes
    # candidate merge, full membership, event identity, and lens/unit decisions;
    # output-row caps, not only input context, determine the number of calls.
    reading = sum(2 * n for n, _ in batches)
    synthesis = 0
    tokens_in = 0
    for n, chars in batches:
        definitions = min(n, 6)
        interpreted = min(definitions, 2)
        requests = (1 + math.ceil(definitions * (definitions - 1) / 2 / MAX_PAIRS_PER_REPLY)
                    + definitions + math.ceil(n * definitions / MAX_PAIRS_PER_REPLY)
                    + math.ceil(n * (n - 1) / 2 / MAX_PAIRS_PER_REPLY)
                    + interpreted * (2 + math.ceil(24 * n / _MAX_ROWS)))
        synthesis += requests
        tokens_in += (math.ceil(chars / 4) * (3 + definitions + n + 24 * interpreted)
                      + requests * 1500)
    tokens_out = reading * 1100 + synthesis * 1700
    return {"readingRequests": reading, "synthesisRequests": synthesis,
            "tokensIn": tokens_in, "tokensOut": tokens_out,
            "costText": Intelligence.estimate(settings.OPENAI_WORKER_MODEL, tokens_in, tokens_out),
            "approximate": True}


def json_value(value: Any) -> Any:
    if hasattr(value, "as_dict"):
        return json_value(value.as_dict())
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if isinstance(value, (date,)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unserializable production payload: {type(value).__name__}")


def _case_entries(case: dict) -> tuple[list[dict], dict[str, int]]:
    ids = {entry["key"]: index for index, entry in enumerate(case["entries"], 1)}
    return ([{"id": ids[entry["key"]], "source_type": "reflection",
              "date": date.fromisoformat(entry["recordedOn"]),
              "content": entry["text"], "content_format": "plain"}
             for entry in case["entries"]], ids)


def _run_case(case: dict, lenses: list, model: Any) -> dict:
    from agent.episodes import EpisodeReader
    from agent.discovery_worker import verify_reading
    from agent import connections
    from agent.reference_evaluation import account_fingerprint

    entries, source_ids = _case_entries(case)
    row: dict[str, Any] = {"caseId": case["id"], "split": case["split"],
                            "sourceIds": source_ids, "stage": "reading"}
    try:
        accounts = []
        omitted_accounts = omitted_fields = 0
        # Production reads and context-checks each eligible reflection before
        # pooling verified accounts for whole-archive discovery.
        for entry in entries:
            reader = EpisodeReader(user_id=0, intelligence=model)
            extracted = reader.read([entry])
            checked, dropped, omitted = verify_reading(extracted, model)
            accounts.extend(checked)
            omitted_accounts += reader.omitted_accounts + dropped
            omitted_fields += reader.omitted_fields + omitted
        row["accounts"] = [{"fingerprint": account_fingerprint(e.as_dict()),
                             "sourceKeys": [key for key, source_id in source_ids.items()
                                            if any(c.entry_id == source_id for c in e.citations)],
                             "payload": e.as_dict()} for e in accounts]
        row["omittedAccounts"] = omitted_accounts
        row["omittedFields"] = omitted_fields
        row["stage"] = "discovering"
        draft = connections.discover_dynamics(accounts, model)
        # Definition identity is owner-scoped even in a synthetic, database-free
        # run. Revalidate after binding a non-real synthetic owner ID.
        from agent.dynamics import DiscoveryDraft
        draft = DiscoveryDraft.from_dict({**draft.as_dict(), "userId": 1})
        row["draft"] = json_value(draft)
        row["stage"] = "interpreting"
        view = connections.interpret_view(draft, "all", date(2026, 9, 30), lenses, model)
        row["view"] = json_value(view)
        row["stage"] = "complete"
    except Exception as exc:
        # An unavailable stage is a failure in the fixed denominator, not no match.
        row["failure"] = {"stage": row["stage"], "kind": type(exc).__name__, "reason": str(exc)}
    return row


def run_live(fixture: dict, split: str) -> dict:
    from agent.config import settings
    from agent.intelligence import Intelligence
    from agent.library import load

    lenses = load()
    model = Intelligence(model=settings.OPENAI_WORKER_MODEL)
    results = [_run_case(case, lenses, model) for case in cohort(fixture, split)
               if case["entries"]]
    # Lens pairs are independent contextual source units. A near miss never
    # counts as satisfying a requirement just because the wording resembles it.
    for lens in fixture["lensCases"]:
        if split != "all" and lens["split"] != split:
            continue
        dates = fixture["lensDates"]
        case = {"id": "lens_" + lens["lensId"], "split": lens["split"],
                "entries": [
                    {"key": "linked_process", "recordedOn": dates["linkedProcess"],
                     "text": lens["positive"]},
                    {"key": "excluded_process", "recordedOn": dates["nearMiss"],
                     "text": lens["nearMiss"]},
                    {"key": "owner_report", "recordedOn": dates["ownerReport"],
                     "text": fixture["lensReports"][lens["lensId"]]}
                ]}
        results.append(_run_case(case, lenses, model))
    return {"model": settings.OPENAI_WORKER_MODEL, "results": results}


def independent_review_template(fixture: dict, split: str) -> dict:
    """Reference-side denominators; model output must not fill adjudication."""
    selected = cohort(fixture, split)
    definitions = [f"{c['id']}:{d['key']}" for c in selected for d in c["expectedDynamics"]]
    positives = sum(len(d["support"]) + len(d.get("ownerReport", []))
                    for c in selected for d in c["expectedDynamics"])
    negatives = sum(len(d["exception"]) + len(d["responseElsewhere"]) + len(d["excluded"])
                    for c in selected for d in c["expectedDynamics"])
    safety = [f"{c['id']}:{boundary}" for c in selected for boundary in c["safety"]]
    lens_count = sum(split == "all" or l["split"] == split for l in fixture["lensCases"])
    return {"expectedDefinitions": definitions,
            "denominators": {"definitions": len(definitions), "positiveMemberships": positives,
                             "negativeOrContraryMemberships": negatives,
                             "lensLinked": lens_count, "lensNearMiss": lens_count,
                             "safetyBoundaries": len(safety)},
            "constantReject": {"membershipPrecision": None, "membershipRecall": 0 if positives else None,
                               "dynamicRecovery": 0 if definitions else None},
            "constantAccept": {"membershipPrecision": positives / (positives + negatives)
                               if positives + negatives else None,
                               "membershipRecall": 1 if positives else None},
            "manualAdjudicationRequired": {"definitionAlignment": definitions,
                                           "factualClauses": "Audit every generated factual clause against original cited paragraphs",
                                           "hypotheses": "Audit tentative relevance, rival, explicit rejection and source scope",
                                           "safety": safety},
            "predeclaredScore": {
                "membershipPrecision": None, "membershipRecall": None,
                "dynamicRecovery": None, "factualClausePrecision": None,
                "safetyErrors": None,
                "status": "awaiting_independent_adjudication"
            },
            "releaseGates": {"passed": None, "reason": "Independent adjudication not supplied; a generator cannot grade itself"}}


def report_path(path: Path) -> Path:
    """Refuse unignored output and collisions before any paid work starts."""
    root = Path(__file__).resolve().parents[1]
    full = path.expanduser().resolve()
    if not any(full.is_relative_to((root / dirname).resolve()) for dirname in ("data", ".jev-runs")):
        raise ValueError("--out must be inside the gitignored data/ or .jev-runs/ directory")
    if full.exists():
        raise ValueError(f"Refusing to overwrite an earlier evaluation: {full}")
    return full


def save_report(path: Path, report: dict) -> None:
    # Passages and even synthetic generated claims belong only in ignored local data.
    full = report_path(path)
    full.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    body = {**report, "reportHash": hashlib.sha256(canonical(report)).hexdigest()}
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(full, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(body, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"Local 0600 evidence report: {full} (sha256 {body['reportHash']})")


def seed_smoke_db(fixture: dict) -> dict:
    # Crucially do not import tests.conftest: its import redirects POSTGRES_DB,
    # while its setup can create a database. This mode accepts existing marked,
    # completely empty scratch databases ONLY; no owner connection is touched.
    name = os.environ.get("POSTGRES_DB", "")
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*test[a-zA-Z0-9_]*", name):
        raise ValueError("--seed-smoke-db requires explicit POSTGRES_DB with 'test' in its name")
    from agent.config import settings
    if settings.POSTGRES_DB != name:
        raise ValueError("Configured PostgreSQL database differs from the explicitly named test database")
    import psycopg2
    from psycopg2 import sql
    conn = psycopg2.connect(dbname=name, user=settings.POSTGRES_USER,
                            password=settings.POSTGRES_PASSWORD,
                            host=settings.POSTGRES_HOST, port=settings.POSTGRES_PORT)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public._iris_test_database')")
            if cur.fetchone()[0] is None:
                raise ValueError("Database lacks the suite's _iris_test_database ownership marker")
            cur.execute("SELECT count(*) FROM public._iris_test_database")
            if cur.fetchone()[0] != 1:
                raise ValueError("Invalid test database ownership marker")
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                        "AND tablename NOT IN ('_iris_test_database', 'schema_migrations')")
            for (table,) in cur.fetchall():
                cur.execute(sql.SQL("SELECT EXISTS (SELECT 1 FROM {} LIMIT 1)").format(
                    sql.Identifier("public", table)))
                if cur.fetchone()[0]:
                    raise ValueError(f"Scratch database is nonempty ({table}); refusing to seed")
    finally:
        conn.close()
    from agent.migrations import upgrade
    from agent.database import db
    upgrade()
    case = next(c for c in fixture["cases"] if c.get("seedSmoke"))
    today = date.today()
    # The permanent reference is anchored to 2026-09-30. Seeded entries retain
    # its wording/semantics but shift explicit EVENT dates along with write dates.
    event_days = {19: "September 11", 13: "September 17", 10: "September 20",
                  7: "September 23", 4: "September 26"}
    substitutions = {old: f"{(today - timedelta(days=offset)):%B} "
                     f"{(today - timedelta(days=offset)).day}"
                     for offset, old in event_days.items()}
    substitutions["Sept 11"] = substitutions["September 11"]
    owner = db.create_user("dynamics_smoke")
    inserted = {}
    for entry in case["entries"]:
        content = entry["text"]
        for original, shifted in substitutions.items():
            content = content.replace(original, shifted)
        inserted[entry["key"]] = db.create_reflection(
            owner, content, reflection_date=today + timedelta(days=entry["offsetDays"]))
    return {"ownerId": owner, "sourceIds": inserted,
            "expectedLedger": [{"key": d["key"], "support": d["support"],
                                "exception": d["exception"],
                                "atLeastIndependent": d["atLeastIndependent"]}
                               for d in case["expectedDynamics"]]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--live", action="store_true")
    modes.add_argument("--seed-smoke-db", action="store_true")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--split", choices=("development", "holdout", "all"), default="holdout")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    fixture, fingerprint = validate(args.fixture)
    if args.seed_smoke_db:
        if args.out:
            parser.error("--seed-smoke-db prints source IDs; --out is for live evidence reports")
        print(json.dumps(seed_smoke_db(fixture), indent=2))
        return 0
    reference = independent_review_template(fixture, args.split)
    budget = estimate(fixture, args.split)
    if args.dry_run:
        if args.out:
            parser.error("--dry-run does not write reports")
        print(json.dumps({"referenceHash": fingerprint, "split": args.split,
                          "estimate": budget, "reference": reference}, indent=2))
        return 0
    if not args.out:
        parser.error("--live requires --out in local ignored data/ or .jev-runs/")
    report_path(args.out)
    report = {"schemaVersion": 1, "referenceHash": fingerprint, "split": args.split,
              "estimate": budget, "reference": reference, **run_live(fixture, args.split)}
    save_report(args.out, report)
    failures = sum("failure" in row for row in report["results"])
    print(f"Provider-stage failures: {failures}/{len(report['results'])}; independent factual/semantic adjudication pending. Release gates not asserted.")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as exc:
        print(f"Evaluation refused: {exc}", file=sys.stderr)
        sys.exit(2)
