"""The owner answers a questionnaire inside IRIS; only their own words are evidence (ADR-0029).

The questionnaire here is invented. The real one is someone else's text and is
never in the repository.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from agent import questionnaire
from agent.database import db
from agent.observations import verify_citations
from agent.questionnaire import Questionnaires
from agent.questionnaire_interview import interview
from iris_api import app, get_current_user_id

FIXTURE = {
    "id": "baseline", "version": "test", "title_pl": "Ankieta", "title_en": "Questionnaire",
    "about_en": "An invented questionnaire.", "about_pl": "Zmyślona ankieta.",
    "sections": [
        {"id": "home", "title_pl": "Dom", "title_en": "Home", "intro_pl": "", "intro_en": "About home.",
         "questions": [
             {"id": "q1", "number": 1, "pl": "Gdzie dorastałeś?", "en": "Where did you grow up?"},
             {"id": "q2", "number": 2, "pl": "Co cię uspokaja?", "en": "What calms you down?"}]},
        {"id": "work", "title_pl": "Praca", "title_en": "Work", "intro_pl": "", "intro_en": "",
         "questions": [{"id": "q3", "number": 3, "pl": "Co daje ci praca?", "en": "What does work give you?"}]},
    ],
}
GREW_UP = "In a small town by a lake, and I left when I was twelve because we moved."


@pytest.fixture
def installed(tmp_path, monkeypatch):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(FIXTURE), encoding="utf-8")
    monkeypatch.setattr(questionnaire, "questionnaire_path", lambda name="baseline": path)
    return path


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def _reflections(user_id: int) -> list[tuple]:
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, source, content_format, content FROM reflections WHERE user_id = %s",
                    (user_id,))
        return cur.fetchall()


def test_a_questionnaire_that_is_not_installed_says_so(client, tmp_path, monkeypatch):
    monkeypatch.setattr(questionnaire, "questionnaire_path", lambda name="baseline": tmp_path / "none.json")
    response = client.get("/api/questionnaire")
    assert response.status_code == 404 and "not installed" in response.json()["detail"]


def test_drafts_are_kept_and_sent_nowhere(test_user, installed):
    service = Questionnaires(test_user["id"])
    state = service.save("q1", GREW_UP)
    assert state["status"] == "draft" and state["answer"] == GREW_UP
    assert _reflections(test_user["id"]) == []
    assert service.save("q1", "")["status"] == "unanswered", "clearing a draft removes it"
    overview = service.overview()
    assert [s["counts"]["unanswered"] for s in overview["sections"]] == [2, 1]
    assert overview["sections"][0]["questions"][0]["text"] == "Where did you grow up?"


def test_adding_a_section_makes_owner_only_sources(test_user, installed):
    service = Questionnaires(test_user["id"])
    service.save("q1", GREW_UP)
    service.save("q3", "Security, mostly.")
    estimate = service.estimate("home")
    assert estimate["answers"] == 1 and "OpenAI" in estimate["text"]
    assert service.add_section("home") == {"added": 1}, "only the section's drafts"
    rows = _reflections(test_user["id"])
    assert [(r[1], r[2]) for r in rows] == [("questionnaire", "session")]
    entry = {"id": rows[0][0], "content": rows[0][3], "content_format": "session",
             "source_type": "reflection", "date": date.today()}
    assert verify_citations([{"entryId": rows[0][0], "text": "a small town by a lake"}],
                            {("reflection", rows[0][0]): entry}) is not None
    assert verify_citations([{"entryId": rows[0][0], "text": "Where did you grow up"}],
                            {("reflection", rows[0][0]): entry}) is None, "the question is not evidence"
    assert service.question("q1")["status"] == "added"
    assert service.question("q3")["status"] == "draft"


def test_revising_an_answer_keeps_the_earlier_one_and_replaces_its_source(test_user, installed):
    service = Questionnaires(test_user["id"])
    service.save("q1", GREW_UP)
    service.add_section("home")
    first = _reflections(test_user["id"])[0][0]
    revised = service.save("q1", "By a lake. I think of it whenever I need quiet.")
    assert revised["status"] == "draft" and revised["revising"]
    service.add_section("home")
    rows = _reflections(test_user["id"])
    assert len(rows) == 1 and rows[0][0] != first, "the old source is gone, the new one stands"
    history = service.history("q1")
    assert [(v["status"], v["answer"]) for v in history] == [
        ("added", "By a lake. I think of it whenever I need quiet."), ("superseded", GREW_UP)]
    assert db.get_reflection(first) is None


def test_a_question_can_be_skipped_and_taken_back(test_user, installed):
    service = Questionnaires(test_user["id"])
    assert service.skip("q2", True)["status"] == "skipped"
    assert service.overview()["sections"][0]["counts"]["skipped"] == 1
    assert service.skip("q2", False)["status"] == "unanswered"


def test_an_interview_answer_keeps_the_exchange_and_only_the_owner_counts(test_user, installed):
    service = Questionnaires(test_user["id"])
    transcript = [{"role": "iris", "text": "Where did you grow up?"},
                  {"role": "owner", "text": "By a lake."},
                  {"role": "iris", "text": "What was it like there for you?"},
                  {"role": "owner", "text": "Quiet, and I felt safe there."}]
    service.save("q1", "By a lake.\n\nQuiet, and I felt safe there.", "interview", transcript)
    service.add_section("home")
    content = _reflections(test_user["id"])[0][3]
    from agent import sessions
    session = sessions.read(content)
    assert [t.role for t in session.turns] == ["asker", "owner", "asker", "owner"]
    assert sessions.owner_turn(content, "What was it like there for you") is None
    assert sessions.owner_turn(content, "Quiet, and I felt safe there") is not None


class Interviewer:
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def chat(self, *, messages, system_prompt, **_):
        self.prompts.append(messages[0]["content"])
        return json.dumps(self.replies.pop(0))


QUESTION = FIXTURE["sections"][0]["questions"][0]


def test_the_interview_asks_follows_up_once_and_drafts_the_owners_own_words():
    model = Interviewer([{"reply": "Where did you grow up?", "done": False},
                         {"reply": "What was it like there for you?", "done": False},
                         {"reply": "Thank you.", "done": True}])
    first = interview(QUESTION, "About home.", [], model)
    assert first == {"reply": "Where did you grow up?", "done": False, "draft": "", "skipped": False}
    turns = [{"role": "iris", "text": first["reply"]}, {"role": "owner", "text": "By a lake."}]
    follow = interview(QUESTION, "About home.", turns, model)
    assert not follow["done"]
    turns += [{"role": "iris", "text": follow["reply"]}, {"role": "owner", "text": "Quiet, I felt safe."}]
    last = interview(QUESTION, "About home.", turns, model)
    assert last["done"] and last["draft"] == "By a lake.\n\nQuiet, I felt safe."
    assert "Where did you grow up?" in model.prompts[0] and "Gdzie dorastałeś?" in model.prompts[0]


def test_skip_ends_the_interview_without_asking_the_model():
    model = Interviewer([])
    result = interview(QUESTION, "", [{"role": "iris", "text": "Where did you grow up?"},
                                      {"role": "owner", "text": "skip"}], model)
    assert result["done"] and result["skipped"] and result["draft"] == "" and model.prompts == []


def test_the_interview_stops_after_three_replies_whatever_the_model_says():
    turns = []
    for n in range(3):
        turns += [{"role": "iris", "text": "Tell me more?"}, {"role": "owner", "text": f"Part {n}."}]
    result = interview(QUESTION, "", turns, Interviewer([]))
    assert result["done"] and result["draft"] == "Part 0.\n\nPart 1.\n\nPart 2."


def test_answers_stay_out_of_recent_entries_and_the_journal_but_are_recalled(test_user, installed, client):
    service = Questionnaires(test_user["id"])
    service.save("q1", GREW_UP)
    service.add_section("home")
    assert db.get_latest_reflections(test_user["id"], 5) == []
    assert client.get("/api/journal").json()["entries"] == []
    from agent import pipeline
    reflection_id = _reflections(test_user["id"])[0][0]
    pipeline.run_processing_pipeline("reflection", reflection_id)
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM session_passages WHERE reflection_id = %s", (reflection_id,))
        passage = cur.fetchone()[0]
    item = db.get_memory_item("session_passage", passage)
    assert item["kind"] == "questionnaire answer" and "Me (owner):" in item["text"]


def test_the_routes(client, installed, mock_llm):
    assert client.put("/api/questionnaire/answers/q1", json={"answer": GREW_UP}).json()["status"] == "draft"
    assert client.put("/api/questionnaire/answers/q99", json={"answer": "x"}).status_code == 404
    assert client.get("/api/questionnaire/sections/home/estimate").json()["answers"] == 1
    assert client.post("/api/questionnaire/sections/home/add").json() == {"added": 1}
    assert client.get("/api/questionnaire/answers/q1/history").json()["versions"][0]["status"] == "added"
    assert client.post("/api/questionnaire/answers/q2/skip", json={"skipped": True}).json()["status"] == "skipped"
    mock_llm.chat.return_value = json.dumps({"reply": "Where did you grow up?", "done": False})
    asked = client.post("/api/questionnaire/interview/q1", json={"messages": []})
    assert asked.status_code == 200 and asked.json()["reply"] == "Where did you grow up?"


# --- suggestions from the owner's own writing ------------------------------------

from agent import questionnaire_suggest  # noqa: E402
from agent import sessions as session_format  # noqa: E402

JOURNAL = "We moved twice when I was small. I grew up mostly in a small town by a lake."
SESSION = session_format.compose(
    [session_format.Segment(0, "Counsellor", "So you grew up near water, by the lake?"),
     session_format.Segment(5, "Ann", "Yes, and the lake was the only quiet place I had as a child.")],
    kind="therapy", started="2026-09-30T18:00", language="en", owner="Ann", therapist="Counsellor")


class Picker:
    def __init__(self, quotes):
        self.quotes = quotes
        self.prompts = []

    def chat(self, *, messages, **_):
        self.prompts.append(messages[0]["content"])
        return json.dumps({"quotes": self.quotes})


@pytest.fixture
def writing(monkeypatch):
    found = [{"kind": "journal", "date": date(2025, 3, 12), "text": JOURNAL, "original": JOURNAL, "session": False},
             {"kind": "therapy session", "date": date(2026, 9, 30), "text": "...", "original": SESSION,
              "session": True}]
    monkeypatch.setattr(questionnaire_suggest, "sources", lambda user_id, query: found)


def test_a_suggestion_is_only_the_owners_sentences_found_word_for_word(writing):
    model = Picker([{"source": "s1", "text": "I grew up mostly in a small town by a lake"},
                    {"source": "s2", "text": "So you grew up near water, by the lake"},
                    {"source": "s2", "text": "the lake was the only quiet place I had as a child"},
                    {"source": "s1", "text": "I grew up in a big city by the sea"}])
    quotes = questionnaire_suggest.suggest(QUESTION, 1, model)
    assert [q["text"] for q in quotes] == [
        "I grew up mostly in a small town by a lake",
        "the lake was the only quiet place I had as a child"], "not the counsellor, not invented"
    assert questionnaire_suggest.draft(quotes).startswith(
        "“I grew up mostly in a small town by a lake” (journal, 2025-03-12)")


def test_suggestions_fill_only_empty_questions(test_user, installed, writing, monkeypatch):
    service = Questionnaires(test_user["id"])
    service.save("q2", "My own answer.")
    asked = []
    monkeypatch.setattr(questionnaire_suggest, "suggest", lambda q, user_id, intel: asked.append(q["id"]) or (
        [{"kind": "journal", "date": "2025-03-12", "text": "I grew up mostly in a small town by a lake"}]))
    assert service.suggest_estimate("home")["questions"] == 1
    assert service.suggest_section("home", object()) == {"suggested": 1, "nothing": 0, "failed": 0}
    assert asked == ["q1"], "the owner's draft is left alone and not asked about"
    state = service.question("q1")
    assert state["status"] == "draft" and state["source"] == "suggested"
    assert service.question("q2")["answer"] == "My own answer."
    assert _reflections(test_user["id"]) == [], "suggesting sends nothing into IRIS"


def test_a_kept_suggestion_is_memory_and_a_rewritten_one_is_evidence(test_user, installed, monkeypatch):
    service = Questionnaires(test_user["id"])
    monkeypatch.setattr(questionnaire_suggest, "suggest", lambda q, user_id, intel: (
        [{"kind": "journal", "date": "2025-03-12", "text": "I grew up mostly in a small town by a lake"}]))
    service.suggest_section("home", object())
    edited = service.question("q1")["answer"] + "\n\nI still go back every summer."
    assert service.save("q1", edited)["source"] == "suggested", "the quotes are still there"
    service.add_section("home")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT evidence_eligible FROM reflections WHERE user_id = %s", (test_user["id"],))
        assert [row[0] for row in cur.fetchall()] == [False, False], "both kept suggestions are memory"
    assert service.save("q1", "In a town by a lake. I still go back every summer.")["source"] == "form"
    service.add_section("home")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT evidence_eligible FROM reflections WHERE user_id = %s", (test_user["id"],))
        assert sorted(row[0] for row in cur.fetchall()) == [False, True], "the rewritten one counts"


def test_the_suggestion_routes(client, installed, monkeypatch):
    monkeypatch.setattr(questionnaire_suggest, "suggest", lambda q, user_id, intel: [])
    assert client.get("/api/questionnaire/sections/home/suggest/estimate").json()["questions"] == 2
    assert client.post("/api/questionnaire/sections/home/suggest").json() == {
        "suggested": 0, "nothing": 2, "failed": 0}
