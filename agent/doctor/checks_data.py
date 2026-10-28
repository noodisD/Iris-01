"""Do the data promises hold? Each is something that must always be true.

Counts and ids only. A promise that breaks here was broken quietly: nothing
raised, and a screen built on it simply showed less, or something false.
"""

from __future__ import annotations

from ..database import db
from . import Result, check


def _count(sql: str, *args) -> int:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(sql, args)
        return int(cur.fetchone()[0] or 0)


def _ids(sql: str, *args, limit: int = 20) -> list[int]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(sql, args)
        return [row[0] for row in cur.fetchall()][:limit]


def _promise(id: str, count: int, ok: str, bad: str, *, evidence: str, causes: list[str], action: str,
             action_class="safe-auto", ids: list[int] | None = None, level="fail") -> Result:
    if count == 0:
        return Result(id, "ok", ok, value=0, expected="0", evidence=evidence)
    return Result(id, level, bad.format(n=count), value=count, expected="0", evidence=evidence,
                  causes=causes, action=action, action_class=action_class, details={"ids": ids or []})


JOURNAL = ("r.content_format <> 'session' AND length(btrim(coalesce(r.content, ''))) > 0")


@check("data.unembedded", "data")
def unembedded() -> Result:
    sql = f"""SELECT r.id FROM reflections r WHERE {JOURNAL}
               AND NOT EXISTS (SELECT 1 FROM embeddings e WHERE e.source_type = 'reflection' AND e.source_id = r.id)
               AND r.processing_status = 'complete'"""
    ids = _ids(sql)
    return _promise("data.unembedded", _count(f"SELECT count(*) FROM ({sql}) x"),
                    "Every processed entry can be recalled.", "{n} processed entries have no embedding.",
                    evidence=sql, ids=ids,
                    causes=["Embedding failed after the entry was marked complete."],
                    action="Re-queue those entries' processing ('reflection' jobs).")


@check("data.unread", "data")
def unread() -> Result:
    sql = """SELECT r.id FROM reflections r
              WHERE r.evidence_eligible AND length(btrim(coalesce(r.content, ''))) > 0
                AND NOT EXISTS (SELECT 1 FROM discovery_reads d WHERE d.reflection_id = r.id
                                  AND d.source_revision = r.discovery_revision)
                AND NOT EXISTS (SELECT 1 FROM processing_queue q
                                 WHERE q.source_type = 'discovery' AND q.source_id = r.id)"""
    queued = _count("SELECT count(*) FROM processing_queue WHERE source_type = 'discovery'")
    result = _promise("data.unread", _count(f"SELECT count(*) FROM ({sql}) x"),
                      "Every eligible entry is read, or queued to be.",
                      "{n} eligible entries are not read and not queued.", evidence=sql, ids=_ids(sql),
                      causes=["A read failed and its job was removed.", "ensure_pending has not run yet."],
                      action="The worker re-queues these on its next pass; if they stay, see queue.exhausted.")
    result.details["queued"] = queued
    return result


