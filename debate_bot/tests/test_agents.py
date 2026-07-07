import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_pro_opening_populates_state(base_state, mock_llm):
    """Pro agent must write a non-empty opening argument."""
    with patch("agents.pro.llm", mock_llm):
        from agents.pro import pro_opening
        result = await pro_opening(base_state)
    assert result["pro_opening"] != ""
    assert "memory_context" in result


@pytest.mark.asyncio
async def test_con_opening_reads_pro_argument(base_state, mock_llm):
    """Con agent must receive the pro opening as context."""
    base_state["pro_opening"] = "AI is superior at coding tasks."
    with patch("agents.con.llm", mock_llm):
        from agents.con import con_opening
        result = await con_opening(base_state)
    assert result["con_opening"] != ""
    assert "memory_context" in result


@pytest.mark.asyncio
async def test_pro_rebuttal_responds_to_con(base_state, mock_llm):
    """Pro rebuttal must respond to con opening."""
    base_state["con_opening"] = "Humans are still needed."
    base_state["memory_context"] = []
    with patch("agents.pro.llm", mock_llm):
        from agents.pro import pro_rebuttal
        result = await pro_rebuttal(base_state)
    assert result["pro_rebuttal"] != ""


@pytest.mark.asyncio
async def test_con_rebuttal_responds_to_pro(base_state, mock_llm):
    """Con rebuttal must respond to pro opening."""
    base_state["pro_opening"] = "AI is transformative."
    base_state["memory_context"] = []
    with patch("agents.con.llm", mock_llm):
        from agents.con import con_rebuttal
        result = await con_rebuttal(base_state)
    assert result["con_rebuttal"] != ""


@pytest.mark.asyncio
async def test_moderator_decision_sets_winner(base_state, mock_llm):
    """Moderator must declare a winner (Pro or Con)."""
    base_state.update({
        "pro_closing": "AI is transformative.",
        "con_closing": "Humans are irreplaceable.",
        "round": "decision",
    })
    mock_llm.astream = MagicMock(
        return_value=aiter(["Winner: ", "Pro. ", "The pro side argued more effectively."])
    )
    with patch("agents.moderator.llm", mock_llm):
        from agents.moderator import moderator_decision
        result = await moderator_decision(base_state)
    assert result["winner"] in ("Pro", "Con")
    assert result["moderator_summary"] != ""


@pytest.mark.asyncio
async def test_moderator_open_sets_round(base_state):
    """Moderator must set the round to 'opening'."""
    from agents.moderator import moderator_open
    result = await moderator_open(base_state)
    assert result["round"] == "opening"


@pytest.mark.asyncio
async def test_moderator_checkpoint_transitions_round(base_state):
    """Moderator checkpoint must transition to the next round."""
    from agents.moderator import moderator_checkpoint

    base_state["round"] = "opening"
    result = await moderator_checkpoint(base_state)
    assert result["round"] == "rebuttal"

    base_state["round"] = "rebuttal"
    result = await moderator_checkpoint(base_state)
    assert result["round"] == "closing"

    base_state["round"] = "closing"
    result = await moderator_checkpoint(base_state)
    assert result["round"] == "decision"


@pytest.mark.asyncio
async def test_pro_closing_generates_argument(base_state, mock_llm):
    """Pro closing must generate a closing argument."""
    base_state["memory_context"] = []
    with patch("agents.pro.llm", mock_llm):
        from agents.pro import pro_closing
        result = await pro_closing(base_state)
    assert result["pro_closing"] != ""


@pytest.mark.asyncio
async def test_con_closing_generates_argument(base_state, mock_llm):
    """Con closing must generate a closing argument."""
    base_state["memory_context"] = []
    with patch("agents.con.llm", mock_llm):
        from agents.con import con_closing
        result = await con_closing(base_state)
    assert result["con_closing"] != ""


def aiter(items):
    async def gen():
        for item in items:
            yield MagicMock(content=item)
    return gen()
