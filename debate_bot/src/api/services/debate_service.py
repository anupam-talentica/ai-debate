import asyncio
import contextlib
import json
import logging
import uuid
from typing import AsyncGenerator, Optional

from langgraph.types import Command, Interrupt

import app
from app import run_debate, memory_store
from deployment.app_ext import event_bus, ownership
from src.core.state import DebateState
from .exceptions import DebateAwaitingInputError, DebateExecutionError, DebateTimeoutError

logger = logging.getLogger(__name__)

# LangGraph's default stream_mode="updates" surfaces a paused interrupt as a
# single-key dict `{"__interrupt__": (Interrupt(...), ...)}` instead of the
# usual `{node_name: state}` shape. This key is intentionally the literal
# string rather than an SDK import — `langgraph.constants.INTERRUPT` is
# deprecated as a public symbol in this version.
_INTERRUPT_KEY = "__interrupt__"


def _pending_interrupt(state_update: dict) -> Optional[Interrupt]:
    """Return the first pending Interrupt if this astream update represents a
    pause, else None."""
    interrupts = state_update.get(_INTERRUPT_KEY)
    return interrupts[0] if interrupts else None


class DebateService:
    """Service layer for debate execution and streaming."""

    def __init__(self, timeout_seconds: int = 60):
        self.timeout_seconds = timeout_seconds

    async def execute_debate(self, topic: str, audience_question: str | None = None) -> dict:
        """
        Execute a full debate synchronously.

        Args:
            topic: The debate topic
            audience_question: Optional audience question to pre-supply — if
                given, the debate never pauses; if omitted and the debate
                reaches the pause point anyway, DebateAwaitingInputError is
                raised rather than returning an incomplete-looking result.

        Returns:
            Final debate state as dict

        Raises:
            DebateExecutionError: If debate execution fails
            DebateTimeoutError: If debate exceeds timeout
            DebateAwaitingInputError: If the debate paused for an audience
                question that wasn't pre-supplied
        """
        if not topic.strip():
            raise DebateExecutionError("Topic cannot be empty")

        run_id = str(uuid.uuid4())
        try:
            result = await asyncio.wait_for(
                run_debate(topic, run_id=run_id, audience_question=audience_question or ""),
                timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.error(f"✗ Debate timeout after {self.timeout_seconds}s: {topic}")
            raise DebateTimeoutError(
                f"Debate execution exceeded {self.timeout_seconds}s timeout"
            )
        except Exception as e:
            logger.error(f"✗ Debate execution failed: {str(e)}", exc_info=True)
            raise DebateExecutionError(f"Debate execution failed: {str(e)}")

        # graph.ainvoke() doesn't raise on a pause — it just returns the state
        # as of the interrupt, so check explicitly rather than let an
        # incomplete result (empty pro_closing/winner) look like a success.
        snapshot = await app.graph.aget_state({"configurable": {"thread_id": run_id}})
        if snapshot and snapshot.interrupts:
            logger.warning(f"[{run_id}] /invoke reached the audience-question pause without one pre-supplied")
            raise DebateAwaitingInputError(
                run_id,
                f"This debate paused for an audience question after the rebuttal round. "
                f"/invoke cannot answer it interactively — resume it via "
                f"GET /debate/stream/{run_id} and POST /debate/{run_id}/audience-question, "
                f"or resubmit to /invoke with 'audience_question' supplied up front.",
            )

        logger.info(f"✓ Debate completed: {topic[:50]}... Winner: {result.get('winner')}")
        return result

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
            "audience_question": "",
            "pro_audience_answer": "",
            "con_audience_answer": "",
        }

        node_count = 0
        try:
            logger.info(f"→ Starting streaming debate [{run_id}]: {topic[:50]}...")
            yield f"data: {json.dumps({'node': 'RUN_START', 'run_id': run_id})}\n\n"

            paused = False
            async for state_update in app.graph.astream(current_state, config=config):
                node_count += 1

                if pending := _pending_interrupt(state_update):
                    # This endpoint has no run-ownership/claim machinery to resume
                    # from, so it can't support answering the audience question —
                    # only /debate/start + /debate/stream/{run_id} +
                    # /debate/{run_id}/audience-question can. Surface that clearly
                    # instead of letting `current_state.update(state)` below throw
                    # on the Interrupt tuple and mis-persist a partial debate as done.
                    logger.warning(f"[{run_id}] paused for an audience question; unsupported on this endpoint")
                    pause_event = {
                        "node": "AWAITING_AUDIENCE_QUESTION_UNSUPPORTED",
                        "run_id": run_id,
                        "prompt": pending.value,
                        "detail": "This debate paused for an audience question. This endpoint cannot "
                                  "resume it — restart the debate via POST /debate/start instead.",
                    }
                    yield f"data: {json.dumps(pause_event)}\n\n"
                    paused = True
                    break

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

            if paused:
                return

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
        Execute (or resume-after-crash) a debate under this node's ownership.

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
                "audience_question": "",
                "pro_audience_answer": "",
                "con_audience_answer": "",
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

        logger.info(f"→ [{node_id}] {'executing' if topic is not None else 'resuming'} run [{run_id}]")
        await self._execute_and_publish(run_id, node_id, graph_input, current_state, start_event)

    async def resume_with_answer(self, run_id: str, node_id: str, question: str) -> None:
        """
        Resume a debate paused waiting for an audience question, injecting the
        submitted question as the interrupt's resume value.

        The caller must have already won `ownership.claim(run_id, node_id)` for
        this run (see `POST /debate/{run_id}/audience-question`), which is only
        possible while the run's status is `waiting_for_input`.

        Args:
            run_id: Thread id of the paused run to resume
            node_id: This node's id, as recorded by ownership.claim()
            question: The submitted audience question
        """
        config = {"configurable": {"thread_id": run_id}}
        snapshot = await app.graph.aget_state(config)
        if not snapshot or not snapshot.values:
            logger.error(f"[{run_id}] audience-question resume requested but no checkpoint exists")
            await event_bus.publish(
                run_id,
                {"node": "ERROR", "run_id": run_id, "error": "no checkpoint found for resume"},
            )
            await ownership.set_status(run_id, node_id, "failed")
            return

        current_state = dict(snapshot.values)
        start_event = {"node": "RUN_RESUME", "run_id": run_id, "node_id": node_id}

        logger.info(f"→ [{node_id}] resuming run [{run_id}] with audience question")
        await self._execute_and_publish(run_id, node_id, Command(resume=question), current_state, start_event)

    async def _execute_and_publish(
        self, run_id: str, node_id: str, graph_input, current_state: dict, start_event: dict
    ) -> None:
        """Shared astream loop for `run_and_publish` and `resume_with_answer`:
        drives `graph_input` to completion or the next pause, publishing every
        event to Redis and refreshing the ownership heartbeat throughout.
        """
        config = {"configurable": {"thread_id": run_id}}
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(run_id, node_id))
        node_count = 0
        try:
            await event_bus.publish(run_id, start_event)

            paused = False
            async for state_update in app.graph.astream(graph_input, config=config):
                node_count += 1

                if pending := _pending_interrupt(state_update):
                    logger.info(f"[{run_id}] paused awaiting audience question")
                    pause_event = {
                        "node": "AWAITING_AUDIENCE_QUESTION",
                        "run_id": run_id,
                        "node_id": node_id,
                        "prompt": pending.value,
                    }
                    await event_bus.publish(run_id, pause_event)
                    await ownership.set_status(run_id, node_id, "waiting_for_input")
                    paused = True
                    break

                for node_name, state in state_update.items():
                    logger.debug(f"  Node: {node_name}")

                    current_state.update(state)

                    event_data = {"node": node_name, "run_id": run_id, "state": state, "node_id": node_id}
                    await event_bus.publish(run_id, event_data)

            if paused:
                return

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

            paused = False
            async for state_update in app.graph.astream(None, config=config):
                node_count += 1

                if pending := _pending_interrupt(state_update):
                    # Same rationale as stream_debate: this endpoint has no
                    # claim/resume machinery for injecting the answer, so make
                    # that explicit rather than crashing on the Interrupt tuple.
                    logger.warning(f"[{run_id}] paused for an audience question; unsupported on this endpoint")
                    pause_event = {
                        "node": "AWAITING_AUDIENCE_QUESTION_UNSUPPORTED",
                        "run_id": run_id,
                        "prompt": pending.value,
                        "detail": "This debate paused for an audience question. This endpoint cannot "
                                  "resume it — use POST /debate/start's ownership-tracked flow instead.",
                    }
                    yield f"data: {json.dumps(pause_event)}\n\n"
                    paused = True
                    break

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

            if paused:
                return

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
