## Context

`deploy-to-agentcore` (archived) established the invocation boundary this change builds on: `POST /invocations` dispatches by an `action` field (`start`, `stream`, `submit_audience_question`, `resume`, `invoke`) to the existing `DebateService`, using the AgentCore `runtimeSessionId` header directly as `run_id`. `DebateService`'s in-process `RunRegistry` already tracks each run's status as one of `running` | `waiting_for_input` | `done` | `failed` (`RunEntry.status`), but nothing exposes that status on its own — the only way to observe it today is to open `action=stream`'s SSE connection and watch for a `COMPLETE`/`AWAITING_AUDIENCE_QUESTION`/`ERROR` event, or to have been the caller that received `DebateAwaitingInputError`/`DebateTimeoutError` from `action=invoke`.

Bedrock Flows (per this project's earlier stack evaluation) has no native node type that targets an AgentCore Runtime ARN — only a `agentAliasArn`-based node for the older, separate Bedrock Agents service. Reaching this project's AgentCore-hosted agent from a Flow requires a Lambda node calling `bedrock-agentcore:InvokeAgentRuntime` directly.

## Goals / Non-Goals

**Goals:**
- Let a Flow drive a debate to a verdict using only the existing AgentCore dispatcher plus one small additive action, with no change to debate behavior.
- Keep the Flow's own topology simple — a handful of nodes, no Flow-level polling loop — by pushing all "wait until settled" logic into the bridge Lambda(s), reserving the Flow's own wait semantics for the one wait that's genuinely open-ended: the human typing an audience question.
- Attach guardrails at the points a business user's input and the system's output actually cross the Flow boundary.

**Non-Goals:**
- Modeling the debate's round-by-round progress inside the Flow. The Flow sees three outcomes — awaiting a question, a completed verdict, or a failure — not seven round-turn events.
- Making the Flow resilient to a wait longer than a single Lambda invocation for the *debate's own* execution (opening → rebuttal, or closing → verdict). Those legs are a handful of LLM calls; per `deploy-to-agentcore`'s own design.md, the multi-hour case this project already engineered for is the *human's* wait, not the model's.
- A generic "any Flow can call any AgentCore agent" abstraction. This bridge is scoped to this one deployed runtime.

## Decisions

### 1. The bridge Lambda polls internally; the Flow does not carry a loop node

Two ways to get from "start the debate" to "it's paused or done": (a) a Flow-level loop/iterator node that calls a status-check Lambda repeatedly, with the Flow itself implementing backoff and a max-attempt bound, or (b) one Lambda invocation that calls `action=start` and then polls the new `action=status` internally (a plain sleep loop), returning to the Flow only once the run has left `running`.

Chose (b). The wait it's covering — opening and rebuttal rounds, a handful of LLM calls — comfortably fits inside a single Lambda's 15-minute ceiling, so there is no correctness reason to spend a Flow-level loop node on it, and keeping the poll inside the Lambda keeps the Flow's visible topology at five nodes (Input → Start-and-wait → Human Input → Submit-and-wait → Guardrail → Output) instead of a loop-with-branches shape a business user would have to understand to maintain the Flow. The same Lambda (parameterized by which phase it's in — `start` vs `submit_audience_question`) is reused for both wait legs, since both are "call an action, then poll `status` until it's no longer `running`."

**Alternative considered**: Flow-level loop node calling a thin status-check Lambda each iteration. Rejected for now — it moves the same logic into the Flow's own graph for no behavioral benefit, at the cost of a more complex Flow a business user has to read. Worth revisiting only if a debate's opening/rebuttal legs are ever observed to run long enough to risk the Lambda ceiling, which nothing in this project's existing round timeouts (`DebateService`'s 60s default `timeout_seconds` for `invoke`, unrelated to this path, but indicative of expected round latency) suggests.

### 2. The human's wait lives entirely in the Flow's Human Input node, not in any Lambda

Once the bridge Lambda's internal poll observes `status=waiting_for_input`, it returns immediately — it does not also wait for the audience question. The Flow's own Human Input node is what pauses, for however long a person takes to type a question, with no Lambda holding a connection or a poll loop open for that duration.

This is the same reasoning the Agent Platform Stack Decision already applied when it flagged that Bedrock Flows' human-input mechanism only pauses *between* Flow steps, not inside an agent's own reasoning loop: that's not a limitation here, because the debate's audience-question pause already externalizes as exactly such a between-steps boundary through the existing AgentCore contract (`Status.INTERRUPTED` → `RunEntry.status = "waiting_for_input"`, resumable later via `submit_audience_question` against the same session id). The Flow never needs to reach inside a live tool-call loop; it only needs to notice the pause from outside, which is precisely what Bedrock Flows' Human Input node is built for.

### 3. A new `status` action, not SSE-parsing inside the Lambda

The bridge Lambda could instead call `action=stream` and read the SSE body until it sees a settling event. Rejected: that requires a Lambda to parse an event-stream response shape it has no other reason to understand, and ties the bridge's polling cadence to whatever `stream_registered`'s queue happens to emit rather than to a cheap, purpose-built check. A new `status` action is a small, additive extension of the same dispatch pattern `deploy-to-agentcore` already established (translate a payload field to a `DebateService` call, format the result) — `DebateService.get_status(run_id)` reads `RunEntry.status`/`.error` when the run is live in `RunRegistry`, and falls back to `read_persisted_graph_status` (the same function `resume()` already calls) when it isn't, so a status check works identically whether the run's compute is warm or was Stopped and not yet resumed.

