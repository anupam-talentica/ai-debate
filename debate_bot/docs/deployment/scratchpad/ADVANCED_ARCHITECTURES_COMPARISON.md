# Advanced Architectures for Streaming Agents: Comparison

This guide compares 5 major architectural approaches for the human-in-the-loop debate bot, with trade-offs for streaming, session persistence, and scalability.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  1. WebSocket (My Proposed)         2. SSE + gRPC (Google)      │
│     - Bidirectional, persistent       - SSE: unidirectional      │
│     - State machine in-process        - gRPC: bidirectional      │
│     - Suitable for 10–100 users       - Scales to 1000s users    │
│                                                                  │
│  3. Pure gRPC                       4. Message Queue Pattern     │
│     - Bidirectional, low-latency      - Decoupled producer/      │
│     - Browser support requires          consumer                │
│       gRPC-Web                        - Scales to millions      │
│     - Simpler than SSE+gRPC          - Eventual consistency      │
│                                                                  │
│  5. Workflow Orchestration            6. HTTP/2 Push             │
│     (Temporal, Durable Functions)     (Limited browser support)  │
│     - Distributed state machine       - Server-initiated push    │
│     - Built-in retries, timeouts      - Not widely adopted      │
│     - Complex, high operational cost  - Browser compatibility    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. WebSocket (My Proposed Approach)

### Architecture Diagram
```
Frontend (React)           WebSocket             Backend (FastAPI)
   ↓                     (persistent)                ↓
  [UI]  ←──────────────────────────────────→  [Session Manager]
   │                                               │
   │ {submit_argument}                            │
   └────────────────────────────────────────→    ├─ State Machine (phase)
                                                  ├─ Timeout Scheduler
   {streaming_tokens}                             ├─ DB Persistence
   ←──────────────────────────────────────────    └─ LangGraph Invoker
                                                      ↓
                                                   [LangGraph]
                                                      ↓
                                                   [Claude LLM]
```

### Characteristics
- **Communication**: Full-duplex, single connection per session
- **Concurrency**: 10–100 concurrent sessions per server (depends on memory)
- **Persistence**: Database (SQLite/PostgreSQL)
- **Latency**: ~100–200ms round-trip
- **Browser Support**: ✅ All modern browsers
- **Scaling**: Vertical (add more servers, need session affinity in load balancer)

### Pros
✅ Simple to implement (FastAPI + asyncio)  
✅ Full bidirectional communication  
✅ No polling overhead  
✅ Easy debugging (single connection per session)  
✅ Low operational complexity  

### Cons
❌ Vertical scaling requires session affinity (sticky sessions)  
❌ Not ideal for 1000+ concurrent connections per instance  
❌ Memory grows linearly with open connections  
❌ Connection pooling complexity if using gRPC to LLM  
❌ No built-in message ordering guarantees (if you scale horizontally with Redis pubsub)

### When to Use
- Debate bot with 10–100 concurrent users
- Low-latency streaming needed
- Simple operational model preferred
- Tight coupling between session state and server acceptable

### Deployment (ECS)
```yaml
# service configuration
desired_count: 3
load_balancer_stickiness: true  # Important for session affinity
memory: 2048  # Grows with open connections
cpu: 1024
```

---

## 2. SSE + gRPC (Google's Approach)

### Architecture Diagram
```
Frontend (React)                    Backend (Envoy/gRPC Gateway)
   ↓                                     ↓
  [UI]  ──── HTTP/1.1 (SSE) ────→  [Streaming Endpoint]
   │    ←──── unidirectional ──────    │
   │                                    │ gRPC
   │                                    ↓
   │ {submit_argument}               [Session Service] (gRPC)
   └──── gRPC-Web (streaming) ───→     │
        (bidirectional)                 ├─ Phase Manager (gRPC)
                                        ├─ Timeout Manager
         ← {streaming_state} ────       ├─ Persistence Layer
                                        └─ LangGraph Driver
                                            ↓
                                         [LangGraph]
```

