"""Owner-scoped persistence for ideas. No model calls."""

from __future__ import annotations

from typing import Any

from psycopg2.extras import Json

from agent.database import db
from agent.observations import _normalized

from .models import (
    SYMMETRIC_LINK_KINDS,
    content_hash,
    empty_dropped,
    rename_wikilinks,
    statement_key,
    wikilink_targets,
)

_RUN_KEYS = (
    "id", "user_id", "kind", "started_at", "finished_at", "status", "model",
    "prompt_version", "items_read", "passes_planned", "passes_completed",
    "proposed", "dropped", "error",
)


def _run(row: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(_RUN_KEYS, row, strict=True))


def start_run(
    user_id: int,
    kind: str,
    model: str | None,
    prompt_version: str | None,
    items_read: int,
    passes_planned: int,
) -> int:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO idea_runs
                (user_id, kind, model, prompt_version, items_read, passes_planned, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'running')
            RETURNING id;
            """,
            (user_id, kind, model, prompt_version, items_read, passes_planned),
        )
        run_id = int(cur.fetchone()[0])
        conn.commit()
        return run_id


def finish_run(
    run_id: int,
    user_id: int,
    *,
    status: str,
    passes_completed: int,
    proposed: int,
    dropped: dict[str, int],
    error: str | None,
) -> None:
    counts = empty_dropped()
    counts.update({key: int(dropped.get(key, 0)) for key in counts})
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE idea_runs
               SET status = %s, passes_completed = %s, proposed = %s,
                   dropped = %s, error = %s, finished_at = NOW()
             WHERE id = %s AND user_id = %s;
            """,
            (status, passes_completed, proposed, Json(counts), error, run_id, user_id),
        )
        conn.commit()


def get_run(run_id: int, user_id: int) -> dict[str, Any] | None:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {", ".join(_RUN_KEYS)}
              FROM idea_runs
             WHERE id = %s AND user_id = %s;
            """,
            (run_id, user_id),
        )
        row = cur.fetchone()
    return _run(row) if row else None


def latest_run(user_id: int) -> dict[str, Any] | None:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {", ".join(_RUN_KEYS)}
              FROM idea_runs
             WHERE user_id = %s
             ORDER BY started_at DESC, id DESC
             LIMIT 1;
            """,
            (user_id,),
        )
        row = cur.fetchone()
    return _run(row) if row else None


