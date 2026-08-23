import os

# Force off before anything imports app.py / src.core.graph — that import wires
# MOCK_LLM (see src/core/graph.py) into the graph once, at import time, from
# whatever's in the developer's local .env. Tests must be deterministic
# regardless of that local UI-testing toggle, so pin it here first; dotenv's
# load_dotenv() (override=False by default) won't clobber this later.
os.environ["MOCK_LLM"] = "false"

import pytest
from unittest.mock import AsyncMock, MagicMock


def async_generator(items):
    """Create an async generator from a list of items."""
    async def gen():
        for item in items:
            yield MagicMock(content=item)
    return gen()


@pytest.fixture
def mock_llm():
    """Returns a mock LLM that returns a fixed string for any invoke."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=MagicMock(content="Mock argument text."))
    llm.astream = MagicMock(return_value=async_generator(["Mock ", "argument ", "text."]))
    return llm


@pytest.fixture
def base_state():
    return {
        "topic": "AI will replace software engineers",
        "round": "opening",
        "pro_opening": "",
        "con_opening": "",
        "pro_rebuttal": "",
        "con_rebuttal": "",
        "pro_closing": "",
        "con_closing": "",
        "moderator_summary": "",
        "winner": "",
        "memory_context": [],
        "audience_question": "",
        "pro_audience_answer": "",
        "con_audience_answer": "",
    }
