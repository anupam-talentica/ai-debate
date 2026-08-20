# T5 — UI Client + Failover Demo Script

## Objective
A visible, repeatable, non-technical-audience-friendly demo: type a topic, watch the
debate stream live, watch it survive a killed node, without anyone needing to read
curl output or Postgres tables to believe it.

## Depends On
T4 (multi-node infra behind a load balancer, already proven to survive node kills
via curl in T4's test procedure).

## Implementation Additions
- `deployment/ui/streamlit_app.py`:
  - Topic text input + "Start Debate" button → `POST {LB_URL}/debate/start` → stores
    `run_id` in `st.session_state`.
  - Streams `GET {LB_URL}/debate/stream/{run_id}` using `httpx.stream("GET", ...)`
    (Streamlit doesn't have native `EventSource`; iterate the response line-by-line
    and re-render incrementally — a placeholder per speaker via `st.empty()`,
    updated as each event arrives, works well for reruns).
  - Each rendered event includes the `node_id` that produced it (surfaced via a
    response field or SSE comment line) — this is the visual proof that the debate
    crossed nodes, e.g. "Pro (opening) — served by node-2" followed later by
    "Con (rebuttal) — served by node-3" after a kill.
  - A visible "Nodes: node-1 ✅ node-2 ✅ node-3 ✅" status row, polling
    `/debate/health` on each node directly (not through the LB) every couple seconds,
    so the audience can see a node go from ✅ to ❌ right as you kill it.
- `deployment/demo_failover.sh`:
  1. `docker compose -f deployment/docker-compose.local.yml up -d`
  2. Wait for health checks to pass.
  3. `streamlit run deployment/ui/streamlit_app.py` (or print instructions to open it
     manually — a script that also launches a UI process is fine for a local demo).
  4. Print instructions: "Start a debate in the UI, then run:
     `./deployment/demo_failover.sh kill-executor <run_id>`"
  5. A `kill-executor <run_id>` mode: looks up the current owner via
     `psql $DATABASE_URL -c "SELECT node_id FROM run_ownership WHERE run_id='$1';"`
     and `docker kill`s that specific container — so the script always kills the
     node actually doing the work, not a random one.

## Local Test Environment
Requires T4's full stack running (`docker-compose.local.yml`) plus Python/Streamlit
locally (`pip install streamlit httpx`, add to `requirements-dev.txt` or similar —
UI deps don't belong in the main app's `requirements.txt` since the UI isn't
deployed inside the debate-node containers).

## Test Procedure

1. **Bring up the stack and the UI:**
   ```bash
   ./deployment/demo_failover.sh
   ```
   Confirm the Streamlit page loads at `http://localhost:8501` and the node status
   row shows all 3 nodes ✅.

2. **Start a debate from the UI.** Type a topic, click "Start Debate." Confirm:
   - The `run_id` appears somewhere in the UI (small text is fine — needed for step 3).
   - Pro/Con/Moderator turns render incrementally as they complete, each labeled
     with the serving `node_id`.

3. **Trigger the failover mid-debate:**
   ```bash
   ./deployment/demo_failover.sh kill-executor 3e9c9f83-5d5d-4c8d-a8a6-d2d2dc796b08
   ```
   Watch the UI: the node status row should flip the killed node to ❌ within a
   couple seconds. The debate stream should briefly pause (up to the ~10-15s
   heartbeat-staleness window from T3), then resume — and the `node_id` label on
   the next rendered turn should differ from the one before the kill.

4. **Confirm completion:** the UI shows a final winner and moderator summary exactly
   once — not duplicated, not stuck.

5. **Repeat with a different node killed** (kill whichever one currently owns a
   *fresh* run) to confirm the failover isn't dependent on which specific node
   happens to die — any of the 3 can go down and any of the remaining 2 can pick up.

6. **Full audience-facing dry run:** do one complete pass start-to-finish, timing how
   long the visible "pause" is after a kill, and confirm it reads clearly on screen
   (adjust T3's heartbeat timeout if 10s feels too long or too short for a live demo).

## Cleanup
```bash
docker compose -f deployment/docker-compose.local.yml down -v
# stop the streamlit process (Ctrl+C or kill its PID)
```

## Gotchas
- Streamlit reruns its whole script on each interaction/rerun trigger by design —
  make sure the SSE-consuming loop uses `st.session_state` to avoid restarting the
  stream connection on every rerun (e.g. run the stream consumption in a background
  thread that appends to a session-state list, and have the main script just render
  that list — polling/`st.rerun()` on an interval, since Streamlit isn't natively
  async-stream-friendly).
- If the "pause" after a kill isn't visually obvious, add an explicit UI banner
  ("Node failure detected, resuming on another node...") driven by the node-health
  polling from step 1, rather than relying on the audience to notice a gap in text.
