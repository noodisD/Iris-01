"""Ideas that share one meaning across fields, and the Life area.

A scripted double stands in for the model. Every entry and idea here is
invented: a gardening rule, a cooking rule and a general principle that the
owner states in their own words.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from agent.ideas.reader import IDEA_READ_PROMPT
from agent.trackers.reflections import ReflectionService
from iris_api import app, get_current_user_id

GARDEN_TEXT = "Planting what the neighbour plants never works for my soil; I only grow what suits this plot."
KITCHEN_TEXT = "Cooking from someone else's menu leaves me unsatisfied, so I cook to my own taste."
LIFE_TEXT = "In every part of life, following a plan someone else made for me has left me unfulfilled."
GARDEN = "Copying another gardener's planting fails; grow what suits your own plot."
KITCHEN = "Cooking to another person's menu is unsatisfying; cook to your own taste."
LIFE = "Following a path set by someone else leaves a person unfulfilled, in any part of life."
SHARED = "Both rest on acting from one's own judgement rather than borrowing another's plan."


class Script:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.model = "scripted"
        self.ids: dict[str, int] = {}
        self.pairs: list[dict] = []

    def chat(self, messages, system_prompt, **kwargs):
        user = messages[0]["content"]
        self.calls.append((system_prompt, user))
        if system_prompt.startswith("You are extracting"):
            return json.dumps({"ideas": [
                self._draft(GARDEN, "markets", self.ids["garden"], "Planting what the neighbour plants never works"),
                self._draft(KITCHEN, "other", self.ids["kitchen"], "Cooking from someone else's menu leaves me unsatisfied"),
                self._draft(LIFE, "life", self.ids["life"], "following a plan someone else made for me has left me unfulfilled"),
            ]})
        if system_prompt.startswith("You are checking"):
            payload = json.loads(user)
            return json.dumps({"quotes": [{"i": q["i"], "stance": "endorsed"} for q in payload["quotes"]]})
        if system_prompt.startswith("You are deciding"):
            return json.dumps({"ideaId": None})
        if system_prompt.startswith("You are finding"):
            return json.dumps({"pairs": self.pairs})
        raise AssertionError(system_prompt[:60])

    @staticmethod
    def _draft(statement, domain, entry_id, quote):
        return {"statement": statement, "domain": domain,
                "quotes": [{"entryId": entry_id, "sourceType": "reflection", "text": quote}]}


@pytest.fixture
def framework(test_user, monkeypatch):
    """Three accepted ideas, one of them filed under Life."""
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    client = TestClient(app)
    reflections = ReflectionService(test_user["id"])
    script = Script()
    script.ids = {
        "garden": reflections.create_reflection(content=GARDEN_TEXT, reflection_date=date(2024, 4, 1)),
        "kitchen": reflections.create_reflection(content=KITCHEN_TEXT, reflection_date=date(2024, 5, 1)),
        "life": reflections.create_reflection(content=LIFE_TEXT, reflection_date=date(2024, 6, 1)),
    }
    monkeypatch.setattr("agent.ideas.service.Intelligence", lambda *_a, **_k: script)
    assert client.post("/api/ideas/discover").status_code == 200
    ids = {}
    for card in client.get("/api/ideas/review").json()["ideas"]:
        idea = card["idea"]
        r = client.post(f"/api/ideas/{idea['id']}/confirm", json={
            "citationIds": [c["id"] for c in card["citations"]], "position": "endorsed", "domain": idea["domain"]})
        assert r.status_code == 200, r.text
        ids[idea["statement"]] = int(idea["id"])
    yield client, script, ids
    app.dependency_overrides.clear()


def test_life_is_an_area_and_the_reader_may_not_generalise_into_it(framework):
    client, _, ids = framework
    domains = {i["statement"]: i["domain"] for i in client.get("/api/ideas/framework").json()["ideas"]}
    assert domains[LIFE] == "life"
    assert "Never generalise" in IDEA_READ_PROMPT


def test_the_estimate_counts_what_would_be_sent_and_sends_nothing(framework):
    client, script, _ = framework
    before = len(script.calls)
    estimate = client.get("/api/ideas/meanings/estimate").json()
    assert estimate["ideas"] == 3 and estimate["calls"] == 1
    assert "tokens in on" in estimate["estimate"]
    assert len(script.calls) == before


def test_ideas_sharing_a_meaning_are_proposed_once_and_wait_for_the_owner(framework):
    client, script, ids = framework
    garden, kitchen, life = ids[GARDEN], ids[KITCHEN], ids[LIFE]
    script.pairs = [
        {"a": kitchen, "b": garden, "kind": "same_meaning", "rationale": SHARED},  # stored lower id first
        {"a": garden, "b": kitchen, "kind": "same_meaning", "rationale": SHARED},  # the same pair again
        {"a": life, "b": life, "kind": "same_meaning", "rationale": SHARED},       # a self-pair is malformed
        {"a": life, "b": 999999, "kind": "same_meaning", "rationale": SHARED},     # an id not supplied is malformed
        {"a": garden, "b": life, "kind": "related", "rationale": SHARED},          # a vague kind is malformed
    ]
    response = client.post("/api/ideas/meanings/discover")
    assert response.status_code == 200, response.text
    run = response.json()["run"]
    assert run["kind"] == "meaning" and run["proposed"] == 1 and run["dropped"]["malformed"] == 3

    # Only accepted statements were sent, never the journal text behind them.
    sent = next(user for prompt, user in script.calls if prompt.startswith("You are finding"))
    assert GARDEN in sent and GARDEN_TEXT not in sent and LIFE_TEXT not in sent

    # Nothing is linked until the owner accepts it.
    assert client.get("/api/ideas/framework").json()["links"] == []
    link = next(item for item in client.get("/api/ideas/review").json()["links"] if item["kind"] == "same_meaning")
    assert (int(link["fromIdeaId"]), int(link["toIdeaId"])) == tuple(sorted((garden, kitchen)))
    assert client.post(f"/api/ideas/links/{link['id']}/confirm").status_code == 200
    accepted = client.get("/api/ideas/framework").json()["links"]
    assert [(item["kind"], item["rationale"]) for item in accepted] == [("same_meaning", SHARED)]

    # Asking again does not re-propose what the owner already decided.
    again = client.post("/api/ideas/meanings/discover").json()["run"]
    assert again["proposed"] == 0 and again["dropped"]["already_decided"] == 1


def test_with_fewer_than_two_ideas_nothing_is_sent(test_user, monkeypatch):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    calls = []
    monkeypatch.setattr("agent.ideas.service.Intelligence", lambda *_a, **_k: calls.append(1))
    try:
        client = TestClient(app)
        assert client.get("/api/ideas/meanings/estimate").json()["calls"] == 0
        assert client.post("/api/ideas/meanings/discover").json()["run"]["status"] == "complete"
        assert calls == []
    finally:
        app.dependency_overrides.clear()


APPLIES = "Cooking to one's own taste is the general principle of acting on one's own judgement, applied in the kitchen."


def test_an_application_of_a_principle_is_not_proposed_as_the_same_meaning(framework):
    """A specific rule and the general principle it applies are related, not one
    meaning. They are proposed as `applies`, keeping which is which."""
    client, script, ids = framework
    kitchen, life = ids[KITCHEN], ids[LIFE]
    script.pairs = [{"a": kitchen, "b": life, "kind": "applies", "rationale": APPLIES}]

    assert client.post("/api/ideas/meanings/discover").json()["run"]["proposed"] == 1

    link = next(item for item in client.get("/api/ideas/review").json()["links"] if item["kind"] == "applies")
    assert (int(link["fromIdeaId"]), int(link["toIdeaId"])) == (kitchen, life), "the specific idea applies the general"
    sent = next(prompt for prompt, _ in script.calls if prompt.startswith("You are finding"))
    assert '"applies"' in sent
    assert "is not the same meaning" in sent


def test_the_owner_can_accept_a_link_as_the_relation_they_see(framework):
    """IRIS proposed one meaning; the owner sees one idea applying the other.
    Their relation is what stands, and IRIS's is kept as dismissed so it is not
    proposed again."""
    client, script, ids = framework
    kitchen, life = ids[KITCHEN], ids[LIFE]
    low, high = sorted((kitchen, life))
    script.pairs = [{"a": kitchen, "b": life, "kind": "same_meaning", "rationale": SHARED}]
    client.post("/api/ideas/meanings/discover")
    proposal = next(item for item in client.get("/api/ideas/review").json()["links"] if item["kind"] == "same_meaning")
    # Stored lower id first; the owner names which way round it goes.
    reverse = (int(proposal["fromIdeaId"]), int(proposal["toIdeaId"])) != (kitchen, life)
    assert (low, high) == (int(proposal["fromIdeaId"]), int(proposal["toIdeaId"]))

    r = client.post(f"/api/ideas/links/{proposal['id']}/confirm", json={"kind": "applies", "reverse": reverse})

    assert r.status_code == 200, r.text
    accepted = client.get("/api/ideas/framework").json()["links"]
    assert [(item["kind"], int(item["fromIdeaId"]), int(item["toIdeaId"])) for item in accepted] == [("applies", kitchen, life)]
    assert r.json()["id"] == accepted[0]["id"]
    again = client.post("/api/ideas/meanings/discover").json()["run"]
    assert again["proposed"] == 0
    assert again["dropped"]["already_decided"] == 1


def test_an_unknown_relation_is_refused(framework):
    client, script, ids = framework
    script.pairs = [{"a": ids[KITCHEN], "b": ids[GARDEN], "kind": "same_meaning", "rationale": SHARED}]
    client.post("/api/ideas/meanings/discover")
    proposal = client.get("/api/ideas/review").json()["links"][0]
    r = client.post(f"/api/ideas/links/{proposal['id']}/confirm", json={"kind": "resembles"})
    assert r.status_code == 409


def test_the_reader_is_told_one_idea_is_one_proposition():
    """It joined two separate sentences from one entry into a single idea with a
    semicolon, only because they sat together."""
    assert "Each idea is one proposition" in IDEA_READ_PROMPT
    assert "never join them into one statement" in IDEA_READ_PROMPT
