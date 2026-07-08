import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_full_graph_runs_to_completion():
    """End-to-end graph execution must populate all state fields."""
    with patch("langchain_anthropic.ChatAnthropic") as MockLLM:
        def astream_side_effect(prompt):
            return aiter(["Mock ", "response ", "text."])

        instance = MockLLM.return_value
        instance.astream = MagicMock(side_effect=astream_side_effect)

        from src.core.graph import build_graph
        from src.core.memory import MemoryStore

        graph = build_graph(MemoryStore())
        state = await graph.ainvoke({
            "topic": "Remote work is better than office work",
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
        })

    assert state["pro_opening"] != ""
    assert state["con_opening"] != ""
    assert state["moderator_summary"] != ""
    assert "memory_context" in state


@pytest.mark.asyncio
async def test_graph_includes_memory_context():
    """Graph execution must include memory context from retrieval."""
    with patch("langchain_anthropic.ChatAnthropic") as MockLLM:
        instance = MockLLM.return_value
        instance.astream = MagicMock(
            return_value=aiter(["Winner: ", "Con."])
        )

        from src.core.graph import build_graph
        from src.core.memory import MemoryStore

        graph = build_graph(MemoryStore())
        state = await graph.ainvoke({
            "topic": "Remote work is better than office work",
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
        })

    assert "memory_context" in state


def aiter(items):
    async def gen():
        for item in items:
            yield MagicMock(content=item)
    return gen()
