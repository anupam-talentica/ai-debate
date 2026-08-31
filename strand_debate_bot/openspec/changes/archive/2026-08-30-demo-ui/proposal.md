## Why

TRD Task 8 / PRD FR-12 (G7) calls for a Streamlit demo UI on top of the new Strands debate graph, minus everything that exists only to narrate multi-node failover. Both of this task's prerequisites — `mock-mode-eval-fixtures` and `debate-durability` — are now complete (16/16 tasks each), so cost-free manual iteration is possible and the API surface it talks to is stable. The only prior UI for this product is `debate_bot/deployment/ui/streamlit_app.py` (a sibling directory, same outer repo), built for a retired multi-node LB/failover deployment that this rewrite explicitly drops; that file's chat-transcript UX is the reference this port targets, not its LB/health/failover code.

## What Changes

- Add a new Streamlit app (`ui/streamlit_app.py`) that talks directly to this project's single FastAPI process (no load balancer) via the `POST /debate/start` → `GET /debate/stream/{run_id}` → `POST /debate/{run_id}/audience-question` flow, plus `POST /debate/invoke` is out of scope for the UI (no interactive path for the pause).
- Port the chat-style transcript rendering from the old UI: sidebar of debates started this session, moderator dividers, per-speaker message bubbles, a "who's up next" pill, and an audience-question form gated on the pause state — remapped onto this graph's actual node ids and state fields (single recurring `moderator` hub instead of `moderator_open`/`moderator_checkpoint`; `state["justification"]` instead of the old `state["moderator_summary"]`; no `node_id` field anywhere in this backend's SSE events).
- Reproduce the "typewriter" reveal effect client-side (`st.write_stream` over a word generator) — the backend only emits whole-turn-complete events, not token deltas, so this is a simulated animation, not a reflection of live generation.
- Handle the audience-question pause as two sequential SSE connections (the stream ends when `AWAITING_AUDIENCE_QUESTION` arrives; after submitting the question, the UI reopens `GET /debate/stream/{run_id}` against a fresh server-side queue) rather than one continuous connection.
- **BREAKING (relative to the old UI only, not this system):** drop `render_node_status()`, per-node health polling (`NODE_HEALTH_URLS`), the failure banner, "resumed on node X" narration, and the `LB_URL` indirection — none of these concepts exist in this single-process backend.
- Add `streamlit` to `requirements.txt` (httpx is already a dependency).

## Capabilities

### New Capabilities
- `demo-ui`: A Streamlit application that renders a running or completed debate as a chat-style transcript — moderator round dividers, animated Pro/Con/Moderator turns, an audience-question form active only during the post-rebuttal pause, and a session-scoped sidebar of past debates — driven entirely by this project's existing FastAPI SSE contract, with no multi-node/failover-specific UI.

### Modified Capabilities
(none — `debate-fastapi-surface` and the other existing capabilities are consumed as-is; nothing about their requirements changes)

## Impact

- New file: `ui/streamlit_app.py`.
- `requirements.txt`: add `streamlit`.
- Consumes existing endpoints unchanged: `POST /debate/start`, `GET /debate/stream/{run_id}`, `POST /debate/{run_id}/audience-question` ([src/api/routes/debates.py](../../../src/api/routes/debates.py)).
- No changes to the graph, agents, memory, durability, or mock-mode code.
