# Spike Findings — Running Total (scaffolding-spike)

Input for Task 2 (core debate graph) and Task 4 (audience-question HITL). Verified against `strandsagents.com` docs and by running `spikes/running_total_spike.py`.

## Open Question 1 — graph-node interrupt/resume

**Confirmed, via a graph-level hook, not a raw call inside a plain custom node.**

A `HookProvider` registered on the `GraphBuilder` (`set_hook_providers`) can intercept `BeforeNodeCallEvent`, check `event.node_id`, and call `event.interrupt(name, reason=...)`. This raises `InterruptException` the first time (graph stops with `status == Status.INTERRUPTED`, `result.interrupts` populated); resuming with `graph.invoke_async([{"interruptResponse": {"interruptId": ..., "response": ...}}])` causes `event.interrupt(...)` to return the human's response directly, and the hook can mutate `event.invocation_state` in place before the node runs.

Caveat for Task 4: a plain `MultiAgentBase` custom node has **no direct interrupt call available inside its own `invoke_async`** — only `Agent` nodes with tools (`tool_context.interrupt`) or the `BeforeNodeCallEvent` hook can raise one. For the real `audience_question` node, use the hook pattern (or make it an `Agent` with a tool), not a raw interrupt call inside a custom node body.

No fallback (split sub-graphs) is needed — the PRD's highest-risk item resolves cleanly.

## Open Question 2 — cyclic/conditional hub edges

**Confirmed.** `GraphBuilder.set_max_node_executions(n)` is a **graph-wide total**, not per-node — set it to comfortably cover every node's total executions across all rounds (our spike used 20 for a 7-execution run). `reset_on_revisit(bool)` is also builder-wide; it resets a revisited node's own conversation/state, not `invocation_state` — irrelevant to our hub since it's not an `Agent`.

Conditional edges support two signatures: legacy `Callable[[GraphState], bool]` and new-style `EdgeConditionWithContext` (`def cond(state, *, invocation_state, **kwargs)`). Incoming edges use OR semantics by default (any completed predecessor triggers the target) — this is exactly what makes the hub revisit-on-return-from-any-branch pattern work with three unconditional edges back to the hub (`adder→hub`, `human_choice→hub`, `subtracter→hub`).

## Open Question 4 — cross-revisit state accumulation

**Confirmed, with one caveat that matters for Task 4/6.** The same `invocation_state` dict object is threaded by reference into every node call within one `graph.invoke_async(...)` call (`self._current_invocation_state = invocation_state`), so in-place mutations by one node are visible to later nodes and to edge conditions — no cross-node copying.

**Caveat:** on a resume call, the framework does **not** automatically restore previously-accumulated `invocation_state` content — it simply uses whatever `invocation_state` object the caller passes on that call. The spike only worked because the driver code kept and re-passed the *same* Python dict object across the initial call and the resume call. For Task 4 (and especially Task 6, Durability, where resume happens in a new process with no shared Python object), the real implementation must explicitly persist and restore `invocation_state` itself — Strands' interrupt/resume does not do this for user-defined state on its own within a single process, and definitely not across a process restart.

## Summary for downstream tasks

- Task 2 (core graph): the single-hub-revisited-via-cyclic-edges design in PRD Section 5 is directly supported as designed.
- Task 4 (HITL): use a `BeforeNodeCallEvent` hook targeting the `audience_question` node id, not an in-node interrupt call.
- Task 6 (Durability): `invocation_state` is not restored automatically by the SDK's own interrupt/resume mechanism — persisting/restoring it (round, memory context, etc.) across a process restart is the application's job, reinforcing why `FileSessionManager` (PRD's chosen mechanism) needs to be wired deliberately rather than assumed free.
