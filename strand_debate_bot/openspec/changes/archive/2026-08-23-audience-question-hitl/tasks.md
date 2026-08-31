## 1. Confirm The Interrupt Result Shape

- [x] 1.1 Confirmed against the installed `strands` package (1.53.0): `GraphResult.interrupts` is `list[Interrupt]` and the id field is `.id`, not `.interrupt_id` as `findings.md` assumed — use `result.interrupts[0].id`. The resume call shape matches exactly what was assumed: `graph.invoke_async([{"interruptResponse": {"interruptId": ..., "response": ...}}], invocation_state=...)`. `BeforeNodeCallEvent` exposes `.node_id`, `.invocation_state`, and `.interrupt(name, reason=...)` (from `strands.hooks`) as assumed.

## 2. Prompts

- [x] 2.1 Add `pro_audience_prompt(state)` and `con_audience_prompt(state)` to `src/core/prompts.py`, following the existing `pro_rebuttal_prompt`/`con_rebuttal_prompt` style (reference `state["audience_question"]`, wrapped with `_with_memory`)
- [x] 2.2 Add matching system prompts (`PRO_AUDIENCE_SYSTEM`, `CON_AUDIENCE_SYSTEM`) alongside the existing per-role system prompts, with a word-count ceiling consistent with the rebuttal round's (~100 words / 130 max)

## 3. Agent Nodes

- [x] 3.1 Add `pro_addresses_question_node(model)` to `src/agents/pro.py`, an `AgentTurnNode` using `PRO_AUDIENCE_SYSTEM`/`pro_audience_prompt`, storing into `pro_audience_answer` (same construction pattern as `pro_rebuttal_node`)
- [x] 3.2 Add `con_addresses_question_node(model)` to `src/agents/con.py`, an `AgentTurnNode` using `CON_AUDIENCE_SYSTEM`/`con_audience_prompt`, storing into `con_audience_answer` (same construction pattern as `con_rebuttal_node`)

## 4. Interrupt Hook and Node

- [x] 4.1 In `src/agents/moderator.py`, repurpose `AudienceQuestionStub` into the audience round's pause-point node: keep it a no-op `MultiAgentBase` under node id `audience_question` (design.md, Decision 2) — all pause/resume logic lives in the hook (Task 4.2), not in this class
- [x] 4.2 Add a `HookProvider` class in `src/agents/moderator.py` that registers a `BeforeNodeCallEvent` handler: when `event.node_id == "audience_question"`, pass through without pausing if `event.invocation_state.get("audience_question")` is already truthy; otherwise call `event.interrupt(...)`, and on a resumed call write the returned response into `event.invocation_state["audience_question"]` before returning (design.md, Decisions 2-3)

## 5. Graph Wiring

- [x] 5.1 In `src/core/graph.py`, register the two new nodes (`pro_addresses_question`, `con_addresses_question`) and reroute the edge `audience_question -> moderator` to `audience_question -> pro_addresses_question -> con_addresses_question -> moderator`
- [x] 5.2 Register the new `HookProvider` (Task 4.2) on the `GraphBuilder` via `set_hook_providers`
- [x] 5.3 Update `MAX_NODE_EXECUTIONS`'s accompanying comment to reflect the new full-run node count (13 old + 2 new = 15 node executions per full run); confirm the existing value of 24 still comfortably covers it, adjusting only if it doesn't (design.md, Risks)

## 6. Tests

- [x] 6.1 Rewrite `test_audience_round_leaves_fields_unset` (`tests/test_graph.py`) — it currently asserts the old inert-placeholder behavior being replaced by this change — into a pause/resume test: run the graph with no pre-supplied question, assert `result.status == Status.INTERRUPTED` after the rebuttal round, resume with a submitted question and the same `invocation_state` object, and assert the run completes with `pro_audience_answer`/`con_audience_answer` populated
- [x] 6.2 Unit test: a pre-supplied `audience_question` in the initial state causes the audience round to complete without pausing, and both debaters still produce answers to it
- [x] 6.3 Unit test: `pro_addresses_question`'s and `con_addresses_question`'s prompts each reference the submitted `audience_question`
- [x] 6.4 Unit test: the moderator's verdict prompt construction includes the populated `pro_audience_answer`/`con_audience_answer` fields once the audience round has completed
- [x] 6.5 Update `EXPECTED_ORDER` in `tests/test_graph.py` to include the two new node ids in `test_full_debate_runs_end_to_end`
- [x] 6.6 Update the hardcoded `len(execution_order) == 13` assertion in `test_verdict_is_structured_and_terminal` to the new full-run count, and update `test_full_debate_runs_end_to_end`/`test_con_opening_and_rebuttal_see_pro_opening`/`test_verdict_is_structured_and_terminal` to each pre-supply an `audience_question` in their initial state so they still exercise a complete single-call run (design.md, Migration Plan)
- [x] 6.7 (Discovered during implementation, not in the original task list) `tests/test_cross_debate_memory.py` — added by the `cross-debate-memory` change, which was implemented and archived after this change's tasks.md was written — ran two full debates without a pre-supplied `audience_question` and started hitting the new pause. Updated both tests to pre-supply a question and extended their memory-context call-index checks from `range(6)` to `range(8)` to cover the two new audience-turn calls.
