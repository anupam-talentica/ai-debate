## Context

This is the first change in the project — no existing scaffolding, dependencies, or code exist yet. See proposal.md - Why for the risk this spike resolves before Task 2 (core debate graph) and Task 4 (audience-question HITL) are built. Strands API specifics (exact `GraphBuilder` interrupt/resume signature, `set_max_node_executions`/`reset_on_revisit` behavior) are themselves unconfirmed going in — that uncertainty is what this spike exists to resolve, not something to be designed around in advance.

## Goals / Non-Goals

**Goals:**
- Stand up the minimal local environment needed to write and run any Strands code (dependency, API key config, skeleton dirs).
- Answer, with working code, whether graph-node interrupt/resume, cyclic hub revisits, and cross-revisit state accumulation behave as PRD Section 5 assumes.
- Leave a written finding per mechanic (works / doesn't work / works with caveats) that Tasks 2 and 4 can start from.

**Non-Goals:**
- Building any part of the real debate graph, agents, or prompts.
- Production-quality error handling, tests, or packaging for the spike code itself — it is throwaway.
- Resolving Open Questions 5-8 (session manager, memory backend, structured verdict, eval fixtures) — out of scope for this task.

## Decisions

- **Arithmetic over text agents.** The spike's "Adder"/"Subtracter"/hub nodes operate on a plain integer rather than LLM-generated text, so exit criteria are exact-value assertions rather than judged text — this isolates the graph/interrupt mechanics from any LLM non-determinism. Alternative considered: mirror Pro/Con with trivial LLM prompts — rejected because it reintroduces text-matching flakiness for no added confidence in the mechanics being tested.
- **Skeleton dirs now, not full layout.** Scaffolding creates `src/core|agents|api` as empty/near-empty directories matching CLAUDE.md's target layout, so Task 2 onward has a consistent place to land code, without building out real modules whose shape depends on spike findings.
- **Spike code lives outside `src/`.** The throwaway graph (hub, Adder, Subtracter, human-choice node) is written under a clearly-throwaway location (e.g. `spikes/` or a notebook), not inside the `src/` skeleton, so it's obvious later it was never meant to be reused directly.
- **One finding per open question, not a pass/fail on the whole spike.** Open Questions 1, 2, and 4 are independent; a failure on one (e.g., no graph-node interrupt) shouldn't be recorded as "spike failed" if the other two mechanics are confirmed — Task 2 and Task 4 need to know which specific assumption to redesign around.

## Risks / Trade-offs

- [Risk] Graph-node interrupt/resume may not exist at all (only tool-call approval via `HumanInTheLoop`) → Mitigation: this is exactly what Open Question 1 flags as highest-risk; if confirmed absent, the finding should record the PRD's documented fallback (split into separately-invoked sub-graphs around the pause point) so Task 4 doesn't rediscover it.
- [Risk] Spike passes but the real debate graph's larger state (memory context, per-round prompts) hits a limit this toy integer state doesn't exercise → Mitigation: explicitly out of scope here (see Non-Goals); Task 2 should re-validate with real agent state, not assume the spike's confirmation fully covers it.
- [Trade-off] Keeping the spike arithmetic-only makes results unambiguous but means it cannot confirm anything about prompt-stitching quality (Open Question 4 is only tested at the state-accumulation level, not the prompt-content level) — acceptable since prompt-content precision is validated for real in Task 2.
