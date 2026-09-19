"""The proto-theme threshold, end to end.

Four near-identical entries are an incident; five are a theme. This checks the
boundary through the whole path — write, queue, embed, discover, admit, render —
rather than at one function.

Each case uses the managed `test_user` fixture. This file used to create its
own users outside it, which is how rows outlived the run — the reason
conftest keeps a marker table and truncates.
"""

import uuid
from datetime import date, timedelta

from agent.core import PersonalAICompanion
from agent.persistence import PersistenceEngine
from agent.trackers.reflections import ReflectionService
from agent.work_queue import drain

HEADER = "# Observed Structural Patterns"


def _surfaced_after_writing(user_id: int, copies: int) -> list[str]:
    text = f"A specific repetitive thought: {uuid.uuid4().hex}"
    service = ReflectionService(user_id)
    # On separate days: a present-tense finding needs the owner to have been
    # observed on several (agent/coverage.py); entries typed in one sitting are
    # several data points and one observation.
    for offset in range(copies):
        service.create_reflection(text, energy_level=8,
                                  reflection_date=date.today() - timedelta(days=offset * 3))
    drain()
    PersistenceEngine(user_id).discover_themes()

    context = PersonalAICompanion(user_id)._get_aggregated_context("check")
    if HEADER not in context:
        return []
    return [line for line in context.split(HEADER)[1].split("\n") if line.strip().startswith("- ")]


def test_four_similar_entries_are_not_yet_a_theme(test_user):
    assert _surfaced_after_writing(test_user["id"], 4) == []


def test_five_are(test_user):
    assert len(_surfaced_after_writing(test_user["id"], 5)) == 1
