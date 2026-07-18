"""GEval rubric metrics mapped to this debate system's real dimensions.

Built-in deepeval metrics (relevancy, faithfulness) assume single-turn QA/RAG,
which does not describe a multi-turn debate transcript. So each metric here is a
custom GEval rubric whose criteria describe the debate slice it grades — see the
plan's §7 "metric-shape mismatch" note.

Three debate-specific rubrics (plan §6 acceptance criteria):
    relevance            — Pro opening argues FOR the topic and stays on-topic.
    rebuttal_engagement  — Con rebuttal engages ≥1 point from Pro's opening.
    moderator_soundness  — the winner decision follows from the arguments.

Every metric is scored by a Claude judge (``ClaudeJudge``), 0.0–1.0, with a
default pass threshold of 0.7.
"""

from __future__ import annotations

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from .judge import ClaudeJudge

DEFAULT_THRESHOLD = 0.7

# One shared judge instance across metrics (lazily builds the LLM on first use).
_JUDGE = ClaudeJudge()


def relevance_metric(threshold: float = DEFAULT_THRESHOLD) -> GEval:
    return GEval(
        name="Relevance",
        criteria=(
            "Given the debate topic (input) and the Pro side's opening argument "
            "(actual output): does the opening argue FOR the topic and stay "
            "on-topic? Penalize openings that argue the wrong side, drift "
            "off-topic, or are empty/degenerate."
        ),
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
        ],
        model=_JUDGE,
        threshold=threshold,
    )


def rebuttal_engagement_metric(threshold: float = DEFAULT_THRESHOLD) -> GEval:
    return GEval(
        name="Rebuttal Engagement",
        criteria=(
            "The input is the Pro side's opening argument; the actual output is "
            "the Con side's rebuttal. Score how directly the rebuttal engages at "
            "least one specific point Pro actually made. Reward addressing Pro's "
            "claims head-on; penalize a generic anti-topic speech that ignores "
            "what Pro said."
        ),
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
        ],
        model=_JUDGE,
        threshold=threshold,
    )


def moderator_soundness_metric(threshold: float = DEFAULT_THRESHOLD) -> GEval:
    return GEval(
        name="Moderator Soundness",
        criteria=(
            "The input is the closing arguments the moderator saw (Pro and Con "
            "closings); the actual output is the moderator's decision. Score "
            "whether the decision is justified by those arguments and declares a "
            "clear valid winner. Penalize decisions that contradict the "
            "arguments, are arbitrary, or fail to name a winner."
        ),
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
        ],
        model=_JUDGE,
        threshold=threshold,
    )


# Ordered list of (key, builder, input_field, output_field) so the test file and
# any future runner can iterate the same set of dimensions consistently.
DIMENSIONS = [
    ("relevance", relevance_metric, "topic", "pro_opening"),
    ("rebuttal_engagement", rebuttal_engagement_metric, "pro_point", "con_rebuttal"),
    ("moderator_soundness", moderator_soundness_metric, "arguments", "moderator_summary"),
]


def make_test_case(fields: dict, input_field: str, output_field: str) -> LLMTestCase:
    """Build an ``LLMTestCase`` from projected debate fields (see eval_provider).

    ``fields`` comes from ``eval_provider.as_testcase_fields``.
    """
    return LLMTestCase(
        input=fields.get(input_field, ""),
        actual_output=fields.get(output_field, ""),
    )
