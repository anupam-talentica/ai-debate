# T4 — Multi-Node Local Infrastructure (docker-compose → Kubernetes)

## Objective
Replace the manual "run 3 uvicorn processes on 3 ports" setup from T2/T3 with real
containerized replicas behind a load balancer — the actual infrastructure the demo
will run on. This is where your existing Docker/K8s knowledge applies directly;
no new application logic is introduced in this task, just packaging.

## Depends On
T1, T2, T3 all working via the manual multi-process test setup.

## Implementation Additions
- `deployment/docker-compose.local.yml`:
  - `postgres` (postgres:16, volume for persistence)
  - `redis` (redis:7)
  - `debate-node` service defined once, run with `--scale debate-node=3` (or three
    explicit services `debate-node-1/2/3` if you want fixed, inspectable `NODE_ID`s —
    prefer explicit services for a demo, since `docker kill <name>` is easier to
    reason about live than picking a scaled instance by container ID).
    - env: `DATABASE_URL`, `REDIS_URL`, `NODE_ID` (`node-1`, `node-2`, `node-3`),
      `ANTHROPIC_API_KEY`
    - healthcheck hitting `/debate/health`
  - `nginx`:
    - `deployment/nginx.conf` — `proxy_buffering off;`, `proxy_read_timeout 3600s;`,
      `proxy_set_header Connection '';`, `chunked_transfer_encoding on;` (SSE needs
      all of these or the stream will buffer/hang through the proxy), round-robin
      upstream across `node-1:8000`, `node-2:8000`, `node-3:8000`.
    - exposed on host `:8080`.
- `deployment/k8s/` (secondary target, once compose works):
  - `postgres-deployment.yaml` + `postgres-service.yaml` (or reuse an external PG for
    simplicity — a local single-pod Postgres is fine for a demo, no need for an
    operator/StatefulSet).
  - `redis-deployment.yaml` + `redis-service.yaml`.
  - `debate-node-deployment.yaml` (`replicas: 3`), each pod's `NODE_ID` set from
    `metadata.name`/`spec.nodeName` via the Downward API so it's unique automatically.
  - `debate-node-service.yaml` (ClusterIP, round-robins across pods by default).
  - Optional `ingress.yaml` if you want a URL instead of port-forwarding.

## Local Test Environment
Nothing extra — this task *is* the environment. Requires Docker (already have) and,
for the K8s half, `kind` or `minikube` (confirm one is installed before starting;
this task assumes "basic Kubernetes understanding," not a running cluster).

## Test Procedure — docker-compose

1. **Bring up the stack:**
   ```bash
   cd debate_bot
   docker compose -f deployment/docker-compose.local.yml up --build
   ```
   Confirm all 5 containers (postgres, redis, node-1, node-2, node-3) report healthy:
   ```bash
   docker compose -f deployment/docker-compose.local.yml ps
   ```

2. **Confirm the LB round-robins.** Add a response header or log line exposing
   `NODE_ID` per request, then:
   ```bash
   for i in 1 2 3 4 5 6; do curl -s http://localhost:8080/debate/health | grep -o 'node-[0-9]'; done
   ```
   Expect to see `node-1`, `node-2`, `node-3` cycling (exact order depends on nginx's
   default round-robin, but all three should appear).

3. **Re-run T3's failover test through the LB instead of raw ports:**
   ```bash
   curl -X POST http://localhost:8080/debate/start -d '{"topic": "Universal basic income"}'
   curl -N http://localhost:8080/debate/stream/<run_id>
   ```
   Mid-stream, find and kill whichever container actually claimed ownership:
   ```bash
   psql $DATABASE_URL -c "SELECT node_id FROM run_ownership WHERE run_id='<run_id>';"
   docker kill debate-node-<that-number>
   ```
   Reconnect through the LB (`curl -N http://localhost:8080/debate/stream/<run_id>`
   again) and confirm it resumes and completes via a surviving container.

4. **Confirm SSE actually survives the nginx hop** specifically (this is the part
   most likely to silently buffer/break) — watch that events arrive incrementally in
   the curl output, not all at once at the very end.

## Test Procedure — Kubernetes (secondary, once compose is proven)

1. `kind create cluster --name debate-demo` (or `minikube start`).
2. `kubectl apply -f deployment/k8s/`.
3. `kubectl get pods -w` — confirm 3 `debate-node` pods reach `Running`.
4. `kubectl port-forward svc/debate-node 8080:8000` (or use the Ingress if configured).
5. Repeat the same start → stream → kill → resume test, using
   `kubectl delete pod <pod-name>` instead of `docker kill` as the failure injection.
   Note: a deleted pod's replacement gets a *new* pod name/IP — the important check
   is that a **different existing pod** (one of the other 2 replicas) picks up
   ownership before the replacement even finishes scheduling.

## Cleanup
```bash
docker compose -f deployment/docker-compose.local.yml down -v
kind delete cluster --name debate-demo   # if used
```

## Gotchas
- The single most common way this silently fails: forgetting `proxy_buffering off`
  in nginx — the SSE stream will appear to hang until the connection closes, then
  dump everything at once. Test this explicitly (step 4) before moving to T5.
- If using compose's `--scale` instead of named services, `docker kill` needs the
  auto-generated container name (`docker compose ps` to find it) — named services
  (`debate-node-1`, etc.) are easier to target live during a demo.
