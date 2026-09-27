"""Two copies of IRIS's database for a with-and-without-history test.

The owner wants to know what the imported archive is worth: does IRIS answer
better knowing years of writing, or only what it was given directly (entries
written in the app, check-ins, chat, habits, decisions and phone readings)?

`iris_eval_full` is a straight copy. `iris_eval_direct` is the same copy with
the historical writing taken out, together with everything derived from it,
so nothing learnt from the archive can leak in by another route:

- the imported entries themselves, their import records, and their embeddings
  for memory search;
- quotes on ideas, and ideas left with no quote at all;
- pattern occasions that cite an imported entry, with their labels;
- topic clusters' samples and occurrences from those entries, and topics left
  empty;
- the older engines' stored findings, which were computed over everything;
- IRIS's own past chat replies, which were written with the archive in view.
  The owner's own chat messages stay: they were given directly.

Neither copy is the live database, and both drop queued background work so a
test instance never repeats a paid call.
"""
from __future__ import annotations

from typing import Any

#: Stored outputs of the older analytical engines, computed over all entries.
DERIVED_FINDINGS = ("pattern_evidence", "pattern_confidence", "pattern_resolutions",
                    "decision_impacts", "insight_priorities", "theme_tensions", "pattern_leverage")


def prune_to_direct(cur: Any) -> dict[str, int]:
    """Take the historical archive out of the database behind `cur`. Returns counts."""
    n: dict[str, int] = {}

    def run(name: str, sql: str, args: tuple = ()) -> None:
        cur.execute(sql, args)
        n[name] = n.get(name, 0) + cur.rowcount

    cur.execute("""CREATE TEMP TABLE historical ON COMMIT DROP AS
                   SELECT reflection_id AS id FROM import_items WHERE reflection_id IS NOT NULL
                   UNION SELECT id FROM reflections WHERE source IN ('import', 'voice')""")
    run("embeddings", "DELETE FROM embeddings WHERE source_type = 'reflection' AND source_id IN (SELECT id FROM historical)")
    run("topic occurrences", "DELETE FROM theme_occurrences WHERE source_type = 'reflection' AND source_id IN (SELECT id FROM historical)")
    run("topic samples", """DELETE FROM theme_prototypes WHERE source_type = 'import_item'
                              OR (source_type = 'reflection' AND source_id IN (SELECT id FROM historical))""")
    run("pattern occasions", """DELETE FROM occasions o WHERE EXISTS (
                                  SELECT 1 FROM jsonb_array_elements(o.citations) c
                                   WHERE c->>'sourceType' = 'reflection'
                                     AND (c->>'entryId')::int IN (SELECT id FROM historical))""")
    run("import records", "DELETE FROM import_items")
    run("imports", "DELETE FROM import_batches")
    # Quotes on ideas go with their entries (ON DELETE CASCADE).
    run("entries", "DELETE FROM reflections WHERE id IN (SELECT id FROM historical)")
    run("ideas", """UPDATE ideas i SET status = 'rejected' WHERE status <> 'rejected' AND NOT EXISTS (
                      SELECT 1 FROM idea_citations c WHERE c.idea_id = i.id AND c.status <> 'rejected')""")
    run("idea links", """UPDATE idea_links SET status = 'rejected' WHERE status <> 'rejected' AND (
                           from_idea_id IN (SELECT id FROM ideas WHERE status = 'rejected')
                           OR to_idea_id IN (SELECT id FROM ideas WHERE status = 'rejected'))""")
    run("idea critiques", "DELETE FROM idea_critiques WHERE idea_id IN (SELECT id FROM ideas WHERE status = 'rejected')")
    run("topics", """UPDATE themes t SET status = 'superseded' WHERE status IN ('active', 'candidate') AND NOT EXISTS (
                       SELECT 1 FROM theme_occurrences o WHERE o.theme_id = t.id)""")
    cur.execute("""UPDATE themes t SET occurrence_count = s.n, first_seen_at = s.first, last_seen_at = s.last
                     FROM (SELECT theme_id, count(*) n, min(occurred_at) first, max(occurred_at) last
                             FROM theme_occurrences GROUP BY theme_id) s
                    WHERE t.id = s.theme_id""")
    for table in DERIVED_FINDINGS:
        run("older findings", f"DELETE FROM {table}")
    run("IRIS's past replies", "DELETE FROM conversation_messages WHERE role = 'assistant'")
    run("queued work", "DELETE FROM processing_queue")
    return n


def clear_queue(cur: Any) -> int:
    """The full copy keeps everything but queued work."""
    cur.execute("DELETE FROM processing_queue")
    return cur.rowcount
