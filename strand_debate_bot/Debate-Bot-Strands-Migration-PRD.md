# Debate Bot on Strands Agents + Bedrock AgentCore

**Status:** Draft for review — seed content for an OpenSpec change proposal
**Source system analyzed:** `debate_bot` (LangGraph + LangChain + Claude, current `main`/`deployment` branches)
**Target stack:** Strands Agents SDK, deployed to Amazon Bedrock AgentCore Runtime
**Scope decision (confirmed):** Full feature parity with the current system, **excluding** multi-node automatic failover and the Redis pub/sub relay — AgentCore Runtime's own session isolation replaces that concern.
**Delivery sequencing (confirmed):** **Local-first.** Build and validate the entire Strands system with zero AWS dependency, then port to Bedrock AgentCore as a distinct, later stage — not a precondition. Every capability below is written as *Local target → AWS target*, and Section 10 labels each delivery phase accordingly.

---

## 1. Purpose & Background

The current debate bot is a FastAPI + LangGraph system that runs a structured Pro/Con/Moderator debate with cross-debate RAG memory, a human-in-the-loop audience-question pause, durable Postgres checkpointing, and a multi-node HA deployment (Redis relay + ownership-based automatic failover) demoed through a Streamlit UI. It has outgrown a simple demo — it's a working reference for agentic-orchestration patterns (state machines, interrupts, streaming, durability) that the org is now evaluating on **Strands Agents + Bedrock AgentCore** as the production agent platform (see the parallel `docs/marvell/agentic-poc-spec.md` POC, which frames the same stack choice for a Supply Chain/Finance triage agent).

This PRD re-scopes the debate bot as a **Strands-native reference implementation**: same product behavior, same interactive/HITL/memory features, rebuilt on Strands' own primitives (`GraphBuilder`, interrupts, a `strands.memory.types.MemoryStore`, session managers, async-iterator streaming). Two deployment targets are addressed, in sequence:

1. **Local target (build here first):** everything runs on a developer machine with no AWS account required — local Strands agents, `FileSessionManager` for durability, a local vector store (Chroma, as today) for cross-debate memory, and the existing FastAPI/Streamlit surface.
2. **AWS target (later stage):** the same graph deployed to Bedrock AgentCore Runtime, swapping only the session manager and memory-store backend — Strands' own docs frame this as a drop-in swap ("you can define a different session manager and swap the component without rewriting the entire app"), not a rewrite.

Nothing about the graph, agents, prompts, or API contract should differ between the two targets — only the storage/runtime adapters underneath them.

## 2. Goals

