#!/usr/bin/env python3
"""Move legacy `journal_entries` rows into `reflections` (see ADR-0010).

Journal entries and reflections are one concept stored in two tables. New
writes all go to `reflections`; this moves anything already in the old table so
nothing written before the change becomes invisible.

Idempotent: a row is skipped if a reflection with the same user, date and
content already exists, so re-running is safe.

Existing embeddings and theme_occurrences still point at ('journal_entry', id)
and are deliberately left alone — they are historical evidence, correctly
attributed to the row that produced them, and rewriting their source would
change what the analytical engines have already concluded. The old table is
therefore kept read-only rather than dropped; dropping it needs a migration
tool (ADR-0008).

    uv run python scripts/backfill_journal_entries.py --dry-run
    uv run python scripts/backfill_journal_entries.py
"""

import argparse
import sys

from agent.database import db


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would move without writing")
    args = ap.parse_args()

    with db.connection() as conn:
        with conn.cursor() as cur:
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