### Characteristics
- **Communication**: SSE (server→client) + gRPC-Web (client→server)
- **Protocol**: HTTP/2 for gRPC, HTTP/1.1 chunked for SSE
- **Concurrency**: 1000+ concurrent sessions per instance
- **Persistence**: Separate backing store (Firestore, Spanner, PostgreSQL)
- **Latency**: ~50–100ms (gRPC binary format is more efficient)
- **Browser Support**: ✅ Via gRPC-Web (requires Envoy proxy)
- **Scaling**: Horizontal scaling (stateless services + external persistence)

### Pros
✅ Stateless services (scales horizontally easily)  
✅ gRPC binary serialization is more efficient than JSON  
✅ Separate gRPC calls for control flow (submit argument) and data (streaming)  
✅ Handles 1000+ concurrent connections per instance  
✅ Built-in gRPC tooling (interceptors, load balancing)  
✅ Message ordering guaranteed by gRPC  
✅ Works with Google Cloud services (Pub/Sub, Spanner, Cloud Tasks)

### Cons
❌ More operational complexity (Envoy proxy, gRPC gateway)  
❌ Requires understanding of gRPC-Web (not standard gRPC in browsers)  
❌ SSE is still HTTP/1.1, not as efficient as full gRPC/2  
❌ Two separate connections (SSE + gRPC) to manage  
❌ Envoy configuration complexity  
❌ Browser debugging harder (gRPC messages are binary)

### Why Google Uses This Hybrid
1. **SSE for streaming**: One-way data (agent tokens) doesn't need gRPC overhead
2. **gRPC for commands**: Control flow (submit argument, pause, resume) uses fast binary protocol
3. **Separation of concerns**: Streaming service ≠ session service
4. **Scalability**: Streaming service can be auto-scaled independently from session service

### When to Use
- Debate bot with 100+ concurrent users
- Enterprise environment (Google Cloud ecosystem)
- Need for stateless, horizontally scalable services
- Team comfortable with gRPC/Envoy complexity

### Deployment (GCP)
```yaml
# Streaming service (SSE endpoint, auto-scale by CPU)
replicas: 10
scaling_metric: cpu
max_replicas: 100

# Session service (gRPC, persistent connections via Envoy)
replicas: 5
load_balancer: Envoy (L7 routing by service)
backing_store: Cloud Spanner (global, strongly consistent)
```

---

## 3. Pure gRPC

### Architecture Diagram
```
Frontend (React)  ──gRPC-Web────→  Backend (gRPC Server)
   [UI]           (bidirectional)        │
                                         ├─ Session Manager
     ←─ streaming_tokens ────────       ├─ Debate State Machine
                                         ├─ Persistence
     {submit_argument}                   └─ LangGraph
     ──→ bidirectional streaming        
                                      [LangGraph + Claude]
```

### Characteristics
- **Communication**: gRPC bidirectional streaming (HTTP/2)
- **Protocol**: Binary (Protocol Buffers)
- **Concurrency**: 1000+ per instance
- **Persistence**: External (PostgreSQL, etc.)
- **Latency**: ~50ms (binary protocol)
- **Browser Support**: ✅ Via gRPC-Web (Envoy proxy required)
- **Scaling**: Horizontal (stateless)

### Pros
✅ Single protocol (no SSE + gRPC mixture)  
✅ Binary serialization more efficient than JSON  
✅ True bidirectional streaming in one connection  
✅ gRPC interceptors for auth, logging, metrics  
✅ Automatic load balancing across replicas  
✅ Well-defined service contracts (proto3)

### Cons
❌ Browser support requires gRPC-Web adapter (Envoy proxy)  
❌ Larger learning curve (proto3, gRPC concepts)  
❌ Harder to debug in browser (binary format)  
❌ Overkill if you don't need the efficiency gains  
❌ Proto version management complexity as services evolve

### When to Use
- Want simplicity over SSE + gRPC mixture
- Team already familiar with gRPC
- Debate bot with 100+ concurrent users
- Internal service-to-service communication is also gRPC-based

