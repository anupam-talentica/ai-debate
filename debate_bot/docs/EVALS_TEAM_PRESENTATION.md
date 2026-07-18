# Evaluating Agentic Systems — Team Presentation

> **Audience:** the whole team — anyone building or reviewing an LLM/agentic system.
> **Goal:** (1) present **generic evaluation strategies** that apply to *any* agentic system,
> and (2) walk through **three concrete tooling options** we have already implemented against
> our Multi-Agent Debate System, ending with a recommendation.
>
> Companion deep-dive: [`EVALUATION_APPROACHES.md`](./EVALUATION_APPROACHES.md)

---

## Agenda

1. Why classic tests aren't enough for agentic systems
2. **Generic evaluation strategies** (portable to any agent — debate bot used only as example)
3. Option 1 — Custom pytest + LLM-as-judge
4. Option 2 — LangSmith
5. Option 3 — deepeval / promptfoo
6. Comparison matrix
7. Recommendation & rollout plan

---

## 1. Why classic tests aren't enough

Unit/integration tests with a **mocked LLM** prove the *plumbing*: the graph runs, fields get
populated, HTTP codes are right. They can **never** tell you whether the *behavior* is good:

- Is the output actually relevant, persuasive, correct?
- Did the agent *use* the context it was given (history, memory, tool results)?
- Does the final decision follow from the intermediate steps?
- Does free-text output parse reliably into the structured fields downstream code needs?

**Evals close that gap:** run the **real model** against a **curated dataset** and **score the
behavior** — with deterministic rules where possible, and an **LLM-as-judge** where judgment
is required.

> **Our system in one line:** `run_debate(topic)` returns the full `DebateState`
> (openings, rebuttals, closings, moderator summary, winner). That single call is the
> entire scorable surface — every approach below evaluates its output.

---

## 2. Generic evaluation strategies for ANY agentic system

These strategies are **system-agnostic**. The debate bot column is just *our* instantiation —
swap in your own agent's equivalents.

| # | Generic strategy | What it validates (any agentic system) | How it's scored | Debate bot example |
|---|---|---|---|---|
| 1 | **Reasoning / output quality** | Is the model's reasoning sound, relevant, and fit for purpose? The core "is it *good*?" question. | **LLM-as-judge** with an explicit 1–5 rubric | **Argument quality**: on-topic relevance, persuasiveness, whether the moderator's verdict follows from the arguments |
| 2 | **Structural correctness / output contract** | Does free-text output satisfy the schema/contract downstream code depends on? (valid enum values, required fields, length limits, parseability) | **Deterministic** Python/regex — cheap, exact, CI-friendly | `winner ∈ {"Pro","Con"}`, all 10 state fields non-empty, word-count caps (250/130/100), moderator's 3-part structure |
| 3 | **Context utilization / multi-turn coherence** | Does each step actually *use* prior turns, retrieved docs, or tool results — or does it ignore them and restate itself? | Hybrid: LLM-judge + string/reference checks | Does the rebuttal engage ≥1 opponent point? Does the closing reinforce earlier arguments (agents currently close "blind")? |
| 4 | **Trajectory / workflow evaluation** | Did the agent take the *right path* — correct node/tool sequence, no skipped or looping steps, correct terminal state? | Trace inspection (deterministic on event logs) | LangGraph node ordering; streaming emits every stage; `COMPLETE`/`ERROR` events present exactly once |
| 5 | **Memory & state persistence** | Does long-term memory measurably influence later behavior, and is state carried correctly across sessions? | Differential runs (with vs. without memory) + judge | Does `memory_context` from earlier debates influence later ones on related topics? |
| 6 | **Robustness / adversarial inputs** | How does the agent handle degenerate, ambiguous, or hostile inputs? (empty/one-word input, injection attempts, off-distribution topics) | Curated "weak-spot" dataset + strategies 1–2 | One-word topics; topics crafted to confuse the brittle winner parser; topics containing the literal words "Pro"/"Con" |
| 7 | **Performance & streaming** | Latency per step, end-to-end duration, event ordering, time-to-first-token | Instrumentation / tracing | Per-node latency via `stream_debate`; event order; total debate duration |
| 8 | **Judge–model separation** | Never let a model grade itself — judge with a *stronger, different* model than the one under test | Process rule, enforced via config | Debates run on **Haiku**; judge is **Sonnet/Opus** via a separate `JUDGE_MODEL_NAME` env var |
| 9 | **Golden dataset + regression tracking** | A versioned dataset of representative + adversarial cases, re-run on every change to catch drift/regressions | Dataset file or hosted dataset store; score deltas over time | `topics.jsonl` (~10 topics incl. weak-spot triggers); LangSmith versioned datasets |
| 10 | **Human-in-the-loop calibration** | Are the judge's scores trustworthy? Periodically spot-check judge output against human ratings and tune the rubric | Manual review of a sample; measure agreement | Team spot-checks a sample of judged debates each iteration; rubric adjusted where judge and humans disagree |

