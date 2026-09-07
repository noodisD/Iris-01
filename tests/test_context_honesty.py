"""The context must not make "filtered out" look like "nothing happened".

The patterns block read "No significant patterns observed recently." whenever it
was empty — whether the engines had found nothing, or the user's own confidence
threshold had removed everything. Those are different facts, and nothing in the
context told them apart, so IRIS would tell someone nothing was happening when
it had observations their own setting had hidden.

That became reachable the moment the gates were exposed in Settings: raising the
threshold is a normal thing to do, and it made IRIS quietly wrong about the
user's life.
"""

from unittest.mock import patch

import pytest

from agent.core import PersonalAICompanion
from agent.preferences import UserPreferencesService

INSIGHT = {
    "engine_name": "resolution", "pattern_type": "theme", "pattern_id": 1,
    "theme_id": 1, "summary": "work pressure", "resolution_label": "persisting",
    "confidence_level": "medium", "recent_count": 6, "past_count": 4,
}


def _patterns_block(user_id, gated, suppression_log):
    companion = PersonalAICompanion(user_id)
    with patch.object(companion.analysis_pipeline, "run", return_value=gated), \
         patch.object(companion.analysis_pipeline, "get_suppression_log",
                      return_value=suppression_log):
        ctx = companion._get_aggregated_context("anything showing up?")
    return ctx.split("Observed Temporal Sequences:")[1].strip()


def test_no_data_says_there_is_no_history(test_user):
    block = _patterns_block(test_user["id"], [], {})
    assert "not enough logged history" in block
    assert "filters" not in block, "there is nothing to blame a filter for"


def test_everything_filtered_says_so_rather_than_nothing_happened(test_user):
    UserPreferencesService(test_user["id"]).update_pref("min_confidence", "high")
    block = _patterns_block(
        test_user["id"], [], {"low_confidence": ["resolution: work pressure (medium)"]}
    )
    assert "held back" in block, "the user's filter must be named as the cause"
    assert "'high'" in block, "say which threshold did it"
    assert "not the same as there being nothing to report" in block
    assert "not enough logged history" not in block, (
        "suppressed evidence must never be reported as absent evidence"
    )


def test_a_partial_list_does_not_pretend_to_be_complete(test_user):
    block = _patterns_block(
        test_user["id"], [INSIGHT], {"low_confidence": ["trajectory: sleep (low)"]}
    )
    assert "work pressure" in block, "what passed is still shown"
    assert "not everything IRIS has" in block


def test_the_systems_own_limits_are_not_blamed_on_the_user(test_user):
    """The budget cut and conflict suppression are IRIS's own limits, not a
    claim about what is true (ADR-0007). Reporting them here would invite IRIS
    to talk about its plumbing instead of the user."""
    block = _patterns_block(
        test_user["id"], [],
        {"budget_cutoff": ["a", "b"], "conflict": ["c"]},
    )
    assert "not enough logged history" in block
    assert "held back" not in block


@pytest.mark.parametrize("count,noun,verb", [(1, "observation", "was"), (2, "observations", "were")])
def test_it_reads_as_english(test_user, count, noun, verb):
    block = _patterns_block(
        test_user["id"], [], {"low_confidence": ["x"] * count}
    )
    assert f"{count} {noun} {verb} held back" in block
