"""Is it still good? Checks of quality that cost nothing, or nearly nothing.

The memory search once compared one memory in a hundred and nothing raised:
it just returned worse memories. Chat once had no idea the owner's
questionnaire existed. These checks measure the result, not the machinery.
"""

from __future__ import annotations

import random

from ..database import db
from . import Result, check

#: Searches compared against an exact computation per run.
SEARCH_PROBES = 12
TOP = 10
#: Share of the exact top ten the real search must return.
MIN_RECALL = 0.95
#: Sections chat's context must always carry, whatever is asked.
CONTEXT_SECTIONS = ("# Today:", "# Relevant Long-Term Memory:", "# Earlier conversations",
                    "# Recent Journal Entries")
CONTEXT_ERRORS = ("Could not retrieve", "Context Retrieval Error", "Could not read")


def _owner() -> int | None:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT user_id, count(*) FROM reflections GROUP BY 1 ORDER BY 2 DESC LIMIT 1")
        row = cur.fetchone()
    return row[0] if row else None


def _vectors(user_id: int):
    """Every vector chat's search may return, keyed as the search keys them."""
    import numpy as np

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT e.source_type, e.source_id, e.vector::text FROM embeddings e
             WHERE (e.source_type = 'reflection' AND e.source_id IN (SELECT id FROM reflections WHERE user_id = %s)
                    AND NOT EXISTS (SELECT 1 FROM entry_passages p WHERE p.reflection_id = e.source_id))
                OR (e.source_type = 'entry_passage' AND e.source_id IN (SELECT id FROM entry_passages WHERE user_id = %s))
                OR (e.source_type = 'session_passage' AND e.source_id IN (SELECT id FROM session_passages WHERE user_id = %s))
                OR (e.source_type = 'message' AND e.source_id IN (
                        SELECT id FROM conversation_messages WHERE user_id = %s AND role = 'user'))
                OR (e.source_type = 'habit_completion' AND e.source_id IN (
                        SELECT hc.id FROM habit_completions hc JOIN habits h ON hc.habit_id = h.id
                         WHERE h.user_id = %s))""",
                    (user_id, user_id, user_id, user_id, user_id))
        rows = cur.fetchall()
    keys = [(kind, sid) for kind, sid, _ in rows]
    matrix = np.array([np.array(text.strip("[]").split(","), dtype=float) for _, _, text in rows])
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
    return keys, matrix


@check("retrieval.complete", "quality")
def retrieval_complete() -> Result:
    import numpy as np

    user_id = _owner()
    if user_id is None:
        return Result("retrieval.complete", "unknown", "No entries to search yet.")
    keys, matrix = _vectors(user_id)
    if len(keys) < TOP * 2:
        return Result("retrieval.complete", "unknown", f"Only {len(keys)} memories; too few to judge.")
    rng = random.Random()
    recalls = []
    for _ in range(SEARCH_PROBES):
        # Between two real memories, so the query is like a question and is no memory's own vector.
        a, b = rng.sample(range(len(keys)), 2)
        query = matrix[a] + matrix[b]
        query /= np.linalg.norm(query)
        best: dict = {}
        for key, distance in zip(keys, 1 - matrix @ query):
            best[key] = min(best.get(key, 2.0), float(distance))
        exact = {k for k, _ in sorted(best.items(), key=lambda kv: kv[1])[:TOP]}
        found = {(r["source_type"], r["source_id"])
                 for r in db.search_similar_embeddings(user_id, query.tolist(), n_results=TOP)}
        recalls.append(len(found & exact) / TOP)
    recall = sum(recalls) / len(recalls)
    details = {"probes": SEARCH_PROBES, "memories": len(set(keys)), "worst": min(recalls)}
    if recall < MIN_RECALL:
        return Result("retrieval.complete", "fail",
                      f"Chat's search returns {recall:.0%} of the true ten nearest memories.",
                      value=round(recall, 3), expected=f"≥ {MIN_RECALL:.0%}", details=details,
                      evidence="exact cosine top-10 in Python vs db.search_similar_embeddings, random queries",
                      causes=["An approximate vector index (IVFFlat/HNSW) is back with too few probes.",
                              "The search query filters out a kind of memory it should include."],
                      action="Check pg_indexes on embeddings; see migration 0052.", action_class="needs-owner")
    return Result("retrieval.complete", "ok", f"Chat's search finds {recall:.0%} of the true nearest memories.",
                  value=round(recall, 3), expected=f"≥ {MIN_RECALL:.0%}", details=details)


@check("context.sections", "quality")
def context_sections() -> Result:
    from ..core import PersonalAICompanion

    user_id = _owner()
    if user_id is None:
        return Result("context.sections", "unknown", "No owner yet.")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM questionnaire_answers WHERE user_id = %s AND status = 'added'",
                    (user_id,))
        answers = cur.fetchone()[0]
    # One embedding of a neutral question: a fraction of a cent.
    context = PersonalAICompanion(user_id=user_id, session_id="doctor-probe")._get_aggregated_context(
        "How has this week been?")
    wanted = list(CONTEXT_SECTIONS) + (["# Baseline questionnaire"] if answers else [])
    missing = [s.strip("#: ") for s in wanted if s not in context]
    errors = [e for e in CONTEXT_ERRORS if e in context]
    details = {"chars": len(context), "missing": missing, "errors": errors}
    if missing or errors:
        return Result("context.sections", "fail",
                      "Chat's context is missing " + ", ".join(missing + errors) + ".",
                      value=len(missing) + len(errors), expected="every section, no errors", details=details,
                      causes=["A section's query raised and was replaced by an error line.",
                              "A section's builder returns nothing for this owner."],
                      action="Run _get_aggregated_context locally and read the journal for the error.",
                      action_class="read-only")
    return Result("context.sections", "ok", f"Chat's context has all {len(wanted)} sections ({len(context)} chars).",
                  value=0, expected="every section, no errors", details=details)