### The three scoring mechanisms behind all of these

| Mechanism | When to use | Cost / reliability |
|---|---|---|
| **Deterministic rules** (regex, schema, counts) | Anything with an objective answer | Free, exact, run on every commit |
| **LLM-as-judge** (rubric-driven) | Subjective quality: reasoning, relevance, tone | Costs API calls; needs a stronger judge model + calibration (#10) |
| **Trace/telemetry inspection** | Path, ordering, latency | Free once instrumented (or free via tracing platforms) |

**Rule of thumb:** score deterministically wherever possible; spend judge calls only where
judgment is genuinely required; and design the dataset around your system's *known weak spots*,
not just happy paths.

---

## 3. Option 1 — Custom pytest + LLM-as-judge

*Build a small harness on the stack we already have. Zero new dependencies.*

**Implemented at:** `tests/custom_pytest/evals/`

```
tests/custom_pytest/evals/
├── datasets/topics.jsonl        # golden topics incl. weak-spot triggers   (#9)
├── scorers/deterministic.py     # winner-valid, word caps, structure       (#2)
├── scorers/llm_judge.py         # Claude judge → 1–5 rubric scores         (#1, #3)
├── run_evals.py                 # run_debate() over dataset → scorecard
└── report.py / results.json     # aggregate scorecard output
```

**How it works:** loop over the dataset → `run_debate(topic)` → deterministic scorer +
judge scorer → aggregate into a markdown/JSON scorecard.

- ✅ Zero new dependencies — reuses pytest + `langchain-anthropic`
- ✅ Full control and transparency: you write every rubric, see every judge call, know the exact cost
- ✅ Fully local (only needs `ANTHROPIC_API_KEY`); trivially demoable — one command prints a scorecard
- ❌ You build **and maintain** the harness, dataset store, and reporting yourself
- ❌ No hosted dashboard; per-node tracing must be hand-instrumented

---

## 4. Option 2 — LangSmith

*The dependency is already in `requirements.txt` — it's just dormant. Turn it on.*

**Implemented at:** `tests/lang_smith/` (`upload_dataset.py`, `evaluators.py`, `run_eval.py`)

**How it works:** set `LANGSMITH_API_KEY` + `LANGCHAIN_TRACING_V2=true`, upload the topics
dataset, register evaluator functions (plain Python returning `{"key", "score"}`), and call
`evaluate(...)`. Scores and **per-node LangGraph traces** appear in the hosted UI.

- ✅ Already a dependency — no install
- ✅ Hosted dashboard: score history, dataset versioning, regression tracking over time (#9)
- ✅ **Per-node tracing for free** — the performance/trajectory strategies (#4, #7) come with zero instrumentation, because LangGraph auto-emits traces
- ❌ Needs an account, API key, and network — **data leaves your machine**
- ❌ Another hosted UI and concept set to learn; less portable for self-contained demos

---

## 5. Option 3 — deepeval / promptfoo

*Purpose-built eval libraries with rich prebuilt metrics.*

**Implemented at:** `tests/deepeval_promptfoo/` (`deepeval/` with G-Eval metrics + pytest tests;
`promptfoo/` with `promptfooconfig.yaml` + Python provider wrapping `run_debate`)

**How it works:**
- **deepeval** — pytest-native; define custom rubrics with `GEval`, assert `metric.score >= threshold`
- **promptfoo** — declarative YAML test cases with `llm-rubric` and `javascript` assertions; a Python provider adapts `run_debate` output; generates a local HTML report

- ✅ Rich prebuilt metrics (relevancy, faithfulness, G-Eval rubrics) — less judge-prompt plumbing (#1)
- ✅ Declarative test cases; promptfoo's local HTML report is a nice shareable artifact
- ❌ **New dependency** to add and maintain
- ❌ Built-in metrics assume RAG/Q&A shapes — need adapting to a multi-turn debate transcript; abstractions can obscure what's actually measured

---

## 6. Comparison matrix

Rated **🟡 Average · 🟢 Good · ⭐ Best** per parameter.

| Parameter | 1 · Custom pytest | 2 · LangSmith | 3 · deepeval/promptfoo |
|---|---|---|---|
| No new dependency | ⭐ zero new deps | ⭐ already in requirements | 🟡 adds a library |
| Setup effort | 🟢 write a small harness | 🟢 keys + wiring | 🟡 install + adapt metrics |
| Learning curve | ⭐ plain Python/pytest | 🟡 new hosted UI + concepts | 🟡 tool-specific DSL/metrics |
| LLM-as-judge support | 🟢 you write the prompt | 🟢 custom evaluators | ⭐ built-in G-Eval/rubrics |
| Deterministic assertions | ⭐ full control | 🟢 custom fns | 🟢 js/python asserts |
| Tracing / dashboard / viz | 🟡 build your own scorecard | ⭐ hosted traces + charts | 🟢 promptfoo local report |
| Per-node performance metrics | 🟡 hand-instrument | ⭐ free via LangGraph traces | 🟡 not native |
| CI integration | ⭐ it *is* pytest | 🟢 CLI/SDK in CI | 🟢 CLI in CI |
| Cost control / transparency | ⭐ every call is yours | 🟢 visible in UI | 🟡 metrics may fan out calls |
| Dataset management | 🟡 a jsonl file you manage | ⭐ versioned datasets | 🟢 YAML/code test cases |
| Data privacy (stays local) | ⭐ fully local | 🟡 data sent to LangSmith | 🟢 mostly local (judge calls aside) |
| Portability / demo | ⭐ self-contained | 🟡 needs account | 🟢 self-contained but extra dep |
| Maintenance burden | 🟡 you own the harness | ⭐ vendor-maintained | 🟢 vendor-maintained |

---

## 7. Recommendation

**Phased hybrid, starting with Option 1.**

1. **Start with Option 1 (custom pytest + LLM-judge).** Zero dependencies, fully
   self-contained, covers strategies #1–#3, #6, #8–#9 out of the box, and forces clarity —
   you write the exact rubric and see every judge call. One command produces a scorecard.

2. **Layer Option 2 (LangSmith) next** for what a hand-rolled harness is worst at:
   tracing, dashboards, and regression tracking over time (#4, #7, #9). It's already a
   dependency; reuse the same dataset and judge logic — only the runner changes.

3. **Treat Option 3 as optional.** Reach for deepeval/promptfoo only if the team wants
   off-the-shelf metrics and accepts a new dependency plus the work of adapting Q&A-shaped
   metrics to a multi-turn transcript.

**Key takeaway for any project:** the *strategies* in §2 are the durable part. Tools come
and go — pick whichever fits your constraints (privacy, dashboards, dependencies) — but every
serious agentic system needs: deterministic contract checks, a rubric-driven judge that is
**not** the model under test, a golden dataset aimed at known weak spots, trajectory/latency
tracing, and periodic human calibration of the judge.

---

## Appendix — Quick start per option

```bash
# Option 1 — custom harness
python tests/custom_pytest/evals/run_evals.py

# Option 2 — LangSmith (needs LANGSMITH_API_KEY)
python tests/lang_smith/upload_dataset.py && python tests/lang_smith/run_eval.py

# Option 3a — deepeval (pytest-native)
pytest tests/deepeval_promptfoo/deepeval/ -v

# Option 3b — promptfoo (needs npx)
npx promptfoo eval -c tests/deepeval_promptfoo/promptfoo/promptfooconfig.yaml
```

- Judge-model rule: debates run on `claude-haiku-4-5-20251001`; judge via `JUDGE_MODEL_NAME`
  (Sonnet/Opus recommended).
- Rough cost: `N topics × (1 debate on Haiku + ~1 judge call on the stronger model)` —
  a 20-topic run is inexpensive.
- Full details, code sketches, and known weak-spot list: [`EVALUATION_APPROACHES.md`](./EVALUATION_APPROACHES.md)
