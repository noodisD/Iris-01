"""Reading only what is new: entries that reached IRIS after the last complete reading."""

from __future__ import annotations

from datetime import date

from agent.database import db
from agent.ideas import store
from agent.ideas.service import IdeaService


def test_only_entries_added_after_the_last_complete_reading_are_new(test_user):
    owner = test_user["id"]
    old = db.create_reflection(owner, "An entry written long ago about a garden I planted.",
                               reflection_date=date(2024, 5, 1))
    run = store.start_run(owner, "discovery", "test-model", "v", 1, 1)
    store.finish_run(run, owner, status="complete", passes_completed=1, proposed=0,
                     dropped={}, error=None)
    later = db.create_reflection(owner, "Imported later, though written in 2023, about the same garden.",
                                 reflection_date=date(2023, 4, 1))
    service = IdeaService(owner)
    assert [e["id"] for e in service._entries("new")] == [later], "added later counts, whatever its date"
    assert {e["id"] for e in service._entries("all")} == {old, later}
    estimate = service.discover_estimate("new")
    assert estimate["entries"] == 1 and estimate["since"]


def test_with_no_complete_reading_everything_is_new(test_user):
    owner = test_user["id"]
    db.create_reflection(owner, "The only entry so far, about learning to cook.")
    assert IdeaService(owner).discover_estimate("new")["entries"] == 1


def _citation(reflection_id: int, text: str, quote: str) -> dict:
    from agent.ideas.models import content_hash, quote_hash
    return {"reflection_id": reflection_id, "quote": quote, "quote_hash": quote_hash(quote),
            "source_hash": content_hash(text), "stance": "endorsed"}


def _statuses(idea_id: int) -> list[str]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT status FROM idea_citations WHERE idea_id = %s ORDER BY id", (idea_id,))
        return [row[0] for row in cur.fetchall()]


def test_a_new_quote_for_a_held_idea_is_added_not_proposed(test_user):
    owner = test_user["id"]
    text = "Gardens teach patience, because nothing you plant hurries for you."
    entry = db.create_reflection(owner, text)
    quote = "Gardens teach patience"
    run = store.start_run(owner, "discovery", "m", "v", 1, 1)
    first = store.stage_citations(owner, run, statement="Gardening teaches patience", domain="life",
                                  citations=[_citation(entry, text, quote)], matched_id=None)
    assert first["created"] == 1
    idea_id = store.list_registry(owner)[0]["id"]
    assert _statuses(idea_id) == ["candidate"], "a new idea is still proposed"
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE ideas SET status = 'active' WHERE id = %s", (idea_id,))
        conn.commit()
    other = db.create_reflection(owner, "Again I saw that nothing you plant hurries for you.")
    added = store.stage_citations(owner, run, statement="Gardening teaches patience", domain="life",
                                  citations=[_citation(other, "Again I saw that nothing you plant hurries for you.",
                                                       "nothing you plant hurries for you")],
                                  matched_id=idea_id)
    assert added["added"] == 1 and added["created"] == 0
    assert _statuses(idea_id) == ["candidate", "accepted"]
    assert store.adopt_pending_quotes(owner) == 1, "the earlier proposal is taken in too"
    assert _statuses(idea_id) == ["accepted", "accepted"]
