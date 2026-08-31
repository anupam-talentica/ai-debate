"""Shared graph-node primitives.

Every debate-turn node builds its own prompt from `invocation_state` and calls
its `Agent` directly, rather than relying on the graph's dependency-based
auto-stitched input -- see design.md, Decision 4. This keeps every node's
data flow uniform: `invocation_state` in, `invocation_state` out.
"""

import asyncio
from pathlib import Path
from typing import Any, Callable

from strands import Agent
from strands.multiagent.base import MultiAgentBase, MultiAgentResult, Status

from src.core import config
from src.core.mock_transcripts import load_transcript


class AgentTurnNode(MultiAgentBase):
    """A single debate turn: build a prompt from invocation_state, call an Agent, store the text."""

    def __init__(
        self,
        node_id: str,
        agent: Agent,
        build_prompt: Callable[[dict[str, Any]], str],
        store_key: str,
    ) -> None:
        super().__init__()
        self.id = node_id
        self._agent = agent
        self._build_prompt = build_prompt
        self._store_key = store_key

    async def invoke_async(
        self, task: Any, invocation_state: dict[str, Any] | None = None, **kwargs: Any
    ) -> MultiAgentResult:
        prompt = self._build_prompt(invocation_state)
        result = await self._agent.invoke_async(prompt)
        invocation_state[self._store_key] = str(result)
        return MultiAgentResult(status=Status.COMPLETED)


class MockTurnNode(MultiAgentBase):
    """A single debate turn replayed from a cached transcript instead of a
    live model call (design.md, Decision 1). Satisfies the same
    `invoke_async(task, invocation_state) -> MultiAgentResult` contract as
    `AgentTurnNode`, so `build_graph()` can swap the two at graph-build time
    without any graph-edge or downstream-consumer changes."""

    def __init__(
        self,
        node_id: str,
        store_key: str,
        cache_dir: Path | None = None,
        delay_seconds: float | None = None,
    ) -> None:
        super().__init__()
        self.id = node_id
        self._store_key = store_key
        self._cache_dir = cache_dir
        self._delay_seconds = delay_seconds

    async def invoke_async(
        self, task: Any, invocation_state: dict[str, Any] | None = None, **kwargs: Any
    ) -> MultiAgentResult:
        delay = self._delay_seconds if self._delay_seconds is not None else config.MOCK_LLM_DELAY_SECONDS
        await asyncio.sleep(delay)
        transcript = load_transcript(invocation_state["topic"], cache_dir=self._cache_dir)
        invocation_state[self._store_key] = transcript.get(self._store_key, "")
        return MultiAgentResult(status=Status.COMPLETED)
