## Why

The debate bot is migrating from LangGraph to Strands Agents (see `Debate-Bot-Strands-Migration-PRD.md`). The scaffolding spike (archived) proved Strands supports the mechanics this depends on — cyclic hub revisits, graph-node interrupt/resume, and cross-revisit state accumulation — but proved them on a throwaway toy graph. This change builds the real Pro/Con/Moderator debate graph on Strands so later work (cross-debate memory, the live audience-question pause, the FastAPI surface, durability) has an actual orchestration layer to attach to.

## What Changes

- New `moderator` hub node merges today's `moderator_open` and `moderator_checkpoint` into one node, revisited via cyclic conditional edges. A round counter in `invocation_state` picks the next branch each visit: opening → rebuttal → audience → closing → done.
- The audience-question round is wired into the hub now as an inert no-op node registered under its eventual real node id (`audience_question`) — the edges and round-counter slot exist, but it performs no pause/interrupt and leaves `audience_question`/`pro_audience_answer`/`con_audience_answer` empty. This lets the real HITL implementation (a later change) swap the node body in without touching graph shape.
- Pro and Con opening/rebuttal/closing turns become dedicated Strands `Agent` nodes with role-specific system prompts. Con's turns get Pro's output via Strands' upstream-output auto-stitching wherever a direct graph edge carries it; `invocation_state` is reserved for round control-flow and any value with no direct-edge path to where it's needed (e.g. the closing arguments feeding the final verdict). This split is validated empirically while implementing/testing this change rather than via a separate spike.
- New terminal `moderator_decision` node, reached only from the hub's final "done" round (not folded into the hub itself), produces a structured verdict (winner, justification) via Strands tool-forced structured output. This replaces the old free-text regex heuristic ("winner:" / "winner is" scanning, falling back to a bare "Pro"/"Con" token search). **BREAKING** relative to the old node's free-text output shape — acceptable since nothing outside this graph consumes that shape in this codebase yet.
- Out of scope for this change: cross-debate memory retrieval, the real audience-question pause/resume, the FastAPI surface, durability/session persistence, mock-mode replay, and the demo UI — each is its own later task per `TRD.md`.

## Capabilities

### New Capabilities
- `debate-graph-orchestration`: the Pro/Con/Moderator round state machine — opening → rebuttal → (inert audience stub) → closing → verdict — running end-to-end on Strands' `GraphBuilder`, driven by a single revisited moderator hub and producing a structured verdict.

### Modified Capabilities
(none — `strands-graph-spike` is a throwaway proof from the prior change and is not being modified)

## Impact

- New/changed code: the graph-building module (Strands `GraphBuilder` equivalent of today's `src/core/graph.py`), the moderator hub node, the `moderator_decision` node, and Pro/Con agent nodes for opening/rebuttal/closing (equivalents of today's `src/agents/pro.py`, `src/agents/con.py`, `src/agents/moderator.py`), plus a shared-state module analogous to today's `src/core/state.py` but shaped for Strands `invocation_state`.
- Tests: an end-to-end test invoking the graph to completion with mocked model calls, verifying round order, the inert audience stub leaving its fields empty, and a structured winner/justification in the final result.
- Depends on: the archived `scaffolding-spike` change's confirmed mechanics (cyclic edges, `invocation_state` threading, node-execution budget sizing).
- Enables: Task 3 (cross-debate memory), Task 4 (swaps the real interrupt-based implementation into the `audience_question` stub), Task 5 (FastAPI surface), Task 6 (durability), Task 7 (mock mode), Task 8 (demo UI) per `TRD.md`.
- No AWS/AgentCore impact — local-only, per this task's scope in `TRD.md`.
