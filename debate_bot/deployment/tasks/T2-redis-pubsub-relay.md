# T2 — Redis Pub/Sub Streaming Relay

## Objective
Prove that a node with **no involvement in executing a run** can still stream that
run's events to a client, purely by relaying Redis pub/sub messages. This isolates
Redis's actual job before T3 adds failover logic on top.

To keep this task independently testable, execution and streaming are split into two
endpoints:
- `POST /debate/start` — creates the run and executes it on whichever node receives
  this call (still single fixed executor, no failover yet — that's T3).
- `GET /debate/stream/{run_id}` — **only** subscribes to Redis and relays. It never
  touches the graph in this task.

## Depends On
T1 (checkpointer + `run_id` concept already exist).

## Implementation Additions
- `requirements.txt`: add `redis` (uses `redis.asyncio`).
- `deployment/app_ext/event_bus.py`:
  - `async def publish(run_id: str, event: dict) -> None` — `XADD`/`PUBLISH` to
    channel `debate:{run_id}`.
  - `async def subscribe(run_id: str) -> AsyncGenerator[dict, None]` — subscribes and
    yields decoded events as they arrive.
- `src/api/routes/debates.py`:
  - New `POST /debate/start {topic}` → generates `run_id`, calls
    `debate_service.execute_and_publish(topic, run_id)` as a background task (don't
    block the response), returns `{"run_id": ...}` immediately.
  - `GET /debate/stream/{run_id}` → rewritten to `async for event in event_bus.subscribe(run_id): yield sse(event)`. No graph calls here at all.
- `src/api/services/debate_service.py`: new `execute_and_publish(topic, run_id)` —
  same `graph.astream` loop as T1, but each event goes through `event_bus.publish(run_id, event)` instead of (or in addition to) a direct yield.

## Local Test Environment
```bash
docker run -d --name debate-redis -p 6379:6379 redis:7
export REDIS_URL="redis://localhost:6379"
# Postgres from T1 still running
```

## Test Procedure

1. **Start two separate instances of the app on different ports**, both pointed at
   the same Postgres and Redis:
   ```bash
   DATABASE_URL=$DATABASE_URL REDIS_URL=$REDIS_URL NODE_ID=node-a \
     uvicorn server:app --port 8001 &

   DATABASE_URL=$DATABASE_URL REDIS_URL=$REDIS_URL NODE_ID=node-b \
     uvicorn server:app --port 8002 &
   ```

2. **Start a debate on node-a:**
   ```bash
   curl -X POST http://localhost:8001/debate/start \
     -H "Content-Type: application/json" \
     -d '{"topic": "Should AI write code"}'
   # => {"run_id": "run-xyz789"}
   ```
   Node-a is now executing the graph in the background and publishing every event
   to Redis channel `debate:run-xyz789`.

3. **Immediately attach to node-b for streaming** (the node that did *nothing* to
   start this run):
   ```bash
   curl -N http://localhost:8002/debate/stream/run-xyz789
   ```
   Expected: node-b streams the full debate — `moderator_open`, `pro_opening`,
   `con_opening`, ... through `moderator_decision` — despite never calling
   `graph.astream` itself. Confirm via node-b's logs that it only logs
   "subscribed to debate:run-xyz789" / "relayed event X", never "executing node X".

4. **Cross-check node-a's own stream still works too** — attach `GET /debate/stream/run-xyz789` on port 8001 as well (either before or after node-b) and confirm both clients receive the identical sequence of events (Redis pub/sub fans out to all subscribers).

5. **Negative check:** attach `GET /debate/stream/{random-uuid-not-started}` to
   either node — confirm it just hangs waiting for events (nothing published) rather
   than erroring, since no `/start` call created that channel.

## Cleanup
```bash
kill %1 %2   # the two backgrounded uvicorn processes
docker stop debate-redis && docker rm debate-redis
```

## Gotchas
- Redis pub/sub has no history — a subscriber that connects *after* an event was
  published misses it. If node-b subscribes late (after `moderator_open` already
  fired), it'll only see events from that point forward. This is expected at this
  stage; if you want late-joiners to see everything from the start, that's an
  enhancement (e.g. Redis Streams + replay), not required for this task's acceptance.
- Keep `POST /start` non-blocking (background task) — don't await the full debate
  before responding, or you lose the "start on one node, watch from another" test.
