"""uv run python -m agent.doctor [--json] [--no-store] [--only AREA_OR_ID ...] [--can-restart]"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from . import changes, report, run, store


def can_restart() -> tuple[bool, str]:
    """Whether restarting IRIS now throws away work in progress."""
    from .checks_moving import _worker

    state = _worker()
    if state is None:
        return True, "IRIS is not answering; a restart loses nothing in progress."
    job = state.get("current")
    if not job:
        return True, "The worker is idle."
    kind = job.get("source_type")
    if kind == "personal_dynamics":
        return False, ("A pattern update is running; a restart throws away its progress. Wait, unless a "
                       "newer read has already made it out of date.")
    return False, f"A {kind} job is running; wait for it (usually minutes)."


def main() -> int:
    ap = argparse.ArgumentParser(prog="doctor")
    ap.add_argument("--json", action="store_true", help="print the whole report as JSON")
    ap.add_argument("--no-store", action="store_true", help="do not keep this run")
    ap.add_argument("--only", nargs="*", help="areas (moving, data, quality) or check ids")
    ap.add_argument("--can-restart", action="store_true", help="say whether a restart is safe now; exit 0 if so")
    ap.add_argument("--fix", action="store_true",
                    help="carry out the safe-auto repairs failing checks name, then check again")
    args = ap.parse_args()
    logging.disable(logging.WARNING)
    if args.can_restart:
        ok, why = can_restart()
        print(("yes: " if ok else "no: ") + why)
        return 0 if ok else 1
    only = set(args.only) if args.only else None
    results = run(only)
    run_id = None if args.no_store else store(results)
    diff = changes(results, run_id)
    repaired: list[dict] = []
    if args.fix:
        from .fixes import apply

        repaired = apply(results, run_id)
        if repaired:
            # What is stored and shown last is the state after the repairs.
            results = run(only)
            after_id = None if args.no_store else store(results)
            diff = changes(results, after_id)
    if args.json:
        print(json.dumps({"results": results, "changes": diff, "repaired": repaired}, default=str, indent=1))
    else:
        text = report(results, diff)
        if repaired:
            text += "\n\nRepaired (safe-auto):\n" + "\n".join(
                f"  {r['outcome']:<9} {r['id']}: {r['summary']}" for r in repaired)
        print(text)
    return 1 if any(r["status"] == "fail" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
