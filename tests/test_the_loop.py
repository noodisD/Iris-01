"""Two engines that need more than one theme, from their evidence to chat.

This replaces six end-to-end tests that built near-identical fixtures and then
mostly asserted that the system prompt was longer than 500 characters. A
coverage run with and without them showed what only they reached: the leverage
pair loop finding a pair, and a tension being recorded once two themes diverge.
Those are kept here, asserted on what the engines report and on whether chat
receives it. The discovery half of the loop is tests/test_system_health_invariant.py.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from agent.core import PersonalAICompanion
from agent.database import db
from agent.leverage import LeverageEngine
from agent.pipeline_orchestrator import admit
from agent.preferences import UserPreferencesService
from agent.resolution import ResolutionEngine
from agent.tension import TensionEngine


def _theme(user_id: int, summary: str, seed: float, at: datetime) -> int:
    return db.create_theme(user_id=user_id, centroid_embedding=[seed] * 1536, summary=summary,
                           first_seen_at=at.isoformat(), last_seen_at=at.isoformat())


def _entry(user_id: int, at: datetime, *theme_ids: int) -> None:
    entry_id = db.create_journal_entry(user_id, f"entry {at:%Y-%m-%d}", {},
                                       created_at=at.isoformat())
    for theme_id in theme_ids:
        db.add_theme_occurrence(theme_id, "journal_entry", entry_id, "a line", 0.9, at.isoformat())
        db.update_theme_stats(theme_id, at.isoformat())


def _system_prompt(user_id: int) -> str:
    companion = PersonalAICompanion(user_id=user_id)
    companion.intelligence.chat = MagicMock(return_value="ok")
    companion.chat("What have you noticed?")
    return companion.intelligence.chat.call_args[1]["system_prompt"]


def test_a_theme_that_precedes_another_is_leverage_and_chat_hears_it(test_user):
    user_id = test_user["id"]
    now = datetime.now()
    start = now - timedelta(days=50)
    driver = _theme(user_id, "Opening preparation", 0.1, start)
    target = _theme(user_id, "Endgame blunders", 0.2, start)
    # Driver on day 10i, target two days later: every target follows a driver
    # within the lag, and no driver follows a target within it.
    for i in range(6):
        _entry(user_id, start + timedelta(days=i * 10), driver)
        _entry(user_id, start + timedelta(days=i * 10 + 2), target)

    results = LeverageEngine(user_id).analyze_all_leverage()

    forward = [r for r in results if (r["source_id"], r["target_id"]) == (driver, target)]
    assert len(forward) == 1
    assert forward[0]["directional_lift"] > 0.5
    assert forward[0]["confidence_level"] in ("medium", "high")
    assert not [r for r in results if (r["source_id"], r["target_id"]) == (target, driver)]

    admitted = admit(user_id, UserPreferencesService(user_id=user_id).get_prefs()).findings
    assert any(f["engine_name"] == "leverage" for f in admitted)
    assert "Opening preparation" in _system_prompt(user_id)


def test_two_themes_become_a_tension_only_once_they_diverge(test_user):
    user_id = test_user["id"]
    now = datetime.now()
    past = now - timedelta(days=60)
    quiet = _theme(user_id, "Time trouble", 0.1, past)
    steady = _theme(user_id, "Tournament schedule", 0.9, past)

    # Six shared days: identical histories are a correlation, not a tension.
    for i in range(6):
        _entry(user_id, past + timedelta(days=i), quiet, steady)
    TensionEngine(user_id).analyze_all_tensions()
    assert db.get_all_tensions(user_id) == []

    # One goes quiet for five weeks and returns once; the other keeps going
    # and picks up. Now they move differently.
    for days_ago in (30, 29, 28, 25, 20, 15, 10):
        _entry(user_id, now - timedelta(days=days_ago), steady)
    _entry(user_id, now - timedelta(days=2), quiet, steady)
    for i in range(6):
        _entry(user_id, now - timedelta(days=1 + i), steady)

    TensionEngine(user_id).analyze_all_tensions()
    stored = db.get_all_tensions(user_id)
    assert len(stored) == 1
    assert {stored[0]["theme_a_id"], stored[0]["theme_b_id"]} == {quiet, steady}

    resolution = ResolutionEngine(user_id)
    assert resolution.analyze_theme(quiet, force_recompute=True)["resolution_label"] == "reappearing"
    assert resolution.analyze_theme(steady, force_recompute=True)["resolution_label"] in (
        "persisting", "stabilized")

    assert "Time trouble" in _system_prompt(user_id)
