## 1. State & Prompts

- [x] 1.1 Add `audience_question`, `pro_audience_answer`, `con_audience_answer` fields to `DebateState` (`src/core/state.py`)
- [x] 1.2 Add `PRO_AUDIENCE_RESPONSE` and `CON_AUDIENCE_RESPONSE` prompt templates to `src/core/prompts.py`, following the existing `PRO_REBUTTAL`/`CON_REBUTTAL` style
- [x] 1.3 Extend `MODERATOR_DECISION` to take `audience_question`, `pro_audience_answer`, `con_audience_answer` as additional format inputs, with instructions to weigh them in the verdict

## 2. Graph & Agent Nodes

- [x] 2.1 Add an `audience_question` node (new module or alongside `moderator.py`) that calls `interrupt()` to pause, skipping the pause if `audience_question` is already present in state; store the resulting question into state
- [x] 2.2 Add `pro_addresses_question` to `src/agents/pro.py` (same streaming pattern as `pro_rebuttal`), using `PRO_AUDIENCE_RESPONSE`
- [x] 2.3 Add `con_addresses_question` to `src/agents/con.py` (same streaming pattern as `con_rebuttal`), using `CON_AUDIENCE_RESPONSE`
- [x] 2.4 In `src/core/graph.py`, register the three new nodes and reroute the edge `con_rebuttal -> moderator_checkpoint` to `con_rebuttal -> audience_question -> pro_addresses_question -> con_addresses_question -> moderator_checkpoint`
- [x] 2.5 Update `app.py`'s and `debate_service.py`'s initial-state dicts to include the three new fields (empty strings)

## 3. Ownership Status for Paused Runs

- [x] 3.1 In `deployment/app_ext/ownership.py`, add `waiting_for_input` as a recognized status value alongside `running`/`done`/`failed`
- [x] 3.2 Update `is_owned_and_alive()` to treat `status == 'waiting_for_input'` as permanently alive, the same way `status == 'done'` is treated today
- [x] 3.3 Confirm `claim()`'s `ON CONFLICT` guard (`WHERE ... status != 'done' AND heartbeat_at < ...`) also excludes `waiting_for_input` from being reclaimed via the stale-heartbeat path (only the audience-question endpoint's explicit claim should move it forward) — updated to allow immediate (non-stale-gated) reclaim specifically for `waiting_for_input`

## 4. Execution Loop: Detecting and Publishing the Pause

- [x] 4.1 In `run_and_publish` (`src/api/services/debate_service.py`), detect the `__interrupt__` key in the astream update dict, distinct from normal `{node_name: state}` entries
- [x] 4.2 On detecting a pause, publish a new SSE event type (e.g. `AWAITING_AUDIENCE_QUESTION`) via `event_bus`, set run status to `waiting_for_input` instead of `done`, and stop the heartbeat loop (existing `finally` block)
- [x] 4.3 Scope decision (confirmed with user): full pause/resume support is `/debate/start` + `/debate/stream/{run_id}` + the new audience-question endpoint only. `stream_debate` and `resume_debate` (the plain, non-ownership-tracked `/debate/stream` and `/debate/resume/{run_id}` endpoints) share the same compiled graph and will hit the same interrupt on every debate, so both got a minimal safety guard: detect `__interrupt__`, emit a clear `AWAITING_AUDIENCE_QUESTION_UNSUPPORTED` event explaining this endpoint can't resume it, and return without mis-persisting the partial state to memory as if the debate were complete. No resume capability was added to either.

## 5. Audience Question Submission Endpoint

- [x] 5.1 Add `AudienceQuestionRequest` schema (`question: str`) to `src/api/schemas.py`
- [x] 5.2 Add `POST /debate/{run_id}/audience-question` route in `src/api/routes/debates.py`
- [x] 5.3 Implement the resume path in `debate_service.py`: claim the run (bypassing normal stale-heartbeat gating since status is `waiting_for_input`), call `graph.astream(Command(resume=question), config=config)`, and publish subsequent events through the same `event_bus` mechanism as `run_and_publish` — added `ownership.get_status()`, `DebateService.resume_with_answer()`, and extracted the shared `_execute_and_publish()` helper used by both `run_and_publish` and `resume_with_answer`
- [x] 5.4 Reject submissions for a run that is not currently `waiting_for_input` (already answered, still running, completed, or unknown `run_id`) with a clear error and no state change

## 6. Synchronous `/invoke` Guard and Pre-Supplied Question

- [x] 6.1 Add an optional `audience_question: str | None` field to `DebateRequest` (`src/api/schemas.py`)
- [x] 6.2 Thread a pre-supplied `audience_question` into the initial state passed to `graph.ainvoke(...)` in `run_debate`/`execute_debate`
- [x] 6.3 After `ainvoke()` returns in `execute_debate`, call `graph.aget_state(config)` and check for a pending interrupt; if found (meaning no question was pre-supplied and the pause was hit), raise a new explicit error (not `DebateResponse`) carrying the `run_id` and guidance to resume via the streaming + question-submission endpoints — added `DebateAwaitingInputError(run_id, message)`
- [x] 6.4 Map that new error to an appropriate HTTP status in the `/invoke` route handler, distinct from the existing timeout/execution-error handling — mapped to 409 with `{message, run_id}` detail
- [x] 6.5 Extend `DebateResponse` with `audience_question`, `pro_audience_answer`, `con_audience_answer` fields

## 7. Tests

- [x] 7.1 Unit test: debate graph pauses after `con_rebuttal` and does not proceed until resumed with a question — `tests/custom_pytest/unit_tests/test_audience_question.py`
- [x] 7.2 Unit test: both `pro_addresses_question` and `con_addresses_question` run after resume, before `moderator_checkpoint`
- [x] 7.3 Unit test: `MODERATOR_DECISION` prompt construction includes the audience Q&A fields
- [x] 7.4 Integration test: start → pause detected (`AWAITING_AUDIENCE_QUESTION`) → resume with answer → debate completes with a winner (service-layer, real graph + in-memory checkpointer, mocked ownership/event_bus) plus route-level accept/dispatch test
- [x] 7.5 Integration test: submitting a second question for an already-answered run is rejected (covered for running/done/failed statuses and for a lost claim race)
- [x] 7.6 Integration test: `/invoke` without a pre-supplied question errors clearly (not a 200) once execution reaches the pause point, and the error includes a usable `run_id`
- [x] 7.7 Integration test: `/invoke` with a pre-supplied `audience_question` completes in one call with no pause
- [x] 7.8 Failover test: a `waiting_for_input` run is not reclaimed/re-executed by the stale-heartbeat relay path while waiting — asserts `is_owned_and_alive()` handles `waiting_for_input` unconditionally, independent of heartbeat staleness

Also fixed two pre-existing tests broken by the new mandatory pause (unrelated `test_graph_execution_with_invalid_state` regression confirmed pre-existing on `main`, left untouched): `tests/custom_pytest/core/test_graph.py`'s two full-graph tests now pre-supply an `audience_question` so they still exercise the complete pipeline, and `tests/custom_pytest/unit_tests/test_e2e.py`'s `/invoke` e2e test was updated similarly plus a new e2e test added for the no-question 409 case.
