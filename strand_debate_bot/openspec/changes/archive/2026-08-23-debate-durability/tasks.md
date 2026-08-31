## 1. Prerequisite Check

- [x] 1.1 Confirm `openspec/changes/debate-fastapi-surface` has landed enough code for this change to attach to: `app.py`, `src/api/services/debate_service.py`, and a working `POST /debate/start` driving a background task against `RunRegistry` must exist. If not, the config/hook/graph-wiring tasks below (Sections 2-4) can still proceed independently (design.md, Impact), but Section 6 (resume endpoint) is blocked until it lands.
  - Confirmed landed (archived as `2026-08-23-debate-fastapi-surface`): `app.py`, `server.py`, `src/api/routes/debates.py`, `src/api/services/debate_service.py` all exist and match design.md's assumed shape (a `graph_factory` closure, `RunEntry`/`RunRegistry`, a `_drive` background-task loop). Section 5-6 are unblocked.

## 2. Config

- [x] 2.1 Add `SESSION_STORAGE_DIRECTORY` to `src/core/config.py`, project-local default, parallel to the existing `MEMORY_PERSIST_DIRECTORY` pattern (design.md, Decision 4)

## 3. `invocation_state` Persistence

- [x] 3.1 Add a module (e.g. `src/core/session.py`) with a `HookProvider` that, on `AfterNodeCallEvent` and `AfterMultiAgentInvocationEvent`, writes the current `invocation_state` to `invocation_state.json` inside `<SESSION_STORAGE_DIRECTORY>/session_<run_id>/` (design.md, Decision 1)
- [x] 3.2 Add a helper to read `invocation_state.json` back into a plain dict for a given `run_id`, returning `None` (not raising) if the file does not exist yet
- [x] 3.3 Unit test: after a node completes, `invocation_state.json` on disk reflects that node's write (spec: "A run's accumulated content survives a process restart")

## 4. Graph Session-Manager Wiring

