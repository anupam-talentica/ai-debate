## 1. Setup

- [x] 1.1 Add `streamlit` to `requirements.txt` and install it
- [x] 1.2 Create `ui/streamlit_app.py` with `st.set_page_config`, an `API_BASE_URL` constant (default `http://localhost:8000`, overridable via env var), and `init_state()` seeding `st.session_state` (`debates`, `debate_order`, `active_run_id`, `draft_topic`) — no `node_alive`/`failure_banner_until` (design.md, Non-Goals)

## 2. Backend client + background stream consumer

- [x] 2.1 Implement `start_debate(topic)`: `POST /debate/start`, register a new entry in `st.session_state.debates` keyed by `run_id`, spawn a background thread
- [x] 2.2 Implement the background stream-consumer thread: `httpx.stream("GET", f"{API_BASE_URL}/debate/stream/{run_id}")`, parse each `data:` line as JSON, push onto that debate's `queue.Queue`, push a `{"node": "_STREAM_CLOSED"}` sentinel and return when the stream ends naturally (design.md, Decisions — "stream ends, then reopens")
- [x] 2.3 Implement `submit_audience_question(run_id, question)`: `POST /debate/{run_id}/audience-question`, then start a *second* stream-consumer thread against the same `run_id` (fresh queue) to receive the rest of the run
- [x] 2.4 Implement `drain_all_queues()`: on every rerun, drain every debate's queue into its `events` list, independent of which debate is currently active

## 3. Transcript rendering

- [x] 3.1 Build the node-id → (role, label, state-key) mapping for `pro_opening`, `con_opening`, `pro_rebuttal`, `con_rebuttal`, `pro_addresses_question`/`con_addresses_question` (→ `pro_audience_answer`/`con_audience_answer`), `pro_closing`, `con_closing` (spec.md "Chat-style transcript rendering"; design.md's node-id mapping decision)
- [x] 3.2 Render the `moderator` hub's own completion events as round dividers keyed off `state["round"]` (opening/rebuttal/audience/closing), replacing the old `moderator_open`/`moderator_checkpoint` two-node handling
- [x] 3.3 Render each speaker turn as a message bubble with a role color/label, with no node-id/"served by" caption (spec.md "No multi-node or failover presentation")
- [x] 3.4 Implement the once-per-turn typewriter reveal (`st.write_stream` over a word generator) gated by a `_shown` flag on the buffered event, so re-renders on later poll ticks show the same turn statically (spec.md "Turn reveal is animated exactly once")
- [x] 3.5 Render the `moderator_decision` event using `state["justification"]` and `state["winner"]` (not the old `state["moderator_summary"]`)
- [x] 3.6 Render `AWAITING_AUDIENCE_QUESTION_UNSUPPORTED` and `ERROR` events as inline error messages

## 4. Audience-question form

- [x] 4.1 Show the question form only when the active debate's latest event is `AWAITING_AUDIENCE_QUESTION` and no question has been submitted yet for that debate (spec.md "Audience-question form is gated to the pause window")
- [x] 4.2 On submit, call `submit_audience_question`, mark the debate's `question_submitted` flag, and hide the form; show a waiting indicator until the resumed stream's first event lands
- [x] 4.3 Render the `audience_question` node's own completion event (question text from `state["audience_question"]`) as its own transcript bubble, same as the pre-existing node/state-key pairing (design.md — this one carries over unchanged)

## 5. Debate history sidebar

- [x] 5.1 Render a sidebar listing every `run_id` in `st.session_state.debate_order` (most recent first), each showing its topic and a relative start time, matching the old UI's `relative_time()` helper
- [x] 5.2 Clicking a sidebar entry sets it as `active_run_id`; clicking "New Debate" clears `active_run_id` without discarding any other debate's background thread/history (spec.md "Session-scoped debate history")
- [x] 5.3 Render a "who's up next" pill beneath the transcript while a debate is running but not yet complete, derived from the latest node id, matching the old UI's per-round pill logic but without any node-identity text

## 6. Verification

- [x] 6.1 Manual run-through: start a debate with `MOCK_LLM=true`, follow it end-to-end (opening → rebuttal → submit an audience question → closing → verdict) in the browser
- [ ] 6.2 DEFERRED — Side-by-side comparison against `debate_bot/deployment/ui/streamlit_app.py`'s chat-transcript behavior (dividers, speaker turns, typewriter, gated form, sidebar) — confirm no node-health/failure-banner/LB UI is present (design.md, Risks — this is a manual/subjective check, not a scripted assertion). To be handled later.
- [ ] 6.3 DEFERRED — Confirm a second, concurrently-started debate keeps streaming into its own history entry while a different debate is being viewed. To be handled later.
