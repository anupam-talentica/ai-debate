# Approach B — LangSmith evaluation

> **Status:** Implemented (`upload_dataset.py`, `evaluators.py`, `run_eval.py`, `README.md`).
> Pending a live run against a real `LANGSMITH_API_KEY` to capture UI screenshots (step 6).
>
> This is the **single reference** for using LangSmith to evaluate the debate bot.
> Read §0 first for the mental model (including *why the dataset upload exists*),
> then §1–§6 for the concrete steps. For the transferable, project-agnostic
> version of these concepts, see [`LANGSMITH_EVALS_LEARNING.md`](./LANGSMITH_EVALS_LEARNING.md).

---

## 0. Mental model — how a LangSmith eval actually works

An LLM eval is not a normal unit test. There is no single "correct" string to
assert against — outputs are open-ended, so instead you **run the system over a
fixed set of inputs and score each output along several dimensions**. Every eval
framework, LangSmith included, is built from the same four moving parts:

```
   Dataset            Target             Evaluators            Experiment
 (the inputs)   →   (your system)   →   (the scorers)    →   (results + traces)
 "list of test      run_debate(topic)   winner_valid?         one row per input,
  topics"           → debate state      arg_quality 1–5?      scored, versioned,
                                                              browsable in the UI
```

1. **Dataset** — the fixed collection of *inputs* (test cases). Here: 15 debate
   topics, each with an `id` and a `note` describing what weak spot it stresses.
2. **Target** — the function under test. Here: `run_debate(topic) → final state`.
   LangSmith calls it once per dataset row.
3. **Evaluators** — functions that look at `(run, example)` and return scores.
   Deterministic ones (word caps, valid winner) and an LLM-as-judge (1–5 quality).
4. **Experiment** — the scored result set. One experiment = one full pass of the
   target over the dataset, with every score and every LangGraph trace attached.

The whole value of a hosted platform is that steps 1 and 4 are **persisted and
versioned on a server**, so you can compare experiments over time on *identical*
inputs (regression tracking) and browse traces in a UI.

### Why upload the dataset? (your question)

Because `evaluate()` does **not** read your local `topics.jsonl`. It takes a
**dataset name** and pulls the examples from the LangSmith *server*. The upload
is a one-time step that turns your local file into that server-side, versioned
object. Concretely, uploading buys you four things a local file can't:

| Reason | What it enables |
|---|---|
| **`evaluate()` needs a server handle** | It fetches examples by name/ID from LangSmith, feeds each `inputs` to the target, and attaches scores + traces back to that example. No uploaded dataset → nothing to iterate over. |
| **Stable identity across runs** | Every experiment scores the *same* versioned examples, so "run today vs. run last week" is an apples-to-apples comparison. A local file can silently change between runs. |
| **Regression tracking & history** | The UI groups all experiments under the dataset and diffs their scores over time. That grouping key *is* the dataset. |
| **Reference outputs live with the input** | An example carries both `inputs` and (optionally) gold `outputs`; evaluators read both. Here we store no gold output — evaluators score behavior — but the slot is why examples, not raw strings, are the unit. |

> **Contrast with Approach A** (local pytest, `tests/custom_pytest/evals/`):
> there the dataset *is* just the local `topics.jsonl`, read at runtime. No
> upload, because there's no hosted service anchoring the runs. That's the entire
> difference between the two approaches — same dataset, same scorers, different
> runner. Upload is the price of admission for the hosted features.

### The one thing you get "for free": traces

Because the debate is a **LangGraph** graph, setting `LANGCHAIN_TRACING_V2=true`
makes every node (pro opening → con opening → rebuttals → closings → moderator)
auto-emit a trace to LangSmith. So the same eval run *also* gives you per-node
latency and event ordering — the performance/streaming dimension — with zero
extra instrumentation. This is the main reason to bother with the hosted path.

---

## 1. Why this approach (trade-offs)

- **Already a dependency** — `langsmith>=0.1` is in `requirements.txt` but wired
  nowhere. No install; just configuration.
- **Per-node performance metrics for free** — see traces note above.
- **Hosted dashboard** — scores + traces, dataset versioning, run history,
  regression tracking over time.

