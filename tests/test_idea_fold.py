"""A proposal the owner recognises as an idea they already hold."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from agent.database import db
from agent.ideas.models import content_hash, quote_hash, statement_key
from agent.ideas.service import _held
from agent.trackers.reflections import ReflectionService
from iris_api import app, get_current_user_id

HELD = "Water the garden in the evening."
REWORDED = "Evening is when the garden should be watered, because less is lost to the sun."
OLD_TEXT = "Evening watering again; less is lost to the sun."
NEW_TEXT = "Watered at dusk and the soil stayed damp far longer."


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def _idea(user_id: int, statement: str, status: str, notes: str = "") -> str:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO ideas (user_id, statement, statement_key, domain, status, notes)
               VALUES (%s, %s, %s, 'life', %s, %s) RETURNING id""",
            (user_id, statement, statement_key(statement), status, notes),
        )
        idea_id = cur.fetchone()[0]
        conn.commit()
    return str(idea_id)


def _quote(idea_id: str, entry: int, text: str, status: str) -> None:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO idea_citations (idea_id, reflection_id, quote, quote_hash, source_hash, stance, status)
               VALUES (%s, %s, %s, %s, %s, 'endorsed', %s)""",
            (idea_id, entry, text, quote_hash(text), content_hash(text), status),
        )
        conn.commit()


def test_folding_moves_the_quotes_to_the_held_idea(client, test_user):
    entries = ReflectionService(test_user["id"])
    old_entry = entries.create_reflection(content=OLD_TEXT, reflection_date=date(2025, 5, 1))
    new_entry = entries.create_reflection(content=NEW_TEXT, reflection_date=date(2025, 7, 1))
    held = _idea(test_user["id"], HELD, "active")
    proposal = _idea(test_user["id"], REWORDED, "candidate")
    _quote(held, old_entry, OLD_TEXT, "accepted")
    _quote(proposal, old_entry, OLD_TEXT, "candidate")  # already the held idea's
    _quote(proposal, new_entry, NEW_TEXT, "candidate")

    response = client.post(f"/api/ideas/{proposal}/fold", json={"intoId": int(held)})
    assert response.status_code == 200, response.text
    assert response.json()["quotesMoved"] == 1

    quotes = client.get(f"/api/ideas/{held}").json()["citations"]
    assert sorted((quote["text"], quote["status"]) for quote in quotes) == [
        (OLD_TEXT, "accepted"), (NEW_TEXT, "accepted"),
    ]
    assert client.get(f"/api/ideas/{proposal}").status_code == 404
    review = client.get("/api/ideas/review").json()["ideas"]
    assert all(card["idea"]["id"] not in (held, proposal) for card in review)


def _link(user_id: int, start: str, end: str, kind: str, status: str = "accepted") -> None:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO idea_links (user_id, from_idea_id, to_idea_id, kind, rationale, status)
               VALUES (%s, %s, %s, %s, 'Invented for a test.', %s)""",
            (user_id, start, end, kind, status),
        )
        conn.commit()


def test_merging_a_held_idea_brings_its_quotes_links_and_notes(client, test_user):
    user = test_user["id"]
    entries = ReflectionService(user)
    old_entry = entries.create_reflection(content=OLD_TEXT, reflection_date=date(2025, 5, 1))
    new_entry = entries.create_reflection(content=NEW_TEXT, reflection_date=date(2025, 7, 1))
    kept = _idea(user, HELD, "active", notes="Kept notes.")
    twin = _idea(user, REWORDED, "active", notes="Twin notes.")
    rule = _idea(user, "Act when losses are smallest.", "active")
    other = _idea(user, "A watched kettle still boils.", "active", notes=f"See [[{REWORDED}]].")
    _quote(kept, old_entry, OLD_TEXT, "accepted")
    _quote(twin, old_entry, OLD_TEXT, "accepted")
    _quote(twin, new_entry, NEW_TEXT, "accepted")
    _link(user, twin, rule, "applies")
    _link(user, kept, rule, "applies")        # the same link twice after the merge
    _link(user, other, twin, "supports")
    _link(user, kept, twin, "same_meaning")  # a link between the two, lower id first

    response = client.post(f"/api/ideas/{twin}/fold", json={"intoId": int(kept)})
    assert response.status_code == 200, response.text
    assert response.json()["quotesMoved"] == 1

    page = client.get(f"/api/ideas/{kept}").json()
    assert sorted(quote["text"] for quote in page["citations"]) == sorted([OLD_TEXT, NEW_TEXT])
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT from_idea_id::text, to_idea_id::text, kind FROM idea_links
                WHERE user_id = %s AND status = 'accepted'""",
            (user,),
        )
        live = set(cur.fetchall())
    assert live == {(kept, rule, "applies"), (other, kept, "supports")}
    assert page["page"]["notes"] == f"Kept notes.\n\n## Merged from: {REWORDED}\n\nTwin notes.\n"
    assert client.get(f"/api/ideas/{other}").json()["page"]["notes"] == f"See [[{HELD}]]."
    assert client.get(f"/api/ideas/{twin}").status_code == 404
    assert all(idea["id"] != twin for idea in client.get("/api/ideas/framework").json()["ideas"])


def test_only_a_live_idea_folds_and_only_into_a_held_idea(client, test_user):
    held = _idea(test_user["id"], HELD, "active")
    proposal = _idea(test_user["id"], REWORDED, "candidate")
    other = _idea(test_user["id"], "Act when losses are smallest.", "candidate")
    gone = _idea(test_user["id"], "A watched kettle still boils.", "rejected")

    assert client.post(f"/api/ideas/{held}/fold", json={"intoId": int(proposal)}).status_code == 409
    assert client.post(f"/api/ideas/{proposal}/fold", json={"intoId": int(other)}).status_code == 409
    assert client.post(f"/api/ideas/{gone}/fold", json={"intoId": int(held)}).status_code == 409
    assert client.post(f"/api/ideas/{proposal}/fold", json={"intoId": int(proposal)}).status_code == 409
    assert client.post(f"/api/ideas/{proposal}/fold", json={"intoId": 999999}).status_code == 404


def test_a_folded_wording_found_again_belongs_to_the_held_idea():
    registry = [
        {"id": 1, "status": "active", "merged_into_id": None},
        {"id": 2, "status": "rejected", "merged_into_id": 1},
        {"id": 3, "status": "rejected", "merged_into_id": None},
    ]
    assert _held(registry[1], registry) == 1
    assert _held(registry[2], registry) == "rejected", "a dismissed wording stays dismissed"
