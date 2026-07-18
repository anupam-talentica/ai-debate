"""promptfoo Python provider (Option C2) — runs a real debate per test case.

promptfoo calls ``call_api(prompt, options, context)`` once per test row. We
ignore ``prompt`` (there is no single prompt — a debate is a graph) and read the
topic from the test's vars, then return the full debate state as JSON so the
asserts in promptfooconfig.yaml can grade individual fields.

promptfoo runs this file from its own working directory, so we add the debate_bot
root to sys.path to import the shared seam.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# debate_bot/tests/deepeval_promptfoo/promptfoo/eval_provider.py → debate_bot/
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.deepeval_promptfoo.eval_provider import run_debate_sync  # noqa: E402


def call_api(prompt, options, context):
    """Return {"output": <debate state as JSON string>} for one topic."""
    topic = context["vars"]["topic"]
    state = run_debate_sync(topic)
    # Keep only JSON-serializable, human-graded fields (drop embeddings, etc.).
    slim = {
        k: state.get(k)
        for k in (
            "topic",
            "pro_opening",
            "con_opening",
            "pro_rebuttal",
            "con_rebuttal",
            "pro_closing",
            "con_closing",
            "moderator_summary",
            "winner",
        )
    }
    return {"output": json.dumps(slim)}
