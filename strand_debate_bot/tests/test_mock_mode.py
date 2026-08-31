import json
import logging
import time
from pathlib import Path

import pytest
from strands.multiagent.base import Status

from src.agents.moderator import MockModeratorDecision
from src.core import config
from src.core.graph import build_graph
from src.core.mock_transcripts import load_transcript
from src.core.nodes import MockTurnNode
from src.core.state import build_invocation_state
from tests.fakes import FakeMemoryStore, FakeModel

FIXTURE_CACHE_DIR = Path(__file__).resolve().parent / "mock_cache"


def _write_transcript(cache_dir, filename, **fields):
    (cache_dir / filename).write_text(json.dumps(fields), encoding="utf-8")


# --- Transcript lookup (tasks 3.2, 3.3) ---------------------------------


def test_exact_topic_match_returns_that_transcript(tmp_path):
    _write_transcript(tmp_path, "a.json", topic="Topic A", pro_opening="A's opening")
    _write_transcript(tmp_path, "b.json", topic="Topic B", pro_opening="B's opening")

    transcript = load_transcript("topic b", cache_dir=tmp_path)  # case-insensitive match

    assert transcript["pro_opening"] == "B's opening"


def test_no_match_falls_back_to_filename_sorted_first_and_logs_warning(tmp_path, caplog):
    _write_transcript(tmp_path, "a.json", topic="Topic A", pro_opening="A's opening")
    _write_transcript(tmp_path, "b.json", topic="Topic B", pro_opening="B's opening")

    with caplog.at_level(logging.WARNING):
        transcript = load_transcript("Some novel topic", cache_dir=tmp_path)

    assert transcript["pro_opening"] == "A's opening"  # "a.json" sorts first
    assert any("no cached transcript matches" in record.message for record in caplog.records)


def test_no_cached_transcripts_raises(tmp_path):
    with pytest.raises(RuntimeError):
        load_transcript("Any topic", cache_dir=tmp_path)


# --- MockTurnNode (tasks 4.2, 4.3) --------------------------------------


@pytest.mark.asyncio
async def test_mock_turn_node_writes_its_own_field_from_the_transcript(tmp_path):
    _write_transcript(
        tmp_path,
        "only.json",
        topic="Topic",
        pro_opening="Pro's opening text",
        con_rebuttal="Con's rebuttal text",
    )
    state = build_invocation_state("Topic")

    pro_opening_node = MockTurnNode("pro_opening", "pro_opening", cache_dir=tmp_path, delay_seconds=0)
    con_rebuttal_node = MockTurnNode("con_rebuttal", "con_rebuttal", cache_dir=tmp_path, delay_seconds=0)

    await pro_opening_node.invoke_async("run", invocation_state=state)
    await con_rebuttal_node.invoke_async("run", invocation_state=state)

    assert state["pro_opening"] == "Pro's opening text"
    assert state["con_rebuttal"] == "Con's rebuttal text"


@pytest.mark.asyncio
async def test_mock_turn_node_honors_configured_delay(tmp_path):
    _write_transcript(tmp_path, "only.json", topic="Topic", pro_opening="text")
    state = build_invocation_state("Topic")
    node = MockTurnNode("pro_opening", "pro_opening", cache_dir=tmp_path, delay_seconds=0.05)

    start = time.monotonic()
    await node.invoke_async("run", invocation_state=state)
    elapsed = time.monotonic() - start

    assert elapsed >= 0.05


@pytest.mark.asyncio
async def test_mock_turn_node_defaults_to_config_delay_when_unset(tmp_path, monkeypatch):
    _write_transcript(tmp_path, "only.json", topic="Topic", pro_opening="text")
    state = build_invocation_state("Topic")
    node = MockTurnNode("pro_opening", "pro_opening", cache_dir=tmp_path)  # no explicit delay_seconds

    monkeypatch.setattr(config, "MOCK_LLM_DELAY_SECONDS", 0.02)

    start = time.monotonic()
    await node.invoke_async("run", invocation_state=state)
    elapsed = time.monotonic() - start

    assert elapsed >= 0.02


