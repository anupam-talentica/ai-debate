## Why

A debate run today exists only in one process's memory: `Graph`'s own execution state lives on the `Graph` object, and every node (`AgentTurnNode`, `ModeratorHub`, `ModeratorDecision`) writes its output only into an `invocation_state` dict the caller holds — nothing survives a process restart. TRD Task 6 requires that a started debate's progress survive a restart, resuming from the last completed node rather than restarting the debate, using Strands' own local session manager (`FileSessionManager`) rather than a hand-rolled Postgres checkpointer (PRD G4). This change makes that true.

## What Changes

- Wire a `FileSessionManager(session_id=run_id, storage_dir=SESSION_STORAGE_DIRECTORY)` into `build_graph()` via `GraphBuilder.set_session_manager()`, so Strands' own per-node checkpointing (`completed_nodes`, `next_nodes_to_execute`, interrupt state) persists to disk automatically as the debate runs.
- Add a second, application-owned persistence path for `invocation_state` itself: confirmed against installed `strands` (1.53.0) that `Graph.serialize_state()` never includes it, and every node in this codebase writes its output only into `invocation_state`, not into a `MultiAgentResult` payload — so Strands' own checkpoint alone is not sufficient to resume with the actual debate text intact. A dedicated `HookProvider` writes `invocation_state` to `invocation_state.json` inside the same session directory, on the same `AfterNodeCallEvent` / `AfterMultiAgentInvocationEvent` hooks Strands' own session manager already listens to.
- `POST /debate/start` (from `debate-fastapi-surface`) now calls `build_graph()` — with the session manager wired — synchronously in the request handler, before returning the run identifier to the client, so on-disk proof-of-life exists as soon as a client holds a `run_id`.
- Add `GET /debate/resume/{run_id}`: rebuilds the graph against the existing session directory, restores `invocation_state` from the side-channel file, registers a fresh in-memory `RunEntry`, and re-drives execution via the same background-task driver `POST /debate/start` uses. If the restored graph is still mid-interrupt, it re-pauses naturally and the existing `POST /debate/{run_id}/audience-question` endpoint resumes it exactly as today.
- Add `SESSION_STORAGE_DIRECTORY` to `src/core/config.py`, parallel to the existing `MEMORY_PERSIST_DIRECTORY` pattern.

## Capabilities

### New Capabilities
- `debate-durability`: A started debate's execution state and accumulated content survive a process restart, and resuming continues from the last completed node rather than restarting the debate.

### Modified Capabilities
- `debate-fastapi-surface`: Adds `GET /debate/resume/{run_id}` — resuming a run from durable storage after a process restart. This was explicitly absent (not stubbed) in that capability's original spec, deferred to this change.

## Impact

- **New**: `src/core/session.py` (or similar — the `invocation_state`-persisting `HookProvider`, and helpers to build/read the side-channel file), a config addition in `src/core/config.py`.
- **Modified**: `src/core/graph.py` (`build_graph()` accepts/wires a session manager keyed by `run_id`), `src/api/services/debate_service.py` and `src/api/routes/debates.py` (once `debate-fastapi-surface` lands — `POST /debate/start`'s handler ordering, new `GET /debate/resume/{run_id}` route).
- **Depends on** (prerequisite, not yet fully implemented): `debate-fastapi-surface` — this change's resume path attaches to that change's `RunRegistry` and background-task driver, which do not exist in code yet (only schemas/exceptions/run-registry are in place as of this proposal). The graph-level session-manager wiring and the `invocation_state` side-channel (this change's core mechanism) do not depend on it and can be built and tested independently of the HTTP layer.
- **Dependencies**: no new packages — `FileSessionManager` ships in the already-installed `strands` package.
- **Out of scope**: any cloud/S3/AgentCore session backend (PRD's later AWS stage), multi-node coordination (already excluded project-wide), and any change to node return contracts (`nodes.py`'s "invocation_state in, invocation_state out" stays exactly as-is).
