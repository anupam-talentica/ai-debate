import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel
from strands import Agent
from strands.hooks import BeforeNodeCallEvent, HookProvider, HookRegistry
from strands.memory.types import MemoryStore
from strands.models.model import Model
from strands.multiagent.base import MultiAgentBase, MultiAgentResult, Status

from src.core import config
from src.core.mock_transcripts import load_transcript
from src.core.prompts import MODERATOR_DECISION_SYSTEM, format_memory_block, moderator_decision_prompt
from src.core.state import ROUND_TRANSITIONS

logger = logging.getLogger(__name__)


class ModeratorHub(MultiAgentBase):
    """Revisited once per round; advances the round counter that the graph's
    outgoing conditional edges route on. Merges the old moderator_open and
    moderator_checkpoint nodes into a single hub (design.md, Decision 1).

    Also performs cross-debate memory's one retrieval call, on the one-time
    ""->"opening" transition (design.md, Decision 3): best-effort, since the
    hub is the single mandatory routing point every run passes through, and a
    store failure here must not stop a debate from starting."""

    def __init__(self, memory_store: MemoryStore) -> None:
        super().__init__()
        self.id = "moderator"
        self._memory_store = memory_store

    async def invoke_async(
        self, task: Any, invocation_state: dict[str, Any] | None = None, **kwargs: Any
    ) -> MultiAgentResult:
        current = invocation_state.get("round", "")
        next_round = ROUND_TRANSITIONS[current]
        invocation_state["round"] = next_round

        if next_round == "opening":
            invocation_state["memory_context"] = await self._retrieve_memory_context(invocation_state["topic"])

        return MultiAgentResult(status=Status.COMPLETED)

    async def _retrieve_memory_context(self, topic: str) -> str:
        try:
            entries = await self._memory_store.search(topic)
        except Exception:
            logger.exception("memory store search failed; proceeding with no past-debate context")
            return ""
        return format_memory_block([entry.content for entry in entries])


class AudienceQuestionStub(MultiAgentBase):
    """The audience round's pause point. Performs no work itself -- by the time
    this node's invoke_async runs, `AudienceQuestionHook` has already either
    found a pre-supplied question or resumed with a submitted one and written
    it into invocation_state["audience_question"] (design.md, Decision 2)."""

    def __init__(self) -> None:
        super().__init__()
        self.id = "audience_question"

    async def invoke_async(
        self, task: Any, invocation_state: dict[str, Any] | None = None, **kwargs: Any
    ) -> MultiAgentResult:
        return MultiAgentResult(status=Status.COMPLETED)


class AudienceQuestionHook(HookProvider):
    """Pauses the graph before the `audience_question` node runs, unless a
    question was already supplied in invocation_state (design.md, Decisions
    2-3). Strands graph-node interrupts only exist via a BeforeNodeCallEvent
    hook -- a plain node has no interrupt call available inside its own
    invoke_async (scaffolding-spike findings.md, Open Question 1)."""

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeNodeCallEvent, self._pause_for_question)

    def _pause_for_question(self, event: BeforeNodeCallEvent) -> None:
        if event.node_id != "audience_question":
            return
        if event.invocation_state.get("audience_question"):
            return

        question = event.interrupt("audience_question", reason="Waiting for an audience question")
        event.invocation_state["audience_question"] = question


class Verdict(BaseModel):
    winner: Literal["Pro", "Con"]
    justification: str


SUMMARY_OPENING_CHAR_CAP = 200


class ModeratorDecision(MultiAgentBase):
    """Terminal node, reached only from the hub's "done" round (design.md, Decision 3).
    Produces a structured verdict instead of the old free-text "winner:" heuristic.

    Also performs cross-debate memory's one write call, immediately after the
    verdict is known (design.md, Decision 4) -- the single site where a debate
    both is complete and knows its own outcome."""

    def __init__(self, agent: Agent, memory_store: MemoryStore) -> None:
        super().__init__()
        self.id = "moderator_decision"
        self._agent = agent
        self._memory_store = memory_store

    async def invoke_async(
        self, task: Any, invocation_state: dict[str, Any] | None = None, **kwargs: Any
    ) -> MultiAgentResult:
        prompt = moderator_decision_prompt(invocation_state)
        result = await self._agent.invoke_async(prompt, structured_output_model=Verdict)
        verdict = result.structured_output
        invocation_state["winner"] = verdict.winner
        invocation_state["justification"] = verdict.justification

        summary = _build_debate_summary(invocation_state)
        await self._memory_store.add(summary, metadata={"topic": invocation_state["topic"], "winner": verdict.winner})

        return MultiAgentResult(status=Status.COMPLETED)


def _build_debate_summary(invocation_state: dict[str, Any]) -> str:
    pro_opening = invocation_state["pro_opening"][:SUMMARY_OPENING_CHAR_CAP]
    con_opening = invocation_state["con_opening"][:SUMMARY_OPENING_CHAR_CAP]
    return (
        f"Topic: {invocation_state['topic']} | "
        f"Pro: {pro_opening} | "
        f"Con: {con_opening} | "
        f"Winner: {invocation_state['winner']}"
    )


def moderator_decision_node(model: Model, memory_store: MemoryStore) -> ModeratorDecision:
    agent = Agent(model=model, system_prompt=MODERATOR_DECISION_SYSTEM)
    return ModeratorDecision(agent, memory_store)


def _normalize_winner(raw: str) -> Literal["Pro", "Con"]:
    """Cleans a cached transcript's `winner` field (e.g. old fixtures' regex-
    heuristic fossil `"Con**"`) into the real `Verdict` model's clean
    `Literal["Pro","Con"]` (design.md, Decision 3). Scoped to mock mode only
    -- the real decision path always gets a clean value from structured
    output and never calls this."""
    cleaned = re.sub(r"[^A-Za-z]", "", raw).strip().lower()
    if cleaned == "pro":
        return "Pro"
    if cleaned == "con":
        return "Con"
    raise ValueError(f"MockModeratorDecision: cannot normalize winner {raw!r} to 'Pro' or 'Con'")


class MockModeratorDecision(MultiAgentBase):
    """Replays a cached transcript's verdict instead of calling the model,
    matching `ModeratorDecision`'s output shape exactly: a clean `winner`
    (`_normalize_winner`) and a `justification` sourced from the cached
    transcript's free-text `moderator_summary` field (design.md, Decision 3).
    Does not write to the memory store -- that write is a real-debate-outcome
    concern, out of scope for a replayed decision (proposal.md)."""

    def __init__(self, cache_dir: Path | None = None, delay_seconds: float | None = None) -> None:
        super().__init__()
        self.id = "moderator_decision"
        self._cache_dir = cache_dir
        self._delay_seconds = delay_seconds

    async def invoke_async(
        self, task: Any, invocation_state: dict[str, Any] | None = None, **kwargs: Any
    ) -> MultiAgentResult:
        delay = self._delay_seconds if self._delay_seconds is not None else config.MOCK_LLM_DELAY_SECONDS
        await asyncio.sleep(delay)
        transcript = load_transcript(invocation_state["topic"], cache_dir=self._cache_dir)
        invocation_state["winner"] = _normalize_winner(transcript.get("winner", ""))
        invocation_state["justification"] = transcript.get("moderator_summary", "")
        return MultiAgentResult(status=Status.COMPLETED)
