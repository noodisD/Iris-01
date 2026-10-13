"""Chat sees the baseline questionnaire: how much is answered, and the answers. Invented throughout."""

from __future__ import annotations

from agent import questionnaire_context, sessions
from agent.database import db


def _add(user_id: int, qid: str, question: str, answer: str) -> None:
    content = sessions.compose([sessions.Segment(0, "Asked", question), sessions.Segment(0, "Ann", answer)],
                               kind="questionnaire", started="2025-03-14T09:30", language="en",
                               owner="Ann", asker="Asked", question=qid)
    reflection_id = db.create_reflection(user_id, content, source="questionnaire", content_format="session")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO questionnaire_answers
                           (user_id, questionnaire, question_id, version, status, answer, source, reflection_id, added_at)
                       VALUES (%s, 'baseline', %s, 1, 'added', %s, 'form', %s, NOW())""",
                    (user_id, qid, answer, reflection_id))
        conn.commit()


def test_nothing_added_means_no_section(test_user):
    assert questionnaire_context.section(test_user["id"], "hello", None) == ""


def test_asking_about_the_questionnaire_shows_every_answer(test_user, monkeypatch):
    monkeypatch.setattr("agent.questionnaire.load", lambda *a: None)
    _add(test_user["id"], "q1", "Which colour was your first bicycle?", "A faded green one with a bent bell.")
    _add(test_user["id"], "q2", "Which vegetable did you plant first this spring?", "Broad beans, along the north fence.")
    text = questionnaire_context.section(test_user["id"], "Can you see my questionnaire?", None)
    assert "answered and added 2 questions" in text
    assert "Q: Which colour was your first bicycle?" in text and "Owner's answer: A faded green one with a bent bell." in text
    assert "Owner's answer: Broad beans, along the north fence." in text


def test_otherwise_only_the_most_related_answers(test_user, monkeypatch):
    monkeypatch.setattr("agent.questionnaire.load", lambda *a: None)
    monkeypatch.setattr(questionnaire_context, "RELATED", 1)
    from agent import pipeline
    _add(test_user["id"], "q1", "Which colour was your first bicycle?", "A faded green one with a bent bell.")
    _add(test_user["id"], "q2", "Which vegetable did you plant first this spring?", "Broad beans, along the north fence.")
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM reflections WHERE user_id = %s", (test_user["id"],))
        for (rid,) in cur.fetchall():
            pipeline.run_processing_pipeline("reflection", rid)
    text = questionnaire_context.section(test_user["id"], "broad beans",
                                         pipeline.generate_embedding("Broad beans, along the north fence."))
    assert "most related to this message" in text
    assert text.count("Owner's answer:") == 1
