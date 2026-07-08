import asyncio
import json
import logging
from typing import AsyncGenerator

from app import run_debate, graph, memory_store
from src.core.state import DebateState
from .exceptions import DebateExecutionError, DebateTimeoutError

logger = logging.getLogger(__name__)


class DebateService:
    """Service layer for debate execution and streaming."""

    def __init__(self, timeout_seconds: int = 60):
        self.timeout_seconds = timeout_seconds

    async def execute_debate(self, topic: str) -> dict:
        """
        Execute a full debate synchronously.

        Args:
            topic: The debate topic

        Returns:
            Final debate state as dict

        Raises:
            DebateExecutionError: If debate execution fails
            DebateTimeoutError: If debate exceeds timeout
        """
        if not topic.strip():
            raise DebateExecutionError("Topic cannot be empty")

        try:
            result = await asyncio.wait_for(
                run_debate(topic),
                timeout=self.timeout_seconds
            )
            logger.info(f"✓ Debate completed: {topic[:50]}... Winner: {result.get('winner')}")
            return result
        except asyncio.TimeoutError:
            logger.error(f"✗ Debate timeout after {self.timeout_seconds}s: {topic}")
            raise DebateTimeoutError(
                f"Debate execution exceeded {self.timeout_seconds}s timeout"
            )
        except Exception as e:
            logger.error(f"✗ Debate execution failed: {str(e)}", exc_info=True)
            raise DebateExecutionError(f"Debate execution failed: {str(e)}")

    async def stream_debate(self, topic: str, sse_delay: float = 0.1) -> AsyncGenerator[str, None]:
        """
        Stream debate execution as Server-Sent Events.

        Args:
            topic: The debate topic
            sse_delay: Delay between SSE events (seconds)

        Yields:
            SSE formatted event strings

        Raises:
            DebateExecutionError: If streaming fails
        """
        if not topic.strip():
            raise DebateExecutionError("Topic cannot be empty")

        initial_state: DebateState = {
            "topic": topic,
            "round": "",
            "pro_opening": "",
            "con_opening": "",
            "pro_rebuttal": "",
            "con_rebuttal": "",
            "pro_closing": "",
            "con_closing": "",
            "moderator_summary": "",
            "winner": "",
            "memory_context": [],
        }

        node_count = 0
        try:
            logger.info(f"→ Starting streaming debate: {topic[:50]}...")

            async for state_update in graph.astream(initial_state):
                node_count += 1

                if isinstance(state_update, tuple) and len(state_update) == 2:
                    node_name, state = state_update
                    logger.debug(f"  Node: {node_name}")

                    # Update initial_state with latest values
                    initial_state.update(state)

                    event_data = {
                        "node": node_name,
                        "state": state,
                    }
                    yield f"data: {json.dumps(event_data)}\n\n"
                    await asyncio.sleep(sse_delay)

            logger.info(f"✓ Streaming complete: {node_count} nodes executed")

            # Send completion event
            completion = {"node": "COMPLETE", "state": initial_state}
            yield f"data: {json.dumps(completion)}\n\n"

            # Always upsert to memory, even if some nodes failed
            memory_store.upsert_debate(initial_state)
            logger.info(f"✓ Debate persisted to memory")

        except Exception as e:
            logger.error(f"✗ Streaming failed at node {node_count}: {str(e)}", exc_info=True)

            # Send error event
            error_event = {"node": "ERROR", "error": str(e), "nodes_completed": node_count}
            yield f"data: {json.dumps(error_event)}\n\n"

            # Attempt to persist partial state
            try:
                memory_store.upsert_debate(initial_state)
                logger.info(f"✓ Partial debate state persisted (nodes: {node_count})")
            except Exception as persist_error:
                logger.error(f"✗ Failed to persist partial state: {str(persist_error)}")
