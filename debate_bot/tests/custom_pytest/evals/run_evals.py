"""CLI entry point: run real debates over the dataset and emit a scorecard.

    cd debate_bot
    export ANTHROPIC_API_KEY=...
    export JUDGE_MODEL_NAME=claude-sonnet-5      # optional; this is the default
    python -m tests.custom_pytest.evals.run_evals            # full dataset
    python -m tests.custom_pytest.evals.run_evals --limit 3  # quick slice

Each topic runs a full debate via ``app.run_debate`` (Haiku by default), then is
scored deterministically (free, no LLM) and by the LLM judge (stronger model).
Judge failures degrade gracefully — the row is still recorded.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

# ``app`` and ``src`` are importable when run from the debate_bot/ directory
# (as a module: ``python -m tests.custom_pytest.evals.run_evals``).
from app import run_debate

from .scorers.deterministic import score_deterministic
from .scorers.llm_judge import score_quality
from .report import print_scorecard

DATASET = Path(__file__).parent / "datasets" / "topics.jsonl"


def load_topics(path: Path = DATASET) -> list[dict]:
    topics = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                topics.append(json.loads(line))
    return topics


async def evaluate_one(t: dict) -> dict:
    """Run + score a single topic into a flat row dict."""
    row = {"id": t.get("id"), "topic": t.get("topic")}
    if t.get("note"):
        row["note"] = t["note"]

    try:
        state = await run_debate(t["topic"])
    except Exception as exc:
        row["run_error"] = str(exc)
        row["judge_ok"] = False
        return row

    row.update(score_deterministic(state))
    row["winner"] = state.get("winner")

    judge = await score_quality(state)
    row["judge_ok"] = judge.pop("ok", False)
    judge.pop("error", None)
    row.update(judge)
    return row


async def main(limit: int | None = None, dataset: Path = DATASET) -> dict:
    topics = load_topics(dataset)
    if limit:
        topics = topics[:limit]

    rows = []
    for i, t in enumerate(topics, 1):
        print(f"[{i}/{len(topics)}] running debate: {t.get('id')} — {t.get('topic')!r}")
        rows.append(await evaluate_one(t))

    return print_scorecard(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the debate eval harness.")
    parser.add_argument("--limit", type=int, default=None,
                        help="only run the first N topics (quick smoke run)")
    args = parser.parse_args()
    asyncio.run(main(limit=args.limit))
