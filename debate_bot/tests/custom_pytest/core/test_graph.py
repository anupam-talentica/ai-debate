import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_full_graph_runs_to_completion():
    """End-to-end graph execution must populate all state fields."""
    # src/agents/*.py construct `llm = ChatAnthropic(...)` once at import time, so
    # patching the ChatAnthropic class has no effect on the already-bound instances -
    # each agent module's `llm` must be patched directly instead.
    with patch("src.agents.pro.llm") as pro_llm, \
         patch("src.agents.con.llm") as con_llm, \
         patch("src.agents.moderator.llm") as moderator_llm:

        def astream_side_effect(prompt):
            return aiter(["Mock ", "response ", "text."])

        pro_llm.astream = MagicMock(side_effect=astream_side_effect)
        con_llm.astream = MagicMock(side_effect=astream_side_effect)
        moderator_llm.astream = MagicMock(side_effect=astream_side_effect)

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
            # Pre-supplied so the audience-question pause is skipped and the
            # graph runs start-to-finish in this single ainvoke() call.
            "audience_question": "What about the environmental impact?",
            "pro_audience_answer": "",
            "con_audience_answer": "",
        })

    assert state["pro_opening"] != ""
    assert state["con_opening"] != ""
    assert state["pro_audience_answer"] != ""
    assert state["con_audience_answer"] != ""
    assert state["moderator_summary"] != ""
    assert "memory_context" in state


@pytest.mark.asyncio
async def test_graph_includes_memory_context():
    """Graph execution must include memory context from retrieval."""
    with patch("src.agents.pro.llm") as pro_llm, \
         patch("src.agents.con.llm") as con_llm, \
         patch("src.agents.moderator.llm") as moderator_llm:

        # Each node's astream() is called with fresh args, so a shared exhausted
        # generator would starve later calls - give each a fresh one per call.
        def make_astream():
            return MagicMock(side_effect=lambda prompt: aiter(["Winner: ", "Con."]))

        pro_llm.astream = make_astream()
        con_llm.astream = make_astream()
        moderator_llm.astream = make_astream()

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
            "audience_question": "",
            "pro_audience_answer": "",
            "con_audience_answer": "",
        })

    assert "memory_context" in state


def aiter(items):
    async def gen():
        for item in items:
            yield MagicMock(content=item)
    return gen()