Costs: needs a LangSmith account + API key + network (**data leaves the
machine**); the UI is another system to learn; less portable for a fully offline
submission. Keep Approach A as the offline, self-contained path.

---

## 2. Layout (`tests/lang_smith/`)

```
tests/lang_smith/
├── __init__.py
├── upload_dataset.py    # one-time, idempotent: topics.jsonl → "debate-topics" dataset
├── evaluators.py        # deterministic_metrics + arg_quality — thin adapters over Approach A's scorers
├── run_eval.py          # evaluate(target=run_debate, data="debate-topics", evaluators=[...])
└── README.md            # setup + run instructions
```

Dataset source of truth stays shared: `tests/custom_pytest/evals/datasets/topics.jsonl`
(Approach A). We upload *from* it rather than duplicating topics.

---

## 3. Configuration (environment)

```bash
export LANGSMITH_API_KEY=lsv2_...
export LANGCHAIN_TRACING_V2=true            # auto-traces each LangGraph node
export LANGCHAIN_PROJECT="debate-bot-evals" # optional — groups runs
export ANTHROPIC_API_KEY=sk-ant-...
export JUDGE_MODEL_NAME=claude-sonnet-5     # stronger model grades the debate
```

---

## 4. Dataset upload (`upload_dataset.py`)

One-time, **idempotent**: creates the `debate-topics` dataset if absent, then
upserts each topic keyed by its stable `id` (stored in example metadata) so
re-running updates rows in place instead of duplicating them.

```python
client = Client()
ds = _get_or_create_dataset(client)          # has_dataset → read_dataset, else create_dataset
existing = {ex.metadata["id"]: ex.id for ex in client.list_examples(dataset_id=ds.id)}
for row in topics:
    if row["id"] in existing:
        client.update_example(example_id=existing[row["id"]], inputs={"topic": row["topic"]}, ...)
    else:
        client.create_example(inputs={"topic": row["topic"]}, outputs={}, dataset_id=ds.id, ...)
```

`outputs={}` on purpose — there is no gold answer; evaluators score *behavior*.

---

## 5. Evaluators (`evaluators.py`)

Thin adapters that **import** Approach A's scorers so there is one
implementation, and scores are comparable across A and B.

- `deterministic_metrics(run, example)` — emits all no-LLM metrics in one pass:
  booleans (`winner_valid`, `all_fields`, `*_wc_ok`, `mod_3part`) as 0/1, plus
  raw word counts. Wraps `score_deterministic`.
- `arg_quality(run, example)` — LLM-as-judge, 1–5 per axis (`relevance`,
  `persuasiveness`, `rebuttal_engagement`, `moderator_soundness`) + `judge_ok`.
  Wraps the shared async `score_quality`; never raises (a judge failure degrades
  to `judge_ok=0`).

An evaluator returns `{"key", "score"}`, or `{"results": [...]}` to emit several
metrics at once.

---

## 6. Runner (`run_eval.py`)

```python
evaluate(
    lambda inputs: asyncio.run(run_debate(inputs["topic"])),   # target
    data="debate-topics",                                       # server-side dataset
    evaluators=[deterministic_metrics, arg_quality],
    experiment_prefix="debate-eval",
    max_concurrency=1,   # graph + memory store in app.py are module-scoped, not thread-safe
)
```

```bash
cd debate_bot
python tests/lang_smith/upload_dataset.py   # once — creates/updates the dataset
python tests/lang_smith/run_eval.py         # each eval run
```

Scores **and** per-node LangGraph traces then appear in the LangSmith UI.

---

## 7. Acceptance criteria

- `upload_dataset.py` creates/updates `debate-topics` without duplicating rows.
- `run_eval.py` produces an experiment with per-topic scores.
- Per-node LangGraph traces (latency + ordering) are visible in the trace view.
- Deterministic evaluators agree with Approach A on the same topics (shared impl).
- No code change outside `tests/lang_smith/` beyond env config + the shared prereq fix.

## 8. Notes

- **Privacy:** debate inputs/outputs and traces are sent to LangSmith. Don't run
  on sensitive data; note this for the assignment reviewer.
- **Portability:** needs an account + network. Approach A stays the offline path;
  use B for tracing/dashboards/regression tracking over time.
</content>
</invoke>
