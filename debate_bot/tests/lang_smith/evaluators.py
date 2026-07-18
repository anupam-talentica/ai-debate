"""LangSmith evaluators for the debate bot (Approach B).

These are thin adapters: the actual scoring logic is **imported** from Approach
A's shared scorers so there is exactly one implementation of "winner valid /
word caps / structure" and the LLM-judge, and scores are directly comparable
across approaches (acceptance criterion #4).

Each evaluator receives ``(run, example)`` where ``run.outputs`` is the final
debate-state dict returned by ``app.run_debate``. Evaluators return either a
single ``{"key", "score"}`` feedback dict or ``{"results": [...]}`` to emit
several metrics at once.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make the shared Approach-A scorers importable without duplicating logic.
# tests/lang_smith/evaluators.py -> parents[2] == debate_bot/ (repo package root)
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.custom_pytest.evals.scorers.deterministic import score_deterministic
from tests.custom_pytest.evals.scorers.llm_judge import AXES, score_quality

# Boolean metrics reported as pass/fail scores (mirror Approach A's report.py).
DET_BOOL_METRICS = [
    "winner_valid",
    "all_fields",
    "opening_wc_ok",
    "rebuttal_wc_ok",
    "closing_wc_ok",
    "mod_3part",
]

# Raw word-count numbers — emitted for debugging/regression tracking.
DET_NUM_METRICS = ["pro_opening_wc", "pro_rebuttal_wc", "pro_closing_wc"]


def deterministic_metrics(run, example) -> dict:
    """Emit all deterministic (no-LLM) metrics for one debate in a single pass.

    Booleans become 0/1 scores; raw word counts pass through as numeric scores.
    """
    outputs = run.outputs or {}
    scored = score_deterministic(outputs)
    results = [
        {"key": m, "score": int(bool(scored.get(m)))} for m in DET_BOOL_METRICS
    ]
    results += [
        {"key": m, "score": scored.get(m)} for m in DET_NUM_METRICS
    ]
    return {"results": results}


def arg_quality(run, example) -> dict:
    """LLM-as-judge: 1-5 score on each argument-quality axis.

    Delegates to the shared async ``score_quality`` (a stronger model grades the
    debate). Never raises — a judge failure yields ``judge_ok=0`` and no axis
    scores so the experiment degrades gracefully.
    """
    outputs = run.outputs or {}
    judged = asyncio.run(score_quality(outputs))

    results = []
    for axis in AXES:
        val = judged.get(axis)
        if val is not None:
            results.append(
                {"key": axis, "score": val, "comment": judged.get(f"{axis}_reason")}
            )
    results.append({"key": "judge_ok", "score": int(bool(judged.get("ok")))})
    return {"results": results}


# Full evaluator set passed to ``evaluate(...)`` in run_eval.py.
EVALUATORS = [deterministic_metrics, arg_quality]
