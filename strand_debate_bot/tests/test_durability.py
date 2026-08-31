"""In-process simulated-restart tests (design.md, Decision 5): a second
`build_graph()` call, against the same `run_id`/`storage_dir`, stands in for
a process restart. The one real subprocess-kill test lives in
test_durability_subprocess.py (tasks.md, Section 7)."""

import pytest
from strands.multiagent.base import Status

from src.core.graph import build_graph
from src.core.session import (
    InvocationStatePersistenceHook,
    load_invocation_state,
    read_persisted_graph_status,
    save_invocation_state,
)
from src.core.state import build_invocation_state
from tests.fakes import FakeMemoryStore, FakeModel


# -- src/core/session.py -----------------------------------------------------


def test_save_and_load_invocation_state_round_trips(tmp_path):
    storage_dir = str(tmp_path)
    save_invocation_state(storage_dir, "run-1", {"topic": "T", "pro_opening": "hello"})

    assert load_invocation_state(storage_dir, "run-1") == {"topic": "T", "pro_opening": "hello"}


def test_load_invocation_state_missing_file_returns_none(tmp_path):
    assert load_invocation_state(str(tmp_path), "never-started") is None


@pytest.mark.asyncio
async def test_node_completion_persists_invocation_state_to_disk(tmp_path):
    """spec: "A run's accumulated content survives a process restart" """
    storage_dir = str(tmp_path)
    run_id = "persist-on-node-stop"
    model = FakeModel(text="turn text", structured={"winner": "Pro", "justification": "j"})
    graph = build_graph(model=model, memory_store=FakeMemoryStore(), run_id=run_id, session_storage_dir=storage_dir)
    state = build_invocation_state("Topic")
    state["audience_question"] = "Pre-supplied question?"

    async for event in graph.stream_async("run", invocation_state=state):
        if event.get("type") == "multiagent_node_stop" and event.get("node_id") == "pro_opening":
            break

    on_disk = load_invocation_state(storage_dir, run_id)
    assert on_disk["pro_opening"].strip() == "turn text"
    assert on_disk["con_opening"] == ""  # not reached yet


# -- src/core/graph.py session-manager wiring ---------------------------------


def test_building_a_graph_writes_an_initial_checkpoint_before_any_node_runs(tmp_path):
    """spec: "A run is resumable as soon as its identifier has been issued" """
    storage_dir = str(tmp_path)
    run_id = "checkpoint-on-construction"

    build_graph(model=FakeModel(), memory_store=FakeMemoryStore(), run_id=run_id, session_storage_dir=storage_dir)

    status = read_persisted_graph_status(storage_dir, run_id)
    assert status is not None
    assert status.status == "pending"


@pytest.mark.asyncio
async def test_resume_continues_without_rerunning_completed_rounds(tmp_path):
    """spec: "Resuming continues from the last completed step, not from the beginning" """
    storage_dir = str(tmp_path)
    run_id = "resume-mid-execution"
    model = FakeModel(text="turn text", structured={"winner": "Pro", "justification": "j"})
    memory_store = FakeMemoryStore()

    graph = build_graph(model=model, memory_store=memory_store, run_id=run_id, session_storage_dir=storage_dir)
    state = build_invocation_state("Topic")
    state["audience_question"] = "Pre-supplied question?"

    async for event in graph.stream_async("run", invocation_state=state):
        if event.get("type") == "multiagent_node_stop" and event.get("node_id") == "con_opening":
            break  # simulated kill: right after the opening round completes

    assert len(model.calls) == 2  # pro_opening, con_opening -- nothing further ran

    # "Restart": a fresh Graph for the same run_id/storage_dir, invocation_state
    # reloaded from disk rather than reusing the in-memory `state` above.
    restored_state = load_invocation_state(storage_dir, run_id)
    assert restored_state["pro_opening"].strip() == "turn text"
    assert restored_state["con_opening"].strip() == "turn text"
    assert restored_state["pro_rebuttal"] == ""

    resumed_graph = build_graph(
        model=model, memory_store=memory_store, run_id=run_id, session_storage_dir=storage_dir
    )
    result = await resumed_graph.invoke_async("resume", invocation_state=restored_state)

    assert result.status == Status.COMPLETED
    assert restored_state["winner"] == "Pro"
    # 10 total calls for an uninterrupted full run (test_graph.py's 8 turn calls plus
    # 2 for FakeModel's structured-output round trip on the verdict) -- if the opening
    # round had re-run, pro_opening/con_opening would each add one more, making 12.
    assert len(model.calls) == 10


@pytest.mark.asyncio
async def test_resume_of_a_run_paused_on_the_audience_question_stays_paused(tmp_path):
    """spec: "A run that was paused awaiting an audience question resumes paused" """
    storage_dir = str(tmp_path)
    run_id = "resume-while-paused"
    model = FakeModel(text="turn text", structured={"winner": "Pro", "justification": "j"})
    memory_store = FakeMemoryStore()

    graph = build_graph(model=model, memory_store=memory_store, run_id=run_id, session_storage_dir=storage_dir)
    state = build_invocation_state("Topic")

    result = await graph.invoke_async("run", invocation_state=state)
    assert result.status == Status.INTERRUPTED

    # "Restart": persisted status/interrupt id read directly off disk, as the
    # resume endpoint does, without trusting the (still in-memory) `graph`/`result`.
    persisted = read_persisted_graph_status(storage_dir, run_id)
    assert persisted.status == "interrupted"
    assert persisted.pending_interrupt_id == result.interrupts[0].id

    restored_state = load_invocation_state(storage_dir, run_id)
    resumed_graph = build_graph(
        model=model, memory_store=memory_store, run_id=run_id, session_storage_dir=storage_dir
    )
    final = await resumed_graph.invoke_async(
        [{"interruptResponse": {"interruptId": persisted.pending_interrupt_id, "response": "What about cost?"}}],
        invocation_state=restored_state,
    )

    assert final.status == Status.COMPLETED
    assert restored_state["audience_question"] == "What about cost?"


def test_persistence_hook_ignores_events_with_no_invocation_state():
    """AfterMultiAgentInvocationEvent's invocation_state is optional (strands/hooks/events.py) --
    the hook must not raise or write a garbage file when it's absent."""
    hook = InvocationStatePersistenceHook("unused-dir", "unused-run")

    class _FakeEvent:
        invocation_state = None

    hook._persist(_FakeEvent())  # should not raise
