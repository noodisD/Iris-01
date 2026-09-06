
import pytest

from agent.narrative import NarrativeFormatter


def test_regex_guardrail_lemmas():
    # Test multiple variants of forbidden word 'cause'
    forbidden = [
        "The theme cause stress",
        "The theme caused stress",
        "The theme causing stress",
        "The theme causes stress"
    ]
    for text in forbidden:
        with pytest.raises(ValueError) as exc:
            NarrativeFormatter._validate_safety(text)
        assert "Forbidden word" in str(exc.value)

def test_prescriptive_language_blocked():
    forbidden = [
        "You should exercise more",
        "I recommend focusing on yoga",
        "This means you are improving"
    ]
    for text in forbidden:
        with pytest.raises(ValueError):
            NarrativeFormatter._validate_safety(text)

def test_fail_closed_silence_mode(monkeypatch):
    # Set to production 'silence' mode
    monkeypatch.setattr("agent.narrative.NARRATIVE_FAIL_MODE", "silence")

    # Insight that uses forbidden word in summary field (which populates template)
    bad_insight = {
        "engine_name": "trajectory",
        "summary": "The cause of work stress",
        "trajectory_label": "increasing"
    }

    # Should return None, not raise
    result = NarrativeFormatter.format_insight(bad_insight)
    assert result is None

def test_order_preservation():
    # Prioritization returns a list. Narrative must follow that list EXACTLY.
    insights = [
        {"engine_name": "persistence", "summary": "A", "occurrence_count": 10, "last_seen_at": "2026-01-01"},
        {"engine_name": "persistence", "summary": "B", "occurrence_count": 5, "last_seen_at": "2026-01-01"}
    ]

    narratives = NarrativeFormatter.format_all(insights)
    assert "A" in narratives[0]
    assert "B" in narratives[1]
