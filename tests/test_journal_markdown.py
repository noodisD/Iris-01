"""Markdown stays stored, and is plain only where a model or an embedding reads it.

Every sentence below is invented.
"""

from __future__ import annotations

import json

from agent.observations import ObservationEngine, verify_citations
from agent.trackers.reflections import ReflectionService

SOUP = "The **basil** went into the soup."
PLAIN_QUOTE = "The basil went into the soup."


def test_a_quote_without_markers_verifies_as_the_original_span():
    entry = {
        "id": 1,
        "content": SOUP,
        "content_format": "markdown",
        "source_type": "reflection",
        "date": None,
    }
    found = verify_citations(
        [{"entryId": 1, "text": PLAIN_QUOTE}],
        {("reflection", 1): entry},
    )
    assert found is not None
    assert found[0].text == "The **basil** went into the soup"


def test_an_invented_word_still_fails():
    entry = {
        "id": 1,
        "content": SOUP,
        "content_format": "markdown",
        "source_type": "reflection",
        "date": None,
    }
    assert verify_citations(
        [{"entryId": 1, "text": "The saffron went into the soup."}],
        {("reflection", 1): entry},
    ) is None


def test_a_model_is_shown_the_words_without_markers():
    rendered = ObservationEngine._render([{
        "id": 4,
        "date": None,
        "content": SOUP,
        "content_format": "markdown",
        "source_type": "reflection",
    }])
    assert "**" not in rendered
    assert "basil" in rendered


def test_markdown_is_embedded_as_plain_text_and_stored_intact(test_user, monkeypatch):
    from agent import pipeline
    from agent.database import db

    seen: list[str] = []
    real = pipeline.generate_embedding
    monkeypatch.setattr(
        pipeline, "generate_embedding",
        lambda text, model=None: seen.append(text) or real(text, model=model),
    )
    rid = ReflectionService(test_user["id"]).create_reflection(
        content="# Soup\n\n" + SOUP,
        content_format="markdown",
    )
    pipeline.run_processing_pipeline("reflection", rid)

    assert seen
    assert "**" not in seen[-1]
    assert "#" not in seen[-1].split("Content: ", 1)[-1]
    assert "basil" in seen[-1]
    assert "Soup" in seen[-1]
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT content, content_format FROM reflections WHERE id = %s;", (rid,))
        stored, fmt = cur.fetchone()
    assert stored == "# Soup\n\n" + SOUP
    assert fmt == "markdown"


def test_episode_reader_is_shown_plain_text_and_cites_the_original():
    from datetime import date

    from agent.episodes import EpisodeReader

    class Reader:
        def __init__(self):
            self.prompts: list[str] = []

        def chat(self, messages, system_prompt, **kwargs):
            self.prompts.append(messages[0]["content"])
            return json.dumps({"episodes": [{
                "actor": "self",
                "modality": "happened",
                "situation": "a pot was on the stove",
                "response": "added the herbs",
                "quotes": [{"entryId": 9, "sourceType": "reflection", "text": PLAIN_QUOTE}],
            }]})

    reader = Reader()
    episodes = EpisodeReader(1, intelligence=reader).read([{
        "id": 9,
        "date": date(2026, 1, 2),
        "content": SOUP,
        "content_format": "markdown",
        "source_type": "reflection",
    }])
    assert reader.prompts
    assert "**" not in reader.prompts[0]
    assert "basil" in reader.prompts[0]
    assert episodes
    assert episodes[0].citations[0].text == "The **basil** went into the soup"
