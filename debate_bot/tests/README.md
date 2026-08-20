# Running the Evaluation Suites

This repo evaluates the same debate system four different ways, all described
and compared in [EVAL_APPROACHES_4WAY_COMPARISON.md](EVAL_APPROACHES_4WAY_COMPARISON.md).
This file is the practical "how do I run it" companion — one command block per
approach. Deep-dive docs for each approach are linked at the end of each section.

All commands assume you start from the `debate_bot/` project root.

## 0. Shared setup

```bash
cp .env.example .env
# then edit .env and set at minimum:
#   ANTHROPIC_API_KEY=sk-ant-...
#   JUDGE_MODEL_NAME=claude-sonnet-5   # optional, this is the default
```

Every approach below debates with `MODEL_NAME` (default
`claude-haiku-4-5-20251001`) and grades with `JUDGE_MODEL_NAME` (default
`claude-sonnet-5`) — a stronger model that never grades itself.

The plain (non-eval) pytest suite runs fully mocked and needs no API key:

```bash
pytest tests/custom_pytest -v -m "not e2e"
```

See [TESTS_OVERVIEW.md](TESTS_OVERVIEW.md) for what those tests cover.

---

## A — Custom pytest + LLM-as-judge harness

Zero new dependencies — reuses the existing `pytest` + `langchain-anthropic` stack.

```bash
cd debate_bot
export ANTHROPIC_API_KEY=...
export JUDGE_MODEL_NAME=claude-sonnet-5   # optional

# Run the harness directly (prints a scorecard, writes results.json + TEST_REPORT.md)
python -m tests.custom_pytest.evals.run_evals

# Or as a CI-style pytest gate (opt-in marker, asserts thresholds)
pytest -m eval tests/custom_pytest/evals/test_evals.py -v
```

Output: `tests/custom_pytest/evals/results.json` and `TEST_REPORT.md`.

Docs: [custom_pytest/PLAN.md](custom_pytest/PLAN.md)

---

## B — Hosted LangSmith evaluation

Reuses Approach A's exact scorer logic, run on the hosted LangSmith platform.
Sends debate inputs/outputs/traces to LangSmith — don't use with sensitive data.

```bash
cd debate_bot
export ANTHROPIC_API_KEY=...
export LANGSMITH_API_KEY=lsv2_...
export LANGCHAIN_TRACING_V2=true            # auto-traces each LangGraph node
export LANGCHAIN_PROJECT=debate-bot-evals   # optional — groups runs in the UI
export JUDGE_MODEL_NAME=claude-sonnet-5     # optional

python tests/lang_smith/upload_dataset.py   # once — creates/updates the hosted dataset
python tests/lang_smith/run_eval.py         # each eval run
```

Output: an experiment in the LangSmith UI (per-topic scores + per-node traces);
CSV snapshots land in `tests/lang_smith/result/`.

Docs: [lang_smith/README.md](lang_smith/README.md)

---

## C1 — deepeval (recommended off-the-shelf option)

Pytest-native, custom GEval rubrics, on-disk debate cache so reruns skip
regeneration.

```bash
cd debate_bot
pip install -r requirements-eval.txt      # installs deepeval
export ANTHROPIC_API_KEY=...
export JUDGE_MODEL_NAME=claude-sonnet-5   # optional

# deepeval's own runner (richer report)
deepeval test run tests/deepeval_promptfoo/deepeval/test_debate_deepeval.py -m eval

# or plain pytest
pytest -m eval tests/deepeval_promptfoo/deepeval/test_debate_deepeval.py
```

Widen coverage with `EVAL_SLICE=10 ...` (default is 3 topics).

Output: pytest/deepeval console report + `.deepeval/` cache dir.

Docs: [deepeval_promptfoo/README.md](deepeval_promptfoo/README.md), [deepeval_promptfoo/learning_deepval.md](deepeval_promptfoo/learning_deepval.md)

---

## C2 — promptfoo (declarative YAML alternative)

No pip dependency — runs via `npx` (Node required).

```bash
cd debate_bot/tests/deepeval_promptfoo/promptfoo
export ANTHROPIC_API_KEY=...

npx promptfoo@latest eval    # runs debates + asserts (3 llm-rubric + 3 JS deterministic checks)
npx promptfoo@latest view    # opens the local HTML report (topics × asserts grid)
```

Docs: [deepeval_promptfoo/README.md](deepeval_promptfoo/README.md), [deepeval_promptfoo/Learning_promptfoo.md](deepeval_promptfoo/Learning_promptfoo.md)

---

## Which one should I run?

- **Default / CI gate:** A — zero-dep, offline, fully self-contained.
- **Need history & per-node traces:** B — same scores as A, hosted dashboard.
- **Want off-the-shelf rubric tooling:** C1 (pytest) or C2 (YAML + HTML report).

Full rationale and a side-by-side matrix: [EVAL_APPROACHES_4WAY_COMPARISON.md](EVAL_APPROACHES_4WAY_COMPARISON.md).
