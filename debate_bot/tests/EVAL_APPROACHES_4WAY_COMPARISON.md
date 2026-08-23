# Debate Bot — 4-way evaluation approach comparison

Four ways to evaluate the *same* debate system, all implemented in this repo.
This doc analyzes each and compares them head-to-head. Deep dives live next to the
code:

| # | Approach | Folder | Deep-dive doc |
|---|---|---|---|
| **A** | Custom pytest + LLM-as-judge harness | [custom_pytest/](custom_pytest/) | [PLAN.md](custom_pytest/PLAN.md) |
| **B** | Hosted LangSmith evaluation | [lang_smith/](lang_smith/) | [LANGSMITH_EVALS_LEARNING.md](lang_smith/LANGSMITH_EVALS_LEARNING.md) |
| **C1** | deepeval (off-the-shelf, pytest-native) | [deepeval_promptfoo/deepeval/](deepeval_promptfoo/deepeval/) | [learning_deepval.md](deepeval_promptfoo/learning_deepval.md) |
| **C2** | promptfoo (off-the-shelf, YAML/CLI) | [deepeval_promptfoo/promptfoo/](deepeval_promptfoo/promptfoo/) | [Learning_promptfoo.md](deepeval_promptfoo/Learning_promptfoo.md) |

## The one thing they all share

Every approach measures the **same system** over the **same inputs**, graded by the
**same judge model** — only the *harness* differs. That's what makes the four
comparable rather than four unrelated test suites.

```
        topics.jsonl (15 golden topics + weak-spot traps)   ← ONE dataset (source of truth)
                              │
                    app.run_debate(topic)                    ← ONE system under test
                              │
              claude-haiku-4-5 debates                       ← model UNDER test
              claude-sonnet-5 judges (JUDGE_MODEL_NAME)       ← STRONGER judge, never itself
                              │
   ┌──────────────┬──────────┴───────────┬─────────────────┐
   A              B                       C1                C2
 pytest      LangSmith                 deepeval          promptfoo
 harness      (hosted)                 (GEval)           (YAML)
```

The dataset (`custom_pytest/evals/datasets/topics.jsonl`) is deliberately seeded
with **weak-spot traps** so every harness has teeth:
- `winner-trap` ("**Pro** athletes are overpaid") — stresses the brittle winner
  parser in `moderator.py:40-53`.
- `con-trap` ("**Con** artists…") — stresses the fallback winner scan.
- `one-word` ("Pineapple") — degenerate topic, stresses relevance.
- `opening-decisive` / `closing-ref` / `rebuttal-chain` — stress the graph's
  information-flow quirks (moderator only sees closings; closings get no transcript).

## How each approach is wired (what the code actually does)

### A — Custom pytest harness (`custom_pytest/`)
The **reference implementation** and the source of truth for scoring logic.
- **Seam:** imports `app.run_debate` directly.
- **Scorers it owns:**
  - [deterministic.py](custom_pytest/evals/scorers/deterministic.py) — pure functions
    over the final state: `winner_valid`, `all_fields`, `opening/rebuttal/closing_wc_ok`
    (word caps from `prompts.py`), `mod_3part`, plus raw word counts. Free, no LLM.
  - [llm_judge.py](custom_pytest/evals/scorers/llm_judge.py) — a Claude judge returning
    **1–5** scores on **4 axes** (relevance, persuasiveness, rebuttal_engagement,
    moderator_soundness). Defensive JSON parsing (strip fences, one retry) and
    **never raises** — `ok=False` degrades gracefully.
- **Runner + report:** [run_evals.py](custom_pytest/evals/run_evals.py) drives the
  dataset; [report.py](custom_pytest/evals/report.py) emits a narrative
  **TEST_REPORT.md** (objective / environment / per-case rationale / defect log /
  conclusion) + **results.json** for diffing.
- **CI gate:** [test_evals.py](custom_pytest/evals/test_evals.py) — `-m eval`,
  skips without an API key; asserts `winner_valid ≥ 90%` and mean relevance `≥ 3.5`.
- **Also the home of the unit tests** (`core/`, `unit_tests/` — ~63 tests with mocked
  LLMs), so Approach A spans both *deterministic unit testing* and *behavioral evals*.

### B — Hosted LangSmith (`lang_smith/`)
Same scorers as A, but on a **hosted platform**.
- **Reuses A's logic verbatim:** [evaluators.py](lang_smith/evaluators.py) *imports*
  `score_deterministic` and `score_quality` from A — there is exactly one
  implementation, so B's numbers are directly comparable to A's.
- **Dataset uploaded, not read:** [upload_dataset.py](lang_smith/upload_dataset.py)
  pushes `topics.jsonl` into a server-side `debate-topics` dataset, **idempotent**
  (upserts by stable `id`).
- **Runner:** [run_eval.py](lang_smith/run_eval.py) calls `aevaluate(target, data,
  evaluators)`; `max_concurrency=1` because the graph/memory store is shared,
  module-level, and not thread-safe.
- **Free bonus:** `LANGCHAIN_TRACING_V2=true` → every LangGraph node auto-emits a
  trace, so **per-node latency + event ordering** (the performance dimension) appear
  in the dashboard with zero instrumentation. Results are versioned for regression
  tracking (see `result/*.csv`).