### Example: Proto Definition
```protobuf
// debate.proto
syntax = "proto3";
package debate;

service DebateBroker {
  // Streaming RPC: agent → client (tokens)
  rpc StreamDebate(StreamRequest) returns (stream DebateEvent);
  
  // Regular RPC: client → server (submit argument)
  rpc SubmitArgument(ArgumentRequest) returns (ArgumentResponse);
}

message StreamRequest {
  string session_id = 1;
}

message DebateEvent {
  string session_id = 1;
  oneof event {
    TokenChunk token = 2;
    PhaseChanged phase_change = 3;
    Timeout timeout = 4;
  }
}

message ArgumentRequest {
  string session_id = 1;
  string phase = 2;
  string content = 3;
}
```

---

## 4. Message Queue Pattern (Kafka/RabbitMQ/AWS SQS)

### Architecture Diagram
```
Frontend (React)                    Backend Service
   [UI]  ───REST───→  [API Gateway]  →  [Message Queue]
                          ↓               (Kafka/RabbitMQ)
                     [Session Service]
                          ↑
                          │ consume
                          
   ←─ Polling/WebSocket ← [State Processor]
                              ↓
                          [LangGraph Worker]
                              ↓
                          [Claude LLM]
```

### Characteristics
- **Communication**: HTTP REST (polling) + async message queue
- **Concurrency**: Millions (decoupled producer/consumer)
- **Persistence**: Message broker (Kafka, RabbitMQ) + external store
- **Latency**: 100–1000ms (eventual consistency)
- **Browser Support**: ✅ (via REST polling or WebSocket to proxy)
- **Scaling**: Extreme horizontal scaling (independent consumer groups)

### Pros
✅ Extremely scalable (decoupled)  
✅ Fault-tolerant (if a worker crashes, messages are replayed)  
✅ Natural fit for microservices (debate service, human service, moderator service)  
✅ Built-in message ordering (per topic/partition)  
✅ Supports complex workflows (state transitions via messages)  
✅ Can handle bursty traffic (queue absorbs load)

### Cons
❌ **Higher latency** (100ms–seconds, depending on queue depth)  
❌ Eventual consistency (state may be inconsistent momentarily)  
❌ Complexity: need to model workflows as message choreography  
❌ Debugging is harder (messages are async, decoupled)  
❌ Operational complexity (manage broker, monitor lag, etc.)  
❌ Overkill for 10–100 concurrent users

### When to Use
- 1000+ concurrent debates
- Asynchronous processing acceptable (latency not critical)
- Multiple independent services (pro agent, con agent, moderator each separate)
- Need resilience to service failures
- High-volume, bursty traffic patterns

### Example: Kafka Topic Topology
```
Topics:
  - debate_commands
    {session_id, participant, phase, argument}
    
  - debate_state
    {session_id, current_phase, pro_opening, con_opening, ...}
    
  - moderator_decisions
    {session_id, winner, summary}

Consumer Groups:
  - session_manager (consumes debate_commands, produces debate_state)
  - agent_worker (consumes debate_state, invokes LangGraph, produces agent_output)
  - moderator_worker (consumes debate_state when phase=DECISION)
  - ui_service (consumes debate_state, pushes via WebSocket to browser)
```

### Deployment (AWS)
```yaml
# MSK (Managed Streaming for Kafka)
broker_nodes: 3
storage_per_broker: 200GB
replication_factor: 3

# Debate service (consumes commands, produces state)
lambda: "debate-state-processor"
concurrency: 100

# Agent worker (invokes LangGraph)
ec2_spot: "agent-worker"
autoscaling: queue_depth > 10
```

---

## 5. Workflow Orchestration (Temporal / Durable Functions)

