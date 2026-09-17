"""The journal is a history, and a quote is the owner's words.

Two faults with the same shape: IRIS showed its own bookkeeping where the owner's
writing belonged. Entries were listed by insertion order and stamped with the day
they were imported, so an archive spanning two years read as one afternoon in
September; and every theme occurrence quoted the text built for embedding —
"Anchor: Self-Reflection | Source: Reflection | Mood: okay (Energy: ?/10 …)" —
which the Insights screen printed as a pull quote.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from agent.database import db
from agent.persistence import PersistenceEngine
from agent.timeutils import utc_now
from agent.trackers.reflections import ReflectionService
from iris_api import app, get_current_user_id


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_the_journal_is_ordered_by_when_entries_were_written(client, test_user):
    """Committed in the order an import commits them, which is not the order
    they were written."""
    service = ReflectionService(test_user["id"])
    service.create_reflection(content="written in 2024", reflection_date=date(2024, 3, 1))
    service.create_reflection(content="written in 2026", reflection_date=date(2026, 5, 10))
    service.create_reflection(content="written in 2025", reflection_date=date(2025, 7, 4))

    entries = client.get("/api/journal").json()["entries"]

    assert [e["occurredOn"] for e in entries] == ["2026-05-10", "2025-07-04", "2024-03-01"]
    assert entries[-1]["importedAt"][:4] == str(utc_now().year), (
        "the import day is reported separately, not as the writing day"
    )


def test_every_entry_is_reachable_by_paging(client, test_user):
    service = ReflectionService(test_user["id"])
    for i in range(7):
        service.create_reflection(content=f"entry {i}",
                                  reflection_date=date(2025, 1, 1) + timedelta(days=i))

    seen: list[str] = []
    cursor = None
    for _ in range(10):
        url = "/api/journal?limit=3" + (f"&cursor={cursor}" if cursor else "")
        body = client.get(url).json()
        seen += [e["id"] for e in body["entries"]]
        cursor = body.get("nextCursor")
        if not cursor:
            break

    assert len(seen) == 7 and len(set(seen)) == 7, f"paging lost or repeated entries: {seen}"


def test_entries_written_on_the_same_day_are_both_reachable(client, test_user):
    """The cursor carries (date, id) because dates repeat; on date alone the
    second entry of a day was skipped."""
    service = ReflectionService(test_user["id"])
    for i in range(3):
        service.create_reflection(content=f"same day {i}", reflection_date=date(2025, 2, 2))

    first = client.get("/api/journal?limit=2").json()
    second = client.get(f"/api/journal?limit=2&cursor={first['nextCursor']}").json()
    ids = [e["id"] for e in first["entries"]] + [e["id"] for e in second["entries"]]

    assert len(set(ids)) == 3


def test_a_quote_is_the_owners_words(test_user):
    rid = ReflectionService(test_user["id"]).create_reflection(
        content="Slept badly before the review and skipped the gym again.")

    snippet = PersistenceEngine(test_user["id"])._get_entry_snippet(rid, "reflection")

    assert snippet.startswith("Slept badly before the review")
    assert "Anchor:" not in snippet and "?/10" not in snippet and "Mood:" not in snippet


def test_snippets_already_stored_are_rewritten(test_user):
    """Fixing the source does not fix what is already on screen."""
    user_id = test_user["id"]
    rid = ReflectionService(user_id).create_reflection(content="Long walk by the canal.")
    theme_id = db.create_theme(user_id, [0.1] * 1536, "Walking",
                               utc_now().isoformat(), utc_now().isoformat())
    db.add_theme_occurrence(
        theme_id, "reflection", rid,
        "Anchor: Self-Reflection | Source: Reflection | Mood: okay (Energy: ?/10) | Content: Long walk",
        0.9, utc_now().isoformat())

    updated = PersistenceEngine(user_id).refresh_snippets()

    assert updated == 1
    snippet = db.get_theme_occurrences(theme_id)[0]["snippet"]
    assert snippet.startswith("Long walk by the canal") and "Anchor:" not in snippet