- [x] 4.1 Update `build_graph()` (`src/core/graph.py`) to accept a `run_id` (or an already-constructed `FileSessionManager`) and wire it via `builder.set_session_manager(...)`, alongside the persistence hook from Task 3.1 via `builder.set_hook_providers([...])` (design.md, Decisions 1-2)
  - Also added `session_storage_dir` param (defaults to config) for test isolation, and made both params optional so `run_id=None` builds a non-durable graph (used by `GET /debate/stream`'s fresh-run path).
- [x] 4.2 Unit test: constructing a graph for a `run_id` writes an initial checkpoint to disk before any node executes (spec: "A run is resumable as soon as its identifier has been issued")
- [x] 4.3 Unit test (in-process simulated restart): run a debate partway via `invoke_async` on one `Graph` instance for a given `run_id`/`storage_dir`, discard that instance, construct a fresh `Graph` for the same `run_id`/`storage_dir`, restore `invocation_state` via Task 3.2's helper, call `invoke_async` again, and assert the debate completes with the pre-restart rounds' content intact in the verdict (spec: "Resuming continues from the last completed step, not from the beginning"; design.md, Decision 5)
- [x] 4.4 Unit test (in-process simulated restart, paused): same as 4.3 but killed while paused awaiting the audience question; assert the fresh graph is still awaiting one, and supplying it completes the run (spec: "A run that was paused awaiting an audience question resumes paused")
  - **Discovery during implementation (not previously in design.md):** `Graph.deserialize_state()` resets to a brand-new `GraphState` (status back to PENDING) whenever the persisted `next_nodes_to_execute` is empty -- true both for a run that never started *and* one that already completed. So `resume()` (Section 6) must read the persisted `status`/`next_nodes_to_execute` from disk itself, *before* rebuilding the graph, rather than rebuild first and inspect `graph.state.status` afterward -- otherwise resuming an already-completed run would silently reset and re-run the entire debate. `read_persisted_graph_status()` in `src/core/session.py` does this raw read (also used to recover the pending interrupt id directly from the persisted `_internal_state`, since a freshly-reconstructed, not-yet-invoked `Graph` has no public accessor for it).

## 5. Application Wiring — `POST /debate/start` Ordering

- [x] 5.1 Update `POST /debate/start`'s handler (`src/api/services/debate_service.py` / `src/api/routes/debates.py`, once `debate-fastapi-surface` has landed) to call `build_graph()` with the session manager wired (Task 4.1) synchronously before returning the run identifier, not inside the background task (design.md, Decision 2)
  - Also applied to `invoke()` and `stream_fresh()` (uniform `graph_factory(run_id)` signature across all three entry points, not just `start()`).
  - **Bug found and fixed:** `save_invocation_state()` must run *after* `graph_factory(run_id)`, not before — it creates the session directory as a side effect (for `invocation_state.json`), and `FileSessionManager.create_session()` unconditionally raises `SessionException` if that directory already exists when it goes to create it. Calling the eager `invocation_state.json` write first (before the graph/`FileSessionManager` was ever constructed) tripped this on every single run. Fixed by building the graph first in all three methods.

## 6. `GET /debate/resume/{run_id}` Endpoint

- [x] 6.1 Add a resume helper in `src/api/services/debate_service.py`: given a `run_id`, rebuild the graph (Task 4.1) against the existing session directory, restore `invocation_state` (Task 3.2) — 404 if neither exists — create a fresh `RunEntry` in the `RunRegistry`, and re-drive the same background-task driver `POST /debate/start` uses (design.md, Decision 3)
  - **Bug found and fixed (the real substance of design.md's Decision 3 addendum):** the terminal-vs-resumable branch initially decided from `persisted.has_next_nodes`, which reads `False` at *every* round boundary (not only once a run is genuinely done — see design.md addendum). That misclassified a run killed right after any round as "terminal," set its status without ever starting `_drive`, and left its `event_queue` with nothing to ever push a closing sentinel — any `GET /debate/stream/{run_id}` against it hung forever. Fixed by branching on the persisted `status` field (`"completed"`/`"failed"` are the only real terminal signals; `"interrupted"` is the pause signal) instead.
  - **Second bug found and fixed:** the paused and terminal branches don't start a `_drive` task, so nothing else will ever populate a freshly-registered entry's `event_queue`. A client streaming that `run_id` before submitting the audience question (paused case) or at all (terminal case) would hang forever. Fixed by having `resume()` push the corresponding event (`AWAITING_AUDIENCE_QUESTION` / `COMPLETE` / `ERROR`) plus the closing `None` sentinel directly, for those two branches only.
- [x] 6.2 Add the route: `GET /debate/resume/{run_id}` → 404 if no session exists for that `run_id`; otherwise calls 6.1's helper and returns the same shape `POST /debate/start` returns
- [x] 6.3 Integration test: resume an interrupted (not paused) run → continues to completion (spec: "Resuming an interrupted run continues it toward completion")
  - Pre-restart state is produced by driving a directly-built graph and breaking its stream partway (same technique as Task 4.3), since `_drive`'s background task runs to completion faster than a real HTTP test could race a cancellation against it with a zero-latency `FakeModel`.
- [x] 6.4 Integration test: resume a run paused on the audience question → still paused; submitting a question completes it (spec: "Resuming a paused run leaves it paused")
- [x] 6.5 Integration test: resume an unknown `run_id` → 404 (spec: "Resuming an unknown run identifier fails")
  - Added two more regression tests beyond the original scope, directly covering the two bugs above: streaming a resumed-but-not-yet-submitted paused run to its close (not a hang), and resuming an already-completed run (no re-execution, `model.calls` count unchanged).

## 7. Exit Criterion — Real Process Restart

- [x] 7.1 Add one test that spawns `server.py` as a real subprocess, starts a debate over HTTP, sends `SIGKILL` at a controlled point (e.g. after the opening round's `multi_agent_node_stop` event is observed), restarts the subprocess, calls `GET /debate/resume/{run_id}`, and asserts the run reaches a completed verdict without repeating the opening round (design.md, Decision 5; TRD Task 6's named exit test)
  - Runs `python -m uvicorn app:app` directly rather than literally `server.py`: that file hardcodes `reload=True`, whose reloader supervisor process would complicate sending one unambiguous SIGKILL to "the server process." Same ASGI app object either way.
  - Landed alongside this change (not part of it): `mock-mode-eval-fixtures` (TRD Task 7), implemented concurrently in this same working tree. Its `MOCK_LLM`/`MOCK_LLM_DELAY_SECONDS` are what make this test possible at all without live Anthropic calls, and the per-node delay is what gives a real wall-clock window to land the kill precisely between two nodes of a round (`tests/test_durability_subprocess.py`).
  - Kills between `pro_opening` and `con_opening` (mid-round, not a round boundary) and asserts the restarted run's stream never repeats `pro_opening` but does still run `con_opening` onward to the audience pause.
