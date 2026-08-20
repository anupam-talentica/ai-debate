# T1 — Postgres Checkpointer for Durable Graph State

## Objective
A debate's execution progress survives a process crash/restart on the **same** node.
This is the foundation everything else (T2-T5) builds on — no other task can be
meaningfully tested without it.

## Depends On
Nothing (base repo state). This task also stands up the Postgres instance that T3
will reuse for the `run_ownership` table.

## Implementation Additions
- `requirements.txt`: add `langgraph-checkpoint-postgres`, `psycopg[binary,pool]`.
- `src/core/graph.py`: `build_graph(memory_store=None, checkpointer=None)` →
  `g.compile(checkpointer=checkpointer)`.
- `app.py`: build an `AsyncPostgresSaver.from_conn_string(DATABASE_URL)`, call
  `await checkpointer.setup()` once at startup (idempotent — creates the
  `checkpoints`/`checkpoint_writes` tables if missing), pass it into `build_graph`.
- `src/api/services/debate_service.py`: `stream_debate(topic: str, run_id: str)`:
  - builds `config = {"configurable": {"thread_id": run_id}}`
  - checks `await graph.aget_state(config)` — if it has no existing checkpoint, call
    `graph.astream(initial_state, config)` (fresh start); if a checkpoint already
    exists for this `run_id`, call `graph.astream(None, config)` (resume — LangGraph
    reads the last checkpoint and continues from the next pending node).
- `src/api/routes/debates.py`: `/debate/stream` accepts an optional `run_id` query
  param. If absent, generate a `uuid4` and include it in the first SSE event so the
  caller can capture it for a later resume call.

## Local Test Environment
```bash
docker run -d --name debate-postgres \
  -e POSTGRES_USER=debate -e POSTGRES_PASSWORD=debate -e POSTGRES_DB=debate \
  -p 5432:5432 postgres:16

export DATABASE_URL="postgresql://debate:debate@localhost:5432/debate"
```

## Test Procedure

1. **Start the app** (single process, as today):
   ```bash
   cd debate_bot && DATABASE_URL=$DATABASE_URL python server.py
   ```

2. **Kick off a debate without a `run_id`:**
   ```bash
   curl -N "http://localhost:8000/debate/stream?topic=Should+AI+write+code"
   ```
   Note the `run_id` returned in the first SSE event, e.g. `run-abc123`.

3. **Simulate a mid-debate crash.** Once you see `moderator_open` and `pro_opening`
   events printed, kill the curl client (Ctrl+C) **and** kill the server process
   (Ctrl+C in its terminal) before `con_opening` completes.

4. **Confirm partial progress was persisted**, independent of the killed process:
   ```bash
   psql $DATABASE_URL -c \
     "SELECT thread_id, checkpoint_id FROM checkpoints WHERE thread_id='run-abc123' ORDER BY checkpoint_id;"
   ```
   Expect at least 2 rows (one per completed node) even though the server is dead.

5. **Restart the server** (same `DATABASE_URL`, fresh process):
   ```bash
   DATABASE_URL=$DATABASE_URL python server.py
   ```

6. **Resume the same run:**
   ```bash
   curl -N "http://localhost:8000/debate/stream?run_id=run-abc123"
   ```
   Expected: the very first event streamed is **`con_opening`** (not `moderator_open`
   again) — proof it resumed rather than restarted. Confirm the debate proceeds
   through rebuttal, closing, and `moderator_decision`, and a `winner` is produced.

7. **Sanity check a totally fresh run still works end-to-end** without a `run_id`,
   uninterrupted, to confirm T1 didn't break the non-failure path.

## Cleanup
```bash
docker stop debate-postgres && docker rm debate-postgres
```

## Gotchas
- `checkpointer.setup()` must run before the first request — call it during FastAPI's
  `lifespan` startup, not lazily on first request (race condition otherwise).
- `graph.astream(None, config)` only resumes correctly if `thread_id` is reused
  *exactly* — treat `run_id` as an opaque string, don't regenerate it per request.
