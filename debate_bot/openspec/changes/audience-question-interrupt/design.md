## Context

See `proposal.md` - Why/What Changes for motivation. Relevant existing constraints this design builds on:

- The debate graph (`src/core/graph.py`) is a fixed LangGraph `StateGraph` compiled with an `AsyncPostgresSaver` checkpointer, keyed by `thread_id` = `run_id`.
- Two execution paths share the same compiled graph: a synchronous path (`POST /debate/invoke` → `graph.ainvoke(...)`, wrapped in a 60s timeout) and a background/streaming path (`POST /debate/start` claims ownership and runs `run_and_publish`, which `astream`s the graph and publishes each node's output to Redis; `GET /debate/stream/{run_id}` relays those events over SSE, and can itself claim + resume execution if the current owner's heartbeat has gone stale).
- `deployment/app_ext/ownership.py` implements race-safe claim/heartbeat/status tracking in Postgres (`run_ownership` table) so exactly one node executes a given run at a time, with automatic failover when a node dies mid-run (stale heartbeat → any node can reclaim and resume from the last checkpoint).

## Goals / Non-Goals

**Goals:**
- Use LangGraph's `interrupt()` as the pause mechanism, since it composes directly with the checkpointer already in place — no new persistence layer needed.
- Make the paused state indistinguishable, from the ownership/failover model's perspective, from "no more work to do right now" rather than "crashed" — so existing stale-heartbeat reclaim logic doesn't spuriously re-run a debate that's simply waiting on a human.
- Keep the synchronous endpoint's contract honest: it either fully completes in one call (question pre-supplied) or fails loudly (question not supplied and pause reached) — never a 200 that looks done but isn't.

**Non-Goals:**
- Supporting more than one audience question per debate (see proposal/spec scope).
- Any timeout, expiry, or auto-generated fallback question if the human never responds.
- Giving the synchronous endpoint a way to receive the question interactively mid-call — structurally impossible for a single blocking HTTP request/response; the pre-supplied-question path is the only accommodation made for that endpoint.

## Decisions

### 1. Pause point is a dedicated graph node, not a branch inside an existing node
Insert `audience_question -> pro_addresses_question -> con_addresses_question` between `con_rebuttal` and `moderator_checkpoint`, replacing that single edge. `con_rebuttal` has no loop-back in this graph, so these three nodes execute exactly once per debate with no conditional routing changes needed elsewhere.

Alternative considered: calling `interrupt()` from inside `moderator_checkpoint` itself, guarded by `if state["round"] == "rebuttal"`. Rejected because it overloads a node whose only current job is a pure state transition, and makes the one-time nature of the pause implicit (dependent on round-string comparison) rather than structural (dependent on graph topology, which is easier to verify and change later).

### 2. New run-ownership status: `waiting_for_input`, treated as permanently "alive"
`is_owned_and_alive()` currently treats `status == 'done'` as permanently alive (never reclaimed) and anything else as alive only while the heartbeat is fresh. Add `waiting_for_input` as a second status with the same "permanently alive" treatment. The execution loop (`run_and_publish`) sets this status and stops heartbeating when the graph pauses on an interrupt, exactly where it currently sets `done`/`failed` and stops heartbeating on real completion/crash.

Alternative considered: keep status `running` and simply let the heartbeat lapse, relying on `STALE_AFTER_SECONDS` to let another node reclaim. Rejected: reclaiming would call `astream(None, config)`, which re-hits the same interrupt harmlessly, but would do so repeatedly (every ~10s per relaying node) for as long as the human takes to answer, spamming duplicate pause events over Redis/SSE. Treating `waiting_for_input` as permanently alive (like `done`) makes the "resume" trigger explicit and singular: only the audience-question endpoint moves the run forward, by directly claiming it and resuming with `Command(resume=question)`.

### 3. Distinguishing an interrupt from a normal node update in the astream loop
With LangGraph's default `stream_mode="updates"`, a pending interrupt surfaces as a distinct `__interrupt__` key in the yielded update dict, not a `{node_name: state}` entry. `run_and_publish` (and `stream_debate`) must check for that key explicitly, publish a new SSE event (e.g. `AWAITING_AUDIENCE_QUESTION`) instead of folding it into `current_state.update(state)`, and set the `waiting_for_input` status instead of `done`.

