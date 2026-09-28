"""An idea's page: its wording can be edited, and it has notes that link to other ideas."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from agent.database import db
from agent.ideas.models import (
    content_hash,
    quote_hash,
    rename_wikilinks,
    statement_key,
    wikilink_targets,
)
from agent.trackers.reflections import ReflectionService
from iris_api import app, get_current_user_id

GARDEN = "Water the garden in the evening."
LOSSES = "Act when losses are smallest."
KETTLE = "A watched kettle still boils."


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def _idea(user_id: int, statement: str, status: str = "active", notes: str = "") -> str:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO ideas (user_id, statement, statement_key, domain, status, notes)
               VALUES (%s, %s, %s, 'life', %s, %s) RETURNING id""",
            (user_id, statement, statement_key(statement), status, notes),
        )
        idea_id = cur.fetchone()[0]
        conn.commit()
    return str(idea_id)


def test_wikilinks_are_read_and_repointed_by_wording_not_casing():
    notes = f"See [[{LOSSES.lower()}]] and [[{LOSSES}|the rule]], not [[{KETTLE}]]."
    assert wikilink_targets(notes) == [LOSSES.lower(), LOSSES, KETTLE]
    renamed = rename_wikilinks(notes, statement_key(LOSSES), "Act while losses are small.")
    assert renamed == (
        "See [[Act while losses are small.]] and [[Act while losses are small.|the rule]], "
        f"not [[{KETTLE}]]."
    )


def test_notes_are_saved_and_the_page_shows_links_and_backlinks(client, test_user):
    losses = _idea(test_user["id"], LOSSES)
    garden = _idea(test_user["id"], GARDEN, status="candidate")

    response = client.patch(f"/api/ideas/{garden}", json={"notes": f"# Why\nIt applies [[{LOSSES}]]. [[Nothing here]]"})
    assert response.status_code == 200, response.text

    page = client.get(f"/api/ideas/{garden}").json()["page"]
    assert page["notes"].startswith("# Why")
    assert page["notesUpdatedAt"] is not None
    assert page["links"] == {LOSSES: losses}

    backlinks = client.get(f"/api/ideas/{losses}").json()["page"]["backlinks"]
    assert backlinks == [{"id": garden, "statement": GARDEN, "status": "candidate"}]


def test_renaming_an_idea_repoints_the_links_to_it(client, test_user):
    losses = _idea(test_user["id"], LOSSES)
    garden = _idea(test_user["id"], GARDEN, notes=f"It applies [[{LOSSES}|this]].")

    renamed = "Act while the losses are still small."
    response = client.patch(f"/api/ideas/{losses}", json={"statement": f"  {renamed}\n"})
    assert response.status_code == 200, response.text
    assert response.json()["statement"] == renamed

    assert client.get(f"/api/ideas/{garden}").json()["page"]["notes"] == f"It applies [[{renamed}|this]]."
    assert client.get(f"/api/ideas/{losses}").json()["page"]["backlinks"][0]["id"] == garden


def test_a_wording_another_idea_has_is_refused(client, test_user):
    _idea(test_user["id"], LOSSES)
    garden = _idea(test_user["id"], GARDEN)

    response = client.patch(f"/api/ideas/{garden}", json={"statement": LOSSES.upper()})
    assert response.status_code == 409
    assert "Another idea already says this" in response.json()["detail"]
    assert client.get(f"/api/ideas/{garden}").json()["idea"]["statement"] == GARDEN


def test_only_a_live_idea_can_be_edited_and_never_to_nothing(client, test_user):
    rejected = _idea(test_user["id"], KETTLE, status="rejected")
    garden = _idea(test_user["id"], GARDEN, status="candidate")

    assert client.patch(f"/api/ideas/{rejected}", json={"notes": "x"}).status_code == 409
    assert client.patch(f"/api/ideas/{garden}", json={"statement": "   "}).status_code == 422
    assert client.patch(f"/api/ideas/{garden}", json={"statement": "x" * 601}).status_code == 422
    assert client.patch(f"/api/ideas/{garden}", json={"notes": "x" * 20001}).status_code == 422
    # Position is still only for an idea the owner has accepted.
    assert client.patch(f"/api/ideas/{garden}", json={"position": "endorsed"}).status_code == 409


def test_a_review_card_shows_new_quotes_apart_from_those_on_record(client, test_user):
    reflections = ReflectionService(test_user["id"])
    old_text = "Evening is the best time to water; less is lost to the sun."
    new_text = "Watering at dusk again: the soil stayed damp far longer."
    old_entry = reflections.create_reflection(content=old_text, reflection_date=date(2025, 5, 1))
    new_entry = reflections.create_reflection(content=new_text, reflection_date=date(2025, 7, 1))
    garden = _idea(test_user["id"], GARDEN)
    with db.connection() as conn, conn.cursor() as cur:
        for entry, text, status in ((old_entry, old_text, "accepted"), (new_entry, new_text, "candidate")):
            cur.execute(
                """INSERT INTO idea_citations (idea_id, reflection_id, quote, quote_hash, source_hash, stance, status)
                   VALUES (%s, %s, %s, %s, %s, 'endorsed', %s)""",
                (garden, entry, text, quote_hash(text), content_hash(text), status),
            )
        conn.commit()

    card = next(card for card in client.get("/api/ideas/review").json()["ideas"] if card["idea"]["id"] == garden)
    assert [quote["text"] for quote in card["citations"]] == [new_text]
    assert [quote["text"] for quote in card["onRecord"]] == [old_text]