- **G1.** Preserve the full debate experience: opening → rebuttal → (audience question) → closing → verdict, with Pro and Con as adversarial, context-aware agents and a Moderator that drives the round state machine and renders a final decision.
- **G2.** Preserve cross-debate memory: a debate on a previously-seen (or similar) topic should retrieve and build on prior debates' arguments.
- **G3.** Preserve the human-in-the-loop audience-question pause, including its effect on the final verdict.
- **G4.** Preserve durable, resumable execution — a debate survives a process restart — using Strands-native session persistence (`FileSessionManager` locally, an AWS-backed manager or AgentCore's native session persistence later) rather than a hand-rolled Postgres checkpointer. **Postgres is not part of the target architecture** — Strands ships no Postgres session manager, and the documented local→AWS upgrade path is File → S3/AgentCore, not File → Postgres.
- **G5.** Preserve the API surface's *behavior* (sync invoke, SSE streaming, start + resume, submit-audience-question) adapted to a single-runtime-session execution model.
- **G6.** Preserve cost-free local iteration via a mock/replay mode.
- **G7.** Preserve the Streamlit demo UI's debate-transcript experience, minus everything that exists only to demonstrate multi-node failover.
- **G8.** Deploy to Bedrock AgentCore Runtime and pick up its native Observability (CloudWatch/OTel traces) in place of ad hoc logging.

## 3. Scope

| | In scope | Notes |
|---|---|---|
| ✅ | Pro / Con / Moderator agent workflow | Rebuilt as a Strands `GraphBuilder` graph |
| ✅ | Round state machine (opening → rebuttal → closing → decision) | Conditional + cyclic edges |
| ✅ | Cross-debate RAG memory | A custom Chroma-backed `strands.memory.types.MemoryStore`, called directly (`search`/`add`) from node code — not through `MemoryManager`'s agent-attached tool/injection machinery (see Capability Mapping) |
| ✅ | Audience-question human-in-the-loop pause | Via Strands interrupt/resume |
| ✅ | Durable checkpoint/resume across process restarts | `FileSessionManager` locally → S3/AgentCore session persistence later |
| ✅ | FastAPI API surface (sync, SSE stream, start/resume, submit-question, health) | Adapted to single-session execution; identical locally and on AWS |
| ✅ | `MOCK_LLM` cached-transcript replay mode | Framework-agnostic; ported as-is in spirit |
| ✅ | Streamlit demo UI (chat-style transcript, typewriter, audience-question form) | Multi-node chrome removed |
| ✅ | Local-only development and demo (no AWS account required) | **Primary near-term deliverable** — see Section 10 |
| ✅ | Deployment to Bedrock AgentCore Runtime | Later stage, once the local build is validated end-to-end |
| ✅ | Observability | Local: existing logging is fine. AWS: AgentCore/CloudWatch traces |

| | Explicitly out of scope | Why |
|---|---|---|
| ❌ | Multi-node automatic failover (`deployment/app_ext/ownership.py`) | Confirmed out of scope — AgentCore's per-session isolation removes the "which node owns this run" problem this solved |
| ❌ | Redis pub/sub event relay (`deployment/app_ext/event_bus.py`) | Confirmed out of scope — only needed to let any node behind an LB relay another node's events |
| ❌ | nginx load balancer / multi-node `docker-compose.yml` topology | Follows from the above — no fleet to balance across |
| ❌ | Streamlit's per-node health polling, failure banner, "resumed on node X" chrome | Existed only to narrate the failover story |

## 4. Current System — Feature Inventory

*(Reference for parity checking; see Appendix A for exact file paths in the source repo.)*

**Core orchestration**
- 12-node LangGraph `StateGraph`: `moderator_open → pro_opening → con_opening → moderator_checkpoint →[conditional]→ {pro_rebuttal…, pro_closing…, moderator_decision}`, with `moderator_checkpoint` re-entered after both the rebuttal and audience-question branches (a cycle).
- Round tracked via a `round` field in a `TypedDict` state (`opening|rebuttal|closing|decision`); a pure Python function (`route_after_checkpoint`) chooses the next edge.
- `MOCK_LLM` env flag swaps every LLM-calling node for a cached-transcript replay (except the two audience-question responder nodes, which always call the real model since the question is novel each run).

**Agents**
- Pro/Con: four turns each (opening, rebuttal, audience-question answer, closing), each streaming from `ChatAnthropic` and built from a per-role, per-round prompt template with an explicit word-count ceiling. Con's opening is explicitly conditioned on Pro's opening (adversarial coupling).
- Moderator: opens the debate, advances the round state machine, triggers the audience-question pause, and produces the final verdict — including a **fragile heuristic** that regex/string-scans the verdict text for "winner:"/"winner is" to extract a winner label, falling back to scanning for a bare "Pro"/"Con" token.

**Memory**
- `MemoryStore`: HuggingFace `all-MiniLM-L6-v2` embeddings + Chroma (or in-memory) vector store. Each completed debate is upserted as a short text summary (topic, truncated Pro/Con openings, winner); a new debate's opening prompts retrieve the top-2 semantically similar past summaries, hard-capped to ~1200 characters, and inject them as a "past debate context" block instructing the model not to reference it explicitly.

**Human-in-the-loop**
- A dedicated `audience_question` node calls LangGraph's `interrupt()` once, after the rebuttal round, unless a question was already pre-supplied (letting the synchronous `/invoke` endpoint skip the pause entirely). The submitted question is answered by both Pro and Con, and the moderator's decision prompt is explicitly instructed to weigh how well each side handled it.

**API surface**
- `GET /debate/health` — liveness + node id.
- `POST /debate/invoke` — synchronous full run; 408 on timeout, 409 (with `run_id`) if it reaches the audience-question pause without a pre-supplied question, since a single request/response can't inject an answer mid-call.
- `GET /debate/stream` — SSE stream of a fresh, single-node run; explicitly errors (rather than crashing) if it hits the pause, since this simple path has no resume machinery.
- `POST /debate/start` + `GET /debate/stream/{run_id}` + `POST /debate/{run_id}/audience-question` — the ownership-tracked async path: claim a run, execute/stream it in the background, resume it with `Command(resume=question)` once the question arrives.
- `GET /debate/resume/{run_id}` — resume a checkpointed run from Postgres after a process restart.
- Typed exception hierarchy (`DebateExecutionError`, `DebateTimeoutError`, `DebateAwaitingInputError`, …) mapped to specific HTTP statuses at the route layer.

**Persistence**
- Every run checkpointed to Postgres via `AsyncPostgresSaver`, keyed by `thread_id = run_id`, enabling resume after restart independent of the memory store.

**Demo UI (Streamlit)**
- Chat-app layout: sidebar of past debates, main panel renders the transcript as moderator dividers + speaker turns with a word-by-word typewriter effect, an audience-question form that appears exactly while the debate is paused, a "who's up next" pill, and — **out of scope for the port** — per-node health polling bypassing the LB and a node-failure banner.

## 5. Target Architecture (Strands + AgentCore)

**Design decision (confirmed): moderator is the graph's single hub.** `moderator_open` and `moderator_checkpoint` collapse into one node — call it `moderator` — that is *revisited* after every round (opening, rebuttal, the audience-question exchange, and closing), using Strands' cyclic-graph support (`set_max_node_executions`, `reset_on_revisit`). Each visit reads a round counter from invocation state and dispatches exactly one round's Pro→Con sub-sequence, which always returns to the same hub. This also absorbs a small behavioral fix: today the audience-question pause is a *hardcoded, unconditional* edge off `con_rebuttal`; once it's just another branch the hub dispatches, every round-transition decision lives in one place instead of being split between `moderator_checkpoint`'s conditional and that one hardcoded edge.

Within each round, Con still reacts to Pro (confirmed: this is a sequential sub-chain inside the branch, not a true simultaneous fan-out) — so the shape below is a loop with a short detour, not a diamond.

```
                         ┌───────────────────────────────────────┐
                   ┌────▶│              moderator  (hub)           │◀────┐
                   │     │  merges moderator_open +                │     │
                   │     │  moderator_checkpoint; revisited each    │     │
                   │     │  round; invocation-state round counter   │     │
                   │     │  picks the next branch below             │     │
                   │     └───────────────────┬─────────────────────┘     │
                   │                         │ round = opening            │
                   │                         ▼                            │
                   │                   pro_opening                        │
                   │                         │                            │
                   │                         ▼                            │
                   │                   con_opening ─────────────────────┬─┘
                   │                                                    │
                   │  (same shape, one visit later)   round = rebuttal  │
                   │        pro_rebuttal ──▶ con_rebuttal ───────────────┤
                   │                                                    │
                   │  (same shape, one visit later)   round = audience  │
                   │        audience_question ◀─ interrupt/resume ─┐    │
                   │              │ (human answer)                  │    │
                   │              ▼                                 │    │
                   │        pro_addresses_question                   │    │
                   │              ▼                                 │    │
                   │        con_addresses_question ──────────────────┴────┤
                   │                                                    │
                   │  (same shape, one visit later)    round = closing  │
                   │        pro_closing ──▶ con_closing ─────────────────┘
                   │
                   │  final visit: round = done → moderator produces the
                   └──────────────────────────  verdict itself → END

async-iterator multi-agent events (one per node completion, across every hub visit and branch) ──▶ FastAPI SSE

┌─────────────────┐  invocation_state  ┌──────────────────────┐
│  Graph node code │◀ ─── search() ────▶│  Chroma-backed        │
│  (not the Agent)  │──── add()  ───────▶│  MemoryStore          │
└─────────────────┘   (direct calls,    └──────────────────────┘
                      no MemoryManager,
                      no tool/injection)

  Stage 1 — Local (build & validate here first, no AWS account needed)
┌──────────────────────────────────────────────────────────────┐
│  Local process (uvicorn)                                     │
│  — FileSessionManager persists graph state to disk            │
│  — Chroma (as today) backs the debate-memory store            │
│  — Python logging for observability                           │
└──────────────────────────────────────────────────────────────┘
                                │
                    swap session manager + memory-store
                    backend only — graph/agents/API unchanged
                                ▼
  Stage 2 — AWS (later; same graph, different adapters)
┌────────────────────────────────────────────────────────────┐
│  Bedrock AgentCore Runtime                                  │
│  — one isolated session per run_id                          │
│  — built-in session persistence (replaces FileSessionManager)│
│  — built-in Observability → CloudWatch (replaces log lines) │
└────────────────────────────────────────────────────────────┘
```

## 6. Capability Mapping

| Capability | Current (LangGraph/LangChain) | Local target (Strands) | AWS target (later) | Confidence |
|---|---|---|---|---|
| Multi-agent orchestration | `StateGraph` + `add_conditional_edges`; `moderator_open` and `moderator_checkpoint` are separate nodes; the audience-question pause is a hardcoded unconditional edge | `GraphBuilder` with a **single `moderator` hub node** (merges `moderator_open`+`moderator_checkpoint`) revisited via a cyclic graph (`set_max_node_executions`, `reset_on_revisit`); every round — including the audience-question exchange — is dispatched from and returns to that one hub, so all round-transition decisions live in one place | Unchanged — same graph deploys as-is | High — pattern exists; exact edge-condition API and the right `set_max_node_executions` value (≥5 visits: initial + after opening/rebuttal/audience/closing) need a spike |
| Shared run state (`round`, `memory_context`, run metadata) | `TypedDict` state threaded through every node | Strands' "invocation state" (a shared dict every node can read without it entering the model prompt) | Unchanged | Medium — prompt-relevant fields (e.g. `con_opening` for the Con rebuttal prompt) vs. non-prompt fields (`round`) need to be deliberately split; Strands auto-stitches upstream *outputs* into downstream *prompts* by node ID, which is a different mental model than reading arbitrary state keys |
| Human-in-the-loop pause | `langgraph.types.interrupt()` / `Command(resume=...)` | Strands interrupt mechanism — documented `HumanInTheLoop` handler is scoped to tool-call approval; need to confirm a "raw interrupt" can pause a **graph node** (not a tool call) and resume with arbitrary text | Unchanged, assuming the local spike succeeds | **Spike required** — highest-risk item, resolve locally before touching AWS |
| Cross-debate memory | Custom `MemoryStore` (Chroma + HF embeddings), manual retrieve → prompt-splice | A custom **Chroma-backed** `strands.memory.types.MemoryStore`, with `search`/`add` called **directly from node code** — `MemoryManager` is not used. Its tool/injection machinery assumes one `Agent` deciding for itself, mid-conversation, when to recall/store facts about "the user" (query derived from that agent's own latest message); this task always retrieves once before the openings and always writes once after the verdict, driven by `invocation_state["topic"]` — a deterministic pipeline step, not an agent decision. A `search_memory` tool would also contradict the "don't reference explicitly" requirement by handing the model visibility into the fact that it's recalling something. Embeddings: Chroma's bundled default function (ONNX MiniLM) rather than the old `langchain_huggingface` + `sentence-transformers` (torch) dependency, to keep the local footprint small | Swap the store's backend to a managed vector store (OpenSearch Serverless, S3 Vectors, or AgentCore Memory) — same direct `search`/`add` call sites, different backend | High — resolved by design discussion; remaining work is a normal implementation task (build the store, decide where in the graph `search`/`add` are called, reproduce the 1200-char cap and "don't reference explicitly" instruction) |
| Durable checkpoint/resume | `AsyncPostgresSaver` keyed by `thread_id` | **`FileSessionManager`** (local filesystem) — Strands' own docs recommend this exact manager for local development | `S3SessionManager` or AgentCore's native session persistence — Strands frames this as a same-interface swap ("swap the component without rewriting the entire app") | Medium — confirmed: `SessionRepository`'s `create_multi_agent`/`read_multi_agent` methods make multi-agent/graph state (not just chat history) a first-class persisted concept in every session manager, including `FileSessionManager`. **No Postgres session manager exists in Strands** — keeping Postgres locally would mean hand-writing a custom `SessionRepository` adapter that provides no benefit, since it can't carry forward to AgentCore either (see Open Question 4) |
| Streaming | LangGraph `astream()` → per-node dict → SSE | Strands async iterators (`agent.stream()` / graph-level events) yield lifecycle, model-token, tool, and **multi-agent** events — a direct analog to "one SSE event per node" | Unchanged | High |
| Winner determination | Regex/string heuristic on free-text verdict | Strands structured output (tool-forced JSON) | Unchanged | High confidence *and* a clear improvement — not a like-for-like port |
| Mock/replay mode | `MOCK_LLM` env var swaps node functions for cached-transcript replay | Same pattern, framework-agnostic — swap node executors at graph-build time | N/A (local-only concern) | High |
| Deployment | Docker Compose (app + Postgres + Redis + nginx) | Local `uvicorn` process, no containers required for the core rewrite | AgentCore Runtime (serverless, per-session microVM isolation, built-in identity/auth integration) | High — Strands documents this deployment path directly |
| Observability | Python `logging` calls | Unchanged — existing logging is sufficient locally | AgentCore Observability → CloudWatch (OTel) | High |

## 7. Functional Requirements

**FR-1 (Orchestration).** The system SHALL run a debate as a directed graph centered on a single `moderator` hub node (merging today's `moderator_open` and `moderator_checkpoint`), revisited after every round — opening, rebuttal, the audience-question exchange, and closing — via Strands' cyclic-graph support. Each visit SHALL dispatch exactly one round's Pro-then-Con sub-sequence, which returns to the hub before the next round is dispatched.

**FR-2 (Adversarial coupling).** Con's opening argument SHALL be generated with Pro's opening argument as context; both SHALL be generated by dedicated Pro/Con Strands `Agent` instances with role-specific system prompts.

**FR-3 (Round-bounded output).** Each debate turn SHALL respect its current word-count ceiling (opening ~200/250, rebuttal ~100/130, audience answer ~100/130, closing ~75/100, verdict ~150).

**FR-4 (Cross-debate memory).** On starting a new debate, the system SHALL retrieve up to 2 semantically similar past-debate summaries once, cap them at ~1200 characters combined, and make that same non-explicit background context available to **every** Pro/Con turn for the rest of the debate — opening, rebuttal, the audience-question answer, and closing, not opening only — matching the old system's behavior (`build_memory_block(state["memory_context"])` re-applied per turn). Since every turn's `Agent` is freshly constructed and stateless (see Capability Mapping), each turn's prompt builder is individually responsible for splicing `invocation_state["memory_context"]` in — nothing propagates automatically. The single retrieval call SHALL happen inside the `moderator` hub, on its one-time `"" → "opening"` round transition, wrapped so any store failure degrades to an empty context rather than blocking the debate (memory is best-effort, matching the old system's normal cold-start behavior of an empty store yielding an empty context). On completing a debate, the system SHALL persist a summary (topic, truncated openings, winner) for future retrieval; this write SHALL happen inside `moderator_decision_node`, immediately after `winner`/`justification` are computed — the single write site, replacing the old system's pattern of calling `upsert_debate` from every API/service call site that could complete a debate.

**FR-5 (Audience-question pause).** After the rebuttal round, the moderator hub SHALL dispatch the audience-question branch as one of its normal routed branches (not a hardcoded unconditional edge, as today), pausing exactly once and waiting for an externally-submitted question unless one was pre-supplied at debate start. Both Pro and Con SHALL answer it before the hub dispatches the closing round. The moderator's verdict prompt SHALL explicitly weigh the quality of each side's answer.

**FR-6 (Verdict).** The system SHALL produce a final structured verdict identifying a winner (Pro/Con) and a justification, without relying on free-text heuristic parsing.

**FR-7 (Sync API).** A synchronous "run to completion" endpoint SHALL exist, accepting an optional pre-supplied audience question, and SHALL return an explicit error (not a silently-incomplete result) if the debate reaches the pause without one.

**FR-8 (Streaming API).** A streaming endpoint SHALL emit one event per graph-node completion (topic, node name, resulting content) as Server-Sent Events, plus a distinct event when the run pauses for the audience question.

**FR-9 (Start/resume API).** Endpoints SHALL exist to (a) start a debate and return a run identifier immediately, (b) stream that run's events by id, (c) submit the audience question for a paused run by id, and (d) resume a run from its last durable checkpoint after a process restart.

**FR-10 (Durability).** A started debate's progress SHALL survive a process restart; resuming SHALL continue from the last completed node rather than restarting the debate.

**FR-11 (Mock mode).** A configuration flag SHALL allow every LLM call except the audience-question responses to be replaced by a cached, topic-matched transcript replay, with a configurable artificial delay, for cost-free demo/UI iteration.

**FR-12 (Demo UI).** A chat-style UI SHALL render a debate's transcript as it streams — moderator dividers, animated speaker turns, an audience-question form gated on pause state, and debate history — without any per-node/failover-specific chrome.

**FR-13 (Deployment).** The system SHALL be packaged and deployable to Bedrock AgentCore Runtime, with tool-call/agent-decision traces visible in CloudWatch.

## 8. Explicitly Out of Scope

- Postgres `run_ownership` table, race-safe claim/heartbeat/staleness logic (`deployment/app_ext/ownership.py`).
- Redis pub/sub cross-node event relay (`deployment/app_ext/event_bus.py`).
- nginx load balancer and the multi-node `docker-compose.yml` topology.
- Streamlit's per-node health polling, node-failure banner, and "resumed on node X" narration.
- Any new multi-tenancy, auth, or rate-limiting beyond what AgentCore Identity provides out of the box.

## 9. Open Questions / Spikes (resolve before or during design)

1. **Graph-node-level interrupt.** Does Strands' interrupt mechanism support pausing a *graph node's* execution for arbitrary external input (not just a tool-call approval via `HumanInTheLoop`), and resuming with a value that becomes part of graph state? This is the load-bearing mechanism for FR-5 and needs a working spike before the rest of the design is finalized.
2. **Conditional-edge API.** What is `GraphBuilder`'s exact API for attaching a runtime predicate to an edge (the equivalent of `add_conditional_edges`)? With the moderator now a single hub revisited 5 times per debate (initial entry, then after opening/rebuttal/audience/closing), confirm `set_max_node_executions` is set accordingly (≥5, with headroom) and decide whether `reset_on_revisit` should be `True` for the moderator node — its job is stateless round-routing driven by invocation state, not accumulated conversation, so clearing its own history each revisit likely avoids unbounded context growth without losing anything it needs.
3. **Moderator-decision consolidation (nice-to-have, not required).** The final verdict (`moderator_decision`) could itself be folded into the same hub node — on the visit where the round counter reads "closing done," the hub produces the verdict directly instead of dispatching yet another branch — making `moderator` the *only* moderator-owned node in the graph. This PRD keeps `moderator_decision` as a separate terminal node by default (smaller behavioral delta from today), but it's a natural follow-on simplification worth revisiting once the hub pattern is validated.
4. **Invocation-state vs. prompt-stitching.** Strands auto-stitches a node's *output* into its downstream *prompt*. Our prompts are hand-tuned to reference exactly one or two specific upstream fields (e.g., Con's rebuttal references Pro's opening, not Pro's rebuttal). Confirm this can be controlled precisely enough to avoid prompt bloat/drift as the graph grows, or whether some prompts need to be built manually from invocation state instead of relying on auto-stitching.
5. **Session manager choice.** Confirmed for local: `FileSessionManager`, persisting multi-agent graph state (not just chat history) to disk, resuming correctly after a process restart. Open for the AWS stage: does AgentCore's native session persistence checkpoint *mid-graph* state the same way, or does the port need `S3SessionManager` plus a thin custom layer? Note there is **no built-in Postgres session manager** — if keeping the existing local Postgres container is ever reconsidered, it would require hand-writing a `SessionRepository` adapter against Strands' abstract CRUD interface, and that adapter would still need to be thrown away when moving to AgentCore, since AgentCore's session persistence is a separate, native mechanism. Recommendation: don't do this — use `FileSessionManager` locally and let Postgres be retired from this stack.
6. **Memory store backend.** Confirmed for local: Chroma, unchanged from today, but with embeddings switched to Chroma's bundled default embedding function (ONNX MiniLM) instead of porting the old `langchain_huggingface` + `sentence-transformers` (torch) dependency — same embedding *quality class* (MiniLM), much smaller local footprint. Confirmed design: node code calls the store's `search`/`add` directly; `MemoryManager` is not used (see Capability Mapping row "Cross-debate memory" for why). Still open for the AWS stage: what backs the custom `MemoryStore` once deployed — a managed vector store (OpenSearch Serverless, S3 Vectors) or AgentCore's own Memory service. Decide during the deploy phase, not before — the local build should not be blocked on this.
7. **Structured verdict output.** Confirm Strands' structured-output/tool-forced-JSON mechanism (referenced in the parallel Marvell POC) for replacing the current winner-parsing heuristic with a typed `{winner, justification}` result.
8. **Eval/mock-mode fixtures.** The current mock mode replays transcripts produced by a `deepeval`/`promptfoo` eval harness (`tests/deepeval_promptfoo/.debate_cache/`). Decide whether that harness is ported as-is, replaced by a Strands-native eval approach, or kept framework-agnostic (it only reads/writes JSON transcripts, so it may not need to change at all).

## 10. Suggested Phased Delivery

Phases 0–7 require **no AWS account** — only an Anthropic API key (or whatever model provider Strands is configured against locally) and local disk. AWS enters only at Phase 8.

| Phase | Target | Work | Exit criteria |
|---|---|---|---|
| 0 — Spike | Local | Resolve open questions 1–3 above with throwaway code | Confirmed: graph-level interrupt/resume works; conditional+cyclic edges behave as expected |
| 1 — Core graph | Local | Pro/Con/Moderator agents + round state machine on `GraphBuilder`, no memory/HITL yet | A full debate runs opening→closing→verdict locally |
| 2 — Memory | Local | Chroma-backed debate-summary `MemoryStore`, called directly (`search`/`add`) from node code, wired into opening prompts | A second debate on a similar topic visibly builds on the first |
| 3 — HITL | Local | Audience-question pause/resume, verdict weighting | Pause triggers after rebuttal; submitted answer reaches both agents and the verdict |
| 4 — API | Local | FastAPI wrapper: sync invoke, SSE stream, start/resume/submit-question, health | Behavioral parity with current endpoints (single-session semantics) |
| 5 — Durability | Local | `FileSessionManager`-backed resume across a process restart | Killing and restarting mid-debate resumes correctly, no Postgres involved |
| 6 — Mock mode + evals | Local | Port `MOCK_LLM` replay and confirm eval fixture compatibility | UI/demo runs with zero API spend |
| 7 — Demo UI | Local | Streamlit port minus multi-node chrome | Same transcript UX as today, single-runtime, no AWS calls |
| 8 — Deploy | **AWS** | Package for AgentCore Runtime; swap `FileSessionManager` → AgentCore session persistence and the Chroma store → a managed vector backend; confirm CloudWatch traces | End-to-end debate runs on AgentCore with visible traces, using the *same* graph/agent code validated in Phases 0–7 |

## 11. Risks & Assumptions

- **Risk:** Item 1 (graph-node interrupt) is unresolved in public docs as scoped to tool-call approval; if raw graph-level interrupts don't exist or don't survive a durable checkpoint, the audience-question feature may need a different mechanism (e.g., splitting the graph into two separately-invoked sub-graphs around the pause point, with the pause modeled as the boundary between two separate invocations rather than an in-graph interrupt). This is a **local-phase risk** — resolve it in Phase 0, entirely without AWS.
- **Risk:** AgentCore's session-persistence guarantees for *mid-graph* state (vs. per-agent conversation history) are not yet confirmed from docs alone — treat as an assumption to validate in Phase 8, not a given. It does not block Phases 0–7, since `FileSessionManager` already confirms multi-agent state persistence works at the Strands layer independent of which backend AgentCore uses later.
- **Assumption:** Dropping multi-node failover means run identity/durability is scoped to "survives a restart of the same deployed service," not "survives loss of the specific compute instance" — acceptable per the confirmed scope cut, but worth stating explicitly since AgentCore's session isolation model differs from the current node/LB model in ways that change what "failover" even means here.
- **Assumption:** The synthetic/mock eval harness under `tests/deepeval_promptfoo/` is out of this PRD's authorship scope beyond confirming its JSON fixtures remain compatible (see Open Question 7).
- **Decision (made):** Postgres is dropped entirely from the target architecture, at both stages. It has no built-in Strands session manager, the documented upgrade path skips it (File → S3/AgentCore), and a custom Postgres adapter would be local-only throwaway code. If local Postgres is still running from the current system's `docker-compose.yml`, it can be decommissioned once the Strands rewrite's Phase 5 (Durability) is validated.

## Appendix A — Source Files Referenced

| Area | File |
|---|---|
| Graph | `src/core/graph.py` |
| State | `src/core/state.py` |
| Memory | `src/core/memory.py` |
| Prompts | `src/core/prompts.py` |
| Pro agent | `src/agents/pro.py` |
| Con agent | `src/agents/con.py` |
| Moderator agent | `src/agents/moderator.py` |
| Mock replay | `src/agents/mock.py` |
| API routes | `src/api/routes/debates.py` |
| API schemas | `src/api/schemas.py` |
| Service layer | `src/api/services/debate_service.py` |
| Exceptions | `src/api/services/exceptions.py` |
| App entrypoint / checkpointer | `app.py` |
| Ownership (out of scope) | `deployment/app_ext/ownership.py` |
| Event bus (out of scope) | `deployment/app_ext/event_bus.py` |
| Demo UI | `deployment/ui/streamlit_app.py` |
| Prior HITL change | `openspec/changes/audience-question-interrupt/proposal.md` |
| Adjacent org POC | `docs/marvell/agentic-poc-spec.md` |

## Appendix B — Strands Docs Consulted

- Multi-Agent Patterns: Graph Workflows (`GraphBuilder`, conditional branching, cyclic graphs, `set_max_node_executions`/`reset_on_revisit`)
- Human-in-the-loop intervention handler (`HumanInTheLoop`, interrupt/resume mode)
- `strands.session.file_session_manager.FileSessionManager` (multi-agent state persistence, local filesystem)
- `strands.session.session_repository.SessionRepository` (abstract CRUD interface — the extensibility point for a custom backend; confirms `create_multi_agent`/`read_multi_agent`/`update_multi_agent` as first-class methods every session manager implements)
- `strands.session.repository_session_manager.RepositorySessionManager` (generic manager over any `SessionRepository`)
- `strands.session.s3_session_manager.S3SessionManager` (cloud session storage — referenced, not yet fetched in full)
- Lesson 9: Persistent Memory With Session Managers (explicitly documents the File → S3 → AgentCore Memory upgrade path as a session-manager swap, with no Postgres option anywhere in it)
- `strands.memory.memory_manager.MemoryManager` (cross-session memory, search/add tools, injection)
- Streaming Responses (async iterators, callback handlers, event types)
- Deploying to Amazon Bedrock AgentCore Runtime
