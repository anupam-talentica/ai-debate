## Context

See proposal.md - Why/What Changes for motivation. Relevant existing constraints this design builds on:

- The debate graph (`src/core/graph.py`) is a Strands `GraphBuilder` graph centered on a single `moderator` hub node, revisited once per round via cyclic edges conditioned on `invocation_state["round"]` (design established in the archived `core-debate-graph` change).
- Every round except audience is a two-node Pro→Con chain built from the reusable `AgentTurnNode` (`src/core/nodes.py`): build a prompt from `invocation_state`, call an `Agent`, store the result text under a fixed key. The audience round is currently a single inert stub node (`AudienceQuestionStub` in `src/agents/moderator.py`) occupying that graph slot.
- The archived `scaffolding-spike` change resolved the load-bearing unknown for this work (`findings.md`, Open Question 1): Strands graph-node interrupts are **not** callable from inside a plain `MultiAgentBase` node's own `invoke_async`. They only exist via a `HookProvider` registered on the `GraphBuilder`, intercepting `BeforeNodeCallEvent` for a specific `node_id` and calling `event.interrupt(name, reason=...)`. The first call raises, leaving the graph result with `status == Status.INTERRUPTED` and a populated `result.interrupts` list; resuming means calling `graph.invoke_async([{"interruptResponse": {"interruptId": ..., "response": ...}}], invocation_state=...)`, at which point `event.interrupt(...)` returns the response and the hook can write it into `event.invocation_state` before the node body runs.
- The same finding also established that Strands does **not** restore accumulated `invocation_state` across a resume call on its own — the caller must keep and re-pass the exact same object. Persisting/restoring that state across a process boundary is out of scope here (proposal.md - Impact, "Out of scope") and belongs to the later Durability phase.
- `MODERATOR_DECISION_SYSTEM` and `moderator_decision_prompt` (`src/core/prompts.py`) already reference `audience_question`/`pro_audience_answer`/`con_audience_answer` unconditionally in every verdict call; they were written ahead of this change and require no further edits.

## Goals / Non-Goals

**Goals:**
- Make the audience round behave like every other round structurally: a chain of `AgentTurnNode`s, so the codebase has one pattern for "a round where debaters produce text," not two.
- Put the interrupt mechanism (the `HookProvider`) in exactly one place, tied to exactly one node id (`audience_question`), so it's unambiguous which node's execution the pause guards.
- Support both the "no question yet, pause" and "question already known, skip the pause" paths from the same hook, so a future caller that pre-supplies a question (e.g. a synchronous API path in a later phase) doesn't need a second code path.

**Non-Goals:**
- Any API, run-identifier, or service-layer surface for triggering/resuming a paused run — this change proves the graph-level mechanism only; a later phase exposes it over HTTP.
- Persisting or restoring `invocation_state` across a process restart — the scaffolding spike already flagged this as the application's responsibility for a later (Durability) phase, not something this change needs to solve.
- Any timeout, expiry, or auto-generated fallback question if none is ever submitted — the graph simply stays interrupted indefinitely, matching the old system's equivalent behavior.
- Supporting more than one audience question per debate.

## Decisions

### 1. Expand the audience round to a three-node chain, not a single multi-agent node
`audience_question` (pause point) → `pro_addresses_question` → `con_addresses_question`, replacing the single-node `AudienceQuestionStub` slot. The two new nodes are `AgentTurnNode` instances built the same way `pro_rebuttal_node`/`con_rebuttal_node` are, with new prompt builders (`pro_audience_prompt`, `con_audience_prompt`) in `src/core/prompts.py` that reference `invocation_state["audience_question"]`.

