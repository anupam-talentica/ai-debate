## Why

The debate graph (`src/core/graph.py`) only runs today through direct Python calls in tests — there is no way for an external client to start, stream, or interact with a debate. PRD Phase 4 (TRD Task 5) calls for a FastAPI wrapper that preserves the old (LangGraph) system's API *behavior* — sync invoke, SSE streaming, a start/stream/submit-question async path — adapted to a single-runtime-session execution model, since the multi-node ownership/ heartbeat machinery and the Redis event relay that the old system needed are both explicitly out of scope for this migration (PRD Section 3/8).

## What Changes

- Add a FastAPI app (`app.py`/`server.py`, `src/api/`) exposing five endpoints that mirror the old system's `/debate/*` surface, minus everything that existed only to support multi-node failover:
  - `GET /debate/health` — liveness, without the old `node_id` field (nothing to disambiguate in a single-process model).
  - `POST /debate/invoke` — synchronous full run; accepts an optional pre-supplied `audience_question`; returns 408 on timeout, 409 (with a `run_id`) if the graph reaches the audience-question pause without one pre-supplied.
  - `GET /debate/stream` — SSE of a fresh, single-connection run; explicitly errors (not crashes) if it hits the pause, since this path has no resume machinery — matching the old system's own `AWAITING_AUDIENCE_QUESTION_UNSUPPORTED` behavior.
  - `POST /debate/start` + `GET /debate/stream/{run_id}` + `POST /debate/{run_id}/audience-question` — claim-free, single-process equivalent of the old ownership-tracked async path: start a background run, stream its events to a connected client, submit the audience question to resume it.
- Introduce an in-process run registry (`run_id -> {graph, invocation_state, status, task}`) as the single-process replacement for the old system's Postgres-backed run-ownership table — it exists purely to bridge the HTTP request/response boundary across the lifetime of one background run, not to survive a process restart.
- Add a typed exception hierarchy and route-layer mapping (adapted from the old system's `DebateExecutionError`/`DebateTimeoutError`/`DebateAwaitingInputError`) that covers both a raised exception from the graph and a returned `Status.FAILED` result without a raised exception — Strands surfaces failures both ways (design.md, Decision 5).
- **Explicitly out of scope, deferred to the Durability change (TRD Task 6):** `GET /debate/resume/{run_id}` (resume after a process restart). No session manager exists yet, so there is nothing to restore state from; adding a stub endpoint now would either silently fail to survive a restart or require faking durability this change doesn't have. This is a deliberate omission, not an oversight.

## Capabilities

### New Capabilities
- `debate-fastapi-surface`: An HTTP surface (health, sync invoke, SSE stream, start/stream/submit-question) over the debate graph, executing within a single process via an in-memory run registry, with parity to the old system's endpoint semantics for everything that doesn't depend on multi-node ownership or durable checkpointing.

### Modified Capabilities
_None._ This change wraps `debate-graph-orchestration` and the audience-question pause (once implemented) in HTTP; it does not change either capability's own requirements.

## Impact

- **New**: `app.py` (FastAPI app factory + graph/model/memory-store wiring), `server.py` (uvicorn entrypoint), `src/api/routes/debates.py`, `src/api/schemas.py`, `src/api/services/debate_service.py` (run registry + background execution), `src/api/services/exceptions.py`.
- **Dependencies**: adds `fastapi` and `uvicorn` to `requirements.txt` (neither is present today).
- **Depends on** (prerequisite, not yet implemented): `openspec/changes/audience-question-hitl` — this change's `/debate/start` + `/debate/{run_id}/audience-question` path wraps that change's `HookProvider`/interrupt-resume mechanism. As of this proposal, `src/agents/moderator.py` still has the inert `AudienceQuestionStub` and `src/core/graph.py` does not register a `HookProvider` — the audience-question-hitl change's code must land before this change's audience-question endpoint can be implemented against real behavior (its sync-invoke and fresh-stream endpoints do not depend on it and can be built independently).
- **Out of scope**: `GET /debate/resume/{run_id}`, any session manager wiring, Postgres, Redis, run-ownership/heartbeat logic, nginx/multi-node topology — all explicitly excluded per PRD Section 3/8 and deferred to the Durability change where noted above.
