## Context

See proposal.md - Why/What Changes for motivation and scope. Two facts from the existing backend shape everything below (verified against [src/api/services/debate_service.py](../../../src/api/services/debate_service.py) and [src/core/graph.py](../../../src/core/graph.py), not assumed from the PRD):

- **Events are whole-turn snapshots, not tokens.** Every SSE event is `{node, run_id, state: <entire invocation_state>}`; `multiagent_node_stream`'s token-level events are never forwarded (`_translate_event`). There is no way to observe a turn "typing" in real time.
- **The audience-question pause is two SSE connections, not one.** `GET /debate/stream/{run_id}` closes (server pushes its sentinel) exactly when `AWAITING_AUDIENCE_QUESTION` arrives. `POST /debate/{run_id}/audience-question` creates a *new* `entry.event_queue`. The client must reopen `GET /debate/stream/{run_id}` after submitting to see the rest of the run.

The only prior UI, `debate_bot/deployment/ui/streamlit_app.py` (sibling directory, same outer git repo — see proposal.md), was built against a different graph (`moderator_open`/`moderator_checkpoint` as two separate nodes, a `moderator_summary` state field, a `node_id` per event, a load-balanced multi-node cluster). Its chat-layout *ideas* (sidebar, dividers, speaker pills, typewriter, gated form) transfer; its node-id mapping and multi-node code do not, and are rebuilt against this backend's actual contract rather than copied.

## Goals / Non-Goals

**Goals:**
- One Streamlit app, talking to this project's single FastAPI process, reproducing the old UI's chat-transcript *behavior* against the new node/event model.
- Correct handling of the two-connection pause boundary as normal, expected behavior (not an error state).

**Non-Goals:**
- Any node-identity, health-polling, or failover UI (proposal.md already scopes this out).
- True token-level streaming — the typewriter effect is a client-side simulation over an already-complete string, not a change to the backend's event granularity.
- Exposing `POST /debate/invoke` (the synchronous path) in the UI — it 409s on reaching the pause with no way to answer interactively, so it has no UI use case beyond what `/start` + `/stream` already covers.
- Surfacing `MOCK_LLM` state in the UI (see Open Questions).

## Decisions

**Single-file Streamlit app (`ui/streamlit_app.py`), matching the old UI's structure.** The old file's separation of concerns (init_state, stream consumer thread, render_* functions) is framework-driven, not failover-specific, and Streamlit demo apps conventionally stay single-file. No design benefit to splitting it up for this scope.

**Node-id → transcript mapping is rebuilt, not copied.** Old `SPEAKERS`/`ROUND_DIVIDER` dicts keyed on `moderator_open`/`moderator_checkpoint`. This graph has one recurring `moderator` hub node ([src/core/graph.py](../../../src/core/graph.py)); the divider text is chosen from `state["round"]` on that node's own completion event, not from two distinct node ids. `audience_question`, `pro_addresses_question`, `con_addresses_question`, `pro_closing`, `con_closing`, `moderator_decision` keep the same node ids and state keys as before and port directly. The moderator's final message reads `state["justification"]` (this backend's field) instead of the old `state["moderator_summary"]` (which doesn't exist here).

**Background thread + queue + polling rerun, same as the old UI.** The old file's own rationale (`st.fragment(run_every=...)` depends on a browser-side JS timer that's unobservable/untestable headlessly) is architectural, not failover-related, so `time.sleep(AUTO_REFRESH_SECONDS); st.rerun()` carries over unchanged.

**The pause boundary is modeled as "stream ends, then reopens," not "connection dropped, reconnect."** The old `consume_stream`'s retry loop existed because *any* node behind the LB could die mid-stream. Here, the single server closing the stream at `AWAITING_AUDIENCE_QUESTION` is the *only* expected closure short of `COMPLETE`/`ERROR`. Implementation: the background thread for a debate exits its first `httpx.stream(...)` call normally on that event (pushing it to `event_q` first) and, if the form later reports a successful submission, is restarted with a second `httpx.stream(...)` call against the same `run_id` rather than looping reconnect attempts against a still-open connection.

**Base URL is a single config constant** (`API_BASE_URL`, default `http://localhost:8000`, overridable via env var) replacing `LB_URL` — there is no load balancer to route through.

**`AUDIENCE_QUESTION_UNSUPPORTED` and `ERROR` events render as inline error text**, same as the old UI — these aren't failover concepts, they're already part of this backend's real contract ([debate_service.py](../../../src/api/services/debate_service.py) `_translate_event`).

## Risks / Trade-offs

- **The typewriter effect no longer means what it looked like it meant.** Old UI: also simulated (LangGraph didn't stream tokens to it either), so this isn't a regression — but worth being explicit in the UI or docs that turn text arrives complete and the reveal is purely cosmetic timing, not live generation.
- **The acceptance test ("matches today's transcript UX") is a manual, subjective comparison against a real file, not an automated diff.** Now that `debate_bot/deployment/ui/streamlit_app.py` is confirmed to exist, a side-by-side manual run-through against it is possible and is what tasks.md's exit criterion should mean — but it's still a human judgment call, not a scripted assertion, since the two apps' backends differ (single-process vs. multi-node) and a byte-identical UI isn't the goal.
- **Streamlit's per-rerun model re-executes the whole script on every tick.** The `_shown` flag on each buffered event (carried over from the old design) is what prevents re-animating history; if that flag handling has a bug, the symptom is the whole transcript replaying its typewriter effect on every 1.5s tick — worth a specific manual check during testing.

## Open Questions

- Should the UI surface whether `MOCK_LLM` is active (e.g. a small badge), or stay visually identical either way? Deferrable: the transcript behaves identically either way since mock mode is transparent server-side: this only affects whether a demo session visibly announces "these responses are cached."
