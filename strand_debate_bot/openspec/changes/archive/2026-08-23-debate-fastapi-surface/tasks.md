## 1. Prerequisite Check

- [x] 1.1 Confirm `openspec/changes/audience-question-hitl` has landed in code (`src/agents/moderator.py` registers a `HookProvider` and no longer uses the inert `AudienceQuestionStub`; `tests/test_graph.py` asserts pause/resume, not the old placeholder behavior). If it hasn't, implement it first — Section 6's audience-question endpoint depends on its actual interrupt/resume shape, not just design.md's documented expectation (design.md, Risks).
  - Confirmed landed and archived (`openspec/changes/archive/2026-08-23-audience-question-hitl`). Correction to design.md's assumed shape: the interrupt id attribute is `result.interrupts[0].id`, not `.interrupt_id` as design.md guessed — the resume payload shape (`[{"interruptResponse": {"interruptId": ..., "response": ...}}]`) was otherwise correct.

## 2. Dependencies & Scaffolding

- [x] 2.1 Add `fastapi` and `uvicorn` to `requirements.txt`
- [x] 2.2 Create `src/api/routes/`, `src/api/services/` packages (`__init__.py` each)

## 3. Schemas & Exceptions

- [x] 3.1 Add `src/api/schemas.py`: `DebateRequest` (topic, optional `audience_question`), `DebateResponse` (mirrors `build_invocation_state`'s fields plus `winner`/`justification`), `AudienceQuestionRequest` (question), `DebateStartResponse` (run_id), `HealthResponse` (status only — no `node_id`, design.md Context)
- [x] 3.2 Add `src/api/services/exceptions.py`: `DebateError` base, `DebateExecutionError`, `DebateTimeoutError`, `DebateAwaitingInputError(run_id, message)` — adapted from the old system's hierarchy (proposal.md - What Changes)

## 4. Run Registry

- [x] 4.1 Add `src/api/services/run_registry.py`: a `RunRegistry` class holding `run_id -> RunEntry {invocation_state, graph, status, task, event_queue}`, with `create()`, `get()`, and a status enum/literal (`running | waiting_for_input | done | failed`) (design.md, Decision 1)
  - Added a `graph` field beyond the original plan: resuming a paused Strands graph reuses the *same* `Graph` instance that raised the interrupt (resume/interrupt state lives on `self` inside `Graph`, confirmed by `audience-question-hitl`'s own test reusing one `graph` variable across both calls) — `invocation_state` alone isn't enough to carry a pause across the HTTP request boundary.
- [x] 4.2 Unit test: two entries created concurrently are independently retrievable and mutable without interference (design.md, Decision "Concurrent runs are isolated" scenario) — `tests/test_run_registry.py`

## 5. Debate Service — Execution Helpers

- [x] 5.1 Add `src/api/services/debate_service.py`: a helper that drives `graph.invoke_async(...)`, wrapped in `asyncio.wait_for(timeout=...)`, raising `DebateTimeoutError` on expiry, `DebateAwaitingInputError` if the result status is `Status.INTERRUPTED`, and `DebateExecutionError` on a raised exception or a returned `Status.FAILED` (design.md, Decision 4)
  - Extended beyond the original plan: on `Status.INTERRUPTED`, also registers the graph+state in the `RunRegistry` under the same `run_id` quoted in the error, so the caller's suggested resume path (`/debate/start`'s async path) actually works against that id, matching the old system's message more literally.
- [x] 5.2 Add a helper that drives `graph.stream_async(...)`, filtering to `multiagent_node_stop` events (not `multi_agent_node_stop` — that underscore placement is from `stream_async`'s docstring, but the actual event dict's `"type"` value has no underscore between "multi" and "agent"; confirmed against `strands/types/_events.py`) and yielding them as flat `{"node": ..., "run_id": ..., "state": ...}` dicts; on reaching `Status.INTERRUPTED` mid-stream, yields a single `AWAITING_AUDIENCE_QUESTION_UNSUPPORTED`-style event and stops (design.md, Decision 3)
- [x] 5.3 Add a background-task function (used by `/start`) that drives the same `stream_async` loop but pushes events onto a `RunEntry`'s `event_queue` instead of yielding directly, updates the entry's `status` on completion/pause/failure, and on `Status.INTERRUPTED` records the interrupt id needed to resume (design.md, Decision 2)
  - Implemented as a single shared `_drive()` method used by both the initial run and the resume call (Task 5.4), parameterized by `graph_input` (`"run"` vs. the `interruptResponse` payload) — avoids duplicating the event-loop/translation logic.
- [x] 5.4 Add a resume function (used by `/audience-question`) that re-invokes the same background-task driver with `graph.invoke_async([{"interruptResponse": {"interruptId": ..., "response": question}}], invocation_state=<same object>)` against the paused entry (design.md, Context; blocked on Task 1.1's confirmed shape)
  - Uses `entry.graph` (the exact same `Graph` instance from the initial run, per Task 4.1's note) and `entry.graph.stream_async(...)`, not `invoke_async` — consistent with 5.2/5.3 using the streaming form throughout so every path emits the same per-node events.

## 6. Routes

- [x] 6.1 `GET /debate/health` → `HealthResponse`
- [x] 6.2 `POST /debate/invoke` → calls the 5.1 helper; maps `DebateTimeoutError`→408, `DebateAwaitingInputError`→409 (with `run_id`), `DebateExecutionError`→500
- [x] 6.3 `GET /debate/stream` → `StreamingResponse` over the 5.2 helper, `text/event-stream`, same `Cache-Control`/`X-Accel-Buffering` headers as the old system
- [x] 6.4 `POST /debate/start` → creates a `RunRegistry` entry, launches the 5.3 background task via `asyncio.create_task`, returns `DebateStartResponse`
- [x] 6.5 `GET /debate/stream/{run_id}` → 404 if unknown (spec's "Streaming an unknown run identifier fails"); otherwise `StreamingResponse` reading the entry's `event_queue` until a terminal event
- [x] 6.6 `POST /debate/{run_id}/audience-question` → 404 if unknown; 409 if `status != "waiting_for_input"`; otherwise calls the 5.4 resume function via `asyncio.create_task` and returns `{"run_id": ..., "status": "resuming"}`

## 7. App Wiring

- [x] 7.1 Add `app.py`: builds the model/memory-store once at startup, constructs the shared `RunRegistry` and `DebateService`, registers the router
  - Correction to the original wording ("builds the graph ... once at startup"): the *model* and *memory store* are built once and shared, but a **fresh `Graph` is built per run** via a `graph_factory` closure — `Graph.stream_async` stores run-specific state on `self` (`self.state`, `self._current_invocation_state`, its interrupt state), so one `Graph` instance cannot safely serve two concurrent debates. This is what makes the "Concurrent runs are isolated" requirement actually hold.
- [x] 7.2 Add `server.py`: uvicorn entrypoint running `app.py`'s FastAPI instance

## 8. Tests

- [x] 8.1 `POST /debate/invoke` with a pre-supplied `audience_question`: asserts 200 and a populated `DebateResponse` (spec: "A pre-supplied question lets the debate complete in one call")
- [x] 8.2 `POST /debate/invoke` without one: asserts 409 with a `run_id` in the response body (spec: "No pre-supplied question surfaces the pause as an explicit error")
- [x] 8.3 `GET /debate/stream`: asserts a sequence of per-round SSE events through the rebuttal round, followed by the unsupported-pause event (not a crash or silent close) — this endpoint has no way to pre-supply a question, so it always reaches the pause (spec correction: the endpoint cannot ever stream to completion; see specs/debate-fastapi-surface/spec.md, "Single-connection streaming of a fresh run")
- [x] 8.4 `POST /debate/start` + `GET /debate/stream/{run_id}` + `POST /debate/{run_id}/audience-question`: full round-trip test — start without a question, stream until the paused event, submit a question, assert the run reaches a completed verdict
- [x] 8.5 `POST /debate/{run_id}/audience-question` against an unknown run_id: asserts 404; against a run not currently paused: asserts 409
- [x] 8.6 Two concurrent `POST /debate/start` calls: assert each run_id's stream only shows that run's own events (spec: "Concurrent runs are isolated")
- [x] 8.7 Confirm `GET /debate/resume/{run_id}` is absent (returns FastAPI's default 404, not a custom handler) — documents the intentional exclusion (design.md, Decision 5) as a test rather than only as prose
- [x] 8.8 (added) `POST /debate/invoke` with `timeout_seconds=0`: asserts 408 (spec: "Execution exceeding the timeout fails distinctly")
