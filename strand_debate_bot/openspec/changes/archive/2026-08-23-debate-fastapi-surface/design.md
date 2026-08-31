## Context

See proposal.md - Why/What Changes for motivation. Relevant existing constraints this design builds on:

- The debate graph (`src/core/graph.py`) is built by `build_graph(model, memory_store)` and returns a Strands `Graph` (a `GraphBuilder` product). It exposes `invoke_async(task, invocation_state=...)` (runs to completion or pause) and `stream_async(task, invocation_state=...)` (an async iterator of lifecycle events, verified against the installed package: `multiagent_node_start` / `multiagent_node_stream` / `multiagent_node_stop` / a final `result` event carrying a `GraphResult`).
- A `GraphResult.status` is one of `Status.COMPLETED`, `Status.FAILED`, or `Status.INTERRUPTED`. Separately, an unhandled exception inside graph execution still propagates out of `invoke_async`/`stream_async` after `Status.FAILED` is set internally — so a caller must handle both "call raised" and "call returned a FAILED result" as distinct failure shapes.
- Strands does not restore `invocation_state` across a resume call on its own (confirmed by the scaffolding spike, restated in `audience-question-hitl`'s design.md) — the caller must keep and re-pass the exact same `invocation_state` object between the initial `invoke_async`/`stream_async` call and the resume call.
- The audience-question pause/resume mechanism (`audience-question-hitl`, proposal.md - Impact) is a prerequisite whose code has not landed yet — this design assumes its documented shape (`result.interrupts[0].id`, resume via `graph.invoke_async([{"interruptResponse": {"interruptId": ..., "response": ...}}], invocation_state=...)`) without depending on its internal implementation details.
- No session manager, checkpointing, or process-restart resume exists in this codebase yet (that is the Durability change, TRD Task 6). This design must not introduce any of that.

## Goals / Non-Goals

**Goals:**
- Provide the five endpoint behaviors described in specs/debate-fastapi-surface/spec.md, running entirely within one server process.
- Keep the graph/agent layer (`src/core/`, `src/agents/`) completely unaware of HTTP — the API layer only calls `build_graph()`, `invoke_async`, and `stream_async`.
- Make the one genuinely new piece of state — "which runs exist, and what's their status" — a single, simple, in-memory structure, since nothing below the API layer tracks this today.

**Non-Goals:**
- Surviving a process restart. `GET /debate/resume/{run_id}` does not exist in this change (proposal.md - What Changes).
- Any run-ownership, claim/heartbeat, or cross-process coordination — there is exactly one process, so there is nothing to claim or race over.
- Relaying events between multiple server instances (no Redis, no pub/sub) — a run's events exist only in the memory of the process that started it.
- Token-level / model-streaming UX. See Decision 3.

## Decisions

### 1. A single in-memory `RunRegistry`, not per-endpoint state
One process-lifetime object holds `run_id -> RunEntry {invocation_state, status, task, event_queue}`, where `status` is one of `running | waiting_for_input | done | failed`. `POST /debate/start` creates an entry and launches a background `asyncio.Task` that drives `graph.stream_async(...)`, pushing each event onto that entry's `event_queue`; `GET /debate/stream/{run_id}` reads from that queue; `POST /debate/{run_id}/audience-question` looks the entry up, checks `status == "waiting_for_input"`, and resumes the same background task with the submitted answer.

**Implementation note (tasks.md, Task 4.1):** `RunEntry` also holds the `Graph` instance itself, not just `invocation_state`. Resuming a paused Strands graph reuses the *same* `Graph` object that raised the interrupt — its resume/interrupt state lives on `self`, confirmed by `audience-question-hitl`'s own test reusing one `graph` variable across both the interrupt and resume calls. `invocation_state` alone can't carry a pause across the HTTP request boundary; the registry has to hold the graph too. This also means `POST /debate/invoke` registers an entry (graph + state + interrupt id) when it hits `Status.INTERRUPTED`, under the same `run_id` it returns in the 409 — otherwise that run_id would be a dead reference the async path couldn't actually resume, undercutting the parity this change is going for (Decision 4's error message points the caller at exactly this path).

Alternative considered: no registry at all, re-deriving everything from the graph's own state each call. Rejected — nothing below the API layer persists `invocation_state` across separate HTTP calls (Context, above); *something* has to hold that object in memory between `POST /start` and the later `POST /audience-question`, and a registry is the narrowest thing that can do it.

Alternative considered: reuse the old system's `ownership`-style module structure (claim/heartbeat/status functions over a shared store) even though there's only one process. Rejected — that shape exists specifically to answer "which node owns this run," a question that no longer has meaning with one process; carrying the abstraction forward would keep code whose only job was solving a problem this architecture no longer has (PRD Section 8).