def list_registry(user_id: int) -> list[dict[str, Any]]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, statement, statement_key, domain, status, position
              FROM ideas
             WHERE user_id = %s
             ORDER BY id;
            """,
            (user_id,),
        )
        keys = ("id", "statement", "statement_key", "domain", "status", "position")
        return [dict(zip(keys, row, strict=True)) for row in cur.fetchall()]


def _lock_sources(cur: Any, user_id: int, reflection_ids: list[int]) -> dict[int, dict[str, Any]]:
    cur.execute(
        """
        SELECT id, content, evidence_eligible
          FROM reflections
         WHERE user_id = %s AND id = ANY(%s)
         ORDER BY id
         FOR UPDATE;
        """,
        (user_id, reflection_ids),
    )
    return {
        int(row[0]): {"content": row[1], "evidence_eligible": bool(row[2])}
        for row in cur.fetchall()
    }


def stage_citations(
    user_id: int,
    run_id: int,
    *,
    statement: str,
    domain: str,
    citations: list[dict[str, Any]],
    matched_id: int | None,
) -> dict[str, int]:
    """Insert a draft's new candidate citations, or record why none were saved.

    Returns counts under `created`, `already_decided`, `duplicate`, and
    `source_changed`. Never overwrites an existing citation's stance.
    """
    result = {"created": 0, "already_decided": 0, "duplicate": 0, "source_changed": 0}
    if not citations:
        result["source_changed"] = 1
        return result
    normalized = _normalized(statement)
    key = statement_key(normalized)
    reflection_ids = sorted({int(item["reflection_id"]) for item in citations})
    with db.connection() as conn, conn.cursor() as cur:
        sources = _lock_sources(cur, user_id, reflection_ids)
        for item in citations:
            source = sources.get(int(item["reflection_id"]))
            if (
                source is None
                or not source["evidence_eligible"]
                or content_hash(source["content"]) != item["source_hash"]
            ):
                result["source_changed"] = 1
                conn.rollback()
                return result

        idea_id = matched_id
        if idea_id is None:
            cur.execute(
                """
                INSERT INTO ideas
                    (user_id, statement, statement_key, domain, status, position, run_id)
                VALUES (%s, %s, %s, %s, 'candidate', 'exploring', %s)
                ON CONFLICT (user_id, statement_key) DO NOTHING
                RETURNING id;
                """,
                (user_id, normalized, key, domain, run_id),
            )
            inserted = cur.fetchone()
            if inserted:
                idea_id = int(inserted[0])
            else:
                cur.execute(
                    """
                    SELECT id, status FROM ideas
                     WHERE user_id = %s AND statement_key = %s
                     FOR UPDATE;
                    """,
                    (user_id, key),
                )
                existing = cur.fetchone()
                if existing is None:
                    result["source_changed"] = 1
                    conn.rollback()
                    return result
                idea_id = int(existing[0])
                if existing[1] == "rejected":
                    result["already_decided"] = 1
                    conn.rollback()
                    return result
        else:
            cur.execute(
                """
                SELECT status FROM ideas
                 WHERE user_id = %s AND id = %s
                 FOR UPDATE;
                """,
                (user_id, idea_id),
            )
            existing = cur.fetchone()
            if existing is None:
                result["source_changed"] = 1
                conn.rollback()
                return result
            if existing[0] == "rejected":
                result["already_decided"] = 1
                conn.rollback()
                return result

        for item in citations:
            cur.execute(
                """
                INSERT INTO idea_citations
                    (idea_id, reflection_id, quote, quote_hash, source_hash,
                     stance, status, run_id)
                VALUES (%s, %s, %s, %s, %s, %s, 'candidate', %s)
                ON CONFLICT (idea_id, reflection_id, quote_hash) DO NOTHING
                RETURNING id;
                """,
                (
                    idea_id,
                    int(item["reflection_id"]),
                    item["quote"],
                    item["quote_hash"],
                    item["source_hash"],
                    item["stance"],
                    run_id,
                ),
            )
            if cur.fetchone():
                result["created"] += 1
                continue
            cur.execute(
                """
                SELECT status FROM idea_citations
                 WHERE idea_id = %s AND reflection_id = %s AND quote_hash = %s;
                """,
                (idea_id, int(item["reflection_id"]), item["quote_hash"]),
            )
            prior = cur.fetchone()
            if prior and prior[0] in ("accepted", "rejected"):
                result["already_decided"] += 1
            else:
                result["duplicate"] += 1
        conn.commit()
    return result


def _valid_source(content: str | None, eligible: bool | None, source_hash: str) -> bool:
    if not eligible or content is None:
        return False
    return content_hash(content) == str(source_hash).strip()



def confirm_idea(
    user_id: int,
    idea_id: int,
    citation_ids: list[int],
    position: str,
    domain: str,
) -> str:
    """Accept the exact pending batch. Returns `missing` or `conflict` or `ok`."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT status FROM ideas
             WHERE user_id = %s AND id = %s
             FOR UPDATE;
            """,
            (user_id, idea_id),
        )
        idea = cur.fetchone()
        if idea is None:
            return "missing"
        if idea[0] == "rejected" or idea[0] not in ("candidate", "active"):
            conn.rollback()
            return "conflict"
        if not citation_ids or len(citation_ids) != len(set(citation_ids)):
            conn.rollback()
            return "conflict"
        cur.execute(
            """
            SELECT c.id, c.source_hash, r.content, r.evidence_eligible
              FROM idea_citations c
              LEFT JOIN reflections r
                ON r.id = c.reflection_id AND r.user_id = %s
             WHERE c.idea_id = %s AND c.status = 'candidate'
             ORDER BY c.id
             FOR UPDATE OF c;
            """,
            (user_id, idea_id),
        )
        rows = cur.fetchall()
        valid = [
            int(row[0])
            for row in rows
            if _valid_source(row[2], row[3], row[1])
        ]
        if valid != sorted(citation_ids) or len(valid) != len(citation_ids):
            conn.rollback()
            return "conflict"
        cur.execute(
            """
            UPDATE idea_citations
               SET status = 'accepted'
             WHERE idea_id = %s AND id = ANY(%s) AND status = 'candidate';
            """,
            (idea_id, citation_ids),
        )
        if cur.rowcount != len(citation_ids):
            conn.rollback()
            return "conflict"
        cur.execute(
            """
            UPDATE ideas
               SET status = 'active', position = %s, domain = %s,
                   confirmed_at = COALESCE(confirmed_at, NOW())
             WHERE user_id = %s AND id = %s;
            """,
            (position, domain, user_id, idea_id),
        )
        conn.commit()
    return "ok"


def reject_idea(user_id: int, idea_id: int) -> str:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT status FROM ideas
             WHERE user_id = %s AND id = %s
             FOR UPDATE;
            """,
            (user_id, idea_id),
        )
        row = cur.fetchone()
        if row is None:
            return "missing"
        if row[0] == "rejected" or row[0] not in ("candidate", "active"):
            conn.rollback()
            return "conflict"
        cur.execute(
            """
            UPDATE ideas SET status = 'rejected'
             WHERE user_id = %s AND id = %s;
            """,
            (user_id, idea_id),
        )
        conn.commit()
    return "ok"


