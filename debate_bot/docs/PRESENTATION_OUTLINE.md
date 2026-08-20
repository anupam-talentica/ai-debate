# Presentation Outline — Testing & Deploying an Agentic System

**Audience:** Mixed / leadership
**Length:** ~15 slides (grew from 10 after feedback — per-approach + deployment-options breakdown). Can be trimmed; see "Trimming options" at the end.
**Working title:** *"Beyond the Demo: Making an Agentic System Trustworthy and Resilient"*
**Grounded in:** the Multi-Agent Debate Bot (LangGraph + Claude — Pro / Con / Moderator)

**Core message:** Building the agent is the easy 20%. Proving it's correct (Testing) and
keeping it alive under failure (Deployment) is the other 80%.

---

## Theme / Branding (for slide generation)

Match the attached Talentica deck template:
- **Colors:** teal → green gradient background on title/section slides; **yellow** for
  key headline text; dark-grey body text on white for content slides.
- **Logo:** Talentica logo top-right on every slide.
- **Accent:** short green vertical bar to the left of each slide title (as in the "Agenda" slide).
- **Footer:** `Copyright © Talentica Software (I) Pvt Ltd. All rights reserved.` on content slides.
- **Title slide** style: big yellow title, subtitle, date, optional stat circles + award badges row.

---

# PART 0 — INTRODUCTION

## Slide 1 — Title & The Agentic System Under Test

- Hook: **"The demo worked. That was the easy part."**
- **Introduce the system under test — the debate agent graph** (this is the running example
  for the whole deck):
  - A LangGraph workflow of specialized Claude agents: **Pro → Con → Moderator**, over
    rounds (opening → rebuttal → closing → verdict).
  - Show the **graph diagram** (nodes + edges + shared state) so the audience has a concrete
    mental model before we talk about testing/deploying it.
  - One line on what makes it "agentic": multiple cooperating agents, shared state, streamed
    output, a decision at the end.
- Frame the two questions leadership cares about: *Can we trust its output? Will it stay up
  when something breaks?* → **Testing** and **Deployment**.

## Slide 2 — Why Agentic Systems Are Different (agenda + risk framing)

- Two properties that break the normal software playbook:
  - **Non-deterministic** — same input, different output each time → traditional pass/fail
    tests don't apply.
  - **Long-running & stateful** — a task is a *sequence of steps*, not one call → a crash
    loses real work, not just a request.
- Agenda: **Part 1 — Testing (trust)**, **Part 2 — Deployment (resilience)**.

---

# PART 1 — TESTING = EARNING TRUST

## Slide 3 — The Shift in Thinking: A 3-Step Framework
*(summary of `docs/EVALUATION_APPROACHES.md` — how testing an agentic system is different)*

The mindset change: you can't assert `==` on a probabilistic system. Instead, follow 3 steps:

- **Step 1 — Define the dimensions that matter *for this system*.** The dimensions are
  derived from what the agent is *for*. For the debate bot:
  - **Argument Quality** — on-topic, persuasive, rebuttals engage the opponent.
  - **Correctness & Robustness** — valid winner, all fields present, word-count caps, no crashes.
  - **Coherence / Debate Integrity** — closings reinforce earlier points; memory influences later debates.
  - **Performance & Streaming** — per-node latency, event ordering, completion events.
- **Step 2 — Split each dimension into deterministic vs. non-deterministic.**
  Some things have a right answer (is the winner "Pro" or "Con"?); some are judgments
  (is the argument persuasive?).
- **Step 3 — Route each to the right tool:**
  - **Deterministic → script / regex** (fast, free, exact — e.g. `winner ∈ {Pro, Con}`, word caps).
  - **Non-deterministic → LLM-as-a-judge**, scored against a **rubric**.
    - Briefly: a **rubric metric** is a named criterion (e.g. "rebuttal engagement") with an
      explicit scoring scale (1–5), graded by a **stronger** model than the one under test —
      so the system never grades itself. Turns a subjective quality into a trackable number.

## Slide 4 — The Framework Generalizes: Applying It to "Nexus Guard"
*(shows the thinking transfers to a different problem — `Nexus_Guard_Recreated.md`)*

Same 3 steps, different agentic system (an enterprise customer-ops agent network with
guardrails). The dimensions fall out of *its* purpose:

