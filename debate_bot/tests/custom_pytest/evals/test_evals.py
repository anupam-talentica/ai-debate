"""Pytest wrapper turning the eval harness into an opt-in CI gate.

Deselected by default (pytest.ini sets ``addopts = -m "not eval"``). Run with:

    cd debate_bot
    ANTHROPIC_API_KEY=... pytest -m eval tests/custom_pytest/evals/test_evals.py

Runs a small slice of the dataset against the real model and asserts thresholds.
Skips automatically when no API key is present so it never fails in offline CI.
"""

import os

import pytest

from .run_evals import main

pytestmark = [
    pytest.mark.eval,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set — eval requires the real model",
    ),
]

# Keep the CI slice small and cheap.
SLICE = int(os.getenv("EVAL_SLICE", "3"))


async def test_eval_thresholds():
    summary = await main(limit=SLICE)

    winner_valid_rate = summary["pass_rates"]["winner_valid"]
    assert winner_valid_rate >= 0.9, (
        f"winner_valid pass-rate {winner_valid_rate:.0%} < 90%"
    )

    # Judge may be flaky; only gate on relevance when judging mostly succeeded.
    if summary["judge_success_rate"] >= 0.5:
        relevance = summary["means"]["judge_relevance"]
        assert relevance is not None and relevance >= 3.5, (
            f"mean relevance {relevance} < 3.5"
        )
