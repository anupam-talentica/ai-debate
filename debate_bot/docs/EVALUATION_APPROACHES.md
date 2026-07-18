# Evaluating the Debate Bot — Three Approaches

> A learning + decision document. It explains **how to use evals to test this agentic
> application**, walks through **three concrete approaches** implemented against *this*
> codebase, compares them on a rated matrix, and ends with a recommendation.
> No eval code is committed yet — pick an approach first, then we build it.

---

## 1. Why evals (and why the current tests aren't enough)

The existing suite in `tests/` **mocks the LLM** (`conftest.py` `mock_llm` returns the fixed
string `"Mock argument text."`). That's correct for what it does — it proves the LangGraph
plumbing runs, fields are populated, and HTTP status codes are right. But it can **never**
tell you:

- Are the Pro/Con arguments actually *on-topic* and *persuasive*?
- Does the moderator's winner decision follow from the arguments?
- Does the winner string actually get parsed correctly out of free text?
- Do rebuttals engage the opponent, or just restate the opening?

**Evals** answer those. An eval runs the **real** model against a **dataset** of topics and
**scores the behavior** — deterministically (rules) and/or with an LLM-as-judge.

The single integration point every approach below uses:

```python
# app.py:14-31 — returns the full DebateState dict for one topic
final_state = await run_debate(topic)
# final_state = {topic, round, pro_opening, con_opening, pro_rebuttal,
#                con_rebuttal, pro_closing, con_closing,
#                moderator_summary, winner, memory_context}
```

That one call is the whole scorable surface. The streaming seam
`DebateService.stream_debate` (`src/api/services/debate_service.py:52-127`) is used for the
performance/streaming dimension.

---

## 2. What we evaluate — 4 dimensions mapped to concrete metrics

| Dimension | Concrete metrics for THIS system | How it's scored |
|---|---|---|
| **Argument quality** | on-topic relevance; persuasiveness; rebuttal actually engages ≥1 opponent point; moderator justification is sound | **LLM-as-judge** rubric (1–5), using a *stronger* Claude model than the one under test |
| **Correctness & robustness** | `winner ∈ {"Pro","Con"}`; all 10 fields non-empty; word-count caps honored (250 / 130 / 100); moderator 3-part structure present; **winner-parser success rate** | Deterministic Python / regex |
| **Coherence / debate integrity** | rebuttal references the opponent; closing reinforces earlier points; memory context measurably influences later debates | Hybrid (LLM-judge + string checks) |
| **Performance & streaming** | per-node latency; event ordering; `COMPLETE`/`ERROR` events present; end-to-end duration | Instrument `stream_debate`, time nodes |

**Judge-model rule:** the debate runs on `claude-haiku-4-5-20251001` (default `MODEL_NAME`).
Judge with a **stronger** model (e.g. Sonnet or Opus) so a model isn't grading itself.
Set the judge model via a separate env var (e.g. `JUDGE_MODEL_NAME`).

### Prime eval targets (known weak spots in the code)

These are the places most likely to fail an eval — design your dataset to hit them:

1. **Brittle winner parser** — `src/agents/moderator.py:40-53` extracts the winner by string
   matching `"winner:"` / `"winner is"` with a fallback scan for a bare `"Pro"`/`"Con"`
   token. It can return `""` or noise (e.g. `"Pro debater's"`). → *correctness* metric.
2. **Moderator sees only closings** — `moderator_decision` is fed `pro_closing` + `con_closing`
   only, not openings/rebuttals. → *coherence* metric.
3. **Closings get no transcript** — `PRO_CLOSING`/`CON_CLOSING` receive only the memory block,
   so the model closes "blind." → *coherence* metric ("does the closing reinforce prior points?").
4. **Con rebuttal targets Pro's *opening***, not Pro's rebuttal (`CON_REBUTTAL` in
   `src/core/prompts.py`). → *coherence* metric.
5. **Word-count caps** (`~200/250`, `~100/130`, `~75/100` words) in `prompts.py` are directly
   checkable → *correctness* metric.

---