| Dimension | What it tests | Det. or Judge? |
|---|---|---|
| **Routing & loop integrity** | passes query across ≥3 agents; breaks infinite loops within 3 hops | Deterministic (hop counter / graph assertion) |
| **PII masking / safety** | Aadhaar, credit cards, API keys masked in every stream | Deterministic (regex/Presidio) **+** judge for "safety" |
| **Self-correction quality** | judge LLM gates on Relevance / Factuality / Safety, one correction loop | LLM-as-judge (rubric) |
| **Streaming performance** | P95 latency < 200 ms per chunk | Deterministic (timing) |
| **Cost & budget guardrails** | token/cost budget → graceful human-in-the-loop handoff | Deterministic (counter + threshold) |

Takeaway: **the dimensions change per system, but the 3-step method doesn't.**

## Slide 5 — We Validated the Same System 4 Ways (the trade-off)

We ran the *same* debate system, *same* dataset, *same* judge model through four tooling
approaches — the only variable is the harness. Present as **buy vs. build / cost vs.
capability**, not a tool list:

- **Build our own (pytest):** total control, zero cost, fully private — but we maintain it.
- **Hosted (LangSmith):** dashboards, history, free per-node traces — data leaves the machine.
- **Off-the-shelf (deepeval / promptfoo):** fast to adopt — but the abstraction can hide
  *what's actually measured*.
- One axis leadership feels immediately: **data privacy** (hosted = data leaves the building).
- Tee up: next four slides go one level into each.

## Slide 6 — Approach 1: Custom pytest + LLM-as-judge

- **What it is:** a small `evals/` harness on the existing pytest + Anthropic stack. No new deps.
- **How it works:** `run_debate(topic)` over a golden dataset → deterministic scorers
  (Python/regex) + an LLM-judge scorer (1–5 on 4 axes) → a scorecard (markdown + JSON).
- **Strengths:** zero dependency, fully offline, you own every metric and the judge prompt,
  trivial to run in CI (`python evals/run_evals.py`).
- **Cost:** you build and maintain the harness, dataset, and report yourself.
- **Role:** the **backbone / default CI gate** and the single source of scoring truth.

## Slide 7 — Approach 2: LangSmith (hosted)

- **What it is:** flip on a dependency that's already present — upload the dataset, define
  evaluators, turn on tracing.
- **How it works:** reuses the *same* scorers as Approach 1 but runs them on a hosted
  platform; LangGraph auto-emits per-node traces.
- **Strengths:** hosted dashboard for scores + traces, **free per-node latency/ordering**,
  versioned datasets and regression history over time.
- **Cost:** needs an account + network; **data leaves the machine** (don't point at sensitive data).
- **Role:** add when you need **history + performance monitoring**.

## Slide 8 — Approach 3: deepeval (G-Eval rubrics in pytest)

- **What it is:** an off-the-shelf eval library with built-in rubric metrics (G-Eval),
  runs natively inside pytest.
- **How it works — G-Eval, adapted to our debate example** *(re-draw the G-Eval algorithm
  figure using debate content instead of the news-summary example):*
  - **Task Introduction:** "You will be given one exchange from a debate. Rate it on one metric."
  - **Evaluation Criteria:** e.g. *Rebuttal Engagement (1–5)* — does the Con rebuttal address
    ≥1 specific point from the Pro opening?
  - **Evaluation Steps (Auto-CoT):** 1) read the Pro opening; 2) read the Con rebuttal and
    check which Pro points it addresses; 3) assign 1–5.
  - **Input Context:** the topic + Pro opening. **Input Target:** the Con rebuttal.
  - **G-Eval output:** probability-weighted 1–5 score (e.g. "Rebuttal Engagement: 4.2").
  - *(Replaces the Paul-Merson news-summary example in the original figure.)*
- **Strengths:** rich prebuilt rubric machinery, on-disk caching, less judge plumbing.
- **Cost:** new dependency; built-in metrics assume QA/RAG shapes and need adapting to a debate.

## Slide 9 — Approach 4: promptfoo (declarative YAML + CLI)

- **What it is:** off-the-shelf, config-driven eval — YAML test cases + a Python provider
  wrapping `run_debate`, run via a Node CLI.
- **How it works:** declare `llm-rubric` asserts (Claude grader) + `javascript` deterministic
  asserts (winner valid, word caps) per topic → HTML report grid.
- **Strengths:** declarative and readable, polished local HTML report, no pip dependency (Node).
- **Cost:** needs a Node toolchain; another tool's conventions to learn.
- **Role:** nice when you want **declarative config + a visual report**.

