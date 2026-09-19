"""Which engines the owner may switch off, and what the space is measured over.

Two findings from the second engineering review, both silent.

`ENGINE_PRIORITY` is an *ordering* — conflict suppression and ranking turn it
into a tie-break index. Settings reused it as the list of engines the owner may
enable, so "observations" was never a valid value. The moment they customised
their engines at all, `apply_preferences` dropped every observation, and nothing
in Settings could put it back.

And the comparison space was measured over embeddings that matching itself
excludes. Copied setup text and placeholders shaped the mean every entry is
compared against, and counted toward the threshold that decides whether the
style-removed space is used at all.

Every entry below is invented.
"""

from __future__ import annotations

from datetime import date, timedelta

from agent.constants import ENGINE_PRIORITY, SELECTABLE_ENGINES
from agent.database import db
from agent.observations import ENGINE_NAME, Citation, Observation, apply_preferences
from agent.preferences import UserPreferencesService
from agent.trackers.reflections import ReflectionService


def _observation(level="high"):
    return Observation(
        claim="The boldest moves appeared alongside the strongest certainty",
        citations=(
            Citation(entry_id=1, entry_date=date(2026, 1, 1), text="went all in"),
            Citation(entry_id=2, entry_date=date(2026, 2, 1), text="doubled down again"),
        ),
        span_start=date(2026, 1, 1), span_end=date(2026, 2, 1),
        entries_read=2, confidence_level=level)


# --- the owner can keep observations on -----------------------------------------

def test_observations_is_a_thing_the_owner_may_choose(test_user):
    assert ENGINE_NAME in SELECTABLE_ENGINES


def test_selecting_observations_is_a_valid_setting(test_user):
    """It was rejected as an invalid engine name, so the owner could not ask for
    the one surface that reads their writing."""
    prefs = UserPreferencesService(test_user["id"])
    prefs.update_pref("enabled_engines", ["trajectory", ENGINE_NAME])
    assert ENGINE_NAME in prefs.get_prefs()["enabled_engines"]


def test_customising_engines_does_not_silently_drop_every_observation(test_user):
    prefs = UserPreferencesService(test_user["id"])
    prefs.update_pref("enabled_engines", ["trajectory", ENGINE_NAME])
    prefs.update_pref("min_confidence", "low")

    kept = apply_preferences([_observation()], test_user["id"])
    assert len(kept) == 1, "the owner asked for observations and got none"


def test_switching_observations_off_still_works(test_user):
    prefs = UserPreferencesService(test_user["id"])
    prefs.update_pref("enabled_engines", ["trajectory"])
    prefs.update_pref("min_confidence", "low")

    assert apply_preferences([_observation()], test_user["id"]) == []


def test_the_ordering_is_not_the_allow_list(test_user):
    """Observations are reviewed and confirmed, never ranked against other
    findings, so they take no part in conflict suppression or prioritisation."""
    assert ENGINE_NAME not in ENGINE_PRIORITY
    assert set(ENGINE_PRIORITY) < SELECTABLE_ENGINES


# --- the space is measured over evidence ----------------------------------------

def test_memory_only_entries_do_not_shape_the_comparison_space(test_user, process_queue):
    """They are excluded from matching and from occurrences. Letting them shape
    the space everything is matched *in* is the same mistake one layer down."""
    service = ReflectionService(test_user["id"])
    for i in range(3):
        service.create_reflection(content=f"A real entry about the {i}th day of the week.",
                                  reflection_date=date.today() - timedelta(days=i + 1))
    process_queue()
    eligible_count, _ = db.get_evidence_style(test_user["id"])

    service.create_reflection(content="Copied setup text that appears twice over.",
                              reflection_date=date.today(), evidence_eligible=False)
    process_queue()
    after_count, _ = db.get_evidence_style(test_user["id"])

    assert after_count == eligible_count, (
        "a memory-only entry was counted into the style mean")


def test_the_count_that_picks_the_regime_counts_evidence_only(test_user, process_queue):
    """The count decides whether the style-removed space is used at all, so a
    placeholder must not be able to push a user across that threshold."""
    service = ReflectionService(test_user["id"])
    service.create_reflection(content="One real entry, written down deliberately.",
                              reflection_date=date.today() - timedelta(days=1))
    for i in range(5):
        service.create_reflection(content=f"placeholder {i}", reflection_date=date.today(),
                                  evidence_eligible=False)
    process_queue()

    count, _ = db.get_evidence_style(test_user["id"])
    assert count == 1, f"five placeholders counted toward the regime threshold: {count}"


def test_the_settings_menu_offers_every_selectable_engine(test_user):
    """The allow-list was fixed so a customised Settings could not silently drop
    observations — and the menu that produces the allow-list was still a second,
    hand-kept list of the 2024 six. Lifelong could be shown and never switched
    off; observations could be selected by nothing on screen."""
    from fastapi.testclient import TestClient

    from agent.constants import SELECTABLE_ENGINES
    from iris_api import app, get_current_user_id

    app.dependency_overrides[get_current_user_id] = lambda: test_user["id"]
    try:
        body = TestClient(app).get("/api/user/analysis").json()
    finally:
        app.dependency_overrides.clear()

    assert body["availableEngines"] == sorted(SELECTABLE_ENGINES)
    assert {"lifelong", "observations"} <= set(body["availableEngines"])
