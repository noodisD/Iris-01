"""What the chat model is told, and whether the prompt describes it truthfully.

Three things went wrong here quietly. The prompt described a "Long-Term Trends"
block that nothing produced. "Recent entries" were ordered by id, which since
importing is import order, so the chat saw the last batch committed rather than
the last thing written. And memories reached the model as the text that had been
embedded — a header with placeholder scores and no date — while entries spanning
years were given without telling the model what today is.
"""

from __future__ import annotations

import re
from datetime import date, datetime

import pytest

from agent.core import PersonalAICompanion
from agent.database import db
from agent.trackers.reflections import ReflectionService
from prompts.system_prompt import SYSTEM_PROMPT


@pytest.fixture
def companion(test_user):
    return PersonalAICompanion(user_id=test_user["id"])


def _context(companion, mocker, memories="No specific long-term memories found."):
    mocker.patch.object(PersonalAICompanion, "_get_relevant_context", return_value=memories)
    return companion._get_aggregated_context("How have I been?")


def _recent_block(context: str) -> str:
    return context.split("# Recent Journal Entries")[1].split("# Current Habits")[0]


def test_the_context_opens_with_today(companion, mocker):
    ctx = _context(companion, mocker)
    first = ctx.splitlines()[0]
    assert first.startswith("# Today: ")
    assert datetime.now().astimezone().date().isoformat() in first


def test_every_block_the_chat_sends_is_described_in_the_prompt(companion, mocker):
    ctx = _context(companion, mocker)
    headers = [re.sub(r"\s*(\(.*\))?:.*$", "", line[2:]).strip()
               for line in ctx.splitlines() if line.startswith("# ")]
    assert len(headers) == 6, headers
    for header in headers:
        assert f"# {header}" in SYSTEM_PROMPT, f"the prompt does not describe the {header!r} block"


def test_recent_entries_are_the_latest_written_not_the_latest_imported(companion, mocker, test_user):
    service = ReflectionService(test_user["id"])
    for day in range(1, 6):
        service.create_reflection(content=f"January note {day}", reflection_date=date(2026, 1, day))
    service.create_reflection(content="An old entry imported last", reflection_date=date(2023, 3, 1))

    block = _recent_block(_context(companion, mocker))
    assert "An old entry imported last" not in block
    assert block.index("2026-01-05") < block.index("2026-01-01"), "newest first"


def test_only_recorded_fields_are_shown(companion, mocker, test_user):
    ReflectionService(test_user["id"]).create_reflection(
        content="No scores on this one", reflection_date=date(2025, 5, 5))
    block = _recent_block(_context(companion, mocker))
    assert "No scores on this one" in block
    for placeholder in ("N/A", "None", "?/10", "mood"):
        assert placeholder not in block


def test_a_list_inside_an_entry_cannot_pass_for_another_entry(companion, mocker, test_user):
    """Obsidian notes carry task lists. With only the first line indented,
    "- [ ] call the bank" sat at the same level as an entry's own bullet."""
    ReflectionService(test_user["id"]).create_reflection(
        content="Plan for the week:\n- [ ] call the bank\n- [ ] gym twice", reflection_date=date(2025, 6, 1))
    block = _recent_block(_context(companion, mocker))
    assert [line for line in block.splitlines() if line.startswith("- ")] == ["- [2025-06-01]"]
    assert "  - [ ] call the bank" in block


def test_a_memory_says_what_it_is_and_when_in_the_owners_words(companion, mocker, test_user):
    service = ReflectionService(test_user["id"])
    old = service.create_reflection(content="Slept badly before the exam", reflection_date=date(2024, 2, 3))
    for day in range(1, 6):
        service.create_reflection(content=f"Recent note {day}", reflection_date=date(2026, 1, day))
    newest = db.get_latest_reflections(test_user["id"], 5)[0]["id"]

    mocker.patch("agent.core.generate_embedding", return_value=[0.1] * 1536)
    mocker.patch.object(db, "search_similar_embeddings", return_value=[
        {"source_type": "reflection", "source_id": newest, "distance": 0.05},
        {"source_type": "reflection", "source_id": old, "distance": 0.10},
    ])
    memories = companion._get_relevant_context("sleep")

    assert "[journal, 2024-02-03] Slept badly before the exam" in memories
    assert "Anchor:" not in memories and "?/10" not in memories
    assert "Recent note" not in memories, "an entry already shown as recent is not repeated"
