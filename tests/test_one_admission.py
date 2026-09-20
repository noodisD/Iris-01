"""Chat and the Insights screen give one answer to "what has IRIS noticed?".

They used to give two. Each surface called the engines itself, at different
grains, and admitted what came back through its own copy of the gates in its
own order. Chat registered leverage and then labelled its rows so the
confidence gate discarded every one at the default setting; the ranker cut to
five before the owner's own budget; a finding about two years won the ties it
was documented to lose. None of it was about the owner's life — it was
plumbing, and it made the two surfaces disagree about their life anyway.

Now there is one collection and one admission (agent/pipeline_orchestrator.py).
These tests hold both surfaces to it. The findings are written here, so what
should be admitted is not a matter of opinion (ADR-0009).
"""

from __future__ import annotations

import pytest

from agent.core import PersonalAICompanion
from agent.insights_service import InsightsService
from agent.preferences import UserPreferencesService


def _finding(engine, key, summary, confidence="medium", label="increasing", theme_id=None,
             **extra):
    theme_id = theme_id if theme_id is not None else int(key.split("-")[0])
    return {
        "engine_name": engine, "pattern_type": "theme", "pattern_id": theme_id,
        "pattern_key": key, "theme_id": theme_id,
        "summary": summary, "theme_summary": summary,
        f"{engine}_label": label, "label": label,
        "recent_count": 3, "past_count": 1, "confidence_level": confidence, **extra,
    }


@pytest.fixture
def world(test_user, journalled_recently, monkeypatch):
    """Both surfaces read the same findings through the one collection seam."""
    journalled_recently()  # recent writing, so present-tense findings may speak

    def install(findings):
        def collect(user_id, unavailable=None):
            return [dict(f) for f in findings]
        monkeypatch.setattr("agent.pipeline_orchestrator.collect_findings", collect)
        monkeypatch.setattr("agent.insights_service.collect_findings", collect)

    return install


def _chat_block(user_id):
    ctx = PersonalAICompanion(user_id)._get_aggregated_context("what have you noticed?")
    return ctx.split("Observed Temporal Sequences:")[1]


def _screen(user_id):
    return {s["summary"].split('"')[1] for s in InsightsService(user_id).list_summaries()}


# --- one answer ---------------------------------------------------------------------

def test_chat_says_nothing_the_screen_would_not_show(test_user, world):
    world([
        _finding("trajectory", "1", "alpha rising"),
        _finding("resolution", "2", "beta steady", confidence="high", label="persisting"),
        _finding("trajectory", "5", "epsilon faint", confidence="low"),
    ])

    chat, screen = _chat_block(test_user["id"]), _screen(test_user["id"])

    for summary in ("alpha rising", "beta steady"):
        assert summary in chat and summary in screen
    assert "epsilon faint" not in chat and "epsilon faint" not in screen, (
        "below the owner's floor on both surfaces, not just one")


def test_leverage_reaches_a_conversation_at_the_default_setting(test_user, world, monkeypatch):
    """Chat read a per-source average with no confidence field; the orchestrator
    filled in 'unknown', the gate scored it 0, and at the default 'medium' floor
    every leverage finding was thrown away. The pair rows carry their own."""
    from agent import leverage

    monkeypatch.undo()  # this one goes through the real collection
    monkeypatch.setattr(
        leverage.LeverageEngine, "analyze_all_leverage",
        lambda self: [{"source_id": 3, "target_id": 4, "influence_score": 0.4,
                       "directional_lift": 1.5, "cooccurrence_count": 6,
                       "confidence_level": "medium", "summary": "gamma before delta",
                       "source_summary": "gamma before delta", "target_summary": "delta"}])

    assert "gamma before delta" in _chat_block(test_user["id"])


def test_the_owners_budget_is_the_only_cut(test_user, world):
    """Settings offers up to 10; the ranker stopped at 5 before the budget."""
    world([_finding("trajectory", str(i), f"theme number {i} rising") for i in range(1, 11)])
    UserPreferencesService(test_user["id"]).update_pref("max_items", 10)

    bullets = [line for line in _chat_block(test_user["id"]).splitlines()
               if line.startswith("- ")]
    assert len(bullets) == 10