When `status == "done"`, the response includes the completed `invocation_state` (`winner`, `justification`, etc.) — the same shape `action=invoke`'s successful return already has — so the Flow's final Lambda call both confirms completion and hands back the verdict content in one round trip, rather than requiring a second call to fetch it.

### 4. Session identity: the Flow owns and threads its own run_id

`deploy-to-agentcore` already decided `run_id` doubles as `runtimeSessionId`, generated by whichever caller starts the run. For a Flow-triggered debate, the *Flow* is that caller: the Start-and-wait Lambda mints a `run_id` (or the Flow does, via its own input/output variables) and every subsequent bridge call for that execution — the status polls, the submit-and-wait call — threads the same id through as the session header. No new identifier space is introduced; this mirrors exactly how the REST surface's `/start` and the AgentCore dispatcher's `start` action already work.

### 5. Guardrails at the Flow's input and output nodes only

Per the earlier stack evaluation's finding that Bedrock Guardrails attach per-node (not just flow-wide), this change attaches one to the topic-input node (before a debate is even started) and one to the verdict-output node (before the winner/justification reach whoever consumes the Flow's output). This is a property of the Flow, not the debate graph — `debate-graph-orchestration` and `audience-question-hitl` are unmodified, so nothing changes about what the two debaters or the moderator produce; the guardrail only gates what crosses the Flow's own boundary.

## Risks / Trade-offs

- **[Risk]** A debate's opening+rebuttal or closing+verdict leg exceeds the Lambda's 15-minute ceiling (e.g. a transient Anthropic API slowdown, or the AgentCore session's compute having been Stopped and needing to cold-resume from S3 mid-poll) before reaching a settled status. → **Mitigation**: the bridge Lambda fails explicitly (timeout error) rather than hanging past its own ceiling; the Flow surfaces that as a distinct failure output, and the underlying debate is unaffected and resumable exactly as `deploy-to-agentcore`'s own resume path already handles a killed run — a retry of the same Flow execution (or a dedicated "resume" bridge path) picks it back up by `run_id`.
- **[Risk]** Bedrock Flows' own maximum single-execution duration is not confirmed from documentation reviewed so far, and a Human Input wait of, say, several hours could conceivably exceed it. → Flagged as an Open Question below rather than assumed.
- **[Trade-off]** Reusing one parameterized Lambda for both the start-and-wait and submit-and-wait legs, rather than two separate functions, means a single function's IAM role and code path cover both call shapes. Accepted — the two legs share all their logic (call an action, poll status, return) except which action they call first, and the existing dispatcher already unifies "make an AgentCore call" behind one action-based contract, so mirroring that in the bridge Lambda avoids duplicating the poll loop.
- **[Risk]** The new `status` action is a genuinely new `DebateService` code path (a status/error read that bypasses the event queue entirely), distinct from every existing action, which all either mutate a run or consume its queue. → **Mitigation**: kept read-only and side-effect-free by construction — it only reads `RunEntry` fields or calls the already-tested `read_persisted_graph_status` — so it cannot itself desynchronize a run's state; new unit tests (tasks.md) cover it directly rather than relying on the existing action tests to catch regressions here.

## Migration Plan

No data migration — this adds a new invocation path and one new dispatcher action to an already-deployed system; nothing about existing persisted sessions, checkpoints, or memory changes.

1. Add `DebateService.get_status(run_id)` and the `status` action on the AgentCore dispatcher; verify against a local `uvicorn` process (no AWS Flow involved) that it reflects `running`/`waiting_for_input`/`done`/`failed` correctly across a live run, a resumed-after-restart run, and an unknown `run_id`.
2. Implement the bridge Lambda(s) against the real deployed AgentCore Runtime (`debate_bot_agentcore-C3ZGzNGB5V`), verified by direct invocation (no Flow yet) for both the start-and-wait and submit-and-wait legs.
3. Define the Bedrock Flow, its Guardrail(s), and the IAM role as CDK/CloudFormation; deploy to a `DRAFT` flow version first.
4. End-to-end verify: run the Flow with a real topic, confirm it pauses for the Human Input node, submit an answer, confirm a guarded verdict comes out; confirm a failure path (e.g. an invalid topic caught by the input guardrail) reports explicitly rather than silently.
5. Promote the Flow to a versioned alias once verified.

**Rollback**: additive at every layer — deleting the Flow, its Guardrail, and the Lambda(s) leaves the existing REST surface, AgentCore dispatcher (minus the new `status` action, which nothing else depends on), and debate graph exactly as they were.

## Open Questions

- **Bedrock Flow maximum execution duration**: needs confirming against current AWS documentation before the Human Input wait is treated as truly open-ended — if Flows impose a ceiling shorter than a realistic "someone gets back to this later" wait, the Flow may need to persist its own paused state externally (e.g. resume the Flow execution itself via a callback/webhook rather than a single long-lived execution) rather than relying on the Human Input node's own wait semantics. Doesn't change this change's specs or task breakdown — the bridge Lambda and `status` action are correct either way — but affects how the Flow itself is authored in task 3.
- **IAM scoping for the bridge Lambda's `InvokeAgentRuntime` call**: whether to scope it to the specific runtime ARN only (recommended, matching this project's existing "scoped resources only, not wildcard" IAM pattern from `deploy-to-agentcore`) is an implementation detail for the task that writes the role, not a design-level decision.
