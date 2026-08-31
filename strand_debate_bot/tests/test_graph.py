import pytest
from strands.multiagent.base import Status

from src.core.graph import build_graph
from src.core.state import build_invocation_state
from tests.fakes import FakeMemoryStore, FakeModel

EXPECTED_ORDER = [
    "moderator", "pro_opening", "con_opening",
    "moderator", "pro_rebuttal", "con_rebuttal",
    "moderator", "audience_question", "pro_addresses_question", "con_addresses_question",
    "moderator", "pro_closing", "con_closing",
    "moderator", "moderator_decision",
]

# model.calls indices for a full debate run with a pre-supplied audience question
# (so no interrupt occurs): [0]=pro_opening [1]=con_opening [2]=pro_rebuttal
# [3]=con_rebuttal [4]=pro_addresses_question [5]=con_addresses_question
# [6]=pro_closing [7]=con_closing [8]=moderator_decision
ALL_DEBATE_TURN_CALL_INDICES = [0, 1, 2, 3, 4, 5, 6, 7]


@pytest.mark.asyncio
async def test_full_debate_runs_end_to_end():
    """A full debate runs opening -> rebuttal -> audience -> closing -> verdict end to end (TRD Task 2's test)."""
    model = FakeModel(text="turn text", structured={"winner": "Con", "justification": "Con's rebuttal landed harder."})
    graph = build_graph(model=model, memory_store=FakeMemoryStore())
    state = build_invocation_state("Remote work beats office work")
    state["audience_question"] = "Pre-supplied question?"

    result = await graph.invoke_async("run", invocation_state=state)

    assert result.status == Status.COMPLETED
    execution_order = [n.node_id for n in result.execution_order]
    assert execution_order == EXPECTED_ORDER


@pytest.mark.asyncio
async def test_con_opening_and_rebuttal_see_pro_opening():
    model = FakeModel(text="turn text", structured={"winner": "Pro", "justification": "j"})
    graph = build_graph(model=model, memory_store=FakeMemoryStore())
    state = build_invocation_state("Topic")
    state["audience_question"] = "Pre-supplied question?"

    await graph.invoke_async("run", invocation_state=state)

    assert "turn text" in str(model.calls[1])  # con_opening's prompt echoes pro_opening's stored text
    assert "turn text" in str(model.calls[3])  # con_rebuttal's prompt echoes pro_opening's stored text


@pytest.mark.asyncio
async def test_audience_round_pauses_and_resumes_with_answers():
    """The audience round pauses after the rebuttal round; the submitted answer
    reaches both agents and is stored (TRD Task 4's test)."""
    model = FakeModel(text="turn text", structured={"winner": "Pro", "justification": "j"})
    graph = build_graph(model=model, memory_store=FakeMemoryStore())
    state = build_invocation_state("Topic")

    result = await graph.invoke_async("run", invocation_state=state)

    assert result.status == Status.INTERRUPTED
    assert state["audience_question"] == ""
    assert state["pro_audience_answer"] == ""
    assert state["con_audience_answer"] == ""

    interrupt_id = result.interrupts[0].id
    result = await graph.invoke_async(
        [{"interruptResponse": {"interruptId": interrupt_id, "response": "What about accessibility?"}}],
        invocation_state=state,
    )

    assert result.status == Status.COMPLETED
    assert state["audience_question"] == "What about accessibility?"
    assert state["pro_audience_answer"].strip() == "turn text"
    assert state["con_audience_answer"].strip() == "turn text"


@pytest.mark.asyncio
async def test_pre_supplied_audience_question_skips_pause():
    model = FakeModel(text="turn text", structured={"winner": "Pro", "justification": "j"})
    graph = build_graph(model=model, memory_store=FakeMemoryStore())
    state = build_invocation_state("Topic")
    state["audience_question"] = "Pre-supplied question?"

    result = await graph.invoke_async("run", invocation_state=state)

    assert result.status == Status.COMPLETED
    assert state["audience_question"] == "Pre-supplied question?"
    assert state["pro_audience_answer"].strip() == "turn text"
    assert state["con_audience_answer"].strip() == "turn text"


@pytest.mark.asyncio
async def test_audience_answers_reference_the_submitted_question():
    model = FakeModel(text="turn text", structured={"winner": "Pro", "justification": "j"})
    graph = build_graph(model=model, memory_store=FakeMemoryStore())
    state = build_invocation_state("Topic")
    state["audience_question"] = "What about accessibility?"

    await graph.invoke_async("run", invocation_state=state)

    assert "What about accessibility?" in str(model.calls[4])  # pro_addresses_question
    assert "What about accessibility?" in str(model.calls[5])  # con_addresses_question


@pytest.mark.asyncio
async def test_verdict_prompt_includes_audience_qna():
    model = FakeModel(text="turn text", structured={"winner": "Pro", "justification": "j"})
    graph = build_graph(model=model, memory_store=FakeMemoryStore())
    state = build_invocation_state("Topic")
    state["audience_question"] = "What about accessibility?"

    await graph.invoke_async("run", invocation_state=state)

    verdict_call = str(model.calls[-1])
    assert "What about accessibility?" in verdict_call
    assert "turn text" in verdict_call  # pro/con audience answers, both "turn text" from FakeModel


@pytest.mark.asyncio
async def test_verdict_is_structured_and_terminal():
    model = FakeModel(structured={"winner": "Con", "justification": "Con's rebuttal landed harder."})
    graph = build_graph(model=model, memory_store=FakeMemoryStore())
    state = build_invocation_state("Topic")
    state["audience_question"] = "Pre-supplied question?"

    result = await graph.invoke_async("run", invocation_state=state)

    assert state["winner"] == "Con"
    assert state["justification"] == "Con's rebuttal landed harder."

    execution_order = [n.node_id for n in result.execution_order]
    assert execution_order[-1] == "moderator_decision"
    assert execution_order.count("moderator_decision") == 1
    assert len(execution_order) == 15  # matches design.md's node-execution count


@pytest.mark.asyncio
async def test_memory_context_reaches_every_pro_con_turn():
    """Cross-debate memory (design.md, Decision 5): a retrieved past-debate summary
    is spliced into every opening/rebuttal/audience/closing prompt, not just the opening."""
    memory_store = FakeMemoryStore(["Topic: Old debate | Pro: efficiency | Con: risk | Winner: Pro"])
    model = FakeModel(structured={"winner": "Pro", "justification": "j"})
    graph = build_graph(model=model, memory_store=memory_store)
    state = build_invocation_state("Topic")
    state["audience_question"] = "Pre-supplied question?"

    await graph.invoke_async("run", invocation_state=state)

    for index in ALL_DEBATE_TURN_CALL_INDICES:
        rendered = str(model.calls[index])
        assert "Past debate context" in rendered
        assert "Old debate" in rendered


@pytest.mark.asyncio
async def test_no_memory_block_when_store_has_no_similar_debate():
    memory_store = FakeMemoryStore([])  # cold store, or no similar match
    model = FakeModel(structured={"winner": "Pro", "justification": "j"})
    graph = build_graph(model=model, memory_store=memory_store)
    state = build_invocation_state("Topic")
    state["audience_question"] = "Pre-supplied question?"

    await graph.invoke_async("run", invocation_state=state)

    for index in ALL_DEBATE_TURN_CALL_INDICES:
        assert "Past debate context" not in str(model.calls[index])
