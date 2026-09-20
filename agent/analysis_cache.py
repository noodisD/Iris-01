"""Remembering an analysis until what it was computed from changes.

Two engines take most of the time spent answering "what has IRIS noticed":
decision impact, which tests every anchor against every target, and tension,
which tests every pair of themes. Once chat and the Insights screen shared one
admission (ADR-0007), both asked them again on every turn and every page load —
about two seconds, over evidence that had usually not changed at all. Chat used
to dodge that for decision impact by reading a cache table, and paid for it by
going silent after a restart until something else warmed the table.

A result here is reused only while nothing it depends on has moved: the same
user, the same evidence, and the same hour. The evidence is a fingerprint of the
user's measured themes and their occurrences, so any new occurrence, deletion,
re-dating or confirmation computes afresh on the next read. The hour bounds the
other input both engines have — "now", which every window is measured back
from.

Nothing is persisted. A restart starts cold and computes, which is the property
the cache table lacked.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from . import timeutils
from .database import db

_results: dict[tuple[str, int], tuple[tuple, list[dict[str, Any]]]] = {}
_lock = threading.Lock()


def evidence_fingerprint(user_id: int) -> tuple:
    """What the cross-theme engines read, as a value that changes whenever it does.

    Counts and sums are not that value. Moving one occurrence a day earlier and
    another a day later leaves every total identical, and the relationships
    these engines measure are made of exactly those distances — so the cached
    answer would be served for evidence that no longer supports it. A digest
    over the rows themselves has no such arithmetic to cancel out.
    """
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT COUNT(o.id),
                      COALESCE(md5(string_agg(
                          o.id || ':' || o.theme_id || ':' ||
                          COALESCE(EXTRACT(EPOCH FROM o.occurred_at)::text, 'undated'),
                          ',' ORDER BY o.id)), ''),
                      (SELECT COUNT(*) FROM themes WHERE user_id = %s AND status = 'active'),
                      (SELECT COALESCE(md5(string_agg(id::text, ',' ORDER BY id)), '')
                         FROM themes WHERE user_id = %s AND status = 'active')
                 FROM theme_occurrences o JOIN themes t ON t.id = o.theme_id
                WHERE t.user_id = %s AND t.status = 'active';""",
            (user_id, user_id, user_id))
        return tuple(cur.fetchone())


def remembered(engine: str, user_id: int, compute: Callable[[], list[dict[str, Any]]],
               force: bool = False) -> list[dict[str, Any]]:
    """`compute()`'s result, or the one from earlier this hour over the same
    evidence. Copies are handed out, because callers annotate findings."""
    now = timeutils.utc_now()
    stamp = (now.replace(minute=0, second=0, microsecond=0), evidence_fingerprint(user_id))
    key = (engine, user_id)
    if not force:
        with _lock:
            hit = _results.get(key)
        if hit and hit[0] == stamp:
            return [dict(r) for r in hit[1]]
    result = compute()
    with _lock:
        _results[key] = (stamp, [dict(r) for r in result])
    return result


def forget(user_id: int | None = None) -> None:
    """Drop remembered results — everyone's, or one user's."""
    with _lock:
        for key in [k for k in _results if user_id is None or k[1] == user_id]:
            del _results[key]
