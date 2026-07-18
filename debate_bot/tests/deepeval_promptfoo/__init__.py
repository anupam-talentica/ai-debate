"""Approach C — off-the-shelf LLM-eval library (deepeval / promptfoo).

Wraps the same ``app.run_debate`` seam as Approach A, but scores debates with a
prebuilt eval tool's rubric metrics instead of a hand-rolled judge. deepeval is
the chosen/default tool (pytest-native); promptfoo is provided as an alternative.

The dataset source of truth is shared with Approach A:
``tests/custom_pytest/evals/datasets/topics.jsonl``.
"""
