## 1. `status` action on the existing AgentCore dispatcher (design.md, Decision 3; specs/agentcore-deployment)

- [ ] 1.1 Add `DebateService.get_status(run_id)`: reads `RunEntry.status`/`.error` from `RunRegistry` when the run is live; falls back to `read_persisted_graph_status` (same as `resume()`) when it isn't; returns `None` for an unknown `run_id`
- [ ] 1.2 When status is `done`, include the completed `invocation_state` (`winner`, `justification`, etc.) in the return value, matching `action=invoke`'s successful shape
- [ ] 1.3 When status is `failed`, include the failure detail
- [ ] 1.4 Add `status` to `_KNOWN_ACTIONS` in `src/api/routes/agentcore.py` and dispatch it to `DebateService.get_status`, returning 404 for an unknown `run_id`
- [ ] 1.5 Add tests: querying `running`, `waiting_for_input`, `done` (with content), `failed` (with detail), a resumed-from-storage run, and an unknown `run_id` — extend `tests/test_agentcore.py`
- [ ] 1.6 Confirm the existing dispatcher tests and the full suite still pass unmodified

## 2. Agent-Bridge Lambda (design.md, Decisions 1, 2, 4)

- [ ] 2.1 Implement the bridge Lambda handler, parameterized by phase (`start` or `submit_audience_question`): call the corresponding AgentCore action via `bedrock-agentcore:InvokeAgentRuntime` against the deployed runtime (`debate_bot_agentcore-C3ZGzNGB5V`), setting the session header from the Flow-supplied (or newly-minted, for `start`) `run_id`
- [ ] 2.2 Implement the internal poll loop: after the initial call, poll `action=status` on an interval until status leaves `running`, then return `{run_id, status, ...content or error}` to the Flow
- [ ] 2.3 Fail explicitly (distinct error) if the poll loop exceeds the Lambda's own execution ceiling without settling, per design.md's Risks section
- [ ] 2.4 Write the IAM role/policy for the Lambda, scoped to `InvokeAgentRuntime` on this specific runtime ARN only (matching `deploy-to-agentcore`'s existing scoped-resources IAM pattern)
- [ ] 2.5 Verify both phases by direct Lambda invocation against the real deployed runtime, with no Flow involved yet: start-and-wait reaches `waiting_for_input`; submit-and-wait (given a question) reaches `done` with verdict content

## 3. Bedrock Flow definition (design.md, Decisions 1, 2, 5; specs/bedrock-flows-visual-workflow)

- [ ] 3.1 Resolve the Open Question on Bedrock Flows' maximum single-execution duration against current AWS documentation before finalizing the Human Input node's role in the topology
- [ ] 3.2 Define the Flow as `AWS::Bedrock::Flow` (CDK or CloudFormation JSON): Input(topic) → Guardrail → Start-and-wait Lambda node → Condition (awaiting-question vs. done vs. failed) → Human Input (question) → Submit-and-wait Lambda node → Guardrail → Output
- [ ] 3.3 Attach a Bedrock Guardrail to the topic-input node and the verdict-output node
- [ ] 3.4 Wire the failure branch(es) (guardrail rejection, bridge Lambda failure, debate execution failure) to an explicit failure output distinct from the verdict output
- [ ] 3.5 Deploy the Flow as a `DRAFT` version first

## 4. End-to-end verification

- [ ] 4.1 Run the Flow with a real topic; confirm it pauses at the Human Input node
- [ ] 4.2 Submit an audience question; confirm the Flow proceeds to a guarded verdict output
- [ ] 4.3 Confirm a topic rejected by the input guardrail produces the explicit failure output, with no debate started
- [ ] 4.4 Confirm two Flow executions triggered concurrently with different topics don't cross-contaminate (specs/bedrock-flows-visual-workflow, "Concurrent Flow executions are isolated")
- [ ] 4.5 Confirm the existing REST surface, AgentCore dispatcher's other actions, and Streamlit demo UI are unaffected
- [ ] 4.6 Promote the Flow to a versioned alias once verified
