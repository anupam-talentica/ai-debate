#!/usr/bin/env bash
# T5 failover demo driver.
#
#   ./deployment/demo_failover.sh                    - bring up the stack + UI
#   ./deployment/demo_failover.sh kill-executor <id>  - kill whichever node
#                                                        currently owns <id>
set -euo pipefail

cd "$(dirname "$0")/.."   # repo root (debate_bot/)

COMPOSE_FILE="deployment/docker-compose.local.yml"
LB_URL="http://localhost:8080"

usage() {
  echo "Usage: $0 [up|kill-executor <run_id>]" >&2
  exit 1
}

kill_executor() {
  local run_id="${1:-}"
  if [ -z "$run_id" ]; then
    echo "Usage: $0 kill-executor <run_id>" >&2
    exit 1
  fi

  local database_url
  database_url=$(grep -E '^DATABASE_URL=' .env 2>/dev/null | tail -1 | cut -d '=' -f2-)
  database_url=${database_url:-postgresql://postgres:postgres@localhost:5432/debate_bot}

  local node_id
  node_id=$(psql "$database_url" -tAc "SELECT node_id FROM run_ownership WHERE run_id='${run_id}';" | tr -d '[:space:]')

  if [ -z "$node_id" ]; then
    echo "No owner found for run_id=${run_id} — has the debate started yet?" >&2
    exit 1
  fi

  local container="debate-${node_id}"
  echo "run_id=${run_id} is currently owned by ${node_id} -> docker kill ${container}"
  docker kill "$container"
}

bring_up() {
  echo "==> Bringing up the multi-node stack (postgres, redis, node-1/2/3, nginx)..."
  docker compose -f "$COMPOSE_FILE" up -d --build

  echo "==> Waiting for the load balancer to answer..."
  for _ in $(seq 1 30); do
    if curl -sf "${LB_URL}/debate/health" >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done

  echo
  docker compose -f "$COMPOSE_FILE" ps
  echo
  echo "Stack is up behind the LB at ${LB_URL}"
  echo
  echo "Once the Streamlit UI opens: start a debate, copy the run_id it shows, then"
  echo "in another terminal run:"
  echo
  echo "    ./deployment/demo_failover.sh kill-executor <run_id>"
  echo
  echo "==> Launching the Streamlit UI (Ctrl+C to stop)..."
  exec streamlit run deployment/ui/streamlit_app.py
}

case "${1:-up}" in
  kill-executor) kill_executor "${2:-}" ;;
  up) bring_up ;;
  *) usage ;;
esac