def reject_citations(user_id: int, idea_id: int, citation_ids: list[int]) -> str | int:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT status FROM ideas
             WHERE user_id = %s AND id = %s
             FOR UPDATE;
            """,
            (user_id, idea_id),
        )
        idea = cur.fetchone()
        if idea is None:
            return "missing"
        if idea[0] != "active":
            conn.rollback()
            return "conflict"
        if not citation_ids or len(citation_ids) != len(set(citation_ids)):
            conn.rollback()
            return "conflict"
        cur.execute(
            """
            SELECT c.id, c.source_hash, r.content, r.evidence_eligible
              FROM idea_citations c
              LEFT JOIN reflections r
                ON r.id = c.reflection_id AND r.user_id = %s
             WHERE c.idea_id = %s AND c.status = 'candidate'
             ORDER BY c.id
             FOR UPDATE OF c;
            """,
            (user_id, idea_id),
        )
        valid = [
            int(row[0])
            for row in cur.fetchall()
            if _valid_source(row[2], row[3], row[1])
        ]
        if valid != sorted(citation_ids):
            conn.rollback()
            return "conflict"
        cur.execute(
            """
            UPDATE idea_citations
               SET status = 'rejected'
             WHERE idea_id = %s AND id = ANY(%s) AND status = 'candidate';
            """,
            (idea_id, citation_ids),
        )
        rejected = int(cur.rowcount)
        conn.commit()
    return rejected


def update_idea(
    user_id: int,
    idea_id: int,
    *,
    position: str | None = None,
    domain: str | None = None,
    statement: str | None = None,
    notes: str | None = None,
) -> str:
    """Change what the owner may change about an idea.

    Position and domain belong to an idea the owner has accepted. The wording
    and the notes can be changed while it is still a candidate too, since
    rewording a proposal is how the owner makes it theirs. A new wording that
    another idea already has is a conflict, not a merge. Renaming repoints
    every `[[link]]` to it in the owner's notes, so no page loses its link.
    """
    if position is None and domain is None and statement is None and notes is None:
        return "conflict"
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT status, statement FROM ideas
             WHERE user_id = %s AND id = %s
             FOR UPDATE;
            """,
            (user_id, idea_id),
        )
        row = cur.fetchone()
        if row is None:
            return "missing"
        status, old_statement = row
        editable = ("active",) if position is not None or domain is not None else ("active", "candidate")
        if status not in editable:
            conn.rollback()
            return "conflict"
        changes: dict[str, Any] = {"position": position, "domain": domain}
        if notes is not None:
            changes["notes"] = notes
        renamed = statement is not None and statement != old_statement
        if renamed:
            assert statement is not None
            new_key = statement_key(statement)
            cur.execute(
                "SELECT 1 FROM ideas WHERE user_id = %s AND statement_key = %s AND id <> %s;",
                (user_id, new_key, idea_id),
            )
            if cur.fetchone() is not None:
                conn.rollback()
                return "duplicate"
            changes |= {"statement": statement, "statement_key": new_key}
        changes = {column: value for column, value in changes.items() if value is not None}
        if changes:
            stamp = ", notes_updated_at = NOW()" if "notes" in changes else ""
            cur.execute(
                f"""
                UPDATE ideas SET {", ".join(f"{column} = %s" for column in changes)}{stamp}
                 WHERE user_id = %s AND id = %s;
                """,
                (*changes.values(), user_id, idea_id),
            )
        if renamed:
            assert statement is not None
            _repoint_notes(cur, user_id, statement_key(old_statement), statement)
        conn.commit()
    return "ok"


