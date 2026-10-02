"""Model verdicts personal-dynamics discovery has already paid for.

Discovery checks every pattern against every account and compares accounts in
pairs. Asked from scratch on each run, that cost about as much for one new
entry as for the whole archive. A verdict depends only on what was asked, so
it is kept under a hash of exactly that: the prompt and schema version, the
model, and the stable fingerprints of the definitions and accounts involved,
never the request-local handles (`a1`, `a2`) that shift when an account is
added. Anything changed is asked afresh.

Per-check verdicts are kept only after the caller has validated them. Whole
replies are kept as they arrive and checked by their caller before the next
request, so when a run fails a check, the reply it kept last is the one that
failed: that one is discarded and never replayed. The replies before it passed their
checks and are kept, so a retry proposes the same definitions and reuses the
verdicts already paid for. Outside `remembering(user_id)` nothing is read or
kept.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from psycopg2.extras import Json

from .database import db

#: Verdicts unused for this long are let go; the archive's own changes make
#: most of them unreachable long before.
KEEP_DAYS = 120

#: Failures that mean the last reply did not pass its check.
_FAILED_CHECKS = frozenset({"invalid_schema", "invalid_matrix", "invalid_selector",
                            "invalid_partition", "invalid_refinement", "invalid_lens_matrix"})

_user: ContextVar[int | None] = ContextVar("discovery_memo_user", default=None)
_fresh: ContextVar[list[str] | None] = ContextVar("discovery_memo_fresh", default=None)


@contextmanager
def remembering(user_id: int) -> Iterator[None]:
    """Read and keep verdicts for this user; a reply that failed its check is forgotten."""
    user_token = _user.set(user_id)
    fresh_token = _fresh.set([])
    try:
        yield
    except BaseException as exc:
        # Only a reply that failed validation is suspect. A provider outage or
        # an interruption says nothing against the replies already kept.
        if str(exc) in _FAILED_CHECKS:
            _forget(user_id, (_fresh.get() or [])[-1:])
        raise
    finally:
        _fresh.reset(fresh_token)
        _user.reset(user_token)


def _forget(user_id: int, keys: list[str]) -> None:
    if not keys:
        return
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM discovery_memo WHERE user_id = %s AND key = ANY(%s);",
                    (user_id, sorted(set(keys))))
        conn.commit()


def active() -> bool:
    return _user.get() is not None


def key(kind: str, *parts: Any) -> str:
    payload = json.dumps([kind, *parts], sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def model_of(intelligence: Any) -> str:
    return str(getattr(intelligence, "model", "") or "")


def recall(keys: list[str]) -> dict[str, Any]:
    """The kept values among `keys`, marked as used."""
    user_id = _user.get()
    if user_id is None or not keys:
        return {}
    wanted = sorted(set(keys))
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT key, value FROM discovery_memo WHERE user_id = %s AND key = ANY(%s);",
            (user_id, wanted),
        )
        found = {row[0]: row[1] for row in cur.fetchall()}
        if found:
            cur.execute(
                "UPDATE discovery_memo SET used_at = NOW() WHERE user_id = %s AND key = ANY(%s);",
                (user_id, sorted(found)),
            )
        conn.commit()
    return found


def keep(kind: str, values: dict[str, Any]) -> None:
    user_id = _user.get()
    if user_id is None or not values:
        return
    with db.connection() as conn, conn.cursor() as cur:
        for item_key, value in values.items():
            cur.execute(
                """INSERT INTO discovery_memo (user_id, key, kind, value) VALUES (%s, %s, %s, %s)
                   ON CONFLICT (user_id, key) DO UPDATE SET value = EXCLUDED.value, used_at = NOW();""",
                (user_id, item_key, kind, Json(value)),
            )
        conn.commit()


def chat(intelligence: Any, system_prompt: str, content: str, **options: Any) -> str:
    """The model's reply to exactly this request, asked only once."""
    if not active():
        return str(intelligence.chat(messages=[{"role": "user", "content": content}],
                                     system_prompt=system_prompt, **options))
    item_key = key("reply", model_of(intelligence), system_prompt, content, options)
    kept = recall([item_key])
    if item_key in kept:
        return str(kept[item_key]["text"])
    text = str(intelligence.chat(messages=[{"role": "user", "content": content}],
                                 system_prompt=system_prompt, **options))
    keep("reply", {item_key: {"text": text}})
    fresh = _fresh.get()
    if fresh is not None:
        fresh.append(item_key)
    return text


def prune(user_id: int) -> None:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM discovery_memo WHERE user_id = %s AND used_at < NOW() - make_interval(days => %s);",
            (user_id, KEEP_DAYS),
        )
        conn.commit()
