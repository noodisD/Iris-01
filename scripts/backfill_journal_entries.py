#!/usr/bin/env python3
"""Move legacy `journal_entries` rows into `reflections` (see ADR-0010).

Journal entries and reflections are one concept stored in two tables. New
writes all go to `reflections`; this moves anything already in the old table so
nothing written before the change becomes invisible.

Idempotent: a row is skipped if a reflection with the same user, date and
content already exists, so re-running is safe.

Two steps, because they answer different questions.

`--dry-run` / no flag moves the rows: each legacy entry becomes a reflection,
and the old row stays where it is. Embeddings and theme_occurrences still point
at ('journal_entry', id), correctly attributed to the row that produced them.

`--retire` finishes the job, which migration 0015 requires before it will drop
the table: every legacy row must already have a reflection, and then each
reference — embeddings, theme_occurrences, processing_queue — is repointed at
that reflection through an explicit old id -> new id crosswalk, and the legacy
rows are deleted. It refuses to run if a single row cannot be matched, and
prints the crosswalk it used. Until this ran, the migration's own instruction
could not be satisfied: moving the rows alone leaves both the rows and their
references in place, which is exactly what the migration's guard counts.

    uv run python scripts/backfill_journal_entries.py --dry-run
    uv run python scripts/backfill_journal_entries.py
    uv run python scripts/backfill_journal_entries.py --retire --dry-run
    uv run python scripts/backfill_journal_entries.py --retire
"""

import argparse
import sys

from agent.database import db


def retire(dry_run: bool) -> int:
    """Repoint every reference at the moved reflections, then delete the rows.

    The guard in migration 0015 counts rows *and* references, so a database
    that has only had the rows copied still cannot be upgraded. This builds the
    crosswalk that makes the references portable, and refuses the whole
    operation if any legacy row has no reflection to point at — a reference to
    an entry that no longer exists would be worse than a table nobody reads.
    """
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('journal_entries');")
        if cur.fetchone()[0] is None:
            print("Nothing to retire: the legacy table is already gone.")
            return 0

        cur.execute(
            """SELECT j.id, r.id
                 FROM journal_entries j
                 LEFT JOIN LATERAL (
                      SELECT id FROM reflections
                       WHERE user_id = j.user_id
                         AND reflection_date = j.created_at::date
                         AND content = j.raw_text
                       ORDER BY id LIMIT 1) r ON TRUE
                ORDER BY j.id;""")
        crosswalk = cur.fetchall()
        unmatched = [old for old, new in crosswalk if new is None]
        if unmatched:
            print(f"Refusing to retire: {len(unmatched)} legacy row(s) have no reflection "
                  f"(ids {unmatched[:10]}...). Run this script without --retire first.")
            return 1
        if not crosswalk:
            print("Nothing to retire: journal_entries is empty. Migration 0015 can drop it.")
            return 0

        moved_refs = 0
        for old_id, new_id in crosswalk:
            print(f"  journal_entry {old_id} -> reflection {new_id}")
            if dry_run:
                continue
            for table in ("embeddings", "theme_occurrences", "processing_queue"):
                cur.execute(
                    f"""UPDATE {table} SET source_type = 'reflection', source_id = %s
                         WHERE source_type = 'journal_entry' AND source_id = %s;""",
                    (new_id, old_id))
                moved_refs += cur.rowcount
        if dry_run:
            print(f"\nwould retire {len(crosswalk)} row(s) and repoint their references.")
            return 0

        cur.execute("DELETE FROM journal_entries;")
        deleted = cur.rowcount
        conn.commit()
        print(f"\nretired {deleted} row(s), repointed {moved_refs} reference(s). "
              "Migration 0015 can now drop the table.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would happen without writing")
    ap.add_argument("--retire", action="store_true",
                    help="repoint every reference at the moved reflections and delete "
                         "the legacy rows, so migration 0015 can drop the table")
    args = ap.parse_args()

    if args.retire:
        return retire(args.dry_run)

    with db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('journal_entries');")
            if cur.fetchone()[0] is None:
                print("Nothing to migrate: the legacy table was retired (migration 0015).")
                return 0
            cur.execute("""
                SELECT id, user_id, raw_text, wellbeing_data, created_at
                FROM journal_entries
                ORDER BY id;
            """)
            rows = cur.fetchall()

            if not rows:
                print("Nothing to migrate: journal_entries is empty.")
                return 0

            moved = skipped = 0
            for entry_id, user_id, raw_text, wellbeing, created_at in rows:
                entry_date = created_at.date()
                cur.execute(
                    """SELECT id FROM reflections
                       WHERE user_id = %s AND reflection_date = %s AND content = %s;""",
                    (user_id, entry_date, raw_text),
                )
                if cur.fetchone():
                    skipped += 1
                    continue

                if args.dry_run:
                    print(f"  would move journal_entries.{entry_id} "
                          f"(user {user_id}, {entry_date})")
                    moved += 1
                    continue

                wb = wellbeing or {}
                cur.execute(
                    """INSERT INTO reflections
                           (user_id, reflection_date, content, energy_level,
                            clarity_level, created_at, processing_status)
                       VALUES (%s, %s, %s, %s, %s, %s, 'complete')
                       RETURNING id;""",
                    (user_id, entry_date, raw_text,
                     wb.get("energy"), wb.get("clarity"), created_at),
                )
                new_id = cur.fetchone()[0]
                print(f"  journal_entries.{entry_id} -> reflections.{new_id}")
                moved += 1

            if not args.dry_run:
                conn.commit()

            verb = "would move" if args.dry_run else "moved"
            print(f"\n{verb} {moved}, skipped {skipped} already present "
                  f"(of {len(rows)} legacy rows).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