# --- MockModeratorDecision (tasks 5.2, 5.3) -----------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("topic", ["AI will replace software engineers", "Pro athletes are overpaid"])
async def test_mock_decision_replays_real_fixtures_with_clean_verdict(topic):
    """Replays both committed fixtures (winner: "Con**" in the raw JSON) and
    confirms the verdict is structurally compatible with the real
    `ModeratorDecision`'s output (spec: "Mock mode verdict is structurally
    compatible with the real verdict")."""
    state = build_invocation_state(topic)
    decision = MockModeratorDecision(cache_dir=FIXTURE_CACHE_DIR, delay_seconds=0)

    result = await decision.invoke_async("run", invocation_state=state)

    assert result.status == Status.COMPLETED
    assert state["winner"] == "Con"  # normalized from the fixtures' dirty "Con**"
    assert state["justification"]  # non-empty, copied from moderator_summary


@pytest.mark.asyncio
async def test_mock_decision_raises_on_unrecognizable_winner(tmp_path):
    _write_transcript(tmp_path, "bad.json", topic="Topic", winner="Neither", moderator_summary="...")
    state = build_invocation_state("Topic")
    decision = MockModeratorDecision(cache_dir=tmp_path, delay_seconds=0)

    with pytest.raises(ValueError):
        await decision.invoke_async("run", invocation_state=state)


@pytest.mark.asyncio
async def test_mock_decision_honors_configured_delay(tmp_path):
    _write_transcript(tmp_path, "only.json", topic="Topic", winner="Pro", moderator_summary="j")
    state = build_invocation_state("Topic")
    decision = MockModeratorDecision(cache_dir=tmp_path, delay_seconds=0.05)

    import time

    start = time.monotonic()
    await decision.invoke_async("run", invocation_state=state)
    elapsed = time.monotonic() - start

    assert elapsed >= 0.05


# --- Graph wiring (tasks 6.2, 6.3) --------------------------------------


@pytest.mark.asyncio
async def test_mock_graph_completes_without_calling_the_model_for_mocked_turns():
    """Full debate run with mock=True: opening/rebuttal/closing/decision come
    from the cached transcript with zero model calls; only the two
    audience-question turns call the (fake) model, matching FR-11's
    exemption (spec: "Full debate run makes zero live API calls" /
    "Audience-question turns are never mocked")."""
    model = FakeModel(text="live audience answer")
    graph = build_graph(model=model, memory_store=FakeMemoryStore(), mock=True)
    state = build_invocation_state("A topic never seen in any fixture")
    state["audience_question"] = "Pre-supplied question?"  # skip the interrupt/pause

    result = await graph.invoke_async("run", invocation_state=state)

    assert result.status == Status.COMPLETED
    assert state["winner"] in ("Pro", "Con")
    assert state["justification"]
    for key in ["pro_opening", "con_opening", "pro_rebuttal", "con_rebuttal", "pro_closing", "con_closing"]:
        assert state[key] != ""
    # Only the two audience-question turns ever call the model in mock mode.
    assert len(model.calls) == 2
    assert state["pro_audience_answer"].strip() == "live audience answer"
    assert state["con_audience_answer"].strip() == "live audience answer"


@pytest.mark.asyncio
async def test_non_mock_graph_is_unaffected_by_default():
    """`build_graph()` with no `mock` argument (the default) wires the real
    Agent-backed nodes exactly as before -- no regression to the non-mock
    path (task 6.3)."""
    model = FakeModel(text="turn text", structured={"winner": "Pro", "justification": "j"})
    graph = build_graph(model=model, memory_store=FakeMemoryStore())
    state = build_invocation_state("Topic")
    state["audience_question"] = "Pre-supplied question?"

    result = await graph.invoke_async("run", invocation_state=state)

    assert result.status == Status.COMPLETED
    # Every argument turn, both audience turns, and the decision all went
    # through the real model -- unlike mock mode's 2 (asserted above), where
    # only the audience turns call it.
    assert len(model.calls) > 2
    assert state["pro_opening"].strip() == "turn text"
    assert state["winner"] == "Pro"
    assert state["justification"] == "j"
