## 1. Scaffolding

- [x] 1.1 Add Strands SDK dependency to the project's dependency file
- [x] 1.2 Add `.env.example` with the Anthropic API key variable and wire `.env` loading
- [x] 1.3 Create empty skeleton directories: `src/core`, `src/agents`, `src/api`
- [x] 1.4 Create a `spikes/` directory for throwaway spike code, kept separate from `src/`

## 2. Spike graph — nodes

- [x] 2.1 Implement the `hub` node with a round counter driving which branch runs next
- [x] 2.2 Implement the `Adder` node (always +5 to the running total)
- [x] 2.3 Implement the `Subtracter` node (always -3 to the running total)
- [x] 2.4 Implement the `human_choice` node that interrupts and resumes with an externally-supplied operation ("add 2" or "subtract 2")
- [x] 2.5 Wire cyclic/conditional edges so the hub is revisited after each turn and dispatches Adder → human_choice → Subtracter → final report, using `set_max_node_executions`/`reset_on_revisit` as needed

## 3. Verify against spec scenarios

- [x] 3.1 Run the graph with human choice "add 2"; confirm final total is exactly 14 and the trace lists all three ops in order
- [x] 3.2 Run the graph with human choice "subtract 2"; confirm final total is exactly 10 and the trace lists all three ops in order
- [x] 3.3 Confirm the run halts at `human_choice` and does not proceed to `Subtracter` until the operation is externally supplied

## 4. Record findings

- [x] 4.1 Write a finding for Open Question 1 (graph-node interrupt/resume): confirmed / not supported / supported with caveats, with the fallback approach noted if not supported
- [x] 4.2 Write a finding for Open Question 2 (cyclic/conditional hub edges): confirmed behavior of `set_max_node_executions`/`reset_on_revisit`
- [x] 4.3 Write a finding for Open Question 4 (cross-revisit state accumulation): confirmed / caveats
- [x] 4.4 Share findings as input to Task 2 (core debate graph) and Task 4 (audience-question HITL)
