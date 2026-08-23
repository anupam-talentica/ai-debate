# Agentic Platform POC — Strands + Bedrock AgentCore

**Author context:** POC for an internal Agent-Building Platform (Agents + Tools + MCP tied through a Workflow). Target business domains: **Supply Chain** and **Finance**. 

**Verdict:** TO keep cost minimal build the agent logic locally with **Strands** (free), then deploy it onto **AgentCore Runtime** for the "production" story. Use synthetic data so you never wait on real system integrations.

---

## 1. Recommended problem statement (Supply Chain)

### "Component Shortage & Purchase-Order Triage Agent"

**Scenario:** A supplier sends a delay notice — *"Part ABC-123 delayed 3 weeks."* Today a planner manually cross-checks inventory, open orders, and customer commitments to figure out what's at risk and what to do. The agent does this end-to-end.

**What the agent does (the workflow):**

1. **Detect** — receives the delay alert (text input or a JSON event).
2. **Enrich** *(MCP tool)* — looks up the affected part's suppliers, alternate parts, and lead times from a reference source exposed via an **MCP server**.
3. **Analyze** *(custom Python tool)* — queries a small inventory + open-orders dataset (SQLite/CSV) to find which products and customer orders depend on the delayed part.
4. **Simulate** *(Code Interpreter tool)* — computes stock-out dates, buffer coverage, and a simple what-if for an alternate supplier.
5. **Recommend** *(model reasoning)* — produces a ranked, structured action list (expedite, re-source, re-prioritize POs, notify customer).
6. **Notify** *(Gateway / MCP tool)* — posts the summary to a mock API endpoint or a Slack MCP channel.

**Input example:** `"Supplier Acme delayed part ABC-123 by 3 weeks starting 2026-09-01"`
**Output example:** a structured risk brief — at-risk products, affected customer orders + revenue exposure, recommended actions ranked by impact, and a one-paragraph human summary.

### Why this problem is the right POC

- It **exercises every platform primitive** you care about: one **Agent** (Strands), multiple **Tools** (Python function + Code Interpreter), an **MCP** server, and an explicit multi-step **Workflow** — deployed on **AgentCore** with Memory + Observability.
- It's **domain-representative** (fabless semiconductor supply chain is a real, high-value pain) without needing any real ERP integration — synthetic CSVs stand in.
- The same skeleton **drops straight into Finance** (see §5), which is the actual point: it proves the platform is domain-agnostic.

---

## 2. How it maps to your platform primitives

| Platform concept | POC implementation |
|---|---|
| **Agent** | A single Strands agent (`Agent(model=..., tools=[...], system_prompt=...)`) running the model-driven reasoning loop. |
| **Tools** | (a) `query_orders()` custom Python function tool over SQLite; (b) AgentCore **Code Interpreter** for the impact math. |
| **MCP** | An MCP server exposing "supplier/part reference" — use a filesystem or SQLite MCP server, or a tiny custom MCP server. Strands connects to it via its MCP client. |
| **Workflow** | The orchestrated Detect→Enrich→Analyze→Simulate→Recommend→Notify sequence. For the POC the Strands agent loop *is* the orchestration; document the steps explicitly so it maps cleanly to n8n / a graph later. |
| **Runtime / Deploy** | Package the agent and deploy to **AgentCore Runtime** (session-isolated serverless host). |
| **Memory** | AgentCore short-term Memory so a follow-up question ("what about part XYZ?") keeps context. |
| **Observability** | AgentCore → CloudWatch traces to show tool calls and decision path in the demo. |

---

## 3. Tech stack

- **SDK:** Strands Agents (`pip install strands-agents strands-agents-tools`) — Apache 2.0, model-driven loop.
- **Model:** **Claude Sonnet 5 on Amazon Bedrock** (recommended — see §6).
- **Data:** 2–3 synthetic CSVs (`parts.csv`, `inventory.csv`, `open_orders.csv`) loaded into SQLite. ~50–100 rows total is plenty.
- **MCP:** an off-the-shelf MCP server (filesystem or SQLite) OR a ~40-line custom MCP server exposing `get_part_info(part_id)`.
- **Runtime:** AgentCore Runtime + Code Interpreter; CloudWatch for Observability.
- **Notify (optional):** AgentCore Gateway fronting a mock Lambda, or a Slack MCP server.

---

## 4. Build plan

| Block | Work |
|---|---|
| 0. Setup  | AWS account + **enable Bedrock model access for Claude Sonnet 5**; `pip install strands-agents`; run the "hello agent" locally against Bedrock. |
| 1. Data + tools  | Create synthetic CSVs → SQLite. Write `query_orders()` and `get_part_impact()` as Strands `@tool` Python functions. Test the agent calling them locally. |
| 2. MCP  | Stand up an MCP server (filesystem/SQLite or a small custom one). Wire it into the Strands agent as an MCP tool. Verify the agent calls it. |
| 3. Workflow + Code Interpreter | Add the simulate step (Code Interpreter). Tune the system prompt so the agent reliably runs Detect→Enrich→Analyze→Simulate→Recommend. Force a **structured JSON output** for the risk brief. |
| 4. Deploy to AgentCore  | Package + deploy to AgentCore Runtime. Invoke remotely. Add short-term **Memory**. Confirm **Observability** traces appear in CloudWatch. |
| 5. Notify + polish  | Add the notify tool (mock Gateway/Lambda or Slack MCP). Capture 2–3 demo runs + screenshots of the trace. |
| Buffer | Slack. |