def _repoint_notes(cur: Any, user_id: int, old_key: str, new_statement: str) -> None:
    cur.execute(
        "SELECT id, notes FROM ideas WHERE user_id = %s AND notes LIKE %s;",
        (user_id, "%[[%"),
    )
    for other_id, text in cur.fetchall():
        rewritten = rename_wikilinks(text, old_key, new_statement)
        if rewritten != text:
            cur.execute(
                "UPDATE ideas SET notes = %s WHERE user_id = %s AND id = %s;",
                (rewritten, user_id, other_id),
            )


def idea_page(user_id: int, idea_id: int) -> dict[str, Any]:
    """An idea's notes, where its links point, and the pages that link to it."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, statement, statement_key, status, notes, notes_updated_at
              FROM ideas
             WHERE user_id = %s AND status <> 'rejected';
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    by_key = {key: (int(row_id), statement) for row_id, statement, key, _, _, _ in rows}
    page: dict[str, Any] = {"notes": "", "notes_updated_at": None, "links": {}, "backlinks": []}
    own_key = None
    for row_id, _, key, _, text, updated in rows:
        if int(row_id) == idea_id:
            own_key = key
            page["notes"] = text
            page["notes_updated_at"] = updated
            for target in wikilink_targets(text):
                found = by_key.get(statement_key(target))
                if found is not None:
                    page["links"][target] = found[0]
    if own_key is not None:
        for row_id, statement, _, status, text, _ in rows:
            if int(row_id) == idea_id:
                continue
            if any(statement_key(target) == own_key for target in wikilink_targets(text)):
                page["backlinks"].append({"id": int(row_id), "statement": statement, "status": status})
    page["backlinks"].sort(key=lambda row: row["statement"].casefold())
    return page


def _citation_rows(cur: Any, user_id: int) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT c.id, c.idea_id, c.reflection_id, c.quote, c.quote_hash, c.source_hash,
               c.stance, c.status, r.reflection_date, r.content, r.evidence_eligible
          FROM idea_citations c
          JOIN ideas i ON i.id = c.idea_id
          LEFT JOIN reflections r
            ON r.id = c.reflection_id AND r.user_id = i.user_id
         WHERE i.user_id = %s;
        """,
        (user_id,),
    )
    keys = (
        "id", "idea_id", "reflection_id", "quote", "quote_hash", "source_hash",
        "stance", "status", "entry_date", "content", "evidence_eligible",
    )
    rows = []
    for raw in cur.fetchall():
        row = dict(zip(keys, raw, strict=True))
        row["valid"] = _valid_source(row["content"], row["evidence_eligible"], row["source_hash"])
        rows.append(row)
    return rows


