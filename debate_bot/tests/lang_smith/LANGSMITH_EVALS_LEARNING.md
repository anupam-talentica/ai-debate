# LangSmith evals — the transferable concept

A project-agnostic cheat sheet. If you understand these four parts and one loop,
you can set up LangSmith evals for *any* LLM/agent system, not just this one.

## The four parts (this is the whole mental model)

| Part | What it is | In code |
|---|---|---|
| **Dataset** | Fixed set of *inputs* (test cases), hosted + versioned on the server | `create_dataset` + `create_example` |
| **Target** | The function/system under test: `inputs → outputs` | your `run(...)`, passed to `evaluate()` |
| **Evaluators** | Scorers over `(run, example)` → `{key, score}` | plain functions or LLM-as-judge |
| **Experiment** | One full pass of target over dataset, scored + traced, stored in the UI | the result of `evaluate()` |

```
Dataset ──► Target ──► Evaluators ──► Experiment
(inputs)   (system)    (scores)       (results + traces, versioned)
```

## Why evals ≠ unit tests

Unit tests assert one exact output. LLM outputs are open-ended, so you can't
`assert ==`. Instead you **run over many inputs and score each along several
dimensions** — some deterministic (length, valid enum, schema present), some
judged by a stronger model (relevance, quality 1–5). You track *aggregate scores
over time*, not pass/fail on one string.

## Why upload a dataset (the part that trips people up)

`evaluate()` takes a **dataset name**, not a local file — it pulls examples from
the server. Uploading turns your local test cases into a **server-side, versioned
object**, which is what unlocks the hosted value:

- `evaluate()` has something to iterate over and attach results to.
- Every experiment scores the *same versioned inputs* → runs are comparable over
  time (regression tracking). A local file can silently drift between runs.
- The dataset is the key the UI groups all experiments (and their score history)
  under.
- Each example holds `inputs` **and** optional gold `outputs`; evaluators read
  both. (Gold outputs are optional — omit them when you score *behavior* instead
  of matching a reference.)

> If you run evals **locally** (e.g. plain pytest reading a `.jsonl`), you don't
> upload — the file *is* the dataset. Upload is specifically the cost of the
> hosted platform's versioning/dashboard/trace features. That trade-off is the
> real decision: offline & portable vs. hosted history & traces.

## The minimal recipe (any project)

```python
from langsmith import Client
from langsmith.evaluation import evaluate

# 1. Upload dataset once (idempotent: key examples by a stable business id,
#    upsert instead of appending, so re-runs don't duplicate rows).
client = Client()
ds = client.create_dataset("my-dataset")
for row in my_cases:
    client.create_example(inputs={...}, outputs={...}, dataset_id=ds.id,
                          metadata={"id": row["id"]})

# 2. Define evaluators: (run, example) -> {"key","score"}  (or {"results":[...]})
def valid_output(run, example):
    return {"key": "valid", "score": int(is_valid(run.outputs))}

# 3. Run the experiment.
evaluate(
    lambda inputs: my_system(inputs["x"]),   # target
    data="my-dataset",                        # server-side name, not a path
    evaluators=[valid_output],
    experiment_prefix="my-exp",
)
```

## Transferable gotchas

- **Traces are free with LangGraph/LangChain**: set `LANGCHAIN_TRACING_V2=true`
  and every node/step auto-emits a trace to LangSmith — per-step latency and
  ordering, no manual instrumentation. Reason enough to use the hosted path for
  agentic systems.
- **Make upload idempotent**: key examples by a stable id and upsert. Otherwise
  every re-run duplicates your dataset.
- **Keep scorers in one place**: import the same scoring functions your local
  tests use, so local and hosted results are directly comparable.
- **Concurrency**: `evaluate()` parallelizes by default. If your target shares
  mutable module-level state (a graph, a memory store), set `max_concurrency=1`.
- **Privacy**: inputs, outputs, and traces leave your machine. Don't point it at
  sensitive data.
- **Judge robustness**: an LLM-as-judge evaluator should never raise — degrade to
  a `judge_ok=0` score so one bad grade doesn't kill the whole experiment.
- **Env at a glance**: `LANGSMITH_API_KEY`, `LANGCHAIN_TRACING_V2=true`,
  `LANGCHAIN_PROJECT` (optional grouping) — plus whatever keys your target/judge
  models need.
</content>
