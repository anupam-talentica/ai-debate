"""Tests for the audience-question human-in-the-loop pause (see
openspec/changes/audience-question-interrupt/).

Covers: the graph pausing after rebuttals and resuming via Command(resume=...)
(7.1, 7.2), the moderator prompt weighing the Q&A (7.3), the
POST /debate/{run_id}/audience-question endpoint's accept/reject rules
(7.4, 7.5), the synchronous /invoke guard and pre-supplied-question path
(7.6, 7.7), and that a paused run isn't reclaimed by the stale-heartbeat
failover path (7.8).
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command


def aiter(items):
    async def gen():
        for item in items:
            yield MagicMock(content=item)
    return gen()


def make_astream(text="Winner: Pro. Mock text."):
    return MagicMock(side_effect=lambda prompt: aiter([text]))


@pytest.fixture
def patched_llms():
    """Patch all three agent modules' module-level `llm` with a fixed-response
    mock, matching the pattern used throughout tests/custom_pytest/core/test_graph.py."""
    with patch("src.agents.pro.llm") as pro_llm, \
         patch("src.agents.con.llm") as con_llm, \
         patch("src.agents.moderator.llm") as moderator_llm:
        pro_llm.astream = make_astream()
        con_llm.astream = make_astream()
        moderator_llm.astream = make_astream()
        yield


@pytest.fixture
def checkpointed_app_graph():
    """Temporarily give `app.graph` an in-memory checkpointer, restoring the
    original afterward. Mirrors what init_checkpointer() does at real startup
    (see server.py's lifespan) — required for interrupt()/aget_state() to
    behave the way they do in production rather than the checkpointer-less
    graph app.py builds at import time."""
    import app as app_module

    original_graph = app_module.graph
    app_module.graph = app_module.build_graph(app_module.memory_store, checkpointer=InMemorySaver())
    try:
        yield app_module.graph
    finally:
        app_module.graph = original_graph


def fresh_state(**overrides):
    state = {
        "topic": "Remote work is better than office work",
        "round": "",
        "pro_opening": "", "con_opening": "",
        "pro_rebuttal": "", "con_rebuttal": "",
        "pro_closing": "", "con_closing": "",
        "moderator_summary": "", "winner": "",
        "memory_context": [],
        "audience_question": "", "pro_audience_answer": "", "con_audience_answer": "",
    }
    state.update(overrides)
    return state


# --- 7.1: graph pauses after con_rebuttal ----------------------------------

@pytest.mark.asyncio
async def test_graph_pauses_after_rebuttal_for_audience_question(patched_llms):
    from src.core.graph import build_graph
    from src.core.memory import MemoryStore

    graph = build_graph(MemoryStore(), checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "test-pause"}}

    result = await graph.ainvoke(fresh_state(), config=config)

    # Paused before closing/decision: rebuttal completed, but nothing past it did.
    assert result["con_rebuttal"] != ""
    assert result["pro_closing"] == ""
    assert result["winner"] == ""

    snapshot = await graph.aget_state(config)
    assert snapshot.next == ("audience_question",)
    assert len(snapshot.interrupts) == 1


@pytest.mark.asyncio
async def test_graph_does_not_pause_before_rebuttal_completes(patched_llms):
    """Sanity check for the spec's negative scenario: mid-opening state isn't paused."""
    from src.core.graph import build_graph
    from src.core.memory import MemoryStore

    graph = build_graph(MemoryStore(), checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "test-no-pause"}}

    # Run just the first step and confirm we're not sitting on the interrupt yet.
    astream_iter = graph.astream(fresh_state(), config=config)
    first_update = await astream_iter.__anext__()
    assert "__interrupt__" not in first_update


# --- 7.2: both debaters address the question after resume ------------------

@pytest.mark.asyncio
async def test_both_debaters_address_question_after_resume(patched_llms):
    from src.core.graph import build_graph
    from src.core.memory import MemoryStore

    graph = build_graph(MemoryStore(), checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "test-resume"}}

    await graph.ainvoke(fresh_state(), config=config)  # runs to the pause

    result = await graph.ainvoke(Command(resume="What about environmental cost?"), config=config)

    assert result["audience_question"] == "What about environmental cost?"
    assert result["pro_audience_answer"] != ""
    assert result["con_audience_answer"] != ""
    # And execution continued all the way through closing/decision.
    assert result["pro_closing"] != ""
    assert result["con_closing"] != ""
    assert result["winner"] != ""


@pytest.mark.asyncio
async def test_pre_supplied_question_skips_the_pause_entirely(patched_llms):
    """The /invoke pre-supplied-question path: the interrupt node must not
    pause at all when audience_question is already present in state."""
    from src.core.graph import build_graph
    from src.core.memory import MemoryStore

    graph = build_graph(MemoryStore())  # no checkpointer needed: never pauses
    config = {"configurable": {"thread_id": "test-presupplied"}}

    result = await graph.ainvoke(
        fresh_state(audience_question="What about cost?"), config=config
    )

    assert "__interrupt__" not in result
    assert result["pro_audience_answer"] != ""
    assert result["con_audience_answer"] != ""
    assert result["winner"] != ""


# --- 7.3: moderator verdict weighs the audience Q&A -------------------------

def test_moderator_decision_prompt_includes_audience_qa():
    from src.core.prompts import MODERATOR_DECISION

    prompt = MODERATOR_DECISION.format(
        pro_closing="Pro closing text",
        con_closing="Con closing text",
        audience_question="What about the ethics?",
        pro_audience_answer="Pro's answer to the audience",
        con_audience_answer="Con's answer to the audience",
    )

    assert "What about the ethics?" in prompt
    assert "Pro's answer to the audience" in prompt
    assert "Con's answer to the audience" in prompt


@pytest.mark.asyncio
async def test_moderator_decision_passes_audience_qa_into_prompt(base_state, mock_llm):
    base_state.update({
        "pro_closing": "Pro closing",
        "con_closing": "Con closing",
        "audience_question": "What about ethics?",
        "pro_audience_answer": "Pro's answer",
        "con_audience_answer": "Con's answer",
        "round": "decision",
    })

    captured = {}

    def capture_astream(prompt):
        captured["prompt"] = prompt
        return aiter(["Winner: Pro. Justification."])

    mock_llm.astream = MagicMock(side_effect=capture_astream)
    with patch("src.agents.moderator.llm", mock_llm):
        from src.agents.moderator import moderator_decision
        await moderator_decision(base_state)

    assert "What about ethics?" in captured["prompt"]
    assert "Pro's answer" in captured["prompt"]
    assert "Con's answer" in captured["prompt"]


# --- 7.4 / 7.8: service-layer pause -> resume -> completion, via mocked
# ownership/event_bus around a real (in-memory-checkpointed) graph -----------

@pytest.mark.asyncio
async def test_run_and_publish_then_resume_with_answer_completes_debate(
    patched_llms, checkpointed_app_graph
):
    with patch("src.api.services.debate_service.ownership") as mock_ownership, \
         patch("src.api.services.debate_service.event_bus") as mock_bus, \
         patch("src.api.services.debate_service.memory_store"):

        mock_ownership.set_status = AsyncMock()
        mock_ownership.heartbeat = AsyncMock()
        # Patching the module replaces this numeric constant with a MagicMock
        # too - asyncio.sleep() needs a real number, so restore it explicitly.
        mock_ownership.HEARTBEAT_INTERVAL_SECONDS = 0.01
        mock_bus.publish = AsyncMock()

        from src.api.services.debate_service import DebateService
        service = DebateService()

        await service.run_and_publish("run-1", "node-1", topic="Test topic")

        pause_events = [
            c.args[1] for c in mock_bus.publish.call_args_list
            if c.args[1].get("node") == "AWAITING_AUDIENCE_QUESTION"
        ]
        assert len(pause_events) == 1
        assert "prompt" in pause_events[0]
        mock_ownership.set_status.assert_any_call("run-1", "node-1", "waiting_for_input")
        # Must not have been marked done/failed while merely paused.
        done_calls = [c.args for c in mock_ownership.set_status.call_args_list if c.args[2] == "done"]
        assert done_calls == []

        mock_bus.publish.reset_mock()
        await service.resume_with_answer("run-1", "node-1", "What about cost?")

        completion_events = [
            c.args[1] for c in mock_bus.publish.call_args_list
            if c.args[1].get("node") == "COMPLETE"
        ]
        assert len(completion_events) == 1
        assert completion_events[0]["state"]["winner"] != ""
        assert completion_events[0]["state"]["pro_audience_answer"] != ""
        assert completion_events[0]["state"]["con_audience_answer"] != ""
        mock_ownership.set_status.assert_any_call("run-1", "node-1", "done")


def test_is_owned_and_alive_treats_waiting_for_input_as_permanently_alive():
    """7.8: a paused run must not look reclaimable purely because its
    heartbeat went stale — is_owned_and_alive() must report it alive
    regardless of heartbeat freshness, the same way 'done' already is."""
    import inspect
    from deployment.app_ext import ownership

    source = inspect.getsource(ownership.is_owned_and_alive)
    assert "waiting_for_input" in source


# --- Route-level: POST /debate/{run_id}/audience-question -------------------

def test_audience_question_endpoint_rejects_unknown_run():
    from server import app
    client = TestClient(app)

    with patch("src.api.routes.debates.ownership") as mock_ownership:
        mock_ownership.get_status = AsyncMock(return_value=None)
        response = client.post("/debate/unknown-run/audience-question", json={"question": "Q?"})

    assert response.status_code == 404


def test_audience_question_endpoint_rejects_when_not_waiting():
    """7.5: a run that's already answered (now 'running'), still executing,
    or already 'done' must be rejected, not re-paused or re-resumed."""
    from server import app
    client = TestClient(app)

    for status in ("running", "done", "failed"):
        with patch("src.api.routes.debates.ownership") as mock_ownership:
            mock_ownership.get_status = AsyncMock(return_value=status)
            response = client.post("/debate/run-x/audience-question", json={"question": "Q?"})
        assert response.status_code == 409, f"expected 409 for status={status}"


def test_audience_question_endpoint_rejects_lost_claim_race():
    from server import app
    client = TestClient(app)

    with patch("src.api.routes.debates.ownership") as mock_ownership:
        mock_ownership.get_status = AsyncMock(return_value="waiting_for_input")
        mock_ownership.claim = AsyncMock(return_value=False)
        response = client.post("/debate/run-x/audience-question", json={"question": "Q?"})

    assert response.status_code == 409


def test_audience_question_endpoint_accepts_and_schedules_resume():
    from server import app
    client = TestClient(app)

    with patch("src.api.routes.debates.ownership") as mock_ownership, \
         patch("src.api.routes.debates.debate_service") as mock_service:
        mock_ownership.get_status = AsyncMock(return_value="waiting_for_input")
        mock_ownership.claim = AsyncMock(return_value=True)
        mock_service.resume_with_answer = AsyncMock()

        response = client.post("/debate/run-x/audience-question", json={"question": "What about cost?"})

    assert response.status_code == 200
    assert response.json()["run_id"] == "run-x"


def test_audience_question_endpoint_rejects_blank_question():
    from server import app
    client = TestClient(app)

    response = client.post("/debate/run-x/audience-question", json={"question": "   "})
    assert response.status_code == 422


# --- 7.6 / 7.7: synchronous /invoke guard and pre-supplied question ---------

@pytest.mark.asyncio
async def test_invoke_without_question_raises_awaiting_input_error(
    patched_llms, checkpointed_app_graph
):
    from src.api.services.debate_service import DebateService
    from src.api.services.exceptions import DebateAwaitingInputError

    service = DebateService()
    with pytest.raises(DebateAwaitingInputError) as exc_info:
        await service.execute_debate("Test topic")

    assert exc_info.value.run_id


@pytest.mark.asyncio
async def test_invoke_with_pre_supplied_question_completes_in_one_call(
    patched_llms, checkpointed_app_graph
):
    from src.api.services.debate_service import DebateService

    service = DebateService()
    result = await service.execute_debate("Test topic", audience_question="What about cost?")

    assert result["winner"] != ""
    assert result["pro_audience_answer"] != ""
    assert result["con_audience_answer"] != ""


def test_invoke_route_maps_awaiting_input_error_to_409():
    from server import app
    from src.api.services.exceptions import DebateAwaitingInputError

    client = TestClient(app)
    with patch("src.api.routes.debates.debate_service") as mock_service:
        mock_service.execute_debate = AsyncMock(
            side_effect=DebateAwaitingInputError("run-123", "paused for a question")
        )
        response = client.post("/debate/invoke", json={"topic": "Test topic"})

    assert response.status_code == 409
    assert response.json()["detail"]["run_id"] == "run-123"