## 3. The three approaches

Each approach is shown as it would look **against this repo**.

### Approach A — Custom pytest + LLM-as-judge harness (no new dependencies)

Build a small `evals/` package that reuses the existing pytest + `langchain-anthropic` stack.
Runs fully offline (just needs `ANTHROPIC_API_KEY`), prints/writes a scorecard.

```
debate_bot/evals/
├── datasets/topics.jsonl        # golden topics, incl. the weak-spot triggers
├── scorers/deterministic.py     # winner-valid, word caps, structure, all-fields
├── scorers/llm_judge.py         # Claude judge → 1–5 rubric scores
└── run_evals.py                 # run_debate() over dataset → aggregate scorecard
```

`run_evals.py` (sketch):

```python
import asyncio, json
from app import run_debate
from evals.scorers.deterministic import score_deterministic
from evals.scorers.llm_judge import score_quality

async def main():
    topics = [json.loads(l) for l in open("evals/datasets/topics.jsonl")]
    rows = []
    for t in topics:
        state = await run_debate(t["topic"])
        det = score_deterministic(state)              # dict of bool/number
        judge = await score_quality(state)            # dict of 1–5 scores
        rows.append({**t, **det, **judge})
    print_scorecard(rows)   # markdown table + averages, write JSON

asyncio.run(main())
```

`scorers/deterministic.py` (sketch — targets the real weak spots):

```python
def score_deterministic(s: dict) -> dict:
    return {
        "winner_valid":  s["winner"] in ("Pro", "Con"),      # moderator.py:40-53
        "all_fields":    all(s[f] for f in ARG_FIELDS),
        "opening_wc_ok": word_count(s["pro_opening"]) <= 250, # prompts.py cap
        "mod_3part":     has_pro_point_con_point_and_winner(s["moderator_summary"]),
    }
```

`scorers/llm_judge.py` (sketch):

```python
JUDGE = ChatAnthropic(model=os.getenv("JUDGE_MODEL_NAME", "claude-sonnet-5"))

async def score_quality(s: dict) -> dict:
    prompt = f'''Score this debate 1-5 on each axis. Return JSON.
    Topic: {s["topic"]}
    Pro opening: {s["pro_opening"]}
    Con opening: {s["con_opening"]}
    Con rebuttal (should engage Pro): {s["con_rebuttal"]}
    Moderator decision: {s["moderator_summary"]}
    Axes: relevance, persuasiveness, rebuttal_engagement, moderator_soundness'''
    resp = await JUDGE.ainvoke(prompt)
    return json.loads(resp.content)
```

**Pros:** zero new deps; reuses pytest patterns; fully portable; trivial to demo/explain;
you control every metric and the exact judge prompt; cheap to reason about cost.
**Cons:** you build (and maintain) the harness, dataset store, and scorecard yourself; no
hosted dashboard; per-node tracing must be hand-instrumented.

---

### Approach B — LangSmith (dependency already present, just dormant)

`langsmith>=0.1` is **already in `requirements.txt`** but wired nowhere. Turn it on: set
`LANGSMITH_API_KEY` + `LANGCHAIN_TRACING_V2=true`, upload a dataset, define evaluators.

```python
from langsmith import Client
from langsmith.evaluation import evaluate

# 1) one-time: create dataset from your topics
client = Client()
# 2) evaluators are plain functions returning {"key","score"}
def winner_valid(run, example):
    return {"key": "winner_valid",
            "score": run.outputs["winner"] in ("Pro", "Con")}

def arg_quality(run, example):    # LLM-judge evaluator
    ...  # call a strong Claude model, return 1–5

evaluate(
    lambda inputs: asyncio.run(run_debate(inputs["topic"])),
    data="debate-topics",
    evaluators=[winner_valid, arg_quality],
)
# Scores + per-node LangGraph traces appear in the LangSmith UI
```

Because LangGraph auto-emits traces to LangSmith, the **Performance/streaming** dimension
(per-node latency, ordering) comes essentially for free in the trace view.

