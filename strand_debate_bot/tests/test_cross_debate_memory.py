"""End-to-end acceptance tests for cross-debate memory (TRD Task 3's bar):
"a second debate on a similar topic visibly references/builds on the first."

Uses the real `ChromaMemoryStore` (not `FakeMemoryStore`) so retrieval genuinely
exercises semantic similarity, not a canned result -- that's the behavior these
tests exist to prove.
"""

import pytest
from strands.multiagent.base import Status

from src.core.graph import build_graph
from src.core.memory import ChromaMemoryStore
from src.core.state import build_invocation_state
from tests.fakes import FakeModel


@pytest.mark.asyncio
async def test_second_debate_on_similar_topic_builds_on_first(tmp_path):
    memory_store = ChromaMemoryStore(str(tmp_path))

    first_model = FakeModel(
        text="ROBUST_UTILITY_MARKER: platforms are essential infrastructure",
        structured={"winner": "Pro", "justification": "j"},
    )
    first_graph = build_graph(model=first_model, memory_store=memory_store)
    first_state = build_invocation_state("Should social media platforms be regulated as public utilities?")
    first_state["audience_question"] = "Pre-supplied question?"
    await first_graph.invoke_async("run", invocation_state=first_state)

    second_model = FakeModel(text="turn text", structured={"winner": "Con", "justification": "j"})
    second_graph = build_graph(model=second_model, memory_store=memory_store)
    second_state = build_invocation_state("Should governments regulate large tech platforms like utilities?")
    second_state["audience_question"] = "Pre-supplied question?"
    await second_graph.invoke_async("run", invocation_state=second_state)

    # calls[0..7] = pro_opening, con_opening, pro_rebuttal, con_rebuttal,
    # pro_addresses_question, con_addresses_question, pro_closing, con_closing
    for index in range(8):
        rendered = str(second_model.calls[index])
        assert "Past debate context" in rendered
        assert "ROBUST_UTILITY_MARKER" in rendered


@pytest.mark.asyncio
async def test_first_ever_debate_runs_normally_with_no_prior_memory(tmp_path):
    memory_store = ChromaMemoryStore(str(tmp_path))  # cold, empty store
    model = FakeModel(text="turn text", structured={"winner": "Pro", "justification": "j"})
    graph = build_graph(model=model, memory_store=memory_store)
    state = build_invocation_state("Should remote work replace office work?")
    state["audience_question"] = "Pre-supplied question?"

    result = await graph.invoke_async("run", invocation_state=state)

    assert result.status == Status.COMPLETED
    for index in range(8):
        assert "Past debate context" not in str(model.calls[index])
