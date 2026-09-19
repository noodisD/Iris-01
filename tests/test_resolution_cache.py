"""The stored resolution is what IRIS says until something recomputes it.

Three files used to test this, two of them reproductions of one stress test
that no longer exists. What they established, kept once each: a stored label
is served, a newer stored label replaces it, a recompute ignores it, and the
stored label is the one chat receives.
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from agent.core import PersonalAICompanion
from agent.database import db
from agent.resolution import ResolutionEngine


def _faded_theme(user_id: int, summary: str = "Test Theme") -> int:
    """A theme seen 30–50 days ago and not since: resolution calls it dissipated."""
    now = datetime.now()
    theme_id = db.create_theme(user_id, [0.1] * 1536, summary,
                               (now - timedelta(days=60)).isoformat(), now.isoformat())
    for i in range(5):
        at = now - timedelta(days=30 + i * 5)
        entry_id = db.create_journal_entry(user_id, f"Entry {i}", {}, created_at=at.isoformat())
        db.add_theme_occurrence(theme_id, "journal_entry", entry_id, "snippet", 0.95, at.isoformat())
        db.update_theme_stats(theme_id, at.isoformat())
    return theme_id


def _store(theme_id: int, label: str, confidence_level: str) -> None:
    db.create_or_update_resolution("theme", theme_id, resolution_label=label,
                                   attenuation_score=0.0, confidence_level=confidence_level,
                                   recent_count=0, past_count=5)


def test_the_stored_label_is_served_until_recomputed(test_user):
    user_id = test_user["id"]
    theme_id = _faded_theme(user_id)
    assert ResolutionEngine(user_id).analyze_theme(theme_id, force_recompute=True)[
        "resolution_label"] == "dissipated"

    _store(theme_id, "persisting", "low")
    assert ResolutionEngine(user_id).analyze_theme(theme_id)["resolution_label"] == "persisting"

    _store(theme_id, "reappearing", "high")
    cached = ResolutionEngine(user_id).analyze_theme(theme_id)
    assert (cached["resolution_label"], cached["confidence_level"]) == ("reappearing", "high")

    recomputed = ResolutionEngine(user_id).analyze_theme(theme_id, force_recompute=True)
    assert recomputed["resolution_label"] == "dissipated"


def test_chat_says_what_the_stored_label_says(test_user, journalled_recently):
    # A present-tense finding needs the owner observed recently (agent/coverage.py).
    journalled_recently()
    user_id = test_user["id"]
    theme_id = _faded_theme(user_id, "Rook endings")
    natural = ResolutionEngine(user_id).analyze_theme(theme_id, force_recompute=True)
    db.create_or_update_resolution("theme", theme_id, "dissipated", 1.0, "high",
                                 natural["recent_count"], natural["past_count"])
    db.create_or_update_confidence("resolution", theme_id, "high", 0.9,
                                natural["past_count"], 100, 1.0, 0.5)

    companion = PersonalAICompanion(user_id=user_id)
    companion.intelligence.chat = MagicMock(return_value="OK")
    companion.chat("Test message")
    prompt = companion.intelligence.chat.call_args[1]["system_prompt"]

    assert "Rook endings" in prompt
    assert "has gone quiet" in prompt
    assert "has continued" not in prompt