### Architecture Diagram
```
Frontend (React)                 Backend
   [UI]  ──REST──→  [HTTP API]
                        │
                        ↓
                   [Temporal Client]
                        │
                        ↓
                  [Temporal Server] ← Persistent store
                        │
      ┌─────────┬───────┼────────┬──────────┐
      ↓         ↓       ↓        ↓          ↓
   [Pro Agent][Con Agent][Moderator][Timeout][Logger]
      │         │         │        │         │
      └─────────┴─────────┴────────┴─────────┘
            (Workers)

   WebSocket to UI (proxy)  ←─ State updates
```

### Characteristics
- **Communication**: REST API + gRPC to Temporal backend
- **Persistence**: Temporal server (event sourced history)
- **Concurrency**: 1000000+ (fully decoupled via workflow)
- **Latency**: 100–500ms (workflow serialization)
- **Browser Support**: ✅ (REST proxy to temporal events)
- **Scaling**: Infinite (Temporal is the state machine)

### Pros
✅ **Best for complex workflows** (built-in retries, timeouts, branching)  
✅ Automatic history replay (recover from any failure)  
✅ Visibility into workflow execution (Temporal UI)  
✅ Durable by design (no need to build state machine)  
✅ Supports human-in-the-loop natively (workflow pauses for human decision)  
✅ Language-agnostic (SDKs in Go, Python, JS, Java)  
✅ Unlimited scalability (workers are stateless)

### Cons
❌ **Overkill for simple, linear workflows** (debate phases are straightforward)  
❌ Operational overhead (run Temporal server, monitor, upgrade)  
❌ Latency higher than WebSocket/gRPC (workflow serialization)  
❌ Learning curve steep (workflow concepts, determinism rules)  
❌ Cost (Temporal Cloud or self-hosted maintenance)  
❌ State transitions are implicit (harder to debug vs explicit state machine)

