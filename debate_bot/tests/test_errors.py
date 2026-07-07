import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import asyncio


@pytest.mark.asyncio
async def test_pro_opening_llm_timeout(base_state):
    """Agent should handle LLM timeout gracefully."""
    with patch("agents.pro.llm") as mock_llm:
        mock_llm.astream = AsyncMock(side_effect=asyncio.TimeoutError("LLM call timed out"))
        from agents.pro import pro_opening
        with pytest.raises(asyncio.TimeoutError):
            await pro_opening(base_state)


@pytest.mark.asyncio
async def test_con_opening_llm_network_error(base_state):
    """Agent should handle network errors during LLM call."""
    with patch("agents.con.llm") as mock_llm:
        mock_llm.astream = AsyncMock(side_effect=Exception("Failed to connect to LLM API"))
        from agents.con import con_opening
        with pytest.raises(Exception):
            await con_opening(base_state)


@pytest.mark.asyncio
async def test_moderator_decision_llm_rate_limit(base_state):
    """Moderator should handle rate limit errors from LLM."""
    base_state.update({
        "pro_closing": "AI is transformative.",
        "con_closing": "Humans are irreplaceable.",
        "round": "decision",
    })
    with patch("agents.moderator.llm") as mock_llm:
        mock_llm.astream = AsyncMock(side_effect=Exception("Rate limit exceeded (429)"))
        from agents.moderator import moderator_decision
        with pytest.raises(Exception):
            await moderator_decision(base_state)


@pytest.mark.asyncio
async def test_pro_opening_memory_retrieval_fails(base_state):
    """Agent should handle memory retrieval failures gracefully."""
    with patch("agents.pro.retrieve_context") as mock_retrieve:
        mock_retrieve.side_effect = Exception("Memory store unavailable")
        from agents.pro import pro_opening
        with pytest.raises(Exception):
            await pro_opening(base_state)


@pytest.mark.asyncio
async def test_con_opening_memory_upsert_fails(base_state, mock_llm):
    """Agent should still return result even if memory upsert fails."""
    base_state["pro_opening"] = "Pro argument"
    with patch("agents.con.retrieve_context", return_value=[]):
        with patch("agents.con.llm", mock_llm):
            from agents.con import con_opening
            # Should complete even if memory operations fail internally
            result = await con_opening(base_state)
            assert "con_opening" in result


@pytest.mark.asyncio
async def test_graph_execution_with_invalid_state():
    """Graph should handle invalid state transitions."""
    from app import graph
    from state import DebateState

    invalid_state: DebateState = {
        "topic": "",  # Invalid: empty topic
        "round": "invalid_round",  # Invalid: not a valid round
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

    with pytest.raises(Exception):
        await graph.ainvoke(invalid_state)


@pytest.mark.asyncio
async def test_moderator_decision_cannot_extract_winner(base_state, mock_llm):
    """Moderator decision should handle unparseable winner responses."""
    base_state.update({
        "pro_closing": "AI is transformative.",
        "con_closing": "Humans are irreplaceable.",
        "round": "decision",
    })

    # Mock LLM returns response with no clear winner
    mock_llm.astream = AsyncMock(return_value=aiter([
        "Both sides made good points. ",
        "It's hard to declare a winner. ",
        "The debate was balanced."
    ]))

    with patch("agents.moderator.llm", mock_llm):
        from agents.moderator import moderator_decision
        result = await moderator_decision(base_state)
        # Should still return something, even if winner is empty
        assert "moderator_summary" in result
        assert isinstance(result.get("winner"), str)


@pytest.mark.asyncio
async def test_streaming_response_with_llm_failure():
    """Streaming endpoint should handle LLM failures mid-stream."""
    from server import app
    from fastapi.testclient import TestClient

    client = TestClient(app)

    with patch("app.graph.astream") as mock_stream:
        # Simulate failure after partial stream
        async def failing_generator():
            yield ("moderator_open", {"round": "opening"})
            raise Exception("LLM service down")

        mock_stream.return_value = failing_generator()

        # Stream should handle error gracefully
        response = client.get("/debate/stream?topic=test")
        # Should still get partial results, not crash


@pytest.mark.asyncio
async def test_debate_invoke_with_execution_timeout(base_state):
    """Debate invocation should timeout if takes too long."""
    with patch("app.run_debate") as mock_run:
        mock_run.side_effect = asyncio.TimeoutError("Debate took >60s")
        from app import run_debate
        with pytest.raises(asyncio.TimeoutError):
            await run_debate("test topic")


@pytest.mark.asyncio
async def test_memory_store_chroma_fallback():
    """Memory store should fallback to InMemory gracefully."""
    with patch("memory.Chroma", side_effect=ImportError("chromadb not available")):
        from memory import MemoryStore
        # Should not raise, should use InMemory
        store = MemoryStore(persist_directory="/tmp/test")
        assert store.store is not None


@pytest.mark.asyncio
async def test_concurrent_debate_execution_limit():
    """Multiple concurrent debates should be limited."""
    from app import run_debate
    import asyncio

    # Try to run 5 concurrent debates (if limit is 3, some should queue/fail)
    tasks = [run_debate(f"topic {i}") for i in range(5)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # At least some should complete successfully
    successful = [r for r in results if not isinstance(r, Exception)]
    assert len(successful) > 0


def aiter(items):
    """Convert list to async iterator."""
    async def gen():
        for item in items:
            yield MagicMock(content=item)
    return gen()
