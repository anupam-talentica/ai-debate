"""A Claude judge wired into deepeval's custom-model interface.

deepeval defaults to OpenAI. This adapter points every GEval metric at a
*stronger* Claude model (``JUDGE_MODEL_NAME``, default ``claude-sonnet-5``) via
the ``langchain-anthropic`` stack already used at runtime — so debates produced
by Haiku are never graded by themselves, and no OpenAI key is required.

deepeval calls ``generate``/``a_generate`` either with just a prompt (older
metrics that parse JSON out of prose) or with a pydantic ``schema`` (GEval's
structured path). Both signatures are supported here; when a schema is passed we
use LangChain's ``with_structured_output`` so the judge returns a typed object.
"""

from __future__ import annotations

import os

from deepeval.models import DeepEvalBaseLLM


def _to_text(content) -> str:
    """Flatten a LangChain message content (str or list-of-blocks) to text."""
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return content if isinstance(content, str) else str(content)


class ClaudeJudge(DeepEvalBaseLLM):
    """Claude-backed judge for deepeval metrics."""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or os.getenv("JUDGE_MODEL_NAME", "claude-sonnet-5")
        self._chat = None

    def load_model(self):
        if self._chat is None:
            from langchain_anthropic import ChatAnthropic

            # temperature is intentionally NOT set — it is deprecated for
            # newer judge models (e.g. claude-sonnet-5) and raises a 400.
            self._chat = ChatAnthropic(model=self.model_name)
        return self._chat

    def generate(self, prompt: str, schema=None):
        chat = self.load_model()
        if schema is not None:
            return chat.with_structured_output(schema).invoke(prompt)
        return _to_text(chat.invoke(prompt).content)

    async def a_generate(self, prompt: str, schema=None):
        chat = self.load_model()
        if schema is not None:
            return await chat.with_structured_output(schema).ainvoke(prompt)
        resp = await chat.ainvoke(prompt)
        return _to_text(resp.content)

    def get_model_name(self) -> str:
        return self.model_name
