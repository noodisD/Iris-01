"""A session waits for the owner, then becomes a dated entry recalled by turn (ADR-0028).

Every line of every transcript below is invented.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from agent import pipeline
from agent.database import db
from agent.session_imports import SessionImportError, SessionImports
from iris_api import app, get_current_user_id

TRANSCRIPT = """# Notes
**[00:00:05] Ann:**
I kept postponing the call to my landlord because I expected an argument about the heating.

**[00:00:21] Counsellor:**
What happened when you finally called him about it?

**[00:00:30] Ann:**
He agreed to fix the heating straight away, and I felt silly for waiting so long.

**[00:00:52] Speaker unsure:**
Yes, that is how it went.
"""


@pytest.fixture
def client(test_user):
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


def _ready(user_id: int) -> tuple[SessionImports, str]:
    imports = SessionImports(user_id)
    staged = imports.stage(TRANSCRIPT, "session.md")
    imports.update(int(staged["id"]), {"startedAt": "2026-09-30T18:00"})
    return imports, staged["id"]


def test_a_staged_session_shows_its_speakers_and_cost_and_is_sent_nowhere(test_user, mocker):
    sent = mocker.patch("agent.pipeline.generate_embedding")
    staged = SessionImports(test_user["id"]).stage(TRANSCRIPT, "session.md")
    assert staged["status"] == "staged"
    assert (staged["owner"], staged["therapist"]) == ("Ann", "Counsellor")
    assert {s["label"]: s["role"] for s in staged["speakers"]} == {
        "Ann": "owner", "Counsellor": "therapist", "Speaker unsure": "unclear"}
    assert staged["missing"] == ["the day and time of the session"]
    assert staged["leftOut"] == 1 and staged["turns"] == 4
    assert staged["estimate"]["readingDollars"] is not None
    assert "OpenAI" in staged["estimate"]["text"]
    assert not sent.called
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM reflections WHERE user_id = %s;", (test_user["id"],))
        assert cur.fetchone()[0] == 0


def test_a_file_without_a_conversation_is_refused(test_user):
    with pytest.raises(SessionImportError):
        SessionImports(test_user["id"]).stage("Just a note with no speakers.", "note.md")


def test_importing_waits_for_the_day_and_for_the_owner_to_be_named(test_user):
    imports = SessionImports(test_user["id"])
    staged = imports.stage(TRANSCRIPT, "session.md")
    with pytest.raises(SessionImportError, match="day and time"):
        imports.commit(int(staged["id"]))
    imports.update(int(staged["id"]), {"startedAt": "2026-09-30T18:00", "owner": None})
    with pytest.raises(SessionImportError, match="which speaker is you"):
        imports.commit(int(staged["id"]))
    with pytest.raises(SessionImportError):
        imports.update(int(staged["id"]), {"owner": "Someone not in it"})
    with pytest.raises(SessionImportError):
        imports.update(int(staged["id"]), {"owner": "Counsellor", "therapist": "Counsellor"})


def test_the_click_makes_a_dated_session_entry_once(test_user):
    imports, import_id = _ready(test_user["id"])
    done = imports.commit(int(import_id))
    assert done["status"] == "imported" and done["reflectionId"]
    entry = db.get_reflection(int(done["reflectionId"]))
    assert entry["content_format"] == "session"
    assert entry["reflection_date"] == date(2026, 9, 30)
    assert "owner: Ann" in entry["content"] and "started: 2026-09-30T18:00" in entry["content"]
    with pytest.raises(SessionImportError):
        imports.commit(int(import_id))
    again = imports.stage(TRANSCRIPT, "copy.md")
    assert again["alreadyImported"] is not None
    imports.update(int(again["id"]), {"startedAt": "2026-10-07T18:00"})
    with pytest.raises(SessionImportError, match="already in your journal"):
        imports.commit(int(again["id"]))


def test_a_session_is_recalled_by_passage_with_its_speakers_and_leaves_no_trace(test_user):
    imports, import_id = _ready(test_user["id"])
    reflection_id = int(imports.commit(int(import_id))["reflectionId"])
    pipeline.run_processing_pipeline("reflection", reflection_id)

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, text FROM session_passages WHERE reflection_id = %s ORDER BY position;",
                    (reflection_id,))
        passages = cur.fetchall()
        cur.execute("SELECT count(*) FROM embeddings WHERE source_type = 'reflection' AND source_id = %s;",
                    (reflection_id,))
        whole = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM theme_occurrences WHERE source_id = %s;", (reflection_id,))
        occurrences = cur.fetchone()[0]
        cur.execute("SELECT processing_status FROM reflections WHERE id = %s;", (reflection_id,))
        status = cur.fetchone()[0]
    assert passages and whole == 0 and occurrences == 0 and status == "complete"
    item = db.get_memory_item("session_passage", passages[0][0])
    assert item["kind"] == "therapy session" and item["date"] == date(2026, 9, 30)
    assert "Ann (owner):" in item["text"] and "Counsellor (therapist):" in item["text"]
    found = db.search_similar_embeddings(test_user["id"], [0.1] * 1536, n_results=50)
    assert {r["source_id"] for r in found if r["source_type"] == "session_passage"} == {p[0] for p in passages}

    imports.undo(int(import_id))
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM embeddings WHERE source_type = 'session_passage' AND source_id = ANY(%s);",
                    ([p[0] for p in passages],))
        assert cur.fetchone()[0] == 0
    assert db.get_reflection(reflection_id) is None
    assert imports.get(int(import_id))["status"] == "staged"


def test_chat_names_a_session_and_recalls_turns_with_their_speakers(test_user, mocker):
    from agent.core import PersonalAICompanion

    imports, import_id = _ready(test_user["id"])
    reflection_id = int(imports.commit(int(import_id))["reflectionId"])
    pipeline.run_processing_pipeline("reflection", reflection_id)
    companion = PersonalAICompanion(user_id=test_user["id"])

    recent = companion._get_reflections_context()
    assert "A therapy session, recorded 2026-09-30 at 18:00" in recent
    assert "postponing the call" not in recent, "the transcript is not pasted into recent entries"

    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM session_passages WHERE reflection_id = %s;", (reflection_id,))
        passage = cur.fetchone()[0]
    mocker.patch("agent.core.generate_embedding", return_value=[0.1] * 1536)
    mocker.patch.object(db, "search_similar_embeddings", return_value=[
        {"source_type": "session_passage", "source_id": passage, "distance": 0.05}])
    memories = companion._get_relevant_context("the landlord")
    assert "[therapy session, 2026-09-30]" in memories
    assert "Counsellor (therapist): What happened" in memories
    assert "never attribute those to the owner" in memories


def test_the_journal_shows_each_turn_with_its_speaker(client, test_user):
    imports, import_id = _ready(test_user["id"])
    imports.commit(int(import_id))
    entries = client.get("/api/journal").json()["entries"]
    session = entries[0]["session"]
    assert entries[0]["format"] == "session"
    assert session["startedAt"] == "2026-09-30T18:00" and session["owner"] == "Ann"
    assert [(t["label"], t["role"]) for t in session["turns"]] == [
        ("Ann", "owner"), ("Counsellor", "therapist"), ("Ann", "owner"), ("Speaker unsure", "unclear")]


def test_the_import_screen_flow_over_http(client):
    staged = client.post("/api/sessions/imports",
                         files={"file": ("session.md", TRANSCRIPT.encode(), "text/markdown")})
    assert staged.status_code == 200, staged.text
    import_id = staged.json()["id"]
    assert client.patch(f"/api/sessions/imports/{import_id}", json={"startedAt": "30/09/2026"}).status_code == 400
    assert client.patch(f"/api/sessions/imports/{import_id}", json={"startedAt": "2026-09-30T18:00"}).json()["missing"] == []
    listed = client.get("/api/sessions/imports").json()["imports"]
    assert [row["id"] for row in listed] == [import_id]
    committed = client.post(f"/api/sessions/imports/{import_id}/commit")
    assert committed.status_code == 200 and committed.json()["status"] == "imported"
    assert client.delete(f"/api/sessions/imports/{import_id}").status_code == 400, "undo first"
    assert client.post(f"/api/sessions/imports/{import_id}/undo").json()["status"] == "staged"
    assert client.delete(f"/api/sessions/imports/{import_id}").json()["status"] == "discarded"
    assert client.get("/api/sessions/imports/999999").status_code == 404
    assert client.post("/api/sessions/imports",
                       files={"file": ("x.md", b"\xff\xfe\x00", "text/markdown")}).status_code == 400


def test_a_session_is_not_counted_as_writing_in_the_weekly_letter(test_user, mock_llm, mocker):
    from agent import review_letter
    from iris_api import _review_letter

    imports, import_id = _ready(test_user["id"])
    reflection_id = int(imports.commit(int(import_id))["reflectionId"])
    seen = {}

    def compose(facts, findings, entries, intelligence, formats):
        seen.update(facts=facts, entries=entries, formats=formats)
        return " ".join(facts), False

    mocker.patch.object(review_letter, "compose_letter", side_effect=compose)
    _review_letter(test_user["id"], [db.get_reflection(reflection_id)], {date(2026, 9, 30)},
                   None, None, 0, 0, with_findings=False)
    assert seen["facts"] == ["Nothing was written this week.", "You had 1 therapy session."]
    assert "What happened when you finally called him" not in seen["entries"][0], \
        "a letter's quotes are checked against the owner's words only"
    assert "I kept postponing the call" in seen["entries"][0] and seen["formats"] == ["plain"]


def test_reading_a_session_stores_only_accounts_in_the_owners_turns(test_user, monkeypatch):
    import json

    from agent import discovery_worker
    from agent.connections import FIELD_PROMPT
    from agent.episodes import SYSTEM_PROMPT as EXTRACTION_PROMPT

    imports, import_id = _ready(test_user["id"])
    reflection_id = int(imports.commit(int(import_id))["reflectionId"])
    shown = []

    class Reader:
        def chat(self, *, messages, system_prompt, **_):
            if system_prompt == EXTRACTION_PROMPT:
                shown.append(messages[0]["content"])
                def quote(text):
                    return [{"entryId": reflection_id, "sourceType": "reflection", "text": text}]
                return json.dumps({"episodes": [
                    {"actor": "self", "recordKind": "event",
                     "situation": "I expected an argument about the heating",
                     "response": "I kept postponing the call to my landlord",
                     "quotes": quote("I kept postponing the call to my landlord because I expected "
                                     "an argument about the heating")},
                    {"actor": "self", "recordKind": "self_report",
                     "selfReport": "What happened when you finally called him about it",
                     "quotes": quote("What happened when you finally called him about it")},
                ]})
            assert system_prompt == FIELD_PROMPT
            return json.dumps({"fields": [
                {"field": field, "verdict": "supported",
                 "refs": [{"accountId": "account", "field": field, "citationIndex": 0}]}
                for field in ("situation", "response")]})

    monkeypatch.setattr(discovery_worker, "Intelligence", lambda **_: Reader())
    discovery_worker.process_reflection(reflection_id)

    assert "Ann (owner):" in shown[0] and "Counsellor (therapist):" in shown[0]
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT data FROM discovery_accounts WHERE reflection_id = %s AND is_current;",
                    (reflection_id,))
        stored = [row[0] for row in cur.fetchall()]
    assert [account["citations"][0]["text"] for account in stored] == [
        "I kept postponing the call to my landlord because I expected an argument about the heating."]
