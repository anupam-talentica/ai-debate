"""Approach B runner: evaluate the debate bot against the LangSmith dataset.

Wraps ``app.run_debate`` as the evaluation target and scores every topic with
the shared evaluators. Because ``LANGCHAIN_TRACING_V2=true`` is set, every
``run_debate`` call auto-emits a LangGraph trace, so per-node latency + event
ordering show up in the LangSmith trace view for free (the performance /
streaming dimension).

Usage:
    export LANGSMITH_API_KEY=...
    export LANGCHAIN_TRACING_V2=true
    export ANTHROPIC_API_KEY=...
    python tests/lang_smith/upload_dataset.py     # once
    python tests/lang_smith/run_eval.py           # each eval run
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure the repo root (debate_bot/) is importable so `app` and the shared
# scorers resolve regardless of the current working directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from langsmith import Client
from langsmith.evaluation import aevaluate

from app import run_debate
from tests.lang_smith.evaluators import EVALUATORS
from tests.lang_smith.upload_dataset import _load_topics

DATASET_NAME = "debate-topics"
NUM_TOPICS = 3  # only evaluate the first N topics from topics.jsonl


def _first_n_examples(n: int) -> list[dict]:
    """Return the LangSmith examples for the first `n` topics in topics.jsonl.

    Filters by the shared `id` metadata rather than trusting LangSmith's
    example ordering, which isn't guaranteed to match upload order.
    """
    target_ids = {row["id"] for row in _load_topics()[:n]}
    client = Client()
    examples = client.list_examples(dataset_name=DATASET_NAME)
    return [ex for ex in examples if (ex.metadata or {}).get("id") in target_ids]


async def _target(inputs: dict) -> dict:
    """Run one debate and return the final state as the run's outputs.

    Runs on the single event loop started by ``asyncio.run(main())`` below, so
    the shared debate graph/memory store and each agent's ``ChatAnthropic``
    client (module-level singletons, see app.py / src/agents/*.py) stay bound
    to one loop for their entire lifetime instead of being torn down and
    reused across a fresh loop per example.
    """
    return await run_debate(inputs["topic"])


async def main() -> None:
    results = await aevaluate(
        _target,
        data=_first_n_examples(NUM_TOPICS),
        evaluators=EVALUATORS,
        experiment_prefix="debate-eval",
        # Shared module-level graph/memory store is not thread-safe; run serially.
        max_concurrency=1,
        metadata={"approach": "B", "runner": "langsmith"},
    )
    # `results` is an AsyncExperimentResults; print the hosted URL for convenience.
    exp_name = getattr(results, "experiment_name", None)
    print(f"\nExperiment complete: {exp_name or 'see LangSmith UI'}")
    print("Scores + per-node LangGraph traces are in the LangSmith dashboard.")


if __name__ == "__main__":
    asyncio.run(main())
