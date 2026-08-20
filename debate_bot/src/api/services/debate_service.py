import asyncio
import contextlib
import json
import logging
import uuid
from typing import AsyncGenerator

import app
from app import run_debate, memory_store
from deployment.app_ext import event_bus, ownership
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

    async def stream_debate(self, topic: str, run_id: str | None = None, sse_delay: float = 0.1) -> AsyncGenerator[str, None]:
        """
        Stream a new debate execution as Server-Sent Events, checkpointed to Postgres
        under `run_id` so it can later be resumed via `resume_debate`.

        Args:
            topic: The debate topic
            run_id: Thread id to checkpoint this run under (generated if omitted)
            sse_delay: Delay between SSE events (seconds)

        Yields:
            SSE formatted event strings

        Raises:
            DebateExecutionError: If streaming fails
        """
        if not topic.strip():
            raise DebateExecutionError("Topic cannot be empty")

        run_id = run_id or str(uuid.uuid4())
        config = {"configurable": {"thread_id": run_id}}

        current_state: DebateState = {
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
            logger.info(f"→ Starting streaming debate [{run_id}]: {topic[:50]}...")
            yield f"data: {json.dumps({'node': 'RUN_START', 'run_id': run_id})}\n\n"

            async for state_update in app.graph.astream(current_state, config=config):
                node_count += 1

                for node_name, state in state_update.items():
                    logger.debug(f"  Node: {node_name}")

                    # Update current_state with latest values
                    current_state.update(state)

                    event_data = {
                        "node": node_name,
                        "run_id": run_id,
                        "state": state,
                    }
                    yield f"data: {json.dumps(event_data)}\n\n"
                    await asyncio.sleep(sse_delay)

            logger.info(f"✓ Streaming complete: {node_count} nodes executed")

            # Send completion event
            completion = {"node": "COMPLETE", "run_id": run_id, "state": current_state}
            yield f"data: {json.dumps(completion)}\n\n"

            # Always upsert to memory, even if some nodes failed
            memory_store.upsert_debate(current_state)
            logger.info(f"✓ Debate persisted to memory")

        except Exception as e:
            logger.error(f"✗ Streaming failed at node {node_count}: {str(e)}", exc_info=True)

            # Send error event
            error_event = {"node": "ERROR", "run_id": run_id, "error": str(e), "nodes_completed": node_count}
            yield f"data: {json.dumps(error_event)}\n\n"

            # Attempt to persist partial state
            try:
                memory_store.upsert_debate(current_state)
                logger.info(f"✓ Partial debate state persisted (nodes: {node_count})")
            except Exception as persist_error:
                logger.error(f"✗ Failed to persist partial state: {str(persist_error)}")

    async def run_and_publish(self, run_id: str, node_id: str, topic: str | None = None) -> None:
        """
        Execute (or resume) a debate under this node's ownership, publishing every
        event to Redis, and keep the run's heartbeat fresh in Postgres for as long
        as this node is doing the work.

        This is the single execution path used by both `POST /debate/start`
        (topic given, fresh run) and the claim branch of `GET /debate/stream/{run_id}`
        (topic omitted, resume from the last Postgres checkpoint) — the caller must
        have already won `ownership.claim(run_id, node_id)` before calling this.

        Args:
            run_id: Thread id to checkpoint/publish this run under
            node_id: This node's id, as recorded by ownership.claim()
            topic: The debate topic for a fresh run; omit to resume from checkpoint
        """
        config = {"configurable": {"thread_id": run_id}}

        if topic is not None:
            current_state: dict = {
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
            start_event = {"node": "RUN_START", "run_id": run_id, "node_id": node_id}
            graph_input = current_state
        else:
            snapshot = await app.graph.aget_state(config)
            if not snapshot or not snapshot.values:
                logger.error(f"[{run_id}] resume requested but no checkpoint exists")
                await event_bus.publish(
                    run_id,
                    {"node": "ERROR", "run_id": run_id, "error": "no checkpoint found for resume"},
                )
                await ownership.set_status(run_id, node_id, "failed")
                return
            current_state = dict(snapshot.values)
            start_event = {"node": "RUN_RESUME", "run_id": run_id, "node_id": node_id}
            graph_input = None

        heartbeat_task = asyncio.create_task(self._heartbeat_loop(run_id, node_id))
        node_count = 0
        try:
            logger.info(
                f"→ [{node_id}] {'executing' if topic is not None else 'resuming'} run [{run_id}]"
            )
            await event_bus.publish(run_id, start_event)

            async for state_update in app.graph.astream(graph_input, config=config):
                node_count += 1

                for node_name, state in state_update.items():
                    logger.debug(f"  Node: {node_name}")

                    current_state.update(state)

                    event_data = {"node": node_name, "run_id": run_id, "state": state, "node_id": node_id}
                    await event_bus.publish(run_id, event_data)

            logger.info(f"✓ [{node_id}] run [{run_id}] complete: {node_count} nodes executed")

            completion = {"node": "COMPLETE", "run_id": run_id, "state": current_state, "node_id": node_id}
            await event_bus.publish(run_id, completion)
            await ownership.set_status(run_id, node_id, "done")

            memory_store.upsert_debate(current_state)
            logger.info(f"✓ Debate persisted to memory")

        except Exception as e:
            logger.error(f"✗ [{node_id}] run [{run_id}] failed at node {node_count}: {str(e)}", exc_info=True)

            error_event = {
                "node": "ERROR",
                "run_id": run_id,
                "error": str(e),
                "nodes_completed": node_count,
                "node_id": node_id,
            }
            await event_bus.publish(run_id, error_event)
            await ownership.set_status(run_id, node_id, "failed")

            try:
                memory_store.upsert_debate(current_state)
                logger.info(f"✓ Partial debate state persisted (nodes: {node_count})")
            except Exception as persist_error:
                logger.error(f"✗ Failed to persist partial state: {str(persist_error)}")
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

    @staticmethod
    async def _heartbeat_loop(run_id: str, node_id: str) -> None:
        """Refresh this node's heartbeat for run_id every few seconds while it executes."""
        try:
            while True:
                await asyncio.sleep(ownership.HEARTBEAT_INTERVAL_SECONDS)
                await ownership.heartbeat(run_id, node_id)
        except asyncio.CancelledError:
            pass

    async def resume_debate(self, run_id: str, sse_delay: float = 0.1) -> AsyncGenerator[str, None]:
        """
        Resume a previously-started debate from its last Postgres checkpoint —
        e.g. after the process that was running it was restarted.

        Args:
            run_id: Thread id of the run to resume (as returned by stream_debate)
            sse_delay: Delay between SSE events (seconds)

        Yields:
            SSE formatted event strings

        Raises:
            DebateExecutionError: If no checkpoint exists for run_id, or streaming fails
        """
        config = {"configurable": {"thread_id": run_id}}

        current_state: dict = {}
        node_count = 0
        try:
            snapshot = await app.graph.aget_state(config)
            if not snapshot or not snapshot.values:
                raise DebateExecutionError(f"No checkpointed run found for run_id={run_id}")
            current_state = dict(snapshot.values)

            logger.info(f"→ Resuming debate [{run_id}] from checkpoint...")
            yield f"data: {json.dumps({'node': 'RUN_RESUME', 'run_id': run_id})}\n\n"

            async for state_update in app.graph.astream(None, config=config):
                node_count += 1

                for node_name, state in state_update.items():
                    logger.debug(f"  Node: {node_name}")

                    current_state.update(state)

                    event_data = {
                        "node": node_name,
                        "run_id": run_id,
                        "state": state,
                    }
                    yield f"data: {json.dumps(event_data)}\n\n"
                    await asyncio.sleep(sse_delay)

            logger.info(f"✓ Resume complete: {node_count} nodes executed")

            completion = {"node": "COMPLETE", "run_id": run_id, "state": current_state}
            yield f"data: {json.dumps(completion)}\n\n"

            memory_store.upsert_debate(current_state)
            logger.info(f"✓ Debate persisted to memory")

        except Exception as e:
            logger.error(f"✗ Resume failed at node {node_count}: {str(e)}", exc_info=True)

            error_event = {"node": "ERROR", "run_id": run_id, "error": str(e), "nodes_completed": node_count}
            yield f"data: {json.dumps(error_event)}\n\n"

            try:
                memory_store.upsert_debate(current_state)
                logger.info(f"✓ Partial debate state persisted (nodes: {node_count})")
            except Exception as persist_error:
                logger.error(f"✗ Failed to persist partial state: {str(persist_error)}")