### When to Use
- Debate workflow is complex (conditional phase skips, human retries, etc.)
- Fault tolerance is critical (debates can't be lost due to server crash)
- High concurrency (1000+) AND complex workflows
- Team already using Temporal for other workflows
- Need audit trail of all state transitions

### Example: Temporal Workflow (Python)
```python
# debate_workflow.py
from temporalio import workflow
from temporalio.common import RetryPolicy
from datetime import timedelta

@workflow.defn
class DebateWorkflow:
    @workflow.run
    async def execute(self, topic: str, pro: str, con: str):
        """Debate orchestration as a workflow."""
        
        # Phase 1: Pro opening
        pro_opening = await workflow.execute_activity(
            invoke_agent,
            args=[topic, "pro", None],
            retry_policy=RetryPolicy(max_attempts=2),
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        # Phase 2: Con opening
        con_opening = await workflow.execute_activity(
            invoke_agent,
            args=[topic, "con", pro_opening],
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        # Phase 3: Human waits for input (if human is participant)
        human_input = await workflow.wait_condition(
            lambda: self.human_submitted,
            timeout=timedelta(seconds=300),
        )
        
        # ... continue phases ...
        
        # Decision
        winner = await workflow.execute_activity(
            invoke_moderator,
            args=[pro_opening, con_opening, ...],
        )
        
        return {
            "winner": winner,
            "pro_opening": pro_opening,
            "con_opening": con_opening,
            ...
        }
    
    @workflow.signal
    async def submit_human_argument(self, content: str):
        """Signal to resume workflow (human submitted argument)."""
        self.human_submitted = True
        self.human_content = content
```

---

## 6. HTTP/2 Server Push (Not Recommended)

### Why Not to Use
- ❌ **Browser support**: Only Chrome/Firefox; deprecated in favor of Server-Sent Events
- ❌ **Proxy incompatibility**: Many CDNs/proxies don't support Server Push
- ❌ **Limited by same origin**: Can only push resources to the same page
- ❌ **No client control**: Server pushes, client can't decline
- ❌ **Falling out of favor**: HTTP/3 (QUIC) doesn't include Server Push

**Skip this unless you have legacy requirements.**

---

## Comparison Matrix

| Criterion | WebSocket | SSE + gRPC | Pure gRPC | Message Queue | Temporal |
|-----------|-----------|-----------|-----------|---------------|----------|
| **Concurrency** | 10–100 | 1000+ | 1000+ | 1M+ | 1M+ |
| **Latency** | ~100ms | ~100ms | ~50ms | ~500ms | ~200ms |
| **Setup Complexity** | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Operational Complexity** | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Browser Support** | ✅ Native | ✅ gRPC-Web | ✅ gRPC-Web | ✅ via proxy | ✅ via REST |
| **Horizontal Scaling** | Hard (sticky) | Yes | Yes | Yes (easy) | Yes |
| **Persistence Built-in** | No | No | No | Yes (queue) | Yes (event log) |
| **Streaming Quality** | ✅✅ | ✅ (SSE only) | ✅✅ | ❌ (async) | ❌ (eventual) |
| **Debugging** | ✅ Easy | ⚠ Medium | ⚠ Binary | ⚠ Async | ⚠ Event log |
| **Cost** | Low | Medium | Medium | Medium–High | High |
| **Best For** | Small debates (10–100 users) | Google Cloud ecosystem | gRPC team | Millions of users | Complex workflows |

---

## Decision Tree

```
Are you building for < 100 concurrent users?
├─ YES → WebSocket (simple, fast)
└─ NO → Are you on Google Cloud?
    ├─ YES → SSE + gRPC
    └─ NO → Is your team familiar with gRPC?
        ├─ YES → Pure gRPC
        └─ NO → Do you expect 1000+ concurrent debates?
            ├─ YES → Message Queue (Kafka)
            └─ NO → Is your debate workflow complex?
                ├─ YES (human decisions, branching) → Temporal
                └─ NO → WebSocket with external job queue
```

---

## Hybrid Recommendations for Debate Bot

### MVP (< 100 users): WebSocket Only
```
Frontend  ←→  WebSocket  ←→  FastAPI  →  LangGraph  →  Claude
                                ↓
                            PostgreSQL
```
**Cost**: ~$30/month  
**Complexity**: Low  
**Scaling**: Works up to ~50 concurrent users per server

---

### Growing Product (100–1000 users): WebSocket + Redis PubSub
```
Frontend  ←→  WebSocket  ←→  Nginx (L7)  ├─→  [FastAPI Instance 1]
              (load balanced)               ├─→  [FastAPI Instance 2]
                                            └─→  [FastAPI Instance 3]
                                                    ↓
                                            Redis PubSub (broadcasts)
                                                    ↓
                                            PostgreSQL (state)
```
**Why Redis PubSub**: When you add instances, they need to broadcast updates to each other's clients.  
**Cost**: ~$100–200/month  
**Complexity**: Medium (session affinity required; or use Redis for session store)

---

### Enterprise (1000+ users): SSE + gRPC or Message Queue
```
Frontend  ──SSE──→  [Streaming Service 1]  ───────┐
   │                [Streaming Service 2]  ───────┤
   │                [Streaming Service 3]  ───────┤ gRPC Gateway (Envoy)
   │                                               │
   └──gRPC-Web──→  [Session Service 1]  ──────────┤
                   [Session Service 2]  ──────────┤
                   [Session Service 3]  ──────────┘
                         ↓
                    Cloud Spanner / PostgreSQL
```
**Why SSE + gRPC**: Separates streaming (one-way, high volume) from control flow (two-way, critical).  
**Cost**: ~$500–2000/month  
**Complexity**: High (Envoy, gRPC-Web, service management)

---

### Ultra-Scale (10,000+ users, Complex Workflows): Temporal + Message Queue
```
Frontend  ──REST──→  [API Gateway]  ──→  Temporal Server
                                              ↓
                                         [Workflow Executions]
                                              ↓
                    ┌───────────┬────────────┬───────────┐
                    ↓           ↓            ↓           ↓
            [Agent Worker 1][Agent Worker 2][Human Wait][Moderator]
                    ↓           ↓            ↓           ↓
                    └───────────┴────────────┴───────────┘
                                    ↓
                        Message Queue (Event Sourcing)
                                    ↓
                            PostgreSQL + Elasticsearch
```
**Why Temporal**: Handles distributed state machine, retries, timeouts, human waits.  
**Why Message Queue**: Decouples workers, enables independent scaling.  
**Cost**: ~$2000–5000/month  
**Complexity**: Very High

---

## Specific Answer: Google's SSE + gRPC

Google likely uses this hybrid because:

1. **SSE for streaming** (one-way agent tokens)
   - Reduces protocol overhead
   - Simple for browsers (native EventSource API)
   - No need for bidirectional channel for data

2. **gRPC for commands** (client→server operations)
   - Binary efficiency (submit argument, pause, resume)
   - Multiplexing via HTTP/2
   - Type safety via proto3

3. **Separation of Concerns**
   ```
   - Streaming Service: Scales independently by request rate
   - Session Service: Scales by session count
   - Stateless: Both can be replicated horizontally
   ```

4. **Enterprise Features**
   - Envoy proxy handles routing, auth, circuit breaking
   - Can route SSE and gRPC to different services
   - gRPC interceptors for observability (Datadog, CloudTrace)

### Google Architecture in Practice
```python
# server.py - SSE endpoint (streaming)
@app.get("/debates/{session_id}/stream")
async def stream_debate(session_id: str):
    async def event_generator():
        async for token in debate_stream(session_id):
            yield f"data: {token}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")

# service.proto - gRPC service (commands)
service DebateService {
  rpc SubmitArgument(SubmitRequest) returns (SubmitResponse);
  rpc PauseDebate(PauseRequest) returns (PauseResponse);
  rpc GetDebateState(StateRequest) returns (DebateState);
}

# Frontend
const eventSource = new EventSource(`/debates/${sessionId}/stream`);
eventSource.onmessage = (e) => updateUI(JSON.parse(e.data));

// Submit argument via gRPC
const response = await debateClient.submitArgument({
  sessionId,
  phase,
  content,
});
```

**Pros of this hybrid:**
- Decouples high-volume data (SSE) from control flow (gRPC)
- Each can be scaled independently
- Familiar browser API (EventSource) for streaming
- Type-safe control flow (proto3)

**Cons:**
- Two separate connections to manage
- Envoy complexity
- Not needed unless you have 100+ concurrent users

---

## Recommendation for Your Debate Bot

Given your requirements:

### **Now (MVP)**: WebSocket + SQLite
- Simple, works perfectly for testing
- One connection per debate
- Persist to SQLite for durability
- Supports streaming and human input

### **When you hit 100 concurrent users**: Add Redis PubSub
- Keep WebSocket on each instance
- Use Redis for broadcasting phase changes
- Sticky sessions or session store in Redis

### **When you hit 1000+ users**: Migrate to SSE + gRPC or Pure gRPC
- Only if latency/efficiency becomes critical
- Use gRPC-Web via Envoy
- Stateless services with external session store (Spanner/PostgreSQL)

### **Don't use Temporal unless**:
- Debate workflow becomes complex (conditional skips, human retries at specific phases)
- You need automatic recovery from failures
- Your team already uses Temporal for other services

---

## Summary Table: When to Use Each

| Use Case | Architecture | Reason |
|----------|--------------|--------|
| Prototype | WebSocket | Simplest, works locally |
| 10–50 users | WebSocket | No scaling headaches |
| 50–200 users | WebSocket + Redis | Basic horizontal scaling |
| 200–1000 users | gRPC (or SSE+gRPC) | Efficiency matters, handle load |
| 1000–10,000 users | SSE + gRPC (Google) | Separate streaming/control, enterprise features |
| 10,000+ users | Message Queue (Kafka) | True decoupling, fault tolerance |
| Complex workflows | Temporal | Built-in workflow engine, human waits |
| All scenarios | Monitor latency, memory, connections | Upgrade only when needed |