### C1 — deepeval (`deepeval_promptfoo/deepeval/`)
Off-the-shelf library, **pytest-native**.
- **Seam:** its own [eval_provider.py](deepeval_promptfoo/eval_provider.py) wraps
  `run_debate` and adds an **on-disk debate cache** (keyed on `MODEL_NAME:topic`),
  so reruns skip regeneration (65s→28s).
- **Own metrics, not A's:** 3 `GEval` rubrics in
  [metrics.py](deepeval_promptfoo/deepeval/metrics.py) — relevance,
  rebuttal_engagement, moderator_soundness — scored **0–1** with a **0.7 threshold**.
  Custom rubrics, because deepeval's built-in relevancy/faithfulness assume QA/RAG,
  not a debate transcript.
- **Judge adapter:** [judge.py](deepeval_promptfoo/deepeval/judge.py) subclasses
  `DeepEvalBaseLLM` to point deepeval (which defaults to OpenAI) at Claude.
- **Runner:** parametrized pytest grid (topics × rubrics), `-m eval`.

### C2 — promptfoo (`deepeval_promptfoo/promptfoo/`)
Off-the-shelf, **declarative YAML + Node CLI**.
- **Seam:** a Python provider ([eval_provider.py](deepeval_promptfoo/promptfoo/eval_provider.py))
  — `call_api` drives the graph from `context.vars` and returns state as JSON.
- **Rubric in config:** [promptfooconfig.yaml](deepeval_promptfoo/promptfoo/promptfooconfig.yaml)
  declares 3 `llm-rubric` asserts (Claude grader via `options.provider`) + 3
  `javascript` deterministic checks (winner-valid, word caps), with `transform`
  focusing each rubric on the right slice.
- **Report:** `npx promptfoo view` → HTML grid (topics × asserts), stored for diffing.

## Side-by-side matrix

| Dimension | A — pytest | B — LangSmith | C1 — deepeval | C2 — promptfoo |
|---|---|---|---|---|
| New dependency | **none** (reuses stack) | `langsmith` (already present) | `deepeval` (`requirements-eval.txt`) | `npx` (Node, no pip) |
| Definition style | Python functions | Python adapters over A | `GEval(criteria=…)` Python | YAML asserts |
| Runs inside | pytest | LangSmith CLI/SDK | pytest | promptfoo CLI |
| Offline? | ✅ fully | ❌ sends data to cloud | ✅ | ✅ |
| Scoring logic | **owns it** | **imports A's** | **own** GEval rubrics | **own** YAML rubrics |
| Judge scale | 1–5, **4 axes** | 1–5, 4 axes (= A) | 0–1, **3 rubrics**, threshold | pass/fail, 3 rubrics |
| Deterministic checks | ✅ Python | ✅ (A's, as 0/1) | ➖ (rubrics only by default) | ✅ JS asserts |
| Judge override | native (ChatAnthropic) | native (A's judge) | `DeepEvalBaseLLM` subclass | `options.provider` |
| Debate caching | in-run only | in-run only | ✅ **on-disk** cache | ✅ (shares C's cache) |
| Report | narrative MD + JSON | **hosted dashboard** | pytest + `.deepeval/` | **HTML grid** |
| Traces / latency | ✖ (manual) | ✅ **free** per-node | ✖ | ✖ |
| Regression history | JSON diff (manual) | ✅ **versioned, hosted** | ✖ | stored runs |
| CI fit | ✅ excellent | ⚠️ needs key + network | ✅ good | ⚠️ needs Node |
| Data privacy | ✅ stays local | ❌ leaves machine | ✅ local | ✅ local |
| Best at | control + zero-dep CI gate | tracing, dashboards, regression | rich prebuilt rubrics in pytest | declarative config + visual report |

## Trade-off axes (how to reason about the choice)

- **Control ↔ convenience.** A gives total control (you write every metric and the
  judge prompt) at the cost of writing it all. C1/C2 give prebuilt rubric machinery
  for less plumbing, but the abstraction can obscure exactly what's measured. B sits
  in the middle — A's logic, someone else's platform.
- **Offline ↔ hosted.** A, C1, C2 run fully locally (a reviewer runs one command).
  B ships inputs/outputs/traces to LangSmith — that's the price of versioning,
  dashboards, and free traces. Don't point B at sensitive data.
- **Dependency weight.** A adds nothing. B leans on an already-present dep. C1 is
  isolated in `requirements-eval.txt` (out of the Docker image). C2 needs a Node
  toolchain but no pip.
- **What "a score" means.** A/B produce fine-grained **1–5** scores on 4 axes (good
  for tracking drift); C1 produces **0–1 GEval** scores with a pass/threshold; C2
  produces **pass/fail**. A/B carry an extra `persuasiveness` axis the C rubrics drop.

## Recommendation (as reflected in the code)

1. **A is the backbone** — implemented, zero-dep, offline, and the single source of
   scoring truth. Use it as the default CI gate and the reviewer-facing report.
2. **B when you need history & traces** — turn it on for regression tracking over
   time and free per-node LangGraph latency; it reuses A's exact scorers, so numbers
   stay comparable.
3. **C is optional / illustrative** — deepeval (C1) is the pick if you want
   off-the-shelf rubric metrics *inside pytest*; promptfoo (C2) if you want a
   declarative config and a polished HTML report. Both prove the system can be scored
   by third-party tooling without forking the dataset or the seam.

Because all four sit on one dataset, one seam, and one judge model, you can run any
subset and trust they're measuring the same thing — the harness is the only variable.
