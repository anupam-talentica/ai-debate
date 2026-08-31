## Context

See `proposal.md` - Why for motivation. This design builds directly on the archived `scaffolding-spike` change's confirmed mechanics: `GraphBuilder` cyclic edges via conditional routing keyed on `invocation_state`, and `invocation_state` threaded by reference across node revisits within one run. That spike used only `NoOpNode`s with no real prompts; this change is the first place those mechanics are exercised with real `Agent` nodes and real prompt content.

## Goals / Non-Goals

**Goals:**
- A `GraphBuilder` graph implementing the full round state machine (opening → rebuttal → audience → closing → verdict) behind a single revisited `moderator` hub node.
- Con's opening and rebuttal turns receive Pro's corresponding argument as context.
- A structured, non-heuristic verdict.
- The audience round exists in the graph's shape now (node + edges), so a later change only has to swap its node body.

**Non-Goals:**
- The audience round pausing for real external input (Task 4).
- Cross-debate memory retrieval/injection (Task 3).
- FastAPI surface, durable session persistence, mock-mode replay, demo UI (Tasks 5-8).

## Decisions

**Single revisited `moderator` hub, not separate open/checkpoint nodes.** Mirrors the spike's `Hub` pattern directly: one node reads a round counter from `invocation_state` and a set of conditional edges route to that round's branch. Alternative considered: keep `moderator_open` and `moderator_checkpoint` as two nodes, closer to the old LangGraph shape — rejected, since that's exactly the "round-transition decisions split across two places" smell the PRD calls out, and the spike already validated the single-hub-revisit pattern.

**Audience round is an inert stub node registered under its final id, `audience_question`.** It does no pause/interrupt and leaves its three state fields unset. Task 4 replaces only this node's body with the real interrupt-based implementation; no edge changes. Alternative considered: omit the audience round from this change's graph entirely and have Task 4 add the node and edges — rejected, since it means touching hub routing logic twice for the cost of building the same shape once now while it's inert.

**`moderator_decision` is a separate terminal node, reached only from the hub's "done" round — the hub does not generate the verdict itself.** Keeps every hub visit doing the same kind of work (read round, pick branch) rather than special-casing the last visit to also run an LLM call and parse structured output, and keeps the verdict node independently testable in isolation (feed it a state dict, assert on the structured result) the way `moderator.py` is tested today. Alternative considered: fold verdict generation into the hub's final visit, as literally sketched in PRD Section 5's diagram — rejected for the isolation/testability reason above; the diagram's actual intent (one entry point, no stray hardcoded edges) holds either way, since `hub → moderator_decision` is still just one more conditional branch off the hub.

**State split: `invocation_state` carries all cross-turn prompt content; graph edges are structural only.** Resolved empirically (per this decision's original plan to "build it and see," rather than a separate spike): reading Strands' `Graph._build_node_input` shows auto-stitch only offers a node its *direct* graph predecessors' output. Once the hub sits between every round, almost no turn's actual content-dependency is its direct predecessor — `pro_rebuttal`'s predecessor is the hub (not `con_opening`, which it needs), `con_rebuttal`'s predecessor is `pro_rebuttal` (not `pro_opening`, which it needs), and `moderator_decision`'s predecessor is the hub (not the closing arguments). Only `con_opening`'s predecessor (`pro_opening`) happens to match its real dependency, and even there, relying on auto-stitch for exactly one of seven turns while every other turn reads `invocation_state` would be a needless split. So every turn node builds its own prompt by reading `invocation_state` directly and calls its `Agent` itself (`AgentTurnNode` in `src/core/nodes.py`); the direct edges (`pro_opening → con_opening`, etc.) are kept for execution ordering only, not for content. This is confirmed by the end-to-end test asserting the actual prompt content each mocked model call received.

**`set_max_node_executions` set with margin, not tuned to the exact count.** One full run executes the hub 5 times (opening/rebuttal/audience/closing/done dispatches) plus 7 branch nodes (Pro/Con × opening/rebuttal/closing, plus the audience stub) plus the `moderator_decision` node = 13. Following the spike's own margin (20 for a 7-execution run, roughly 3x), this change sets the limit to 24 rather than 13, so it isn't the first thing that needs re-tuning when a later task changes the round count.

**Structured verdict forces a winner; no "unclear" escape hatch.** The verdict schema requires `winner` to be exactly `"Pro"` or `"Con"`, plus a free-text `justification`. This removes the old regex heuristic's silent-empty-winner failure mode by construction. Alternative considered: a nullable or "tie" winner — rejected, since the old system always tried to declare one and nothing in the spec calls for an ambiguous result.

## Risks / Trade-offs

- [Risk] Bypassing auto-stitch entirely means a node that forgets to read a value from `invocation_state` fails silently (empty string in the prompt) rather than erroring → [Mitigation] The end-to-end test asserts on the actual rendered prompt content each mocked model call received, so a missing wire-up is caught directly instead of surfacing later as a subtly wrong argument.
- [Risk] The inert `audience_question` stub could be mistaken for "done" and left in place instead of being replaced → [Mitigation] It's named exactly `audience_question` (its eventual real id) and documented here as a body-only swap for Task 4; it produces no output that could be mistaken for a real answered question.
- [Risk] `set_max_node_executions` is a manually-reasoned constant that a later change (e.g. Task 4's real interrupt/resume, which may re-enter the audience node more than once) could silently exceed → [Mitigation] Set with margin now, and this document flags it for re-derivation whenever the round count or re-entry behavior changes.

## Migration Plan

Greenfield code in a new repo; no existing consumers of the old free-text verdict shape exist here. No rollback plan beyond removing the new module and its tests.
