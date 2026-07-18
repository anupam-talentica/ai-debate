# Approach B — Hosted LangSmith evaluation

Turns on the already-present `langsmith` dependency to get **hosted dataset
management**, **LLM-as-judge + deterministic evaluators**, and — for free —
**per-node LangGraph traces** (the performance / streaming dimension).

It reuses the *same* dataset and scorer logic as Approach A
(`tests/custom_pytest/evals/`); only the runner changes. So the deterministic
scores are directly comparable across the two approaches.

## Files

| File | Purpose |
|---|---|
| `upload_dataset.py` | One-time (idempotent) push of `topics.jsonl` → a LangSmith `debate-topics` dataset |
| `evaluators.py` | `deterministic_metrics` + `arg_quality` (LLM-judge) — thin adapters over Approach A's shared scorers |
| `run_eval.py` | Runs `evaluate(target=run_debate, data="debate-topics", evaluators=[...])` |

The dataset source of truth stays shared:
`tests/custom_pytest/evals/datasets/topics.jsonl`.

## Setup

```bash
# From debate_bot/.env (see .env.example)
export ANTHROPIC_API_KEY=sk-ant-...
export LANGSMITH_API_KEY=lsv2_...
export LANGCHAIN_TRACING_V2=true            # auto-traces each LangGraph node
export LANGCHAIN_PROJECT=debate-bot-evals   # optional — groups runs
export JUDGE_MODEL_NAME=claude-sonnet-5     # stronger model grades the debate
```

With `LANGCHAIN_TRACING_V2=true`, every `run_debate` call auto-traces each
LangGraph node — no hand-instrumentation.

## Run

```bash
cd debate_bot

python tests/lang_smith/upload_dataset.py   # once — creates/updates the dataset
python tests/lang_smith/run_eval.py         # each eval run
```

`upload_dataset.py` is idempotent: it upserts by the topic's stable `id`
(stored in example metadata), so re-running updates rows in place instead of
duplicating them.

## What you get in the LangSmith UI

- **Experiment** `debate-eval-*` with per-topic scores:
  - Deterministic (0/1): `winner_valid`, `all_fields`, `opening_wc_ok`,
    `rebuttal_wc_ok`, `closing_wc_ok`, `mod_3part`, plus raw word counts.
  - LLM-judge (1–5): `judge_relevance`, `judge_persuasiveness`,
    `judge_rebuttal_engagement`, `judge_moderator_soundness`, plus `judge_ok`.
- **Per-node LangGraph traces** — latency and event ordering for each node
  (pro/con openings → rebuttals → closings → moderator) in the trace view.
- Dataset versioning, run history, and regression tracking over time.

## Notes

- **Privacy:** debate inputs/outputs and traces are sent to LangSmith. Don't run
  on sensitive data. Approach A (`tests/custom_pytest/evals/`) remains the
  offline, self-contained path; use B for tracing/dashboards/regression tracking.
- **Concurrency:** the debate graph and memory store in `app.py` are shared at
  module scope and not thread-safe, so `run_eval.py` sets `max_concurrency=1`.
- **Shared scorers:** `evaluators.py` imports `score_deterministic` and
  `score_quality` from Approach A rather than reimplementing them, so both
  approaches agree on the same topics.
