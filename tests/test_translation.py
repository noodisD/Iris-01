"""A record in another language is read in English, with its original kept (ADR-0036).

Everything here is invented.
"""

from __future__ import annotations

import json
import re
from datetime import date

import pytest

from agent import sessions, translation
from agent.database import db

SESSION = """---
session: therapy
started: 2026-03-02T18:00
language: pl
owner: Ania
therapist: Trener
---

**[00:00:05] Ania:**
Znowu przegrałam partię w ostatniej minucie, bo grałam za szybko.

**[00:00:40] Trener:**
Co się działo, kiedy zegar zaczął się kończyć?

**[00:01:10] Ania:**
Czułam, że muszę odpowiedzieć od razu, więc nie sprawdziłam wieży.
"""

ENGLISH = {
    "Znowu przegrałam partię w ostatniej minucie, bo grałam za szybko.":
        "I lost the game in the last minute again, because I played too fast.",
    "Co się działo, kiedy zegar zaczął się kończyć?": "What was happening when the clock started running out?",
    "Czułam, że muszę odpowiedzieć od razu, więc nie sprawdziłam wieży.":
        "I felt I had to reply at once, so I did not check the rook.",
}


class Translator:
    """Answers each numbered turn from ENGLISH; `drop` leaves one out to look half-done."""

    def __init__(self, drop: int | None = None):
        self.drop, self.calls = drop, 0

    def chat(self, *, messages, system_prompt, **kwargs):
        self.calls += 1
        request = messages[0]["content"]
        if "JSON" not in system_prompt:
            return ENGLISH.get(request, "")
        turns = [{"n": int(n), "text": ENGLISH[text]}
                 for n, text in re.findall(r"^\[(\d+)\] [^:]+: (.*)$", request, re.M) if int(n) != self.drop]
        return json.dumps({"turns": turns})


def test_a_session_is_translated_turn_by_turn_with_its_speakers_and_times():
    english = translation.translate(SESSION, "session", Translator())
    session = sessions.read(english)
    assert session.language == "en"
    assert [(t.at, t.label, t.role) for t in session.turns] == [
        (5, "Ania", "owner"), (40, "Trener", "therapist"), (70, "Ania", "owner")]
    # Whose words they are is read from the English exactly as from the original.
    assert sessions.owner_turn(english, "I did not check the rook") is not None
    assert sessions.owner_turn(english, "the clock started running out") is None


def test_a_translation_missing_a_turn_is_not_kept():
    model = Translator(drop=1)
    with pytest.raises(translation.TranslationFailed):
        translation.translate(SESSION, "session", model)
    assert model.calls == 2  # asked once more before giving up


def test_english_writing_needs_no_translation():
    assert not translation.needed("I played the Sicilian again today.", "plain")
    assert translation.needed("Zagrałam dziś obronę sycylijską i źle liczyłam warianty.", "plain")
    assert translation.needed(SESSION, "session")


def test_a_translation_of_words_since_edited_is_not_used():
    made = translation.source_hash(SESSION)
    assert translation.for_reading(SESSION, "english", made) == "english"
    assert translation.for_reading(SESSION + " ", "english", made) == SESSION + " "


def _session_entry(test_user) -> int:
    return db.create_reflection(test_user["id"], SESSION, reflection_date=date(2026, 3, 2), source="session",
                                content_format="session")


def test_the_translation_is_kept_and_an_edit_throws_it_away(test_user):
    rid = _session_entry(test_user)
    english = translation.ensure(rid, SESSION, "session", model=Translator())
    assert sessions.read(english).language == "en"
    # Kept: asked again, it is not translated again.
    again = Translator()
    assert translation.ensure(rid, SESSION, "session", english, translation.source_hash(SESSION), again) == english
    assert again.calls == 0
    db.update_reflection(rid, content=SESSION.replace("wieży", "hetmana"))
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT translation, translation_hash FROM reflections WHERE id = %s", (rid,))
        assert cur.fetchone() == (None, None)


def test_a_failed_translation_leaves_the_record_in_its_own_words(test_user):
    rid = _session_entry(test_user)
    assert translation.ensure(rid, SESSION, "session", model=Translator(drop=0)) is None
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT translation FROM reflections WHERE id = %s", (rid,))
        assert cur.fetchone() == (None,)


def test_the_reader_checks_quotes_against_the_english_it_read(test_user):
    from agent.discovery import _source_rows

    rid = _session_entry(test_user)
    translation.ensure(rid, SESSION, "session", model=Translator())
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT discovery_revision FROM reflections WHERE id = %s", (rid,))
        revision = cur.fetchone()[0]
        source = _source_rows(cur, test_user["id"], {rid: revision})[rid]
        conn.rollback()
    assert "I did not check the rook" in source["content"]


def test_chat_and_the_journal_get_the_english_and_the_journal_keeps_the_original(test_user):
    from fastapi.testclient import TestClient

    from iris_api import app, get_current_user_id

    rid = db.create_reflection(test_user["id"], "Zagrałam dziś obronę sycylijską i źle liczyłam warianty.",
                               reflection_date=date(2026, 3, 3))
    original = "Zagrałam dziś obronę sycylijską i źle liczyłam warianty."
    english = "Today I played the Sicilian Defence and calculated the lines badly."
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("UPDATE reflections SET translation = %s, translation_hash = %s WHERE id = %s",
                    (english, translation.source_hash(original), rid))
        conn.commit()
    assert db.get_latest_reflections(test_user["id"], 1)[0]["content"] == english
    assert db.get_memory_item("reflection", rid)["text"] == english
    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    try:
        entry = TestClient(app).get("/api/journal").json()["entries"][0]
    finally:
        app.dependency_overrides.clear()
    assert entry["text"] == original
    assert entry["translation"] == {"text": english, "from": "pl", "session": None}


def test_ideas_quote_the_english_and_keep_the_original_for_staleness(test_user):
    from agent.ideas.service import IdeaService

    rid = _session_entry(test_user)
    english = translation.ensure(rid, SESSION, "session", model=Translator())
    entry = next(e for e in IdeaService(test_user["id"])._entries("all") if e["id"] == rid)
    assert entry["content"] == english
    assert entry["original"] == SESSION
