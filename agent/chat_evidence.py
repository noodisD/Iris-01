"""A chat conversation added to IRIS as evidence, at the owner's click (ADR-0032).

Chat is where the owner says why: IRIS asks what led to something, how it
felt, what happened after, and the answers are in the conversation, not in any
entry. Chat messages were recalled in later chats but never read for patterns.
Added, a conversation becomes a reflection in the session format, the same
shape as a questionnaire interview: IRIS's turns are what was asked, and
context; the owner's turns are evidence, quoted only where the owner spoke
(ADR-0028). Nothing is added without the click, and the cost is shown first.

Added again after it went on, the new copy replaces the old one, so what IRIS
read is always the whole conversation and never two overlapping copies.
"""

from __future__ import annotations

import logging

from . import sessions
from .config import settings
from .database import db

logger = logging.getLogger(__name__)

OWNER = "Me"
IRIS = "IRIS"


class ChatEvidenceError(Exception):
    """Why a conversation cannot be added, in words the owner can act on."""


def _session(cur, user_id: int, session_id: str) -> dict:
    cur.execute("""SELECT id, reflection_id, added_messages, added_at FROM chat_sessions
                    WHERE id = %s AND user_id = %s""", (session_id, user_id))
    row = cur.fetchone()
    if row is None:
        raise LookupError("No such conversation.")
    return dict(zip(("id", "reflection_id", "added_messages", "added_at"), row))


def _messages(cur, user_id: int, session_id: str) -> list[tuple[str, str, object]]:
    cur.execute("""SELECT role, content, created_at FROM conversation_messages
                    WHERE user_id = %s AND session_id = %s AND length(btrim(content)) > 0
                    ORDER BY created_at, id""", (user_id, session_id))
    return cur.fetchall()


def content(messages: list[tuple[str, str, object]]) -> str:
    """The conversation as a session: each message a turn, timed from the first."""
    first = messages[0][2]
    found = [sessions.Segment(max(0, int((at - first).total_seconds())),
                              OWNER if role == "user" else IRIS, " ".join(text.split()))
             for role, text, at in messages]
    said = " ".join(text for role, text, _ in messages if role == "user")
    return sessions.compose(found, kind="chat", started=first.strftime("%Y-%m-%dT%H:%M"),
                            language=sessions.guess_language(said), owner=OWNER, asker=IRIS)


def status(user_id: int, session_id: str) -> dict:
    """Whether the conversation is in IRIS, whether it has gone on since, and the cost."""
    from .episodes import SYSTEM_PROMPT as READ_PROMPT
    from .intelligence import Intelligence

    with db.connection() as conn, conn.cursor() as cur:
        session = _session(cur, user_id, session_id)
        messages = _messages(cur, user_id, session_id)
    yours = sum(1 for role, _, _ in messages if role == "user")
    chars = sum(len(text) for _, text, _ in messages)
    model, tier = settings.OPENAI_WORKER_MODEL, settings.OPENAI_WORKER_SERVICE_TIER or None
    price = Intelligence.PRICE_PER_MTOK.get(model)
    factor = Intelligence.TIER_PRICE_FACTOR.get(tier or "", 1.0)
    # One reading and a field check for what it finds.
    dollars = (((len(READ_PROMPT) + 3000 + chars) // 3 * price[0] + 1500 * price[1])
               / 1_000_000 * factor) if price and yours else None
    added = session["reflection_id"] is not None
    return {"added": added, "addedAt": session["added_at"].isoformat() if added and session["added_at"] else None,
            "messages": len(messages), "yourMessages": yours,
            "newSinceAdded": len(messages) - (session["added_messages"] or 0) if added else len(messages),
            "dollars": round(dollars, 4) if dollars is not None else None,
            "text": ("Adds this conversation to IRIS: your messages are read for patterns and ideas, "
                     f"IRIS's are only context. Sent to OpenAI, under ${max(dollars, 0.001):.3f}."
                     if dollars is not None else "")}


def add(user_id: int, session_id: str) -> dict:
    """The owner's click: the conversation becomes a reflection IRIS reads."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(73202, %s)", (user_id,))
        session = _session(cur, user_id, session_id)
        messages = _messages(cur, user_id, session_id)
        conn.commit()
    if not any(role == "user" for role, _, _ in messages):
        raise ChatEvidenceError("There is nothing of yours in this conversation to add yet.")
    if session["reflection_id"] is not None and session["added_messages"] == len(messages):
        return status(user_id, session_id)
    from .importing.store import content_hash

    text = content(messages)
    reflection_id = db.create_reflection(
        user_id, text, reflection_date=messages[0][2].date(), source="chat", content_format="session",
        content_hash=content_hash(text), date_source="user", date_confidence="certain")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE chat_sessions SET reflection_id = %s, added_messages = %s, added_at = NOW()
                        WHERE id = %s AND user_id = %s""", (reflection_id, len(messages), session_id, user_id))
        conn.commit()
    if session["reflection_id"] is not None:
        db.delete_reflection(session["reflection_id"])
    from .importing.service import _kick_the_queue
    _kick_the_queue()
    logger.info(f"Chat {session_id} added as reflection {reflection_id}")
    return status(user_id, session_id)
