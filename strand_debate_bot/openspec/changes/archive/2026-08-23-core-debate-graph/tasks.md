## 1. Graph scaffolding

- [x] 1.1 Define the `invocation_state` shape for this change: round counter, and any value with no direct-edge path to its consumer (Pro's/Con's closing arguments feeding `moderator_decision`); leave `audience_question`/`pro_audience_answer`/`con_audience_answer` as always-unset placeholders for now.
- [x] 1.2 Implement the `moderator` hub node: reads the round counter from `invocation_state`, advances it (opening → rebuttal → audience → closing → done) on each visit.
- [x] 1.3 Wire conditional edges from the hub to each round's first node, keyed on the round-counter value, and unconditional edges from each round's last node back to the hub.
- [x] 1.4 Set `set_max_node_executions` to 24 and confirm the builder compiles with the full node set.

## 2. Round agent nodes

- [x] 2.1 Implement `pro_opening` as a Strands `Agent` node with a role-specific system prompt targeting ~200-250 words.
- [x] 2.2 Implement `con_opening` as a Strands `Agent` node; wire it to receive Pro's opening argument. Resolved via `invocation_state`, not auto-stitch: inspecting `Graph._build_node_input` showed auto-stitch only reaches a node's *direct* predecessor, and using it for this one turn while every other turn needs `invocation_state` anyway would split the data-flow model for no benefit — see design.md, Decision 4 (updated).
- [x] 2.3 Implement `pro_rebuttal` and `con_rebuttal` nodes (~100-130 words), with Con's rebuttal referencing Pro's opening argument as context (via `invocation_state`, same reasoning as 2.2).
- [x] 2.4 Implement `audience_question` as an inert stub node registered under its final id: performs no pause/interrupt, leaves its three state fields unset, and returns immediately to the hub.
- [x] 2.5 Implement `pro_closing` and `con_closing` nodes (~75-100 words).

## 3. Verdict node

- [x] 3.1 Define the structured verdict schema: `winner` constrained to exactly `"Pro"` or `"Con"`, plus a free-text `justification`.
- [x] 3.2 Implement `moderator_decision` as a node separate from the hub, reading Pro's and Con's closing arguments (and the always-empty audience fields) from `invocation_state`, and producing the structured verdict via Strands tool-forced structured output.
- [x] 3.3 Wire the hub's "done" round to route to `moderator_decision`, and `moderator_decision` to the graph's terminal state (no edge back to the hub).

## 4. Tests

- [x] 4.1 Write an end-to-end test that invokes the graph to completion with a mocked model, asserting the rounds complete in order: opening → rebuttal → audience → closing → verdict.
- [x] 4.2 Assert Con's opening and rebuttal prompts actually contain Pro's corresponding argument text, confirming the `invocation_state`-based wiring from 2.2/2.3 actually reaches the model call.
- [x] 4.3 Assert the audience round leaves `audience_question`, `pro_audience_answer`, and `con_audience_answer` unset after a full run.
- [x] 4.4 Assert the final verdict's `winner` is one of `"Pro"`/`"Con"` and `justification` is non-empty.
- [x] 4.5 Assert no node executes after the verdict is produced (graph reaches a terminal status with no further node calls).

## 5. Verification

- [x] 5.1 Run the full test suite locally and confirm a full debate runs opening → rebuttal → closing → verdict end-to-end, matching TRD Task 2's stated test.
- [x] 5.2 Confirm the `set_max_node_executions` margin (24) is not exhausted by a full run; adjust and re-document in design.md if the actual node count changes. (A full run executes exactly 13 nodes, well under the 24 cap — no change needed.)
