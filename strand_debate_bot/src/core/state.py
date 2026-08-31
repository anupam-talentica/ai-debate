"""Shape and transitions of the debate graph's shared `invocation_state`.

Fields carry cross-round prompt content that has no direct graph edge to its
consumer (e.g. a rebuttal referencing the opponent's opening, or the verdict
reading both closing statements) -- see design.md, Decision 4. `round` is
pure control-flow, read only by the moderator hub and its outgoing edges.
"""

from typing import Any

# "" is the pre-first-visit sentinel the hub advances away from immediately.
ROUND_TRANSITIONS = {
    "": "opening",
    "opening": "rebuttal",
    "rebuttal": "audience",
    "audience": "closing",
    "closing": "done",
}


def build_invocation_state(topic: str) -> dict[str, Any]:
    """Initial invocation_state for a new debate run."""
    return {
        "topic": topic,
        "round": "",
        "memory_context": "",
        "pro_opening": "",
        "con_opening": "",
        "pro_rebuttal": "",
        "con_rebuttal": "",
        "audience_question": "",
        "pro_audience_answer": "",
        "con_audience_answer": "",
        "pro_closing": "",
        "con_closing": "",
        "winner": "",
        "justification": "",
    }