Alternative considered: a single node that internally calls both Pro's and Con's `Agent` in sequence and stores both fields itself. Rejected because every other node in this codebase follows "one node, one agent call, one stored field" (`nodes.py`'s own docstring states this as the uniform contract); a node that breaks this pattern would be harder to reason about and would make the hook's target (`audience_question`) do double duty as both "the pause point" and "an agent-calling node."

### 2. The `audience_question` node itself stays a no-op; the `HookProvider` does the pausing and state-writing
The node registered under id `audience_question` performs no work — by the time its `invoke_async` runs, the hook has either found a pre-supplied question (and let the call straight through) or already resumed with one (writing it into `invocation_state["audience_question"]` before the node body executes). This mirrors `AudienceQuestionStub`'s existing shape (already a no-op `MultiAgentBase`) and keeps the interrupt logic entirely inside the hook, rather than splitting "does it pause" and "does it store the answer" across two places.

### 3. The hook checks `invocation_state` for a pre-supplied question before interrupting
On `BeforeNodeCallEvent` where `event.node_id == "audience_question"`: if `event.invocation_state.get("audience_question")` is already truthy, return without calling `event.interrupt(...)` — the node runs immediately with the question already in place. Otherwise, call `event.interrupt(name, reason=...)`; on the initial call this raises (graph reports `INTERRUPTED`), and on a subsequent resume call it returns the submitted response, which the hook writes into `event.invocation_state["audience_question"]` before returning.

Alternative considered: giving the `audience_question` node itself a conditional edge or a check inside `ModeratorHub` to skip routing to the audience round entirely when a question is pre-supplied. Rejected — that would still run the round (needed either way, since Pro/Con must still answer the pre-supplied question), and it would split the "is a question already known" check across two places (a hub-level routing decision and a hook-level pause decision) instead of one.

### 4. Hook class lives in `src/agents/moderator.py`
Alongside `ModeratorHub`, `AudienceQuestionStub` (repurposed into the no-op node described in Decision 2 — kept as a distinct class rather than reused as `ModeratorHub`, since it's a different node id with different semantics), and `ModeratorDecision`. This keeps every class that concerns "how the audience/moderator machinery works" in one file, matching the file's existing scope, rather than introducing a new module for a single hook class.

### 5. Test shape: single-process, same-object resume
The exit test (per TRD Task 4 / proposal.md's "Out of scope" note) calls `graph.invoke_async(...)`, asserts `result.status == Status.INTERRUPTED`, reads the interrupt id off `result.interrupts`, then calls `graph.invoke_async([{"interruptResponse": {"interruptId": ..., "response": <question>}}], invocation_state=<the same state dict from the first call>)` and asserts the run completes with both audience-answer fields populated and reflected in the final verdict prompt. No persistence layer is introduced to support this — the test process holds the one `invocation_state` object across both calls, exactly as the scaffolding spike's own driver did.

## Risks / Trade-offs

- **[Risk, resolved during implementation]** `findings.md` assumed the interrupt id was read as `result.interrupts[0].interrupt_id`. Confirmed against the installed `strands` package (1.53.0, `strands/interrupt.py`): `GraphResult.interrupts` is a `list[Interrupt]` and the field is `.id`, not `.interrupt_id` — i.e. `result.interrupts[0].id`. Everything else assumed (the resume call shape `graph.invoke_async([{"interruptResponse": {"interruptId": ..., "response": ...}}], invocation_state=...)`, `event.node_id`, `event.invocation_state`, `event.interrupt(name, reason=...)`) matched exactly.
- **[Risk]** `MAX_NODE_EXECUTIONS` (currently 24, sized as "~2x margin over old 13-execution full run") has a comment that will read as stale once the full-run node count grows to 15. The numeric value likely still holds (24 comfortably covers 15), but an uncorrected comment could mislead whoever tunes it next. → **Mitigation**: update the comment alongside the node-count change; only bump the numeric value if the margin genuinely stops holding once the real node count is confirmed.
- **[Trade-off]** Keeping the `audience_question` node itself as an inert no-op (Decision 2) means all of the interesting logic lives in a `HookProvider` that isn't visible by reading the graph's node/edge definitions alone — someone auditing `graph.py` in isolation could miss that this node ever pauses. → **Accepted**: this is the only mechanism Strands exposes for a graph-node-level interrupt (per the scaffolding spike), so the alternative isn't "put the logic somewhere more visible," it's "there is nowhere else for it to go."

## Migration Plan

No data migration — this is graph/agent code with no persisted state format. Existing tests that run a full debate to completion (`test_full_debate_runs_end_to_end`, `test_con_opening_and_rebuttal_see_pro_opening`, `test_verdict_is_structured_and_terminal` in `tests/test_graph.py`) currently don't supply a pre-supplied audience question, so they will start hitting the new pause; each needs either a pre-supplied `audience_question` in its initial state (to exercise the skip-the-pause path, matching how the old system's equivalent full-run tests handled this) or an explicit interrupt-then-resume sequence, decided per test in tasks.md. Rollback is a straightforward revert of the graph/agent/prompt changes; nothing outside this change's own files depends on the new node ids or hook.
