## Why

The debate graph currently treats the audience round as an inert placeholder (`AudienceQuestionStub`) that completes without pausing and leaves `audience_question`/`pro_audience_answer`/`con_audience_answer` unset — a deliberate stand-in left by the core-debate-graph change for this work to replace. The old (LangGraph) debate bot supported a real human-in-the-loop audience question after the rebuttal round, factored into the final verdict, and PRD Phase 3 calls for porting that same behavior onto Strands' own interrupt/resume primitives now that the scaffolding spike has confirmed how those primitives actually work.

## What Changes

- Replace the audience round's single inert stub node with a three-node chain — `audience_question` (pause point) → `pro_addresses_question` → `con_addresses_question` — mirroring the existing two-node Pro→Con pattern used by every other round.
- Add a `HookProvider`, registered on the `GraphBuilder`, that intercepts the `audience_question` node's call and pauses the graph (`event.interrupt(...)`) to wait for an externally-submitted question, unless a question was already pre-supplied in `invocation_state` before the run started — in which case it passes through with no pause.
- Add two new agent-turn nodes (`pro_addresses_question`, `con_addresses_question`) that generate each debater's response to the submitted question, once it's available, before the closing round runs.
- No prompt changes needed for verdict weighting: `MODERATOR_DECISION_SYSTEM` and `moderator_decision_prompt` already instruct the moderator to weigh the audience Q&A and already splice those three state fields into every verdict call — they've simply been empty until now.
- **BREAKING** (spec-level, not API-level — no API exists yet): a full debate run no longer completes in a single `invoke_async` call by default. A run that reaches the audience round without a pre-supplied question now returns `Status.INTERRUPTED` and requires a second `invoke_async` call (with the same `invocation_state` object and the interrupt id) to resume and complete. Existing/future callers must handle this.

## Capabilities

### New Capabilities
- `audience-question-hitl`: Pausing a debate after the rebuttal round to accept an externally-submitted audience question (or skip the pause if one was pre-supplied), having both debaters answer it, and resuming execution through to the verdict.

### Modified Capabilities
- `debate-graph-orchestration`: The "Audience round is an inert placeholder" requirement is replaced — the audience round no longer completes immediately and no longer leaves the three audience fields unset; it now pauses (or skips the pause when pre-supplied) and populates them.

## Impact

- **Graph**: `src/core/graph.py` — audience round expands from one node to three (`audience_question`, `pro_addresses_question`, `con_addresses_question`); the `GraphBuilder` gains a registered `HookProvider`; `MAX_NODE_EXECUTIONS`'s sizing comment needs updating for the new full-run node count (no behavior change expected, margin already covers it).
- **Agents**: `src/agents/moderator.py` — `AudienceQuestionStub` is replaced/repurposed alongside a new `HookProvider` class; both new turn nodes reuse the existing `AgentTurnNode` (`src/core/nodes.py`) with no changes to that class.
- **Prompts**: `src/core/prompts.py` — two new prompt builders (`pro_audience_prompt`, `con_audience_prompt`); no changes to `MODERATOR_DECISION_SYSTEM` or `moderator_decision_prompt`, which already account for the audience Q&A fields.
- **State**: `src/core/state.py` — no field changes; `audience_question`/`pro_audience_answer`/`con_audience_answer` already exist in `build_invocation_state`.
- **Tests**: `tests/test_graph.py` — `EXPECTED_ORDER` and the hardcoded execution-count assertion need updating for the two new nodes; `test_audience_round_leaves_fields_unset` asserts the old inert-placeholder behavior being replaced here and needs to be rewritten as a pause/resume test.
- **Out of scope**: no FastAPI/route/service changes, no run identifier, session-manager, or cross-process durability — this change is graph-level only (PRD Phase 3); pausing and resuming both happen within a single test process against the same `invocation_state` object, per the scaffolding spike's finding that Strands does not restore accumulated `invocation_state` across a resume call on its own. API-level exposure of this pause (Phase 4) and durable resume across a process restart (Phase 5) are separate, later work.
