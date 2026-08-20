# T3 — Run Ownership + Heartbeat (Automatic Failover)

## Objective
This is the task that actually delivers "kill the executing node, a different node
continues the debate." T1 gave us resumability; T2 gave us relay. T3 adds the
missing piece: a way for a node to detect that the run's owner is dead and take over
execution itself, instead of execution always being pinned to whichever node
received `/start`.

## Depends On
T1 (checkpointer/resume) and T2 (redis publish/subscribe, start/stream split).

## Implementation Additions
- Postgres table (add to the same `DATABASE_URL` database from T1):
  ```sql
  CREATE TABLE run_ownership (
    run_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'running'  -- running | done | failed
  );
  ```
- `NODE_ID` env var per process (already introduced in T2's test, now used for real).
- `deployment/app_ext/ownership.py`:
  - `claim(run_id, node_id) -> bool` — 
    `INSERT INTO run_ownership (run_id, node_id, heartbeat_at) VALUES (...) ON CONFLICT (run_id) DO UPDATE SET node_id = EXCLUDED.node_id, heartbeat_at = now() WHERE run_ownership.heartbeat_at < now() - interval '10 seconds' RETURNING node_id`
    — returns True only if *this* node_id ends up owning the row.
  - `heartbeat(run_id, node_id)` — refresh `heartbeat_at` while executing (called
    every ~3s from a background task alongside the `graph.astream` loop).
  - `is_owned_and_alive(run_id) -> bool` — for a stream-only request to decide whether
    to just relay (T2 behavior) or claim + execute (new behavior).
- `GET /debate/stream/{run_id}` logic changes:
  1. Subscribe to Redis first (never miss an event).
  2. If `is_owned_and_alive(run_id)` → relay only, exactly like T2.
  3. Else → `claim(run_id, NODE_ID)`; if claim succeeds, start `execute_and_publish`
     as a background task on **this** node (resuming via T1's checkpointer +
     `thread_id=run_id`, since a checkpoint already exists from whoever ran it before),
     while also relaying from Redis to this client.
- `POST /debate/start` now just creates the initial `run_ownership` row (or lets the
  first `/stream` call claim it) — the actual execution trigger is unified through the
  claim path so there's exactly one code path for "start" and "resume."

## Local Test Environment
Same as T2 (Postgres + Redis running), plus the new table:
```bash
psql $DATABASE_URL -f deployment/tasks/sql/run_ownership.sql
```

## Test Procedure

1. **Start three local processes** (simulating three nodes, still manual — full
   containerized multi-replica setup is T4):
   ```bash
   NODE_ID=node-a uvicorn server:app --port 8001 &
   NODE_ID=node-b uvicorn server:app --port 8002 &
   NODE_ID=node-c uvicorn server:app --port 8003 &
   ```

2. **Start a debate on node-a:**
   ```bash
   curl -X POST http://localhost:8001/debate/start -d '{"topic": "AI regulation"}'
   # => {"run_id": "run-fail01"}
   curl -N http://localhost:8001/debate/stream/run-fail01
   ```
   Confirm in Postgres that node-a owns it:
   ```bash
   psql $DATABASE_URL -c "SELECT node_id, heartbeat_at FROM run_ownership WHERE run_id='run-fail01';"
   # node_id = node-a
   ```

3. **Let 2-3 nodes complete** (watch the SSE output for `moderator_open`,
   `pro_opening`, `con_opening`).

4. **Kill node-a hard**, simulating a real crash (not a graceful shutdown):
   ```bash
   kill -9 %1
   ```

5. **Wait ~12 seconds** (past the 10s heartbeat staleness window), then attach to a
   *different* node for the same `run_id`:
   ```bash
   curl -N http://localhost:8002/debate/stream/run-fail01
   ```
   Expected:
   - node-b's logs show it detected a stale owner and claimed the run.
   - The debate **resumes from `con_opening` or wherever it left off** (per T1's
     checkpoint), not from `moderator_open`.
   - The debate completes with `moderator_decision` and a winner.
   - `psql ... SELECT node_id FROM run_ownership WHERE run_id='run-fail01';` now
     shows `node-b`.

6. **Race check:** immediately after killing node-a, attach `/stream/run-fail01` on
   **both** node-b and node-c within the same second. Confirm only one of them
   actually claims ownership and executes (check logs — one says "claimed", the
   other says "already owned, relaying only"), and both still stream the identical
   event sequence to their respective clients. This proves the `ON CONFLICT ... WHERE`
   claim is race-safe, not just "first one wins by luck."

7. **No-duplicate-work check:** confirm the debate produces exactly one
   `moderator_decision` / winner, not two (i.e., node-a coming back from the dead
   after node-b already resumed shouldn't cause a duplicate run — optional stretch
   check, node-a is dead in this test so this mainly documents the assumption).

## Cleanup
```bash
kill %2 %3 2>/dev/null
psql $DATABASE_URL -c "DROP TABLE run_ownership;"
```

## Gotchas
- The 10-second staleness window is a demo-friendly value — tune it for how
  patient you want the demo to look. Too short and a briefly-slow node gets its
  run stolen; too long and the failover looks unconvincing on camera.
- `kill -9` (not Ctrl+C) is important for the test — a graceful shutdown could be
  special-cased to release ownership immediately, which wouldn't demonstrate the
  heartbeat-timeout path this task is actually about.
- Make sure the heartbeat background task is cancelled/stopped when a node's
  execution finishes normally (`status='done'`), so a completed run doesn't look
  perpetually "owned" if inspected later.
