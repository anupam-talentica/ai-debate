# Approach C — deepeval / promptfoo

Off-the-shelf LLM-eval libraries scoring the debate system with prebuilt rubric
metrics, wrapping the **same** `run_debate` seam and dataset as Approach A
(`tests/custom_pytest/evals/`).

**Chosen tool: deepeval** (pytest-native, stays inside our existing stack).
**promptfoo** is provided as a documented alternative (YAML + a Python provider,
ships a nice local HTML report).

Both options are graded by a **Claude** judge (`JUDGE_MODEL_NAME`, default
`claude-sonnet-5`) — a stronger model than the Haiku under test, so a model never
grades itself.

## Layout

```
tests/deepeval_promptfoo/
├── eval_provider.py            # shared: run_debate wrapper + shared dataset loader
├── deepeval/                   # Option C1 (recommended)
│   ├── judge.py                # Claude wired into deepeval's custom-model interface
│   ├── metrics.py              # 3 GEval rubrics (relevance / rebuttal / moderator)
│   └── test_debate_deepeval.py # GEval rubrics as pytest tests
├── promptfoo/                  # Option C2 (alternative)
│   ├── eval_provider.py        # python provider calling run_debate
│   └── promptfooconfig.yaml    # providers + tests + asserts (Claude grader)
└── README.md
```

The three debate-specific rubrics map to this system's real dimensions:

| Rubric                 | Grades                                                  |
| ---------------------- | ------------------------------------------------------- |
| `relevance`            | Pro opening argues FOR the topic and stays on-topic     |
| `rebuttal_engagement`  | Con rebuttal engages ≥1 specific point from Pro         |
| `moderator_soundness`  | winner decision is justified by the arguments           |

Built-in relevancy/faithfulness metrics assume single-turn QA/RAG, so we use
**custom GEval / llm-rubric** metrics whose criteria describe a debate
transcript. The deterministic checks (winner-valid, word caps) mirror Approach A
so C's numbers stay comparable to A and B.

## Setup

The eval dependency is isolated from the runtime image:

```bash
cd debate_bot
pip install -r requirements-eval.txt      # deepeval (promptfoo is npx, no pip)
export ANTHROPIC_API_KEY=...              # required
export JUDGE_MODEL_NAME=claude-sonnet-5   # optional; this is the default
```

## Option C1 — deepeval (recommended)

```bash
cd debate_bot
# deepeval's own runner (richer report):
deepeval test run tests/deepeval_promptfoo/deepeval/test_debate_deepeval.py -m eval
# or plain pytest:
pytest -m eval tests/deepeval_promptfoo/deepeval/test_debate_deepeval.py
```

- Tests are marked `eval`, so a normal `pytest` run (`addopts = -m "not eval"`)
  and offline CI never hit the API. Pass `-m eval` to opt in.
- Each of `EVAL_SLICE` topics (default 3) is debated once, then scored on all 3
  rubrics — a 3×3 grid of GEval scores, printed with each metric's reason.
- Widen coverage with `EVAL_SLICE=10 ...`.

## Option C2 — promptfoo (alternative)

```bash
cd debate_bot/tests/deepeval_promptfoo/promptfoo
export ANTHROPIC_API_KEY=...
npx promptfoo@latest eval          # runs debates + asserts
npx promptfoo@latest view          # opens the local HTML report
```

The `python:eval_provider.py` provider runs a real debate per topic and returns
the state as JSON; `defaultTest.assert` applies the three `llm-rubric` rubrics
(graded by Claude) plus the deterministic JS checks to every topic.

## Reading the report

- **deepeval:** per-test pass/fail with a GEval `score` (0–1) and a natural-language
  `reason` for each (topic × rubric). deepeval also writes its own cache/report
  under `.deepeval/`.
- **promptfoo:** `npx promptfoo view` renders a grid (topics × asserts) with
  pass/fail and grader rationale; results are also stored for diffing across runs.
