import pytest
from state import DebateState


def test_debate_state_structure():
    """Test that DebateState has all required fields."""
    state: DebateState = {
        "topic": "AI will replace software engineers",
        "round": "opening",
        "pro_opening": "AI is superior.",
        "con_opening": "Humans are needed.",
        "pro_rebuttal": "But efficiency matters.",
        "con_rebuttal": "Creativity is irreplaceable.",
        "pro_closing": "The evidence supports this.",
        "con_closing": "Our position is stronger.",
        "moderator_summary": "Both sides made valid points.",
        "winner": "Pro",
        "memory_context": ["Previous debate summary"],
    }

    assert state["topic"] != ""
    assert state["round"] in ("opening", "rebuttal", "closing", "decision", "")
    assert isinstance(state["pro_opening"], str)
    assert isinstance(state["con_opening"], str)
    assert isinstance(state["pro_rebuttal"], str)
    assert isinstance(state["con_rebuttal"], str)
    assert isinstance(state["pro_closing"], str)
    assert isinstance(state["con_closing"], str)
    assert isinstance(state["moderator_summary"], str)
    assert state["winner"] in ("Pro", "Con", "")
    assert isinstance(state["memory_context"], list)


def test_debate_state_initial_empty_values():
    """Test that state can be initialized with empty values."""
    state: DebateState = {
        "topic": "Test topic",
        "round": "",
        "pro_opening": "",
        "con_opening": "",
        "pro_rebuttal": "",
        "con_rebuttal": "",
        "pro_closing": "",
        "con_closing": "",
        "moderator_summary": "",
        "winner": "",
        "memory_context": [],
    }

    assert state["topic"] == "Test topic"
    assert state["pro_opening"] == ""
    assert state["memory_context"] == []
