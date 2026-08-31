import pytest

from src.agents.moderator import moderator_decision_node, ModeratorHub
from src.core.memory import ChromaMemoryStore
from src.core.prompts import format_memory_block
from src.core.state import build_invocation_state
from tests.fakes import FakeMemoryStore, FakeModel


@pytest.mark.asyncio
async def test_add_then_search_returns_the_added_entry(tmp_path):
    store = ChromaMemoryStore(str(tmp_path))

    await store.add(
        "Topic: Should AI replace human judges? | Pro: efficiency argument | Winner: Pro",
        metadata={"topic": "Should AI replace human judges?", "winner": "Pro"},
    )

    entries = await store.search("Should courts use AI to assist judges?")

    assert len(entries) == 1
    assert "Should AI replace human judges" in entries[0].content
    assert entries[0].metadata["winner"] == "Pro"


@pytest.mark.asyncio
async def test_search_on_empty_store_returns_no_results(tmp_path):
    store = ChromaMemoryStore(str(tmp_path))

    entries = await store.search("Any topic at all")

    assert entries == []


def test_format_memory_block_with_no_entries_is_empty():
    assert format_memory_block([]) == ""


def test_format_memory_block_wraps_a_single_entry():
    block = format_memory_block(["Topic: X | Pro: ... | Winner: Pro"])

    assert "do not reference explicitly" in block
    assert "Topic: X | Pro: ... | Winner: Pro" in block


def test_format_memory_block_caps_combined_length():
    entries = ["a" * 1000, "b" * 1000]

    block = format_memory_block(entries)

    # cap applies to the joined entry text, not the whole rendered block
    header, _, body = block.partition(":\n")
    assert len(body) <= 1200


@pytest.mark.asyncio
async def test_hub_populates_memory_context_on_first_visit():
    memory_store = FakeMemoryStore(["Topic: Old debate | Pro: efficiency | Winner: Pro"])
    hub = ModeratorHub(memory_store)
    state = build_invocation_state("Topic")

    await hub.invoke_async("run", invocation_state=state)

    assert state["round"] == "opening"
    assert "Old debate" in state["memory_context"]


@pytest.mark.asyncio
async def test_hub_memory_context_stays_empty_on_cold_store():
    memory_store = FakeMemoryStore([])
    hub = ModeratorHub(memory_store)
    state = build_invocation_state("Topic")

    await hub.invoke_async("run", invocation_state=state)

    assert state["memory_context"] == ""


@pytest.mark.asyncio
async def test_hub_degrades_to_empty_context_on_search_failure():
    memory_store = FakeMemoryStore(raise_on_search=True)
    hub = ModeratorHub(memory_store)
    state = build_invocation_state("Topic")

    await hub.invoke_async("run", invocation_state=state)  # must not raise

    assert state["round"] == "opening"
    assert state["memory_context"] == ""


@pytest.mark.asyncio
async def test_moderator_decision_writes_summary_exactly_once():
    memory_store = FakeMemoryStore()
    model = FakeModel(structured={"winner": "Pro", "justification": "j"})
    decision = moderator_decision_node(model, memory_store)
    state = build_invocation_state("Should AI replace human judges?")
    state["pro_opening"] = "Pro's opening"
    state["con_opening"] = "Con's opening"
    state["pro_closing"] = "Pro's closing"
    state["con_closing"] = "Con's closing"

    await decision.invoke_async("run", invocation_state=state)

    assert len(memory_store.added) == 1
    summary, metadata = memory_store.added[0]
    assert "Should AI replace human judges?" in summary
    assert "Pro" in summary
    assert metadata["winner"] == "Pro"
