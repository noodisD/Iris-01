"""What chat knows of the owner's baseline questionnaire (ADR-0029).

Answers were reachable only by similarity, as one kind of memory among
journal entries, sessions and chat, and the five shown were rarely theirs:
asked whether it could see the questionnaire, IRIS said it could not. Chat
now always sees how much has been answered, the answers most related to the
message, and every answer when the owner asks about the questionnaire itself.
Only the owner's turns are their answer; the question is what was asked.
"""

from __future__ import annotations

import re

from . import sessions
from .database import db

#: The answers most related to the message, shown on every turn.
RELATED = 3
#: How much of the questionnaire is shown when the owner asks about it.
ALL_CHARS = 12000
ABOUT_IT = re.compile(r"questionnaire|kwestionariusz|ankiet|intake|baseline", re.I)


def _answer(content: str) -> tuple[str, str] | None:
    session = sessions.read(content)
    if session is None:
        return None
    asked = " ".join(t.text for t in session.turns if t.role == "asker")
    said = " ".join(t.text for t in session.turns if t.role == "owner")
    return (" ".join(asked.split()), " ".join(said.split())) if said.strip() else None


def _line(asked: str, said: str, limit: int = 600) -> str:
    said = said if len(said) <= limit else said[:limit - 1] + "…"
    return f"- Q: {asked}\n  Owner's answer: {said}"


def section(user_id: int, message: str, query_vector: list | None) -> str:
    """The questionnaire part of chat's context; empty when nothing was added."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT r.id, r.content FROM questionnaire_answers a
                         JOIN reflections r ON r.id = a.reflection_id
                        WHERE a.user_id = %s AND a.status = 'added'
                        ORDER BY a.question_id""", (user_id,))
        added = cur.fetchall()
    if not added:
        return ""
    from .questionnaire import load

    doc = load()
    total = sum(len(s["questions"]) for s in doc["sections"]) if doc else None
    head = (f"# Baseline questionnaire\nThe owner has answered and added {len(added)}"
            + (f" of its {total} questions" if total else " questions")
            + ". Their answers are their own words; the questions are what was asked.")
    if ABOUT_IT.search(message or ""):
        lines, used = [], 0
        for _, content in added:
            pair = _answer(content)
            if pair is None:
                continue
            line = _line(*pair, limit=400)
            if used + len(line) > ALL_CHARS:
                lines.append(f"(and {len(added) - len(lines)} more answers not shown here)")
                break
            lines.append(line)
            used += len(line)
        return head + "\nAll answers added so far:\n" + "\n".join(lines)
    if query_vector is None:
        return head
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT r.content, min(e.vector <=> %s::vector) AS d
                         FROM session_passages p
                         JOIN reflections r ON r.id = p.reflection_id
                         JOIN embeddings e ON e.source_type = 'session_passage' AND e.source_id = p.id
                        WHERE r.user_id = %s AND r.source = 'questionnaire'
                        GROUP BY r.id, r.content ORDER BY d LIMIT %s""", (query_vector, user_id, RELATED))
        nearest = [row[0] for row in cur.fetchall()]
    pairs = [pair for pair in map(_answer, nearest) if pair]
    if not pairs:
        return head
    return head + "\nThe answers most related to this message:\n" + "\n".join(_line(*p) for p in pairs)