## Slide 10 — Testing: The Recommendation

- **Default:** Approach 1 (custom pytest) — zero-cost, offline, enforced on every release.
- **Add LangSmith** when you need regression history and per-node performance over time.
- **deepeval / promptfoo** are optional — proof the system can be scored by third-party
  tooling without forking the dataset.
- Bottom line: **subjective quality → an automatic, enforced release gate**
  *(e.g. winner-valid ≥ 90%, mean relevance ≥ 3.5).*

---

# PART 2 — DEPLOYMENT = SURVIVING FAILURE

## Slide 11 — Deployment Options: The Landscape

Lay out the choices before picking one:

- **Managed platform — LangSmith / LangGraph Platform:** hosted agent server, durable state
  and streaming handled for you. Fastest path; vendor lock-in + cost + **Enterprise license**
  for self-hosting the server.
- **Managed platform — Google ADK (Agent Development Kit):** Google's managed agent runtime /
  Vertex Agent Engine. Cloud-native, scales for you; ties you to GCP.
- **Self-hosted:** you run it (containers + your own orchestration). Full control and privacy;
  **you** must solve durability, streaming, and failover — which is what the next slides show.

Framing: managed = speed & convenience; self-hosted = control & privacy, at the cost of
building the resilience machinery yourself.

## Slide 12 — The Self-Hosting Challenge: What Breaks Without Redis

- A single-node demo glues **graph execution and the client's live stream into one process**.
  - If the user's connection drops, or the node handling their stream hiccups, **the live
    view dies** — even if the work is fine elsewhere.
  - With multiple nodes behind a load balancer, the node the user is *watching* may not be the
    node *doing the work* — there's no way to relay updates between them.
- **Redis (pub/sub) is the missing piece:** a channel per run decouples "who's streaming to
  the user" from "who's executing the agent." Any node can relay any run.
- (Pair it with durable state — Postgres checkpoints — so a dead *executor* can be resumed;
  Redis alone fixes streaming, not execution recovery.)

## Slide 13 — The Reference Architecture (official LangSmith, with Redis)

- Show the **official LangSmith / LangGraph Agent Server architecture diagram** including Redis.
- Walk the pieces at a conceptual level:
  - **Postgres** — durable run/thread state (checkpoints) → any node resumes from the last step.
  - **Redis** — pub/sub streaming per run → streaming decoupled from execution.
  - **Load balancer + N server nodes** — no single point of failure.
- Message: our self-hosted design is a **hand-rolled version of this proven pattern** — the
  same two building blocks (durable state + decoupled streaming) the official platform uses.

## Slide 14 — The Payoff: Watch It Survive a Crash *(optional demo slide)*

- The moment that sells it: **kill the node running a live debate — another node picks it up
  mid-sentence and finishes it.** The user never notices.
- Two failure types, both handled: *losing your screen* (Redis re-attach) vs. *losing the
  worker* (resume from Postgres checkpoint).

## Slide 15 — What Transfers to Every Agent We Build

- **Trust:** define dimensions → split deterministic vs. judge → gate releases automatically.
- **Resilience:** durable state + decoupled streaming (Redis) + failover.
- Land on: **"An agent isn't ready when it works — it's ready when it's *measurable* and
  *survivable*."**

---

## Trimming options (to get back toward 10 slides)

- Merge Slides 6–9 (four approaches) into **two** slides (2 approaches each) if depth allows.
- Fold Slide 14 (demo) into Slide 13.
- Drop Slide 4 (Nexus Guard) if the audience only cares about the debate system — but it's the
  strongest proof the *method* generalizes, so keep it if you can.

## Source docs (for detail / appendix / speaker notes)

- Testing framework & 4-way comparison — `docs/EVALUATION_APPROACHES.md`,
  `tests/EVAL_APPROACHES_4WAY_COMPARISON.md`, `tests/TESTS_OVERVIEW.md`
- Second problem statement (dimensions example) — `Nexus_Guard_Recreated.md`
- G-Eval figure to re-draw — `tests/deepeval_promptfoo/deepeval/metrics_g-eval_algorithm.png`
- Deployment architecture (self-hosted failover) — `deployment/TRD_ARCHITECTURE.md`
- Pre-deployment critical review — `docs/deployment/CRITICAL_REVIEW.md`
