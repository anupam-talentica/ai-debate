"""A minimal Strands Model test double.

Implements the same `Model` interface a real provider (Anthropic, Bedrock, ...)
would, at the lowest boundary Strands defines -- `stream()`/`structured_output()`
-- rather than patching internal attributes. Records every call's messages so
tests can assert on exactly what a node's Agent was prompted with.
"""

import json
from typing import Any, AsyncGenerator, AsyncIterable

from strands.event_loop.streaming import process_stream
from strands.memory.types import MemoryEntry, Metadata, SearchOptions
from strands.models.model import Model
from strands.tools.structured_output import convert_pydantic_to_tool_spec
from strands.types.content import Messages
from strands.types.streaming import StreamEvent


class FakeModel(Model):
    def __init__(self, text: str = "mock response", structured: dict[str, Any] | None = None):
        self._config: dict[str, Any] = {}
        self.text = text
        self.structured = structured or {}
        self.calls: list[Messages] = []

    def update_config(self, **model_config: Any) -> None:
        self._config.update(model_config)

    def get_config(self) -> Any:
        return self._config

    async def stream(
        self,
        messages: Messages,
        tool_specs=None,
        system_prompt=None,
        *,
        tool_choice=None,
        system_prompt_content=None,
        invocation_state=None,
        **kwargs: Any,
    ) -> AsyncIterable[StreamEvent]:
        self.calls.append(messages)

        if tool_choice is not None and tool_specs:
            tool_spec = tool_specs[0]
            yield {"messageStart": {"role": "assistant"}}
            yield {
                "contentBlockStart": {
                    "contentBlockIndex": 0,
                    "start": {"toolUse": {"name": tool_spec["name"], "toolUseId": "fake-1"}},
                }
            }
            yield {
                "contentBlockDelta": {
                    "contentBlockIndex": 0,
                    "delta": {"toolUse": {"input": json.dumps(self.structured)}},
                }
            }
            yield {"contentBlockStop": {"contentBlockIndex": 0}}
            yield {"messageStop": {"stopReason": "tool_use", "additionalModelResponseFields": None}}
            yield {
                "metadata": {
                    "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                    "metrics": {"latencyMs": 1},
                    "trace": None,
                }
            }
            return

        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockStart": {"contentBlockIndex": 0, "start": {}}}
        yield {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": self.text}}}
        yield {"contentBlockStop": {"contentBlockIndex": 0}}
        yield {"messageStop": {"stopReason": "end_turn", "additionalModelResponseFields": None}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                "metrics": {"latencyMs": 1},
                "trace": None,
            }
        }

    async def structured_output(
        self, output_model, prompt: Messages, system_prompt=None, **kwargs: Any
    ) -> AsyncGenerator[dict, None]:
        tool_spec = convert_pydantic_to_tool_spec(output_model)
        response = self.stream(
            messages=prompt, tool_specs=[tool_spec], system_prompt=system_prompt, tool_choice={"any": {}}, **kwargs
        )
        async for event in process_stream(response):
            yield event

        stop_reason, message, _, _ = event["stop"]
        if stop_reason != "tool_use":
            raise ValueError(f"FakeModel: expected stop_reason tool_use, got {stop_reason}")

        output_response = None
        for block in message["content"]:
            if block.get("toolUse") and block["toolUse"]["name"] == tool_spec["name"]:
                output_response = block["toolUse"]["input"]

        yield {"output": output_model(**output_response)}


class FakeMemoryStore:
    """A minimal `strands.memory.types.MemoryStore` test double.

    Returns canned `search` results and records every `add` call, so tests can
    assert on exactly what a node wrote without touching a real Chroma store.
    """

    def __init__(self, search_results: list[str] | None = None, *, raise_on_search: bool = False):
        self.name = "fake"
        self.description: str | None = None
        self.max_search_results: int | None = None
        self.writable = True
        self.extraction = None
        self._search_results = search_results or []
        self._raise_on_search = raise_on_search
        self.added: list[tuple[str, Metadata | None]] = []

    async def search(self, query: str, options: SearchOptions | None = None) -> list[MemoryEntry]:
        if self._raise_on_search:
            raise RuntimeError("FakeMemoryStore: simulated search failure")
        return [MemoryEntry(content=content) for content in self._search_results]

    async def add(self, content: str, metadata: Metadata | None = None) -> str:
        self.added.append((content, metadata))
        return f"fake-{len(self.added)}"
