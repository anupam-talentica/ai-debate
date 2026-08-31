Deployed the Strands-based multi-agent debate bot (Pro/Con/Moderator graph, HITL audience-question pause, cross-debate memory) to a real Amazon Bedrock AgentCore Runtime in ap-south-1.

Below are my key findings.

1. AgentCore forces everything behind a single API.
AgentCore only exposes POST /invocations + GET /ping, port 8080, Linux/ARM64, ECR image.
We had 5 separate routes — start, stream, resume, audience-question, invoke. Had to put a single dispatcher in front using an action field.
This was mostly routing work. Didn't have to touch the graph/agent logic.

2. Session-to-microVM affinity actually works.

Same runtimeSessionId stays on the same warm microVM. Session also survives StopRuntimeSession / resume. It only really goes away when the Runtime ARN is deleted.

Default idleRuntimeSessionTimeout is 15 min — too short for a debate waiting on an audience question, so bumped it to 4h. maxLifetime is a hard 8h ceiling.

Because of this, existing in-process state (Graph, RunRegistry, asyncio.Queue) kept working almost as-is. Didn't need to redesign everything as stateless.

3. AgentCore doesn't provide pause/resume.

It keeps the microVM alive, but the framework still has to handle "pause mid-graph → wait for input → resume".

Strands' native serialization doesn't cleanly capture this state. Had to add InvocationStatePersistenceHook and write a separate invocation_state.json, then reload it on resume.

This was the most bespoke part of the migration.

LangGraph's interrupt() + checkpointer + Command(resume=...) handles this natively. So if HITL pause/resume is important, this is a real LangGraph advantage — we actually hit the gap.

4. S3SessionManager was a clean durability option.

Used Strands S3SessionManager instead of AgentCore Managed Session Storage (still Preview/no SLA, 1GB/session, 14-day idle wipe).

Strands' SessionRepository interface made the swap easy. No changes to graph/node code.

5. Memory didn't fit the AgentCore pattern.

Used S3 Vectors instead of AgentCore Memory/OpenSearch.

Our moderator node directly calls memory_store.search() / add() rather than having an LLM agent call memory as a tool.

AgentCore Memory doesn't really fit this pattern, so wrote a thin S3VectorMemoryStore using boto3 s3vectors.

Embeddings: Bedrock Titan amazon.titan-embed-text-v2:0 (1024-dim).

If memory is a normal call from a deterministic/non-agent node, expect some custom plumbing.

6. AgentCore errors are annoyingly opaque.

Hit a bare 422 Unprocessable Entity with no useful error body.

Turned out to be FastAPI's automatic body/header inference not working with the way AgentCore sends the request. Fixed it by manually reading req.body() / headers.

Add defensive logging at the dispatcher/edge. Don't expect AgentCore to give you enough detail to debug your own request handling.

7. IAM naming can bite you.

Wanted a hyphenated runtime name, but AgentCore rejected it and created:

debate_bot_agentcore-C3ZGzNGB5V

IAM policies written against the expected name then broke.

Better to create the runtime first, get the actual ARN, and then tighten the IAM policy.

8. Runtime billing is genuinely consumption-based.

No standing cost just because the Runtime exists.

CPU: $0.0895/vCPU-hour
Memory: $0.00945/GB-hour

CPU idle/I/O wait isn't charged, but memory is charged while the microVM is alive — including HITL pauses.

Still only cents for a several-hour pause at our scale.

9. Actually verified Stop/Resume.

Used MOCK_LLM + a real StopRuntimeSession, which forces actual microVM teardown, followed by a real resume from S3.

State recovery worked. Didn't need Anthropic credits to prove the persistence mechanism.

10. Chat model stayed on direct Anthropic API.

Didn't use Bedrock-hosted Claude.

Only needed Bedrock IAM (bedrock:InvokeModel) for the Titan embedding model. Anthropic credentials were passed through AgentCore environmentVariables.

For the POC, didn't need Secrets Manager.

11. Docker had a couple of unrelated potholes.

Needed linux/arm64 build on Apple Silicon.

One Docker tag got corrupted — fixed by re-tagging the existing image instead of rebuilding.

Also hit a macOS Docker permission issue because the Dockerfile was sitting in /tmp and Docker was scanning unrelated files. Moving it into the project directory fixed it.

12. Observability was easy.

aws-opentelemetry-distro + wrapping CMD with opentelemetry-instrument gives real spans in CloudWatch Transaction Search with no application code changes.

Framework-agnostic, so worth adding regardless of whether the underlying graph is Strands or LangGraph.

Bottom line: AgentCore itself was fairly straightforward. The main migration work was the single API dispatcher and making state durable when the microVM eventually dies.

The rough part was Strands + HITL + durable resume. AgentCore can keep the microVM alive, but Strands doesn't give you a clean native way to serialize a graph paused in the middle waiting for external input. That's where most of the custom plumbing ended up — and where LangGraph has a much more mature story.