def test_on_one_theme_chat_keeps_the_fortnight_and_the_screen_shows_both(test_user, world):
    """A prompt has room for one finding per theme, and the two-year view is the
    wider context rather than the news — so chat keeps the fortnight. The screen
    is a list the owner scrolls, and shows both."""
    world([
        _finding("trajectory", "1", "alpha rising"),
        _finding("lifelong", "1", "alpha across the record", label="spread",
                 claims_present=False, occurrence_count=9, first_seen_at="2024-06-01",
                 span_days=600, densest_year=2025, densest_count=4, share_in_densest=0.44,
                 active_months=7, days_since_last=40),
    ])

    chat, screen = _chat_block(test_user["id"]), _screen(test_user["id"])

    assert "alpha rising" in chat and "alpha across the record" not in chat
    assert {"alpha rising", "alpha across the record"} <= screen


def test_a_pair_is_its_own_finding(test_user, world):
    """A tension between themes 1 and 2 used to be grouped with every finding
    about theme 1, so in a prompt it could displace one — or be displaced."""
    world([
        _finding("trajectory", "1", "alpha rising"),
        _finding("tension", "1-2", "alpha against beta", label="persistent"),
    ])

    chat = _chat_block(test_user["id"])
    assert "alpha rising" in chat and "alpha against beta" in chat


# --- a theme can still be explained -------------------------------------------------

def test_a_theme_is_explainable_without_recent_writing(test_user):
    """The explanation reads a stored confidence record, and the only writer was
    the persistence finding — run on chat turns, and only for themes with three
    occurrences in the last thirty days. Retiring that finding would have removed
    the writer; on this archive it had already stopped writing, because nothing
    had been written for a month, and every theme explained as "No analytical
    record found." It is computed on request now."""
    from datetime import UTC, datetime, timedelta

    from agent.database import db
    from agent.explanation import ExplanationEngine

    theme_id = db.create_theme(test_user["id"], [0.1] * 1536, "an old theme",
                               datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat())
    for i in range(8):
        when = (datetime.now(UTC) - timedelta(days=400 - i * 30)).isoformat()
        db.add_theme_occurrence(theme_id, "reflection", 1000 + i, f"entry {i}", 0.8, when)
    db.update_theme_stats(theme_id)

    explanation = ExplanationEngine(test_user["id"]).explain("theme", theme_id)

    assert explanation["summary"] != "No analytical record found."


def test_a_broken_engine_is_not_reported_as_a_thin_history(test_user, journalled_recently,
                                                           monkeypatch):
    """An engine that throws was logged and skipped, and the empty result became
    "there is not enough logged history" — the software's failure described as
    the owner's not having written enough."""
    journalled_recently()
    monkeypatch.setattr("agent.trajectory.TrajectoryEngine.analyze_all_themes",
                        lambda self: (_ for _ in ()).throw(RuntimeError("engine down")))

    from agent.core import PersonalAICompanion
    from agent.pipeline_orchestrator import admit

    admission = admit(test_user["id"])
    assert "trajectory" in admission.unavailable

    context = PersonalAICompanion(test_user["id"])._get_aggregated_context("what have you noticed?")
    assert "not enough logged history" not in context
    assert "unavailable" in context


def test_a_gate_that_fails_withholds_rather_than_passes_everything(test_user, world, monkeypatch):
    """A gate exists to hold findings back, so a gate that throws was passing
    whatever it had been given. Coverage has its own fail-closed wrapper; the
    shared mechanism now fails closed too."""
    world([_finding("trajectory", "9", "alpha rising", confidence="high")])
    monkeypatch.setattr("agent.pipeline_orchestrator.confidence_gate",
                        lambda findings, context: (_ for _ in ()).throw(RuntimeError("gate down")))

    from agent.pipeline_orchestrator import admit

    assert admit(test_user["id"]).findings == []
