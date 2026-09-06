
import pytest

from agent.narrative import NarrativeFormatter


def test_forbidden_lexicon_blocks_causality():
    # Test a few variants of forbidden words
    forbidden_sentences = [
        "This theme caused a change.",
        "I recommend you sleep more.",
        "This means you are stressed.",
        "It lead to poor outcomes."
    ]

    for text in forbidden_sentences:
        with pytest.raises(ValueError) as exc:
            NarrativeFormatter._validate_safety(text)
        assert "Narrative violation" in str(exc.value)

def test_safe_language_passes():
    safe_sentences = [
        "The pattern appeared frequently.",
        "It was preceded by another event.",
        "Frequency increased recently.",
        "The theme was absent."
    ]
    for text in safe_sentences:
        # Should not raise
        NarrativeFormatter._validate_safety(text)

def test_format_all_preserves_order():
    insights = [
        {"engine_name": "trajectory", "summary": "First", "trajectory_label": "increasing"},
        {"engine_name": "resolution", "summary": "Second", "resolution_label": "dissipated"}
    ]

    narratives = NarrativeFormatter.format_all(insights)

    assert len(narratives) == 2
    assert "First" in narratives[0]
    assert "Second" in narratives[1]

def test_fail_closed_silence_mode(monkeypatch):
    # Temporarily set to silence mode
    monkeypatch.setattr("agent.narrative.NARRATIVE_FAIL_MODE", "silence")

    # Create an insight that will fail validation (uses a forbidden word in summary)
    bad_insight = {
        "engine_name": "trajectory",
        "summary": "This caused issues", # 'caused' is forbidden
        "trajectory_label": "increasing"
    }

    result = NarrativeFormatter.format_insight(bad_insight)

    # Should return None instead of raising
    assert result is None