**Pros:** already a dependency (no install); hosted dashboard for scores + traces; dataset
versioning and run history built in; **per-node LangGraph tracing for free**; good for
tracking quality over time / regressions.
**Cons:** needs a LangSmith account + API key + network (data leaves your machine); the UI is
another system to learn; less portable for a self-contained assignment submission.

---

### Approach C — deepeval / promptfoo (add a purpose-built eval library)

Off-the-shelf LLM-eval tooling with rich built-in metrics.

**promptfoo** (YAML + a Python provider wrapping `run_debate`):

```yaml
providers:
  - id: python:eval_provider.py    # calls run_debate, returns the state
tests:
  - vars: { topic: "AI will replace software engineers" }
    assert:
      - type: llm-rubric
        value: "The Pro opening argues FOR the topic and stays on-topic"
      - type: javascript
        value: "['Pro','Con'].includes(JSON.parse(output).winner)"
```

**deepeval** (pytest-native, custom rubric via `GEval`):

```python
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase

relevance = GEval(
    name="Relevance",
    criteria="Does the Pro opening argue for the topic and stay on-topic?",
    evaluation_params=[...],
)
def test_debate():
    state = asyncio.run(run_debate("AI will replace software engineers"))
    relevance.measure(LLMTestCase(input=state["topic"], actual_output=state["pro_opening"]))
    assert relevance.score >= 0.7
```

**Pros:** rich prebuilt metrics (relevancy, faithfulness, G-Eval rubrics); config/declarative
test cases; promptfoo has a nice local HTML report; less judge-prompt plumbing to write.
**Cons:** **new dependency** to add + maintain; built-in metrics assume RAG/QA shapes and need
adapting to a multi-turn debate transcript; another tool's conventions to learn; can obscure
what's actually being measured.

---

## 4. Comparison matrix

Rated **🟡 Average · 🟢 Good · ⭐ Best** per parameter.

| Parameter | A · Custom pytest | B · LangSmith | C · deepeval/promptfoo |
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
| Portability / assignment demo | ⭐ self-contained | 🟡 needs account | 🟢 self-contained but extra dep |
| Maintenance burden | 🟡 you own the harness | ⭐ vendor-maintained | 🟢 vendor-maintained |

---

## 5. Recommendation

**Phased hybrid, starting with Approach A.**

1. **Start with A (custom pytest + LLM-judge).** Zero new dependencies, fully self-contained,
   trivial to run and explain, and it covers all four dimensions. For an assignment it's the
   most demonstrable — a reviewer runs `python evals/run_evals.py` and sees a scorecard.
   It also forces clarity: you write the exact rubric and see every judge call.

2. **Layer B (LangSmith) next** for tracing, dashboards, and regression tracking over time —
   it's *already a dependency*, and it gives you per-node performance metrics for free. Reuse
   the same dataset and the same judge logic; only the runner changes.

3. **Treat C as optional** — reach for deepeval/promptfoo only if you want off-the-shelf
   metrics and are willing to add + maintain a dependency and adapt its QA-shaped metrics to a
   debate transcript.

**If you only do one thing:** build Approach A with a ~10-topic dataset that includes the
weak-spot triggers (a topic likely to confuse the winner parser, a one-word topic, a topic
where a good closing *must* reference the opening). That single harness surfaces the real
behavior gaps this system has today.

---

## Appendix

- **The eval seam:** `run_debate(topic)` (`app.py:14-31`) is the one function all three
  approaches call. It returns the complete `DebateState` (`src/core/state.py:4-15`).
- **Judge model + rough cost:** run debates on Haiku, judge with Sonnet/Opus. Cost ≈
  `N topics × (1 debate on Haiku + ~1 judge call on the stronger model)`. A 20-topic run is
  inexpensive; keep the judge prompt tight.
- **Baseline caveat:** before trusting the current suite as a baseline, fix the invalid-syntax
  lines `from app import src.core.graph as graph` in `tests/test_edge_cases.py:136` and
  `tests/test_errors.py:66`, and note agent-patch tests target `agents.pro` not `src.agents.pro`.
