"""The owner's idea framework, from the HTTP seam.

A scripted chat double stands in for the model. The acceptance sequence is
the one named in the ideas plan: read, review, link, tension, critique,
invalidation, and a remembered rejection.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from agent.database import db
from agent.trackers.reflections import ReflectionService
from iris_api import app, get_current_user_id

FIRST = "A price is information. When a government fixes prices, it destroys the signal that tells people what is scarce."
SECOND = "I no longer think price controls are a kindness. They hide scarcity and make shortages worse."
THIRD = "Central planning cannot know what millions of people want, because that knowledge is dispersed."
PLANNER_TEXT = "A central planner can know enough to set better prices than a market."
UNDATED_TEXT = "People cannot plan an economy from a single office."
REJECT_TEXT = "A just society does not treat birth as a claim on other people's work."
CHAT = "I believe inheritance should be abolished."
INELIGIBLE = "I hold that taxation is theft."

PRICE = "Price controls destroy the information prices carry about scarcity."
KNOWLEDGE = "The knowledge needed to allocate resources is dispersed among people."
PLANNER = "A central planner can know enough to set better prices than a market."
REJECTED = "Inheritance should be abolished as a matter of justice."
UNDATED_IDEA = "An economy cannot be planned from one office."
Q1 = "When a government fixes prices, it destroys the signal that tells people what is scarce."
Q2 = "They hide scarcity and make shortages worse."
Q3 = "Central planning cannot know what millions of people want, because that knowledge is dispersed."
BAD = "this sentence was never written in the entry"
INVALID = "Markets always allocate resources perfectly."
OBJECTION = "A signal can be noisy without being destroyed."
RATIONALE = "The scarcity-signal claim needs the claim that the relevant knowledge is dispersed."


class Script:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.model = "scripted"
        self.extracts = 0
        self.ids: dict[str, int] = {}

    def chat(self, messages, system_prompt, **kwargs):
        user = messages[0]["content"]
        self.calls.append(system_prompt + "\n" + user)
        if system_prompt.startswith("You are extracting"):
            self.extracts += 1
            return json.dumps({"ideas": self._ideas()})
        if system_prompt.startswith("You are checking"):
            payload = json.loads(user)
            return json.dumps({"quotes": [{"i": item["i"], "stance": "endorsed"} for item in payload["quotes"]]})
        if system_prompt.startswith("You are deciding"):
            return json.dumps({"ideaId": None})
        if system_prompt.startswith("You are proposing"):
            return json.dumps({"links": self._links(json.loads(user))})
        if system_prompt.startswith("You are a sparring partner"):
            return json.dumps({
                "objections": [{"argument": OBJECTION, "question": "What would count as a destroyed signal?"}],
                "possiblePremises": [{
                    "premise": "Only prices carry the relevant scarcity information.",
                    "question": "What else could carry it?",
                }],
                "relatedThought": [{
                    "name": "Hayek",
                    "kind": "thinker",
                    "connection": "Dispersed knowledge is a familiar theme, not a sourced quotation.",
                }],
            })
        raise AssertionError(system_prompt[:60])

    def _ideas(self) -> list[dict]:
        if self.extracts == 1:
            return [
                self._draft(PRICE, [(self.ids["first"], Q1), (self.ids["second"], Q2)]),
                self._draft(KNOWLEDGE, [(self.ids["third"], Q3)]),
                self._draft(INVALID, [(self.ids["first"], BAD)]),
            ]
        if self.extracts == 2:
            return [self._draft(PLANNER, [(self.ids["planner"], PLANNER_TEXT)])]
        if self.extracts == 3:
            return []
        if self.extracts in (4, 5):
            return [self._draft(REJECTED, [(self.ids["reject"], REJECT_TEXT)])]
        return [self._draft(UNDATED_IDEA, [(self.ids["undated"], UNDATED_TEXT)])]

    def _draft(self, statement: str, quotes: list[tuple[int, str]]) -> dict:
        return {
            "statement": statement,
            "domain": "economics",
            "quotes": [{"entryId": entry_id, "sourceType": "reflection", "text": text} for entry_id, text in quotes],
        }

    def _links(self, payload: dict) -> list[dict]:
        subject = payload["subject"]
        ideas = payload["ideas"]
        if "Price controls" in subject["statement"]:
            other = next(item for item in ideas if "dispersed" in item["statement"])
            return [{
                "fromIdeaId": subject["id"],
                "toIdeaId": other["id"],
                "kind": "depends_on",
                "rationale": RATIONALE,
            }]
        if "central planner" in subject["statement"].lower():
            other = next(item for item in ideas if "Price controls" in item["statement"])
            return [{
                "fromIdeaId": subject["id"],
                "toIdeaId": other["id"],
                "kind": "contradicts",
                "rationale": "These cannot both be accepted about the same prices.",
            }]
        return []


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def _confirm(client: TestClient, idea_id: str, citations: list[dict]) -> None:
    response = client.post(f"/api/ideas/{idea_id}/confirm", json={
        "citationIds": [item["id"] for item in citations],
        "position": "endorsed",
        "domain": "economics",
    })
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "active"


def test_the_framework_is_read_reviewed_and_invalidated(client, test_user, monkeypatch):
    reflections = ReflectionService(test_user["id"])
    script = Script()
    script.ids = {
        "first": reflections.create_reflection(content=FIRST, reflection_date=date(2024, 1, 1)),
        "second": reflections.create_reflection(content=SECOND, reflection_date=date(2024, 6, 1)),
        "third": reflections.create_reflection(content=THIRD, reflection_date=date(2025, 1, 1)),
    }
    db.create_conversation_message(test_user["id"], "session-ideas", "user", CHAT)
    reflections.create_reflection(content=INELIGIBLE, reflection_date=date(2024, 3, 1), evidence_eligible=False)
    monkeypatch.setattr("agent.ideas.service.Intelligence", lambda *_a, **_k: script)

    discovered = client.post("/api/ideas/discover")
    assert discovered.status_code == 200, discovered.text
    run = discovered.json()["run"]
    assert run["dropped"]["invalid_quote"] == 1
    assert CHAT not in "".join(script.calls)
    assert INELIGIBLE not in "".join(script.calls)

    review = client.get("/api/ideas/review").json()
    by_statement = {card["idea"]["statement"]: card for card in review["ideas"]}
    assert PRICE in by_statement
    assert KNOWLEDGE in by_statement
    assert BAD not in json.dumps(review)
    assert INVALID not in by_statement
    _confirm(client, by_statement[PRICE]["idea"]["id"], by_statement[PRICE]["citations"])
    _confirm(client, by_statement[KNOWLEDGE]["idea"]["id"], by_statement[KNOWLEDGE]["citations"])
    price_id = by_statement[PRICE]["idea"]["id"]
    knowledge_id = by_statement[KNOWLEDGE]["idea"]["id"]

    framework = client.get("/api/ideas/framework").json()
    statements = {idea["statement"] for idea in framework["ideas"]}
    assert {PRICE, KNOWLEDGE} <= statements
    assert framework["tensionIds"] == []
    assert knowledge_id not in framework["foundationIds"]

    linked = client.post(f"/api/ideas/{price_id}/links/discover")
    assert linked.status_code == 200, linked.text
    pending = client.get("/api/ideas/review").json()["links"]
    depends = next(link for link in pending if link["kind"] == "depends_on")
    assert depends["rationale"] == RATIONALE
    assert client.post(f"/api/ideas/links/{depends['id']}/confirm").status_code == 200
    framework = client.get("/api/ideas/framework").json()
    assert framework["foundationIds"] == [knowledge_id]

    script.ids["planner"] = reflections.create_reflection(
        content=PLANNER_TEXT, reflection_date=date(2025, 2, 1),
    )
    assert client.post("/api/ideas/discover").status_code == 200
    planner_card = next(
        card for card in client.get("/api/ideas/review").json()["ideas"]
        if card["idea"]["statement"] == PLANNER
    )
    planner_id = planner_card["idea"]["id"]
    _confirm(client, planner_id, planner_card["citations"])
    assert client.post(f"/api/ideas/{planner_id}/links/discover").status_code == 200
    contradiction = next(
        link for link in client.get("/api/ideas/review").json()["links"]
        if link["kind"] == "contradicts"
    )
    assert client.post(f"/api/ideas/links/{contradiction['id']}/confirm").status_code == 200
    framework = client.get("/api/ideas/framework").json()
    assert framework["tensionIds"] == [contradiction["id"]]
    assert client.patch(f"/api/ideas/{planner_id}", json={"position": "exploring"}).status_code == 200
    framework = client.get("/api/ideas/framework").json()
    assert framework["tensionIds"] == []
    assert any(link["id"] == contradiction["id"] and link["status"] == "accepted" for link in framework["links"])

    before_critique = len(script.calls)
    critique = client.post(f"/api/ideas/{knowledge_id}/critique")
    assert critique.status_code == 200, critique.text
    assert critique.json()["critique"]["origin"] == "iris"
    detail = client.get(f"/api/ideas/{knowledge_id}").json()
    assert detail["critiques"][0]["origin"] == "iris"
    assert OBJECTION not in json.dumps(client.get("/api/ideas/framework").json())
    calls_before_later = len(script.calls)
    assert client.post("/api/ideas/discover").status_code == 200
    assert OBJECTION not in "".join(script.calls[calls_before_later:])

    reflections.update_reflection(int(script.ids["third"]), content="The quoted passage was edited away.")
    detail = client.get(f"/api/ideas/{knowledge_id}").json()
    assert detail["idea"]["needsEvidence"] is True
    assert all(item["entryId"] != str(script.ids["third"]) for item in detail["citations"])
    framework = client.get("/api/ideas/framework").json()
    assert all(knowledge_id not in (link["fromIdeaId"], link["toIdeaId"]) for link in framework["links"])
    assert client.get(f"/api/ideas/{knowledge_id}").json()["critiques"][0]["isCurrent"] is False
    calls_after_edit = len(script.calls)
    assert client.post(f"/api/ideas/{knowledge_id}/critique").status_code == 409
    assert client.post(f"/api/ideas/{knowledge_id}/links/discover").status_code == 409
    assert len(script.calls) == calls_after_edit
    assert before_critique < calls_after_edit

    script.ids["reject"] = reflections.create_reflection(
        content=REJECT_TEXT, reflection_date=date(2025, 3, 1),
    )
    assert client.post("/api/ideas/discover").status_code == 200
    rejected = next(
        card for card in client.get("/api/ideas/review").json()["ideas"]
        if card["idea"]["statement"] == REJECTED
    )
    assert client.post(f"/api/ideas/{rejected['idea']['id']}/reject").status_code == 200
    again = client.post("/api/ideas/discover")
    assert again.status_code == 200, again.text
    assert again.json()["run"]["dropped"]["already_decided"] >= 1
    stored = db.connection()
    with stored as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM ideas WHERE user_id = %s AND statement = %s;",
            (test_user["id"], REJECTED),
        )
        assert cur.fetchone()[0] == 1

    script.ids["undated"] = reflections.create_reflection(content=UNDATED_TEXT, undated=True)
    assert client.post("/api/ideas/discover").status_code == 200
    undated = next(
        card for card in client.get("/api/ideas/review").json()["ideas"]
        if card["idea"]["statement"] == UNDATED_IDEA
    )
    _confirm(client, undated["idea"]["id"], undated["citations"])
    assert client.get(f"/api/ideas/{undated['idea']['id']}").json()["citations"][0]["entryDate"] is None
    calls_before_date = len(script.calls)
    db.set_reflection_date(script.ids["undated"], test_user["id"], date(2023, 5, 1))
    dated = client.get(f"/api/ideas/{undated['idea']['id']}").json()["citations"][0]
    assert dated["entryDate"] == "2023-05-01"
    assert len(script.calls) == calls_before_date

    other = db.create_user(f"other_{test_user['username']}")
    app.dependency_overrides[get_current_user_id] = lambda: other
    assert client.get(f"/api/ideas/{price_id}").status_code == 404
    assert client.post(f"/api/ideas/{price_id}/reject").status_code == 404
    assert client.post(f"/api/ideas/links/{contradiction['id']}/reject").status_code == 404
    assert client.get("/api/ideas/framework").json()["ideas"] == []


def test_a_failed_read_is_502_and_still_recorded(client, test_user, monkeypatch):
    ReflectionService(test_user["id"]).create_reflection(content=FIRST, reflection_date=date(2024, 1, 1))

    class Down:
        model = "scripted"

        def chat(self, messages, system_prompt, **kwargs):
            raise RuntimeError("do not store this")

    monkeypatch.setattr("agent.ideas.service.Intelligence", lambda *_a, **_k: Down())
    response = client.post("/api/ideas/discover")
    assert response.status_code == 502
    assert response.json()["detail"] == "Ideas analysis could not finish. Review the last run."
    recorded = client.get("/api/ideas/framework").json()["lastRun"]
    assert recorded["status"] == "failed"
    assert recorded["error"] == "model_failed"
    assert "do not store" not in json.dumps(recorded)


def test_a_non_integer_citation_id_is_422(client, test_user):
    response = client.post("/api/ideas/1/confirm", json={
        "citationIds": ["nope"],
        "position": "exploring",
        "domain": "ethics",
    })
    assert response.status_code == 422


def test_a_critique_without_a_model_client_is_502_and_saves_nothing(client, test_user, monkeypatch):
    reflections = ReflectionService(test_user["id"])
    script = Script()
    script.ids = {
        "first": reflections.create_reflection(content=FIRST, reflection_date=date(2024, 1, 1)),
        "second": reflections.create_reflection(content=SECOND, reflection_date=date(2024, 6, 1)),
        "third": reflections.create_reflection(content=THIRD, reflection_date=date(2025, 1, 1)),
    }
    monkeypatch.setattr("agent.ideas.service.Intelligence", lambda *_a, **_k: script)
    assert client.post("/api/ideas/discover").status_code == 200
    knowledge = next(
        card for card in client.get("/api/ideas/review").json()["ideas"]
        if card["idea"]["statement"] == KNOWLEDGE
    )
    _confirm(client, knowledge["idea"]["id"], knowledge["citations"])

    def unavailable(*_a, **_k):
        raise ValueError("No API key configured. Set OPENAI_API_KEY in .env")

    monkeypatch.setattr("agent.ideas.service.Intelligence", unavailable)
    response = client.post(f"/api/ideas/{knowledge['idea']['id']}/critique")
    assert response.status_code == 502
    assert response.json()["detail"] == "Iris could not produce a critique. No critique was saved."
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM idea_critiques WHERE idea_id = %s",
            (int(knowledge["idea"]["id"]),),
        )
        assert cur.fetchone()[0] == 0


def test_confirming_a_missing_idea_is_404_even_with_an_empty_list(client):
    response = client.post("/api/ideas/999999/confirm", json={
        "citationIds": [],
        "position": "exploring",
        "domain": "ethics",
    })
    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found"