@check("data.quotes", "data")
def quotes() -> Result:
    from ..readable import locate
    from ..translation import for_reading

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT a.reflection_id, a.data->'citations', r.content, r.translation, r.translation_hash
                         FROM discovery_accounts a JOIN reflections r ON r.id = a.reflection_id
                        WHERE a.is_current""")
        # A translated record is read in English (ADR-0036): its quotes are in
        # the current translation, not in the original words.
        accounts = [(rid, cites, for_reading(content, english, made_from))
                    for rid, cites, content, english, made_from in cur.fetchall()]
        cur.execute("""SELECT c.id, c.quote, r.content FROM idea_citations c
                         JOIN reflections r ON r.id = c.reflection_id WHERE c.status <> 'rejected'""")
        ideas = cur.fetchall()
    lost = [rid for rid, cites, content in accounts for c in (cites or [])
            if not c.get("text") or locate(content or "", c["text"]) is None]
    lost_ideas = [cid for cid, quote, content in ideas if locate(content or "", quote or "") is None]
    total = len(lost) + len(lost_ideas)
    return _promise("data.quotes", total,
                    f"All {sum(len(c or []) for _, c, _ in accounts) + len(ideas)} quotes are found word for word.",
                    "{n} quotes are not found word for word in their source.",
                    evidence="locate(source, quote) over current account citations and idea citations",
                    ids=sorted(set(lost))[:20] + lost_ideas[:20],
                    causes=["The source was edited and its accounts were not invalidated.",
                            "A reading copy's words drifted from the entry.",
                            "A translation was replaced without the record being read again."],
                    action="Re-read the listed entries (needs-owner: sets off a pattern update).",
                    action_class="needs-owner")


@check("data.orphan_embeddings", "data")
def orphans() -> Result:
    sql = """SELECT count(*) FROM embeddings e WHERE
               (e.source_type = 'reflection' AND NOT EXISTS (SELECT 1 FROM reflections r WHERE r.id = e.source_id))
            OR (e.source_type = 'message' AND NOT EXISTS (SELECT 1 FROM conversation_messages m WHERE m.id = e.source_id))
            OR (e.source_type = 'session_passage' AND NOT EXISTS (SELECT 1 FROM session_passages p WHERE p.id = e.source_id))
            OR (e.source_type = 'entry_passage' AND NOT EXISTS (SELECT 1 FROM entry_passages p WHERE p.id = e.source_id))"""
    return _promise("data.orphan_embeddings", _count(sql), "No memory points at something deleted.",
                    "{n} embeddings point at deleted sources.", evidence=sql,
                    causes=["A delete path that forgets one kind of vector."],
                    action="Delete those embedding rows; find the delete path that left them.")


@check("data.passages", "data")
def passages() -> Result:
    from ..entry_passages import MIN_WORDS

    sessions_sql = """SELECT r.id FROM reflections r
                       WHERE r.content_format = 'session' AND r.source IN ('session', 'questionnaire')
                         AND r.processing_status = 'complete'
                         AND NOT EXISTS (SELECT 1 FROM session_passages p WHERE p.reflection_id = r.id)"""
    long_sql = f"""SELECT r.id FROM reflections r WHERE {JOURNAL} AND r.processing_status = 'complete'
                    AND array_length(regexp_split_to_array(btrim(r.content), '\\s+'), 1) > {MIN_WORDS}
                    AND NOT EXISTS (SELECT 1 FROM entry_passages p WHERE p.reflection_id = r.id)"""
    ids = _ids(sessions_sql) + _ids(long_sql)
    n = _count(f"SELECT count(*) FROM ({sessions_sql}) x") + _count(f"SELECT count(*) FROM ({long_sql}) x")
    return _promise("data.passages", n, "Every session and long entry has recall passages.",
                    "{n} sessions or long entries have no recall passages.", evidence=f"{sessions_sql}\n{long_sql}",
                    ids=ids, causes=["Passage indexing failed (it logs and carries on)."],
                    action="Run pipeline._index_entry_passages / re-queue the reflection job for those ids.")


@check("data.reading_copies", "data")
def reading_copies() -> Result:
    from ..readable import same_words

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, content, reading_copy FROM reflections WHERE reading_copy IS NOT NULL")
        rows = cur.fetchall()
    stale = [rid for rid, content, copy in rows if not same_words(content or "", copy)]
    return _promise("data.reading_copies", len(stale), f"All {len(rows)} reading copies have their entry's words.",
                    "{n} reading copies no longer have their entry's words.", ids=stale,
                    evidence="same_words(content, reading_copy) for every stored copy",
                    causes=["An edit path that did not clear reading_copy."],
                    action="Set reading_copy to NULL for those ids; the next read makes a new one.")


@check("data.excluded_counted", "data")
def excluded_counted() -> Result:
    sql = """SELECT count(*) FROM reflections r WHERE NOT r.evidence_eligible AND (
               EXISTS (SELECT 1 FROM discovery_accounts a WHERE a.reflection_id = r.id AND a.is_current)
            OR EXISTS (SELECT 1 FROM theme_occurrences o WHERE o.source_type = 'reflection' AND o.source_id = r.id))"""
    return _promise("data.excluded_counted", _count(sql), "Nothing excluded from evidence is counted.",
                    "{n} entries excluded from evidence still have accounts or theme occurrences.", evidence=sql,
                    causes=["An entry was excluded after it was read, without invalidating its accounts."],
                    action="Invalidate those entries' accounts (needs-owner: sets off a pattern update).",
                    action_class="needs-owner")


@check("data.duplicates", "data")
def duplicates() -> Result:
    sql = """SELECT count(*) FROM (SELECT content_hash FROM reflections WHERE content_hash IS NOT NULL
               GROUP BY content_hash HAVING count(*) > 1) x"""
    return _promise("data.duplicates", _count(sql), "No two entries have the same text.",
                    "{n} texts are stored more than once.", evidence=sql, level="warn",
                    causes=["An import that ran twice.", "The source itself repeated an entry."],
                    action="Show the owner the pair; deleting is their call.", action_class="needs-owner")
