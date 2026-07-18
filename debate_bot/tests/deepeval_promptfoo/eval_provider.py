"""Shared seam for Approach C — wraps ``run_debate`` and the shared dataset.

Both the deepeval option and the promptfoo option call through here so they run
the *exact same* debate seam and dataset as Approach A, keeping the numbers
comparable across approaches.

    from tests.deepeval_promptfoo.eval_provider import run_debate_sync, load_topics
    state = run_debate_sync("AI will replace software engineers")

The final state dict has the shape documented in ``app.run_debate``:
    {topic, round, pro_opening, con_opening, pro_rebuttal, con_rebuttal,
     pro_closing, con_closing, moderator_summary, winner, memory_context}
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path

# Dataset source of truth is shared with Approach A — do NOT fork it.
_DATASET = (
    Path(__file__).resolve().parents[1]
    / "custom_pytest"
    / "evals"
    / "datasets"
    / "topics.jsonl"
)

# Debate generation (7 agent calls/topic) dwarfs judge scoring in token cost,
# and the eval reruns the same handful of topics constantly. The debate
# outcome itself isn't under test here — only the judge's scoring of it is —
# so cache each topic's debate transcript locally and skip regenerating it.
# Gate via .env: EVAL_CACHE_DEBATES=false forces a live run every time.
_CACHE_DIR = Path(__file__).resolve().parent / ".debate_cache"


def _cache_enabled() -> bool:
    return os.getenv("EVAL_CACHE_DEBATES", "true").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def _cache_path(topic: str) -> Path:
    # Keyed on the debating model too — a MODEL_NAME change must miss cache.
    model = os.getenv("MODEL_NAME", "default")
    digest = hashlib.sha256(f"{model}:{topic}".encode("utf-8")).hexdigest()[:16]
    return _CACHE_DIR / f"{digest}.json"


def load_topics(path: Path = _DATASET) -> list[dict]:
    """Load the shared golden topics (one JSON object per line)."""
    topics: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                topics.append(json.loads(line))
    return topics


async def run_debate_async(topic: str) -> dict:
    """Run one full debate and return the final state (async).

    Reads/writes the on-disk debate cache when ``EVAL_CACHE_DEBATES`` is not
    disabled (default: enabled); otherwise always hits the live model.
    """
    if _cache_enabled():
        cache_path = _cache_path(topic)
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))

    # Imported lazily so importing this module (e.g. for ``load_topics``) does
    # not require the model stack or an API key.
    from app import run_debate

    state = await run_debate(topic)

    if _cache_enabled():
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(topic).write_text(json.dumps(state, indent=2), encoding="utf-8")

    return state


def run_debate_sync(topic: str) -> dict:
    """Blocking wrapper — convenient for the promptfoo provider and notebooks."""
    return asyncio.run(run_debate_async(topic))


def as_testcase_fields(state: dict) -> dict:
    """Project a debate state onto the strings the eval metrics consume.

    Keeps the field selection in one place so deepeval and promptfoo score the
    same slices of the transcript.
    """
    return {
        "topic": state.get("topic", ""),
        # Relevance: does the Pro opening argue FOR the topic and stay on-topic?
        "pro_opening": state.get("pro_opening", ""),
        "con_opening": state.get("con_opening", ""),
        # Rebuttal engagement: Con rebuttal vs the Pro opening it should engage.
        "pro_point": state.get("pro_opening", ""),
        "con_rebuttal": state.get("con_rebuttal", ""),
        # Moderator soundness: the decision vs the arguments it saw (closings).
        "arguments": (
            f"Pro closing:\n{state.get('pro_closing', '')}\n\n"
            f"Con closing:\n{state.get('con_closing', '')}"
        ),
        "moderator_summary": state.get("moderator_summary", ""),
        "winner": state.get("winner", ""),
    }