### 2. `GET /debate/stream/{run_id}` reads a queue; it does not re-run `stream_async`
The background task started by `POST /debate/start` is the *only* thing that ever calls `graph.stream_async`/resumes the graph for a given `run_id`. `GET /debate/stream/{run_id}` only ever reads events already pushed to that run's `event_queue` — it never drives the graph itself. This is what makes "submit the audience question" and "stream the run" independent of each other: a client can start a run, disconnect before streaming it, and still submit the audience question later purely against the registry entry.

Alternative considered: have `GET /debate/stream/{run_id}` itself resume-and-drive the graph if no background task is currently running for it (mirroring the old system's `GET /debate/stream/{run_id}` claiming a stale run and re-executing it). Rejected — that behavior existed specifically to recover from a node dying mid-run in a multi-node deployment; with one process, "the task that was running this isn't running anymore" only happens if the process itself died, which is a restart scenario and out of scope here (Goals/Non-Goals, above).

### 3. SSE emits one event per completed round turn, from `multiagent_node_stop`; `multiagent_node_stream` (token-level) is not forwarded
`stream_async` yields far more granular events than the old system's flat "one dict per completed LangGraph node" contract, including forwarded token-level agent output (`multiagent_node_stream`). This change filters down to `multiagent_node_stop` events only, translated to the same flat `{"node": ..., "run_id": ..., "state": ...}` shape the old system emitted, for behavioral parity with the reference system's SSE contract (spec's "one event per completed round turn").

Alternative considered: also forward `multiagent_node_stream` for a live-typing UX, since Strands provides it for free. Rejected for this change specifically: TRD Task 5's own exit test is "each endpoint hit directly matches current API's behavior for the same scenario," which is a parity test, not a UX-improvement test — token-level streaming changes the wire contract in a way existing consumers (the eventual Streamlit port, TRD Task 8) aren't written against yet. Nothing here prevents adding a second, richer event stream later; it's just not what this change delivers.

### 4. Failure mapping covers both a raised exception and a returned `Status.FAILED`
The service layer wraps every `invoke_async`/`stream_async` call so that: an exception raised out of the call, and a returned result with `status == Status.FAILED` and no raised exception, both translate to the same `DebateExecutionError`-equivalent at the route layer (distinct from `DebateTimeoutError` on `asyncio.wait_for` expiry, and from the `Status.INTERRUPTED`-without-pre-supplied-question case, which maps to `DebateAwaitingInputError`).

Alternative considered: treat a returned `Status.FAILED` as equivalent to success and let the response schema surface whatever partial state exists. Rejected — the old system's `execute_debate` explicitly checks `snapshot.interrupts` after a call returns rather than trusting an implicit "no exception means success," precisely to avoid a partial run looking like a completed one; the same discipline applies here to `Status.FAILED`.

### 5. `GET /debate/resume/{run_id}` is absent, not stubbed
No route is registered for it in this change. A request to that path returns FastAPI's default 404, which is indistinguishable from any other unknown route — this change does not add a custom error message explaining "this lands in the Durability change," since a stub endpoint that always errors is still a maintenance burden (a route to keep in sync, tests to write against a permanent failure) for a capability with a firm, already-sequenced follow-on (proposal.md - Impact).

## Risks / Trade-offs

- ~~**[Risk]** This design assumes `audience-question-hitl`'s documented interrupt/resume shape... without that change's code existing yet to verify against.~~ **Resolved during implementation** (tasks.md, Task 1.1): `audience-question-hitl` had already landed and archived by the time this change was implemented. The resume payload shape was confirmed correct as documented; the interrupt-id attribute path was not (`result.interrupts[0].id`, corrected throughout this document — it was originally guessed as `.interrupt_id`).
- **[Risk]** An in-memory `RunRegistry` means every started-but-not-yet-streamed run's `invocation_state` lives only in process memory — a server restart loses all in-flight runs with no recovery, and there is no eviction policy for finished runs, so the registry grows for the lifetime of the process. → **Mitigation**: explicitly accepted for this change (Goals/Non-Goals — restart survival is the Durability change's job); an eviction policy is deferred as a follow-up once real usage patterns (how long clients wait before streaming/submitting) are known, rather than guessed at now.
- **[Trade-off]** Filtering `stream_async` down to `multiagent_node_stop` only (Decision 3) means this change ships less capability than Strands' own streaming API offers. → **Accepted**: matches the parity goal stated in TRD Task 5; revisit once the demo UI (Task 8) has an actual reason to want token-level output.

## Migration Plan

No data migration — this is new code with no existing persisted state to carry forward. Rollback is deleting the new files and the two new dependencies; nothing outside this change's own files depends on the run registry, the routes, or the service layer, since no HTTP surface exists in this repo today.