**Cut-if-tight order:** drop Notify (§5) first, then Memory. The core demo (Agent + Python tool + MCP + Code Interpreter + workflow, on AgentCore) is the must-have.

**Demo script:** paste a delay alert → watch the agent enrich via MCP, query orders, run the impact math, and emit a ranked action brief → show the CloudWatch trace of the tool calls → ask a follow-up to show Memory.

---

## 5. Finance variant (same skeleton, swap the data + tools)

### "Invoice Exception & Spend-Anomaly Triage Agent"

Given a batch of invoices/transactions, the agent runs the **same 6-step workflow**:

1. **Detect** — a new invoice batch arrives.
2. **Enrich** *(MCP)* — pulls the matching PO and the AP/spend policy doc from an MCP server.
3. **Analyze** *(Python tool)* — 3-way match (invoice ↔ PO ↔ receipt); flags mismatches.
4. **Simulate** *(Code Interpreter)* — statistical anomaly check (duplicates, out-of-band amounts, unusual vendors).
5. **Recommend** — approve / hold / escalate, with the reason.
6. **Notify** — routes exceptions to the right approver.

Because only the tools and data change — not the agent, MCP wiring, or runtime — building one and swapping to the other is the cleanest way to prove the platform generalizes across domains. If you have time for a "wow," build Supply Chain fully and stub the Finance swap to show reuse.

---

## 6. Model recommendation

**Use Claude Sonnet 5 on Amazon Bedrock.** It's the sweet spot for agentic tool-use and reasoning at **$2 / 1M input, $10 / 1M output** — currently the same price as the cheaper-tier Sonnet 4.6 was, so there's no reason to go older. Keeping the model on **Bedrock** means the entire POC lands on **one AWS bill**, which makes the cost story clean and matches Marvell's existing Bedrock footprint.

- Want it cheaper for heavy iteration? **Claude Haiku 4.5** at **$1 / $5** roughly halves model cost with minor quality loss for this workload.
- **Prompt caching** (0.1× on cache hits) cuts repeated-context cost hard once your system prompt/tool schemas stabilize.

*(Bedrock list prices track Anthropic's; confirm the exact number on the Bedrock pricing page for your region before you quote it upward.)*

---

## 7. Tentative AWS cost for the POC

The model tokens dominate; AgentCore infra is rounding error at POC scale. Estimates assume **Claude Sonnet 5 on Bedrock** and that you **develop locally on Strands** (free) and only deploy to AgentCore late.

### Model cost (the real driver)

Agent loops re-send growing context each step, so per *invocation* means the cumulative tokens across all steps.

| Testing intensity | Invocations | ~Input toks | ~Output toks | Sonnet 5 cost | Haiku 4.5 cost |
|---|---|---|---|---|---|
| Light | ~100 | 4M | 0.6M | ~**$14** | ~**$7** |
| Moderate (typical) | ~300 | 18M | 2.4M | ~**$60** | ~**$30** |
| Heavy iteration | ~500 | 40M | 5M | ~**$130** | ~**$65** |

### AgentCore + supporting infra (whole POC)

| Component | Basis | POC cost |
|---|---|---|
| AgentCore **Runtime** | $0.0895/vCPU-hr + $0.00945/GB-hr, active session only (~6 vCPU-hr of testing) | **< $2** |
| **Code Interpreter** | same compute shape, only when invoked | **< $1** |
| Short-term **Memory** | $0.25 / 1k events (a few hundred events) | **< $0.50** |
| **Gateway** (if used) | per 1k invocations | **< $0.10** |
| **Observability** | CloudWatch trace ingestion (likely within free tier) | **< $1** |
| **S3 / misc** | synthetic data | pennies |
| **Infra subtotal** | | **~$3–5** |

### Bottom line

| Model choice | Typical total POC cost | Worst-case (heavy iteration) |
|---|---|---|
| **Claude Sonnet 5** | **~$25–65** | ~$135 |
| **Claude Haiku 4.5** | **~$12–35** | ~$70 |

**Plan for roughly $25–65, hard cap well under ~$150.** This is a coffee-budget POC — the cost risk isn't the POC, it's forgetting to add TTLs and turn off idle compute *at scale later*.

### Keep it cheap

- Build and debug **locally on Strands** — no AgentCore charges until you deploy for the demo.
- Turn on **prompt caching** once prompts stabilize (0.1× on cache hits).
- Use **Haiku 4.5** while iterating; switch to **Sonnet 5** for the final demo runs.
- Set a **Budgets alert** at $50 so nothing surprises you.
- Set a **TTL on long-term Memory** if you enable it — unbounded memory is AgentCore's classic cost trap at scale (irrelevant at POC size, but build the habit).

---

## 8. Suggested next steps

1. Enable Bedrock access to Claude Sonnet 5 in your target region.
2. `pip install strands-agents strands-agents-tools` and get the local hello-agent running (Block 0).
3. Follow the build plan; ship the Supply Chain demo, stub the Finance swap if time allows.
4. After the POC, decide the real orchestration layer (Strands agent-loop vs. n8n graph vs. AgentCore-native) — the POC deliberately keeps the workflow inside Strands so this stays an open, low-cost decision.
