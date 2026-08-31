"""Service layer driving the debate graph for each of the API's endpoint
behaviors (design.md, Decisions 1-4).

A fresh Graph is built per run via `graph_factory` rather than sharing one
Graph instance across concurrent runs: `Graph.stream_async` stores
run-specific state on `self` (`self.state`, `self._current_invocation_state`,
its interrupt state), so one Graph instance cannot safely serve two
concurrent debates. Model and memory-store instances are still shared across
runs -- only the graph's node/edge topology and its per-run state need to be
distinct per run.
"""

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncGenerator, Callable

from strands.multiagent.base import Status

from src.api.services.exceptions import DebateAwaitingInputError, DebateExecutionError, DebateTimeoutError
from src.api.services.run_registry import RunEntry, RunRegistry
from src.core.session import load_invocation_state, read_persisted_graph_status, save_invocation_state, session_exists
from src.core.state import build_invocation_state

logger = logging.getLogger(__name__)

GraphFactory = Callable[[str], Any]


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


class DebateService:
    def __init__(
        self,
        graph_factory: GraphFactory,
        registry: RunRegistry,
        session_storage_dir: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._graph_factory = graph_factory
        self._registry = registry
        self._session_storage_dir = session_storage_dir
        self._timeout_seconds = timeout_seconds

    # -- Synchronous full run (POST /debate/invoke) --------------------------

    async def invoke(self, topic: str, audience_question: str | None = None, run_id: str | None = None) -> dict[str, Any]:
        """`run_id`: normally minted here (the REST `/invoke` route never
        passes one). The AgentCore dispatcher passes its `runtimeSessionId`
        instead, so a debate that pauses here can still be resumed by a later
        call under that same session id (deploy-to-agentcore design.md,
        Decision 2)."""
        run_id = run_id or str(uuid.uuid4())
        state = build_invocation_state(topic)
        if audience_question:
            state["audience_question"] = audience_question

        # Build the graph before saving invocation_state, not after:
        # FileSessionManager.create_session() raises if its session directory
        # already exists, and save_invocation_state() would have created that
        # same directory first if called before the graph is built.
        graph = self._graph_factory(run_id)
        save_invocation_state(self._session_storage_dir, run_id, state)
        try:
            result = await asyncio.wait_for(
                graph.invoke_async("run", invocation_state=state), timeout=self._timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            raise DebateTimeoutError(f"Debate execution exceeded {self._timeout_seconds}s timeout") from exc
        except Exception as exc:
            raise DebateExecutionError(f"Debate execution failed: {exc}") from exc

        if result.status == Status.INTERRUPTED:
            # Register under the same run_id quoted in the error so the caller
            # can actually resume it via /debate/start's async path, matching
            # the old system's equivalent message (proposal.md - What Changes).
            entry = self._registry.create(run_id, state)
            entry.graph = graph
            entry.status = "waiting_for_input"
            entry.interrupt_id = result.interrupts[0].id
            raise DebateAwaitingInputError(
                run_id,
                "This debate paused for an audience question after the rebuttal round. "
                "/invoke cannot answer it interactively -- resume it via "
                f"GET /debate/stream/{run_id} and POST /debate/{run_id}/audience-question.",
            )
        if result.status == Status.FAILED:
            raise DebateExecutionError(f"Debate execution failed for run {run_id}")

        return dict(state)

    # -- Fresh single-connection stream (GET /debate/stream) ------------------

    async def stream_fresh(self, topic: str) -> AsyncGenerator[str, None]:
        run_id = str(uuid.uuid4())
        state = build_invocation_state(topic)
        graph = self._graph_factory(run_id)
        save_invocation_state(self._session_storage_dir, run_id, state)

        yield _sse({"node": "RUN_START", "run_id": run_id})

        async for event in graph.stream_async("run", invocation_state=state):
            sse_event = _translate_event(event, run_id, state, resumable=False)
            if sse_event is not None:
                yield _sse(sse_event)

    # -- Start + background execution (POST /debate/start) --------------------

    def start(self, topic: str, audience_question: str | None = None, run_id: str | None = None) -> str:
        """`run_id`: see `invoke()`'s docstring -- same reason, same default."""
        run_id = run_id or str(uuid.uuid4())
        state = build_invocation_state(topic)
        if audience_question:
            state["audience_question"] = audience_question

        # build_graph() (via graph_factory) must run here, synchronously, before
        # this method returns run_id to the route handler -- Graph construction
        # writes FileSessionManager's own initial checkpoint as a side effect of
        # `MultiAgentInitializedEvent` firing, so a restart between "response
        # sent" and "background task's first line runs" would otherwise leave a
        # run_id with nothing on disk to resume from (design.md, Decision 2).
        # It also must run before save_invocation_state(): FileSessionManager's
        # own create_session() raises if its session directory already exists,
        # which save_invocation_state() would have created first otherwise.
        graph = self._graph_factory(run_id)
        save_invocation_state(self._session_storage_dir, run_id, state)
        entry = self._registry.create(run_id, state)
        entry.graph = graph
        entry.task = asyncio.create_task(self._drive(run_id, entry, "run"))
        return run_id

    # -- Resume after a process restart (GET /debate/resume/{run_id}) ---------

    def resume(self, run_id: str) -> str | None:
        """Returns None if no session exists on disk for run_id (never started,
        or a storage_dir/run_id mismatch); otherwise run_id, once the resumed
        run has been registered (design.md, Decision 3)."""
        if not session_exists(self._session_storage_dir, run_id):
            return None

        state = load_invocation_state(self._session_storage_dir, run_id) or {}
        persisted = read_persisted_graph_status(self._session_storage_dir, run_id)

        # Rebuilding restores Strands' own checkpoint (topology, interrupt
        # state) automatically via FileSessionManager -- see build_graph().
        graph = self._graph_factory(run_id)
        entry = self._registry.create(run_id, state)
        entry.graph = graph

        if persisted is not None and persisted.pending_interrupt_id is not None:
            # Paused when the process died: nothing was in flight, so there is
            # nothing to re-drive yet -- just make the pause visible again,
            # exactly as it would be right after a live INTERRUPTED result
            # (_translate_event's AWAITING_AUDIENCE_QUESTION case).
            entry.status = "waiting_for_input"
            entry.interrupt_id = persisted.pending_interrupt_id
            # No _drive task runs for this branch, so nothing else will ever
            # populate this fresh entry's queue -- without pushing the pause
            # (and its closing sentinel) here, a client streaming this run_id
            # before the question is submitted would wait forever for events
            # that only a *future* submit_audience_question call would produce.
            entry.event_queue.put_nowait({"node": "AWAITING_AUDIENCE_QUESTION", "run_id": run_id})
            entry.event_queue.put_nowait(None)
        elif persisted is not None and persisted.status in ("completed", "failed"):
            # Already reached a terminal state before the restart. Strands
            # itself would silently reset and re-run the whole debate here if
            # asked to resume (deserialize_state's next_nodes_to_execute-empty
            # branch), so this never calls _drive once persisted status is
            # genuinely terminal.
            #
            # Deciding from `status` here, not from whether `next_nodes_to_execute`
            # is empty: this graph's cyclic routing is driven entirely by
            # invocation_state["round"], not by Strands' own per-node bookkeeping,
            # and its resume-readiness computation can't mark an already-visited
            # node (the revisited `moderator` hub) ready again -- so
            # next_nodes_to_execute reads empty at *every* round boundary, not
            # only at genuine completion. Strands' reset-and-reenter-from-the-
            # entry-point response to that (deserialize_state) happens to still
            # be correct here, because `moderator` *is* the entry point and
            # `round` alone decides where it routes next -- confirmed directly
            # against installed strands 1.53.0 by killing a run right after a
            # round boundary and resuming it; only `status` reliably tells a
            # genuinely finished run apart from one merely at a round boundary.
            entry.status = "done" if persisted.status == "completed" else "failed"
            # Same reasoning as the paused branch above: no _drive task runs
            # here either, so a stream listener needs this pushed explicitly.
            node_name = "COMPLETE" if persisted.status == "completed" else "ERROR"
            entry.event_queue.put_nowait({"node": node_name, "run_id": run_id, "state": dict(state)})
            entry.event_queue.put_nowait(None)
        else:
            # Either genuinely mid-execution when killed (round boundary or
            # not), or killed before the first node ever ran (persisted is
            # None, or status is "pending") -- all three resume correctly via
            # the same driver POST /debate/start uses.
            entry.task = asyncio.create_task(self._drive(run_id, entry, "run"))

        return run_id

    async def _drive(self, run_id: str, entry: RunEntry, graph_input: Any) -> None:
        """Drives `entry.graph` from `graph_input` to completion or the next
        pause, publishing every event onto `entry.event_queue`. Used both for
        a fresh run (graph_input="run") and a resume (graph_input=the
        interruptResponse payload)."""
        try:
            async for event in entry.graph.stream_async(graph_input, invocation_state=entry.invocation_state):
                sse_event = _translate_event(event, run_id, entry.invocation_state, resumable=True)
                if sse_event is None:
                    continue

                if sse_event["node"] == "AWAITING_AUDIENCE_QUESTION":
                    entry.status = "waiting_for_input"
                    entry.interrupt_id = sse_event.pop("_interrupt_id")
                elif sse_event["node"] == "ERROR":
                    entry.status = "failed"
                    entry.error = sse_event.get("error")
                elif sse_event["node"] == "COMPLETE":
                    entry.status = "done"

                await entry.event_queue.put(sse_event)
        except Exception as exc:
            logger.exception("[%s] run failed", run_id)
            entry.status = "failed"
            entry.error = str(exc)
            await entry.event_queue.put({"node": "ERROR", "run_id": run_id, "error": str(exc)})
        finally:
            await entry.event_queue.put(None)  # sentinel: no more events for this drive call

    # -- Stream a registered run by id (GET /debate/stream/{run_id}) ----------

    def stream_registered(self, run_id: str) -> AsyncGenerator[str, None] | None:
        entry = self._registry.get(run_id)
        if entry is None:
            return None

        async def _generator() -> AsyncGenerator[str, None]:
            while True:
                event = await entry.event_queue.get()
                if event is None:
                    break
                yield _sse(event)

        return _generator()

    # -- Resume a paused run (POST /debate/{run_id}/audience-question) --------

    def submit_audience_question(self, run_id: str, question: str) -> str | None:
        """Returns None if run_id is unknown, "not_waiting" if it isn't
        currently paused, or "resuming" once the resume task is launched.

        The waiting_for_input -> running transition happens synchronously,
        before any `await`, so two concurrent submissions for the same
        run_id can't both pass the status check (no race window exists in a
        single-threaded event loop unless a call yields control first)."""
        entry = self._registry.get(run_id)
        if entry is None:
            return None
        if entry.status != "waiting_for_input" or entry.interrupt_id is None:
            return "not_waiting"

        interrupt_id = entry.interrupt_id
        entry.status = "running"
        entry.interrupt_id = None
        entry.event_queue = type(entry.event_queue)()  # fresh queue for this drive call's events

        graph_input = [{"interruptResponse": {"interruptId": interrupt_id, "response": question}}]
        entry.task = asyncio.create_task(self._drive(run_id, entry, graph_input))
        return "resuming"


def _translate_event(
    event: dict[str, Any], run_id: str, invocation_state: dict[str, Any], *, resumable: bool
) -> dict[str, Any] | None:
    """Maps one `Graph.stream_async` event to this API's flat SSE contract
    (design.md, Decision 3): one event per completed round turn, from
    `multiagent_node_stop` only -- `multiagent_node_stream`'s token-level
    events are not forwarded. Returns None for events this contract ignores."""
    event_type = event.get("type")

    if event_type == "multiagent_node_stop":
        return {"node": event["node_id"], "run_id": run_id, "state": dict(invocation_state)}

    if event_type != "multiagent_result":
        return None

    result = event["result"]
    if result.status == Status.INTERRUPTED:
        if not resumable:
            return {
                "node": "AWAITING_AUDIENCE_QUESTION_UNSUPPORTED",
                "run_id": run_id,
                "detail": "This debate paused for an audience question. This endpoint cannot "
                "resume it -- restart the debate via POST /debate/start instead.",
            }
        return {
            "node": "AWAITING_AUDIENCE_QUESTION",
            "run_id": run_id,
            "_interrupt_id": result.interrupts[0].id,
        }

    if result.status == Status.FAILED:
        return {"node": "ERROR", "run_id": run_id, "error": "debate execution failed"}

    return {"node": "COMPLETE", "run_id": run_id, "state": dict(invocation_state)}
