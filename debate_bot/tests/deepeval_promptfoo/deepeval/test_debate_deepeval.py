"""deepeval GEval rubrics as pytest tests over the shared debate dataset.

Runs the *real* model (Haiku by default) via ``run_debate`` for a small slice of
the shared topics, then scores each debate on the three debate-specific rubrics
with a Claude judge. Marked ``eval`` so it is deselected by default (pytest.ini:
``addopts = -m "not eval"``) and only hits the API when explicitly requested.

Run (either driver works — deepeval's runner gives the richer report):

    cd debate_bot
    pip install -r requirements-eval.txt
    export ANTHROPIC_API_KEY=...
    export JUDGE_MODEL_NAME=claude-sonnet-5            # optional; this is default

    deepeval test run tests/deepeval_promptfoo/deepeval/test_debate_deepeval.py -m eval
    # or plain pytest:
    pytest -m eval tests/deepeval_promptfoo/deepeval/test_debate_deepeval.py

Tune breadth with EVAL_SLICE (default 3 topics — keeps a run cheap).
"""

from __future__ import annotations

import os

import pytest

# Optional dep (requirements-eval.txt). Skip the whole module cleanly if absent
# so a normal `pytest` run never errors on collection.
pytest.importorskip("deepeval", reason="pip install -r requirements-eval.txt")

from ..eval_provider import as_testcase_fields, load_topics, run_debate_sync
from .metrics import DIMENSIONS, make_test_case

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set — deepeval run requires the real model",
    ),
]

SLICE = int(os.getenv("EVAL_SLICE", "3"))
_TOPICS = load_topics()[:SLICE]

# Run each topic's debate at most once, even though 3 metrics consume it.
_STATE_CACHE: dict[str, dict] = {}


def _fields_for(topic: str) -> dict:
    if topic not in _STATE_CACHE:
        _STATE_CACHE[topic] = run_debate_sync(topic)
    return as_testcase_fields(_STATE_CACHE[topic])


@pytest.mark.parametrize(
    "dim_key,builder,input_field,output_field",
    DIMENSIONS,
    ids=[d[0] for d in DIMENSIONS],
)
@pytest.mark.parametrize(
    "topic_row",
    _TOPICS,
    ids=[t.get("id", t["topic"]) for t in _TOPICS],
)
def test_debate_rubric(topic_row, dim_key, builder, input_field, output_field):
    """Score one (topic, rubric) pair; assert the GEval score clears threshold."""
    fields = _fields_for(topic_row["topic"])
    metric = builder()
    test_case = make_test_case(fields, input_field, output_field)

    metric.measure(test_case)

    print(
        f"\n[{topic_row.get('id')}] {dim_key}: "
        f"score={metric.score:.2f} (threshold={metric.threshold})\n"
        f"reason: {metric.reason}"
    )
    assert metric.score is not None
    assert metric.score >= metric.threshold, (
        f"{dim_key} for topic {topic_row.get('id')!r} scored "
        f"{metric.score:.2f} < {metric.threshold}: {metric.reason}"
    )
