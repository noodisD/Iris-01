"""The rule against causes and advice applies wherever IRIS speaks.

It ran on chat's templates and nowhere else: not on the Insights read, which
carries a theme summary a model wrote; not on the system prompt's own examples,
one of which taught the model to ask what "triggered" something; and the
templates it did cover said "frequently" where nothing had measured frequency.
"""

from __future__ import annotations

import re

from agent.narrative import NarrativeFormatter
from agent.narrative_policy import FORBIDDEN_REGEX


def test_the_insights_read_drops_a_sentence_that_claims_a_cause():
    from agent.insights_service import InsightsService

    read = InsightsService(1)._iris_read({
        "summary": "Walking helps sleep", "label": "increasing", "confidence_level": "medium",
        "measures": [{"label": "Recent", "value": 4, "sub": "last 14 days"}],
    })
    assert not FORBIDDEN_REGEX.search(read)
    assert "Recent: 4 (last 14 days)." in read, "the measured parts remain"


def test_the_system_prompts_examples_pass_the_firewall():
    from prompts.system_prompt import SYSTEM_PROMPT

    examples = SYSTEM_PROMPT.split("GOOD EXAMPLES:")[1].split("CORE PRINCIPLES")[0]
    for line in (line for line in examples.splitlines() if line.strip().startswith("-")):
        assert not FORBIDDEN_REGEX.search(line), line


def test_the_proactive_prompt_states_only_what_was_recorded(mock_llm, test_user):
    """The mood was inferred from tags — "okay" when there were none — and the
    context builder already refused to present it as given. This hint handed it
    to the model anyway."""
    from agent.core import PersonalAICompanion

    PersonalAICompanion(test_user["id"]).generate_proactive_comment(
        "reflection", {"content": "Walked to the lake.", "mood": "okay", "energy_level": None})
    sent = mock_llm.chat.call_args.kwargs["messages"][0]["content"]
    assert "mood" not in sent and "okay" not in sent and "None" not in sent


def test_every_sentence_quotes_what_was_measured():
    """Trajectory and tension had no counts, leverage dropped its target, and
    decision impact's window was the literal "14"."""
    rendered = {
        "trajectory": NarrativeFormatter.format_insight({
            "engine_name": "trajectory", "theme_summary": "late nights",
            "trajectory_label": "increasing", "recent_count": 5, "past_count": 2}),
        "tension": NarrativeFormatter.format_insight({
            "engine_name": "tension", "theme_a_summary": "late nights",
            "theme_b_summary": "low energy", "tension_label": "persistent", "cooccurrence_count": 9}),
        "leverage": NarrativeFormatter.format_insight({
            "engine_name": "leverage", "summary": "late nights", "target_summary": "low energy",
            "label": "associated", "cooccurrence_count": 6}),
    }
    assert "5 times" in rendered["trajectory"] and "2 in" in rendered["trajectory"]
    assert "9 of the same days" in rendered["tension"]
    assert "'late nights' and" in rendered["tension"], "not 'Unknown Pattern'"
    assert "'low energy'" in rendered["leverage"], "the target is named"
    for text in rendered.values():
        assert "frequently" not in text
        assert not re.search(r"\bstable in\b|\bpersisting\b", text)
