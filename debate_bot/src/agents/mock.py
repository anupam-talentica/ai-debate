"""Mock agent nodes for MOCK_LLM=true.

Replays a cached debate transcript instead of calling the real model, so the
UI/failover demo can be exercised without spending API tokens. Reuses the same
cache the deepeval/promptfoo harness writes to (tests/deepeval_promptfoo/.debate_cache/)
rather than maintaining a separate fixture — see tests/deepeval_promptfoo/eval_provider.py
for how those files are produced.

Wired in by src/core/graph.py, which imports these in place of the real
src/agents/{pro,con,moderator}.py functions when MOCK_LLM is set. Only the
LLM-calling nodes are replaced — moderator_open/moderator_checkpoint do no
model call in the real implementation either, so they're always real.
"""

import asyncio
import json
import logging
import os
from pathlib import Path

from src.core.state import DebateState

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parents[2] / "tests" / "deepeval_promptfoo" / ".debate_cache"
MOCK_DELAY_SECONDS = float(os.getenv("MOCK_LLM_DELAY_SECONDS", "1.5"))


def _load_transcript(topic: str) -> dict:
    """Find a cached transcript matching `topic`, falling back to whichever
    cached transcript comes first so mock mode still works for a topic that
    was never cached."""
    candidates = sorted(_CACHE_DIR.glob("*.json")) if _CACHE_DIR.is_dir() else []
    if not candidates:
        raise RuntimeError(
            f"MOCK_LLM is enabled but no cached transcripts exist at {_CACHE_DIR} — "
            "run one real debate (or `pytest tests/deepeval_promptfoo`) first to seed it."
        )

    topic_key = topic.strip().lower()
    for path in candidates:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("topic", "").strip().lower() == topic_key:
            return data

    logger.warning(f"MOCK_LLM: no cached transcript matches topic {topic!r} — replaying {candidates[0].name}")
    return json.loads(candidates[0].read_text(encoding="utf-8"))


async def _mock_field(state: DebateState, field: str) -> str:
    await asyncio.sleep(MOCK_DELAY_SECONDS)
    return _load_transcript(state["topic"]).get(field, "")


async def pro_opening(state: DebateState) -> dict:
    return {"pro_opening": await _mock_field(state, "pro_opening"), "memory_context": []}


async def con_opening(state: DebateState) -> dict:
    return {"con_opening": await _mock_field(state, "con_opening"), "memory_context": []}


async def pro_rebuttal(state: DebateState) -> dict:
    return {"pro_rebuttal": await _mock_field(state, "pro_rebuttal")}


async def con_rebuttal(state: DebateState) -> dict:
    await asyncio.sleep(10)
    return {"con_rebuttal": await _mock_field(state, "con_rebuttal")}


async def pro_closing(state: DebateState) -> dict:
    return {"pro_closing": await _mock_field(state, "pro_closing")}


async def con_closing(state: DebateState) -> dict:
    return {"con_closing": await _mock_field(state, "con_closing")}


async def moderator_decision(state: DebateState) -> dict:
    await asyncio.sleep(MOCK_DELAY_SECONDS)
    transcript = _load_transcript(state["topic"])
    return {"moderator_summary": transcript.get("moderator_summary", ""), "winner": transcript.get("winner", "")}
