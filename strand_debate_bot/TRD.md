# TRD — Debate Bot on Strands (Task Breakdown)

Source: `Debate-Bot-Strands-Migration-PRD.md`. Each task below becomes its own openspec change; no elaboration here by design.

1. Scaffolding + spike (project setup; interrupt/resume + cyclic graph edges)
   - Test: "Running Total" toy graph — Adder (+5), a human-in-the-loop choice (add/subtract 2), Subtracter (−3), and a hub revisited each round via cyclic edges. Start at 10; with human choosing "add 2" final total must be exactly 14 (and "subtract 2" must give exactly 10), with the trace showing all 3 ops in order — proves graph-node interrupt/resume, cyclic/conditional edges, and cross-revisit state accumulation all work
2. Core debate graph (Pro/Con/Moderator + round state machine)
   - Test: a full debate runs opening→rebuttal→closing→verdict locally end-to-end
3. Cross-debate memory (Chroma-backed `MemoryStore`, called directly — no `MemoryManager`)
   - `MemoryManager`'s tool/injection machinery assumes one `Agent` deciding for itself when to
     recall/store facts about "the user"; this task always retrieves before opening and always
     writes after the verdict, so node code calls a custom `MemoryStore`'s `search`/`add` directly.
   - Chroma's bundled default embedding function (ONNX MiniLM), not the old
     `langchain_huggingface`/`sentence-transformers` dependency — keeps the local footprint small.
   - Retrieved context is threaded through every Pro/Con turn (opening, rebuttal, audience answer,
     closing) via `invocation_state["memory_context"]`, not just the opening — matches the old
     system's per-turn `build_memory_block` re-application. Each turn's Agent is freshly built and
     stateless, so every prompt builder must explicitly splice the block in; nothing carries over
     on its own.
   - The one retrieval call per run happens inside the `moderator` hub's one-time `"" → "opening"`
     transition, wrapped in try/except degrading to an empty context on any store failure — memory
     is best-effort and must never block a debate from running (mirrors the old system's normal
     "empty store, empty context" cold-start behavior).
   - The one write call per run happens inside `moderator_decision_node`, right after `winner`/
     `justification` are computed — the single write site, replacing the old system's pattern of
     calling `upsert_debate` from every API/service call site that could complete a debate.
   - Test: a second debate on a similar topic visibly references/builds on the first
4. Audience-question HITL (pause/resume + verdict weighting)
   - Test: run pauses after rebuttal; submitted answer reaches both agents and shows up in the verdict
5. FastAPI surface (sync/stream/start-resume/submit-question)
   - Test: each endpoint hit directly (curl/httpx) matches current API's behavior for the same scenario
6. Durability (FileSessionManager restart resume)
   - Test: kill process mid-debate, restart, resume continues from last completed node
   - **Decision: `invocation_state` needs its own persistence, separate from Strands' own checkpoint.**
     Confirmed against installed `strands` 1.53.0: `Graph.serialize_state()` persists topology
     (`completed_nodes`, `node_results`, `next_nodes_to_execute`, `current_task`, interrupt state) but
     never `invocation_state` itself, and every node in this codebase (`AgentTurnNode`, `ModeratorHub`,
     `ModeratorDecision`) writes its output only into `invocation_state`, returning a bare
     `MultiAgentResult(status=COMPLETED)` with no payload — so `node_results` never carries the debate
     text either. A dedicated `HookProvider` writes `invocation_state` to an `invocation_state.json`
     file inside the same `FileSessionManager` session directory, on the same `AfterNodeCallEvent` /
     `AfterMultiAgentInvocationEvent` hooks Strands' own session manager already listens to. Node
     return contracts (`nodes.py`'s "invocation_state in, invocation_state out") are unchanged.
   - **Decision: `run_id == session_id`, and `build_graph()` runs before the HTTP response, not inside
     the background task.** `Graph.__init__` fires `MultiAgentInitializedEvent` synchronously, which
     (via a wired `FileSessionManager(session_id=run_id, storage_dir=SESSION_STORAGE_DIRECTORY)`)
     writes an initial `multi_agent.json` to disk before any node executes. `POST /debate/start` must
     call `build_graph()` (with the session manager wired) synchronously in the request handler, before
     returning `run_id` to the client — otherwise a client can hold a `run_id` for which no on-disk
     proof of life exists yet if the process dies between "task scheduled" and "task's first line runs."
   - **Decision: add `GET /debate/resume/{run_id}`** (name matches the old system's endpoint, kept for
     the parity goal TRD Task 5 already commits to). It rebuilds the graph against the existing session
     directory, restores `invocation_state` from the side-channel file above, registers a fresh
     in-memory `RunEntry` (the `RunRegistry` from Task 5 is never durable and is empty again after every
     restart — this is expected, not a gap to close), and re-drives execution via the same
     background-task driver `POST /debate/start` uses. No new interrupt-handling path is needed: if the
     restored graph is still mid-interrupt, it re-pauses naturally (Strands' own `_interrupt_state`
     already round-trips through `serialize_state`/`deserialize_state`), and the existing
     `POST /debate/{run_id}/audience-question` endpoint resumes it exactly as it does today.
   - **Decision: `SESSION_STORAGE_DIRECTORY` config var** in `src/core/config.py`, project-local default
     (parallel to the existing `MEMORY_PERSIST_DIRECTORY` pattern), passed as `FileSessionManager`'s
     `storage_dir`.
   - **Decision: two-tiered test strategy.** In-process tests call `build_graph()` twice against the same
     `storage_dir`/`session_id` (no real process kill — matches how `scaffolding-spike` and
     `audience-question-hitl` validated single-process assumptions) for coverage of multiple kill points;
     exactly one real subprocess `SIGKILL`-and-restart test serves as this task's literal exit criterion.
   - **Discovery during implementation:** a resumed run must never be classified "nothing left to do" by
     checking whether Strands' own `next_nodes_to_execute` reads empty — for this graph specifically, that
     reads empty at *every* round boundary (the next step is always revisiting the already-completed
     `moderator` hub, which `Graph`'s resume-readiness computation can't mark ready again), not only once a
     run has genuinely completed. The correct signal is the persisted `status` field itself
     (`"completed"`/`"failed"` are the only real terminal states; anything else is safe to resume). Getting
     this wrong silently classified a run killed right after any round as done and never resumed it — see
     `openspec/changes/debate-durability/design.md`'s Decision 3 addendum and `tasks.md` Section 6 for the
     full mechanism and the fix.
7. Mock mode + eval fixture compatibility
   - Test: full demo run with MOCK_LLM on, zero live API calls made
8. Demo UI (Streamlit port, no failover chrome)
   - Test: manual run-through of a full debate in the UI matches today's transcript UX

Out of scope for now (later stage per PRD Section 10): AWS/AgentCore deployment (Phase 8).