def _idea_rows(cur: Any, user_id: int) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT id, statement, domain, status, position
          FROM ideas
         WHERE user_id = %s;
        """,
        (user_id,),
    )
    keys = ("id", "statement", "domain", "status", "position")
    return [dict(zip(keys, row, strict=True)) for row in cur.fetchall()]


def _summarize(idea: dict[str, Any], citations: list[dict[str, Any]]) -> dict[str, Any]:
    relevant_status = "accepted" if idea["status"] == "active" else "candidate"
    counted = [
        row for row in citations
        if row["valid"] and row["status"] == relevant_status and row["idea_id"] == idea["id"]
    ]
    pending = [
        row for row in citations
        if row["valid"] and row["status"] == "candidate" and row["idea_id"] == idea["id"]
    ]
    dated = [row for row in counted if row["entry_date"] is not None]
    undated = {row["reflection_id"] for row in counted if row["entry_date"] is None}
    reflections = {row["reflection_id"] for row in counted}
    pending_reflections = {row["reflection_id"] for row in pending}
    dates = [row["entry_date"] for row in dated]
    return {
        **idea,
        "citation_count": len(reflections),
        "pending_citation_count": len(pending_reflections),
        "first_written_on": min(dates) if dates else None,
        "last_written_on": max(dates) if dates else None,
        "undated_count": len(undated),
        "needs_evidence": len(reflections) == 0,
        "anchored": idea["status"] == "active" and len(reflections) > 0,
    }


def load_graph(user_id: int) -> dict[str, Any]:
    with db.connection() as conn, conn.cursor() as cur:
        citations = _citation_rows(cur, user_id)
        ideas = [_summarize(idea, citations) for idea in _idea_rows(cur, user_id)]
        cur.execute(
            """
            SELECT l.id, l.user_id, l.from_idea_id, l.to_idea_id, l.kind, l.rationale,
                   l.status, f.statement, t.statement
              FROM idea_links l
              JOIN ideas f ON f.user_id = l.user_id AND f.id = l.from_idea_id
              JOIN ideas t ON t.user_id = l.user_id AND t.id = l.to_idea_id
             WHERE l.user_id = %s;
            """,
            (user_id,),
        )
        link_keys = (
            "id", "user_id", "from_idea_id", "to_idea_id", "kind", "rationale",
            "status", "from_statement", "to_statement",
        )
        links = [dict(zip(link_keys, row, strict=True)) for row in cur.fetchall()]
        cur.execute(
            """
            SELECT id, idea_id, created_at, model, prompt_version, input_hash, basis, content
              FROM idea_critiques
             WHERE user_id = %s
             ORDER BY created_at DESC, id DESC;
            """,
            (user_id,),
        )
        critique_keys = (
            "id", "idea_id", "created_at", "model", "prompt_version",
            "input_hash", "basis", "content",
        )
        critiques = [dict(zip(critique_keys, row, strict=True)) for row in cur.fetchall()]
    by_id = {int(idea["id"]): idea for idea in ideas}
    return {"ideas": ideas, "by_id": by_id, "citations": citations, "links": links, "critiques": critiques}




def stage_links(
    user_id: int,
    run_id: int,
    subject_id: int | None,
    proposals: list[dict[str, Any]],
) -> dict[str, int]:
    """Stage proposed links as candidates. With a subject, every link must touch it."""
    result = {"created": 0, "already_decided": 0, "duplicate": 0, "source_changed": 0, "malformed": 0}
    if not proposals:
        return result
    with db.connection() as conn, conn.cursor() as cur:
        for proposal in proposals:
            from_id = int(proposal["from_idea_id"])
            to_id = int(proposal["to_idea_id"])
            if proposal["kind"] in SYMMETRIC_LINK_KINDS and from_id > to_id:
                from_id, to_id = to_id, from_id
            if from_id == to_id or (subject_id is not None and subject_id not in (from_id, to_id)):
                result["malformed"] += 1
                continue
            first, second = sorted((from_id, to_id))
            cur.execute(
                """
                SELECT id, status FROM ideas
                 WHERE user_id = %s AND id IN (%s, %s)
                 ORDER BY id
                 FOR UPDATE;
                """,
                (user_id, first, second),
            )
            locked = {int(row[0]): row[1] for row in cur.fetchall()}
            if locked.get(from_id) != "active" or locked.get(to_id) != "active":
                result["source_changed"] += 1
                continue
            if not _anchored_locked(cur, user_id, from_id) or not _anchored_locked(cur, user_id, to_id):
                result["source_changed"] += 1
                continue
            cur.execute(
                """
                SELECT status FROM idea_links
                 WHERE user_id = %s AND from_idea_id = %s AND to_idea_id = %s AND kind = %s;
                """,
                (user_id, from_id, to_id, proposal["kind"]),
            )
            prior = cur.fetchone()
            if prior and prior[0] in ("accepted", "rejected"):
                result["already_decided"] += 1
                continue
            if prior:
                result["duplicate"] += 1
                continue
            cur.execute(
                """
                INSERT INTO idea_links
                    (user_id, from_idea_id, to_idea_id, kind, rationale, status, run_id)
                VALUES (%s, %s, %s, %s, %s, 'candidate', %s)
                ON CONFLICT (user_id, from_idea_id, to_idea_id, kind) DO NOTHING
                RETURNING id;
                """,
                (user_id, from_id, to_id, proposal["kind"], proposal["rationale"], run_id),
            )
            if cur.fetchone():
                result["created"] += 1
            else:
                result["duplicate"] += 1
        conn.commit()
    return result


def _anchored_locked(cur: Any, user_id: int, idea_id: int) -> bool:
    cur.execute(
        """
        SELECT c.source_hash, r.content, r.evidence_eligible
          FROM idea_citations c
          LEFT JOIN reflections r
            ON r.id = c.reflection_id AND r.user_id = %s
         WHERE c.idea_id = %s AND c.status = 'accepted';
        """,
        (user_id, idea_id),
    )
    return any(_valid_source(row[1], row[2], row[0]) for row in cur.fetchall())


def decide_link(user_id: int, link_id: int, status: str,
                kind: str | None = None, reverse: bool = False) -> tuple[str, int]:
    """Accept or reject a link. Returns the outcome and the id of the link that
    now stands.

    Accepting with a different `kind`, or `reverse`d, is the owner correcting
    the relation IRIS proposed. The proposal is kept as rejected, so it is not
    proposed again, and the relation the owner named is stored as accepted,
    carrying the proposal's rationale and run.
    """
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT from_idea_id, to_idea_id, status, kind, rationale, run_id
              FROM idea_links
             WHERE user_id = %s AND id = %s
             FOR UPDATE;
            """,
            (user_id, link_id),
        )
        row = cur.fetchone()
        if row is None:
            return "missing", link_id
        current = row[2]
        if status == "accepted":
            if current != "candidate":
                conn.rollback()
                return "conflict"
            for idea_id in sorted((int(row[0]), int(row[1]))):
                cur.execute(
                    """
                    SELECT status FROM ideas
                     WHERE user_id = %s AND id = %s
                     FOR UPDATE;
                    """,
                    (user_id, idea_id),
                )
                idea = cur.fetchone()
                if idea is None or idea[0] != "active" or not _anchored_locked(cur, user_id, idea_id):
                    conn.rollback()
                    return "conflict", link_id
            from_id, to_id = (int(row[1]), int(row[0])) if reverse else (int(row[0]), int(row[1]))
            new_kind = kind or row[3]
            if new_kind in SYMMETRIC_LINK_KINDS and from_id > to_id:
                from_id, to_id = to_id, from_id
            if (from_id, to_id, new_kind) != (int(row[0]), int(row[1]), row[3]):
                cur.execute(
                    "UPDATE idea_links SET status = 'rejected' WHERE user_id = %s AND id = %s;",
                    (user_id, link_id),
                )
                cur.execute(
                    """
                    INSERT INTO idea_links
                        (user_id, from_idea_id, to_idea_id, kind, rationale, status, run_id, confirmed_at)
                    VALUES (%s, %s, %s, %s, %s, 'accepted', %s, NOW())
                    ON CONFLICT (user_id, from_idea_id, to_idea_id, kind)
                    DO UPDATE SET status = 'accepted', confirmed_at = NOW()
                    RETURNING id;
                    """,
                    (user_id, from_id, to_id, new_kind, row[4], row[5]),
                )
                new_id = int(cur.fetchone()[0])
                conn.commit()
                return "ok", new_id
        elif current == "rejected" or current not in ("candidate", "accepted"):
            conn.rollback()
            return "conflict", link_id
        cur.execute(
            """
            UPDATE idea_links
               SET status = %s, confirmed_at = CASE WHEN %s = 'accepted' THEN NOW() ELSE confirmed_at END
             WHERE user_id = %s AND id = %s;
            """,
            (status, status, user_id, link_id),
        )
        conn.commit()
    return "ok", link_id


def insert_critique(
    user_id: int,
    idea_id: int,
    *,
    model: str,
    prompt_version: str,
    input_hash: str,
    basis: dict[str, Any],
    content: dict[str, Any],
) -> dict[str, Any]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO idea_critiques
                (user_id, idea_id, model, prompt_version, input_hash, basis, content)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at;
            """,
            (user_id, idea_id, model, prompt_version, input_hash, Json(basis), Json(content)),
        )
        row = cur.fetchone()
        conn.commit()
    return {
        "id": int(row[0]),
        "idea_id": idea_id,
        "created_at": row[1],
        "model": model,
        "prompt_version": prompt_version,
        "input_hash": input_hash,
        "basis": basis,
        "content": content,
    }


