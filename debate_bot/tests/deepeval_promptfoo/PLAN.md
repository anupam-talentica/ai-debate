# Approach C — deepeval / promptfoo

> **Status:** Plan only. No eval code committed yet.
> **Goal:** Use an off-the-shelf LLM-eval library with rich, prebuilt metrics (G-Eval rubrics,
> relevancy, faithfulness) and declarative test cases, wrapping the same `run_debate` seam. Two
> viable tools are scoped here — **deepeval** (pytest-native) and **promptfoo** (YAML + a Python
> provider). Pick one during implementation; deepeval is the default recommendation because it
> stays inside pytest.

---

## 1. Why this approach

- **Rich prebuilt metrics** — G-Eval rubrics, relevancy, faithfulness, etc., with less
  judge-prompt plumbing to write yourself.
- **Declarative test cases** — config-driven (promptfoo YAML) or concise pytest (deepeval).
- **Local reports** — promptfoo ships a nice local HTML report; deepeval integrates with pytest
  output.

Trade-offs: **adds a dependency** to install + maintain; built-in metrics assume RAG/QA shapes
and must be adapted to a multi-turn **debate transcript**; another tool's conventions to learn;
the abstraction can obscure exactly what is being measured. This is why the recommendation
(`docs/EVALUATION_APPROACHES.md §5`) treats C as **optional**, after A and B.

---

## 2. Target layout (lands in `tests/deepeval_promptfoo/`)

```
tests/deepeval_promptfoo/
├── __init__.py
├── eval_provider.py            # shared: wraps run_debate → returns the DebateState
├── deepeval/
│   ├── test_debate_deepeval.py # GEval rubrics as pytest tests
│   └── metrics.py              # relevance / rebuttal-engagement / moderator-soundness GEvals
├── promptfoo/
│   ├── promptfooconfig.yaml    # providers + tests + asserts
│   └── eval_provider.py        # python provider calling run_debate
└── README.md                   # which tool, setup, run
```

The dataset source of truth stays shared: reuse
`tests/custom_pytest/evals/datasets/topics.jsonl` (Approach A).

---

## 3. Option C1 — deepeval (recommended, pytest-native)

```python
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

relevance = GEval(
    name="Relevance",
    criteria="Does the Pro opening argue FOR the topic and stay on-topic?",
    evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
    model="claude-sonnet-5",           # judge model, stronger than Haiku under test
)

def test_debate_relevance():
    state = asyncio.run(run_debate("AI will replace software engineers"))
    tc = LLMTestCase(input=state["topic"], actual_output=state["pro_opening"])
    relevance.measure(tc)
    assert relevance.score >= 0.7
```

Add G-Eval metrics that map to this system's real dimensions:
- **relevance** — Pro/Con openings argue the correct side and stay on-topic.
- **rebuttal_engagement** — Con rebuttal actually engages ≥1 Pro point.
- **moderator_soundness** — the winner decision follows from the arguments.

Configure deepeval to use a **Claude** judge model (via its custom-model interface) so scoring
uses Sonnet/Opus, not the default provider.

Run:
```bash
cd debate_bot
pip install deepeval
deepeval test run tests/deepeval_promptfoo/deepeval/test_debate_deepeval.py
```

## 4. Option C2 — promptfoo (YAML + python provider)

`eval_provider.py`:
```python
import asyncio, json
from app import run_debate

def call_api(prompt, options, context):
    state = asyncio.run(run_debate(context["vars"]["topic"]))
    return {"output": json.dumps(state)}
```

`promptfooconfig.yaml`:
```yaml
providers:
  - id: python:eval_provider.py
tests:
  - vars: { topic: "AI will replace software engineers" }
    assert:
      - type: llm-rubric
        value: "The Pro opening argues FOR the topic and stays on-topic"
      - type: javascript
        value: "['Pro','Con'].includes(JSON.parse(output).winner)"
```

Run:
```bash
cd debate_bot/tests/deepeval_promptfoo/promptfoo
npx promptfoo eval        # then: npx promptfoo view   (local HTML report)
```

Point promptfoo's `llm-rubric` grader at a Claude model via its provider config.

---

## 5. Implementation steps (do NOT start yet)

1. **Prereq fix** — same import fixes as Approach A so `run_debate` imports cleanly.
2. **Pick one tool** (default: deepeval) and add it to `requirements.txt`
   (or a separate `requirements-eval.txt` to keep runtime deps lean).
3. Implement `eval_provider.py` wrapping `run_debate` (shared by both options).
4. Configure the tool's judge/grader to use a **Claude** model (`JUDGE_MODEL_NAME`).
5. Implement the G-Eval metrics (deepeval) or asserts (promptfoo) mapped to the 4 dimensions,
   reusing the shared dataset topics.
6. Do one run; confirm scores + report render.
7. Write `README.md`: chosen tool, install, run, and how to read the report.

## 6. Acceptance criteria

- The chosen tool runs `run_debate` over the shared topics and produces per-topic scores.
- At least the three debate-specific rubrics (relevance, rebuttal_engagement,
  moderator_soundness) are implemented and scored by a Claude judge.
- A local report (deepeval output or promptfoo HTML) is produced.
- The added dependency is isolated (its own requirements file or clearly marked) so it doesn't
  bloat the runtime image.

## 7. Notes

- **Metric-shape mismatch:** deepeval/promptfoo built-ins assume single-turn QA/RAG. Prefer
  **custom G-Eval / llm-rubric** metrics over generic relevancy/faithfulness so the criteria
  actually describe a debate transcript, not a retrieval answer.
- **Comparability:** keep deterministic checks (winner-valid, word caps) identical to Approach A
  (import them) so C's numbers can be compared against A and B.