### 4. Resuming: `Command(resume=question)` vs. plain `astream(None, ...)`
The two existing resume paths (crash recovery via `astream(None, config)`, still needed unchanged for `waiting_for_input` runs where a node itself crashes before an answer arrives) and the new one (`astream(Command(resume=question), config)`, used once the answer is available) are structurally distinct and must not be conflated: passing `None` against a paused-on-interrupt checkpoint just re-raises the same interrupt (safe, idempotent, used by ordinary relay/failover); only `Command(resume=...)` actually injects the answer and advances execution. The new audience-question endpoint always uses the latter.

### 5. Synchronous endpoint: explicit-error guard plus optional pre-supplied question
After `ainvoke()` returns, check `graph.aget_state(config)` for a pending interrupt (non-empty `.tasks` with pending interrupts). If found and no question was pre-supplied, raise an explicit error carrying the `run_id` and pointing to the streaming + question-submission endpoints, instead of building a response with empty closing/verdict fields. Additionally, accept an optional audience question on the synchronous request; when present, thread it into the initial state so the pause node observes it's already satisfied and skips calling `interrupt()` entirely, preserving today's single-round-trip behavior for callers who already know their question (e.g. eval harnesses).

Alternative considered: leaving the synchronous endpoint's behavior unchanged and only documenting the caveat. Rejected per proposal's Why — an unguarded 200 with empty `winner`/`pro_closing` looks like a valid completed debate, and today's response schema has no `run_id` to let a caller even discover which checkpoint is stuck, making the paused run unrecoverable through the API.

### 6. `stream_debate` / `resume_debate` get a safety guard, not full support
Because the interrupt node is unconditional graph topology (Decision 1), the plain `GET /debate/stream?topic=...` and `GET /debate/resume/{run_id}` endpoints — which execute the same compiled graph directly, with no `run_ownership` row and no claim/resume machinery — will reach the same pause on every debate, not just ones started via `/debate/start`. Unhandled, their existing `current_state.update(state)` call throws on the `Interrupt` tuple LangGraph yields for a pause, which their generic `except Exception` handler then reports as an opaque error *and* persists the pre-pause partial state to `memory_store` as if the debate were complete — corrupting future debates' retrieved memory context.

Decided (confirmed with user): full pause/resume support is scoped to `/debate/start` + `/debate/stream/{run_id}` + the new audience-question endpoint only, since only that path has the ownership tracking a resume needs. `stream_debate` and `resume_debate` instead get a minimal guard — detect the interrupt, emit a distinct `AWAITING_AUDIENCE_QUESTION_UNSUPPORTED` event naming the correct endpoint to use instead, and return before reaching the completion/memory-persistence code. This stops the silent corruption and confusing error without building a second resume mechanism for a path the original design didn't cover.

## Risks / Trade-offs

- **[Risk]** A relaying node could still observe a `waiting_for_input` run and, seeing it's not "done," attempt to treat it as needing resumption in some code path that isn't updated consistently with `is_owned_and_alive()`. → **Mitigation**: all "should I claim and re-execute this run" decisions must route through `is_owned_and_alive()` / `claim()`; no code path should independently reinterpret run status.
- **[Risk]** Marking `/invoke`'s guard behavior as breaking changes existing caller expectations (a 200 becomes an error). → **Mitigation**: this is called out explicitly in the proposal as **BREAKING**, and the pre-supplied-question option gives affected callers (who know their question ahead of time) a path back to unchanged behavior.
- **[Risk]** Extending `MODERATOR_DECISION` to weigh the audience Q&A changes verdict outcomes for every debate that includes one, with no way to A/B against the old verdict logic. → **Mitigation**: accepted as intended behavior per the proposal; not a regression since this only applies to debates that now include an audience question, which didn't previously exist.

## Migration Plan

No data migration required — `run_ownership.status` is a free-text column already, and no existing rows will have `waiting_for_input`. Existing in-flight debates (started before this change deploys) that predate the new graph nodes will simply never hit the pause point, since it's new graph topology; only debates started after deployment traverse it. Rollback is a straightforward revert of the graph/state/endpoint changes; no persisted state format becomes invalid.
