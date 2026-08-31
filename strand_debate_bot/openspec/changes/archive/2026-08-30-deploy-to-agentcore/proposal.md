## Why

`Debate-Bot-Strands-Migration-PRD.md` scoped this rewrite in two stages: a local target (Phases 0-7 — core graph, memory, HITL, API, durability, mock mode, demo UI) and an AWS target (Phase 8 — deploy the same graph to Bedrock AgentCore Runtime). Phases 0-7 are complete and archived (`2026-08-23-core-debate-graph`, `2026-08-23-cross-debate-memory`, `2026-08-23-audience-question-hitl`, `2026-08-23-debate-fastapi-surface`, `2026-08-23-debate-durability`, `2026-08-23-mock-mode-eval-fixtures`, `2026-08-30-demo-ui`). This change is Phase 8: get the validated local system running on AgentCore Runtime, the platform this whole rewrite was built toward (PRD G8), without changing the graph, agents, prompts, or debate behavior that Phases 0-7 already proved out.

## What Changes

- Add an AgentCore-compatible HTTP entrypoint (`POST /invocations`, `GET /ping`, port 8080) that dispatches to the existing `DebateService` methods via an `action` field in the request payload (`start`, `stream`, `submit_audience_question`, `resume`, `invoke`) — the existing REST surface in `src/api/routes/debates.py` is left unchanged and keeps serving local dev and the Streamlit demo UI unmodified.
- Map each debate 1:1 to an AgentCore `runtimeSessionId` (the existing `run_id` serves directly as the session id), relying on AgentCore's documented session-to-microVM affinity to keep a paused run's live `RunRegistry` entry, `Graph` object, and event queue reachable across the separate HTTP calls a pause-then-resume flow requires — no new in-process coordination mechanism is introduced.
- Swap `FileSessionManager` for `S3SessionManager` in `build_graph()` (`src/core/graph.py`), and rewrite `src/core/session.py`'s hand-rolled `invocation_state` persistence (currently `glob`/`tempfile`/`os.path` against local disk) to call `S3SessionManager`'s `create_multi_agent`/`read_multi_agent` API instead.
- Add a new `MemoryStore` implementation backed by Amazon S3 Vectors, matching `ChromaMemoryStore`'s existing shape (`search`/`add`, called directly from `src/agents/moderator.py`'s node code — no change to *when* or *how* memory is used), and wire it in as the memory-store backend for the AgentCore deployment.
- Containerize the app for `linux/arm64`, publish to ECR, and deploy via `create_agent_runtime` with `idleRuntimeSessionTimeout` configured for a realistic audience-question wait (recommend a few hours) rather than the 900s default.
- Enable AgentCore Observability (CloudWatch/OTel traces) per PRD G8 — additive, existing local logging is untouched.
- **BREAKING**: none to existing local-dev behavior. The REST surface, demo UI, and mock mode are all unaffected; this change only adds an alternate entrypoint and swaps two storage backends behind interfaces (`SessionManager`, `MemoryStore`) that already abstract over their implementation.

Explicitly out of scope (evaluated and rejected earlier in this change's discovery, see design.md):
- AgentCore Memory and OpenSearch Serverless as the memory backend.
- AgentCore Managed Session Storage as the durability backend.
- Any change to graph topology, node return contracts, or the round state machine.
- Switching the model layer from direct Anthropic API (`AnthropicModel`) to Bedrock's hosted Claude — left as an open question in design.md, not decided here.

## Capabilities

### New Capabilities
- `agentcore-deployment`: the system's AgentCore Runtime-compatible invocation contract — a single `POST /invocations` endpoint dispatching by action, a `GET /ping` health check, and the session-identity mapping that lets a paused debate be resumed through AgentCore's session model.

### Modified Capabilities
(none — swapping `debate-durability`'s and `cross-debate-memory`'s storage backends changes no requirement either spec describes; both are written behavior-first with no implementation named, so the backend swap is an implementation detail confined to design.md, not a spec-level change.)

## Impact

- New: an AgentCore entrypoint module (routing + action dispatch over the existing `DebateService`), a `Dockerfile`, and deploy tooling (ECR push, `create_agent_runtime` invocation with `lifecycleConfiguration`).
- Modified: `src/core/session.py` (S3SessionManager-backed persistence), `src/core/graph.py` (`build_graph()` session-manager wiring), `src/core/memory.py` (new S3-Vectors-backed store class), `app.py` (mounts or wraps the new entrypoint), `requirements.txt` (`boto3` for S3 Vectors; `strands-agents`'s `S3SessionManager` ships already).
- New AWS dependencies: an S3 bucket (session checkpoints), an S3 Vectors bucket + index (cross-debate memory), an ECR repository, an AgentCore Runtime resource, and an IAM execution role scoped to those.
- New config: S3 bucket/index names and region, surfaced the same way existing config (`ANTHROPIC_API_KEY`, `MEMORY_PERSIST_DIRECTORY`, etc.) is surfaced in `src/core/config.py`.
