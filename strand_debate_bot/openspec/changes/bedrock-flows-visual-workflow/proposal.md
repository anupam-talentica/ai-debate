## Why

The debate system already runs as a Strands agent on Bedrock AgentCore Runtime (`agentcore-deployment`), but every caller today has to be code — the REST surface, the AgentCore dispatcher, or the Streamlit demo UI. There is no way for a non-engineer to visually trigger a debate, watch it pause for the audience question, and see a guarded verdict come out, which is exactly the "visual front door" role the org's Agent Platform Stack Decision (n8n → Dify → Bedrock Flows evaluation) concluded should sit in front of the Strands/AgentCore layer, native to the same AWS account this system is already deployed in. This change gives the already-deployed agent that front door without touching the debate graph, the agents, or any existing endpoint.

## What Changes

- New AWS Bedrock Flow (defined as `AWS::Bedrock::Flow` via CDK/CloudFormation, not hand-edited in the console) that: accepts a topic, starts the debate, waits for it to either pause for the audience question or finish, collects the audience question through a Flow Human Input node when it pauses, resumes the debate with that answer, and outputs the guarded verdict.
- New Agent-Bridge Lambda(s) that translate a Flow node's call into the existing AgentCore `/invocations` contract — setting the `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id` header, choosing the right `action`, and internally polling run status until the debate reaches a pause or a terminal state (bounded by the Lambda's own execution window; the open-ended wait is for the *human's* answer, which lives entirely in the Flow's own Human Input step, not in the Lambda).
- New `status` action on the existing AgentCore dispatcher (`src/api/routes/agentcore.py`) and a corresponding `DebateService` method, so the bridge Lambda can cheaply check whether a run is still going, paused, done, or failed — without opening the SSE stream `action=stream` returns. **Additive only**: `start`, `stream`, `submit_audience_question`, `resume`, `invoke`, and the REST surface in `src/api/routes/debates.py` are unchanged.
- Bedrock Guardrails attached to the Flow's topic-input node and its verdict-output node.

Explicitly out of scope:
- Any change to the debate graph, agents, prompts, or the round state machine (`debate-graph-orchestration`, `audience-question-hitl` are untouched).
- Real-time, per-turn streaming through the Flow — the Flow's visible steps are coarse ("submitted" → "awaiting audience question" or "verdict ready" or "failed"), not a token-by-token feed. Anyone who wants that already has `action=stream` via the REST or AgentCore surface.
- Any multi-agent A2A protocol work inside the Flow itself — the Agent Platform Stack Decision already assigns A2A to the Strands/AgentCore layer, not the visual layer, and this change doesn't revisit that.

## Capabilities

### New Capabilities
- `bedrock-flows-visual-workflow`: the observable behavior of the Bedrock Flow itself — given a topic, it drives the already-deployed debate agent to a guarded verdict, surfacing the audience-question pause as a human-input step.

### Modified Capabilities
- `agentcore-deployment`: adds a `status` operation to the single dispatched invocation endpoint, and a new requirement that a run's status is queryable without consuming its event stream.

## Impact

- New: a CDK/CloudFormation stack defining the Bedrock Flow, its Guardrail(s), and the Agent-Bridge Lambda(s); new Lambda source.
- Modified: `src/api/routes/agentcore.py` (new `status` action), `src/api/services/debate_service.py` (new status-query method reading `RunEntry.status`/error, falling back to `read_persisted_graph_status` the same way `resume()` already does when a run isn't live in the in-process `RunRegistry`).
- New AWS resources: a Bedrock Flow, a Bedrock Guardrail, one or two Lambda functions, and an IAM role granting those Lambdas `bedrock-agentcore:InvokeAgentRuntime` against the existing deployed runtime (`debate_bot_agentcore-C3ZGzNGB5V`).
- No new dependency on graph topology, session-manager, or memory-store internals — this change sits entirely at the invocation boundary already established by `deploy-to-agentcore`.
