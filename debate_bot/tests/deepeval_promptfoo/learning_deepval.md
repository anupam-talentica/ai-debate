# deepeval — the transferable concept + how this project uses it

A project-agnostic cheat sheet, then the concrete wiring in
`tests/deepeval_promptfoo/deepeval/`. deepeval is the **chosen/default** eval tool
for this repo because it is *pytest-native* — evals are just marked tests, so they
live in the same runner, same fixtures, same CI as everything else.

## The mental model (this is the whole thing)

deepeval reframes "test an LLM output" as **score a test case along a metric**,
where the score comes from a judge model rather than an `assert ==`.

| Part | What it is | In this project |
|---|---|---|
| **`LLMTestCase`** | One row: `input`, `actual_output` (+ optional `expected_output`, `context`, `retrieval_context`) | Built by `make_test_case()` from a projected debate state |
| **Metric** | A scorer over a test case → `score` (0–1) + `reason` + `success` | 3 × `GEval` rubrics in `metrics.py` |
| **`GEval`** | A *custom-rubric* metric: you write `criteria` in plain English, the judge does chain-of-thought and returns a normalized score | `relevance`, `rebuttal_engagement`, `moderator_soundness` |
| **Judge model** | The LLM that grades. Defaults to OpenAI — you override it | `ClaudeJudge` (Sonnet) via the custom-model interface |
| **Runner** | `deepeval test run …` **or** plain `pytest` — metrics assert inside test functions | `test_debate_deepeval.py`, marked `eval` |

```
run_debate(topic) ──► DebateState ──► as_testcase_fields() ──► LLMTestCase
                                                                    │
                                              GEval(criteria, judge=Claude)
                                                                    │
                                                        score 0–1 + reason ──► assert ≥ threshold
```

## Why GEval and not the built-in metrics

deepeval ships `AnswerRelevancyMetric`, `FaithfulnessMetric`, `HallucinationMetric`,
etc. **They all assume a single-turn QA/RAG shape** (question → answer, optionally
grounded in retrieved context). A debate is a *multi-turn transcript* with roles
(Pro/Con/Moderator) — that shape doesn't map onto "was this answer faithful to the
retrieved passage?"

So this project uses **`GEval`** exclusively. `GEval` is the escape hatch: you hand
it `criteria` (a rubric in prose) and the fields it may look at, and the judge
grades against *your* description of correctness. This is the single most important
decision in the implementation — see the note in `metrics.py:1-15` and PLAN §7
"metric-shape mismatch."

## The three rubrics (mapped to the system's real dimensions)

Each is a `GEval` in [metrics.py](deepeval/metrics.py), scored 0–1, default
threshold **0.7**:

| Metric | `input` field | `actual_output` field | Criteria (abridged) |
|---|---|---|---|
| `relevance` | `topic` | `pro_opening` | Does the Pro opening argue FOR the topic and stay on-topic? Penalize wrong-side / off-topic / degenerate. |
| `rebuttal_engagement` | `pro_point` (= pro_opening) | `con_rebuttal` | Does the rebuttal engage ≥1 *specific* point Pro made, vs a generic anti-topic speech? |
| `moderator_soundness` | `arguments` (Pro+Con closings) | `moderator_summary` | Is the winner decision justified by the arguments, and does it name a clear valid winner? |

They are registered once as an ordered `DIMENSIONS` list
(`(key, builder, input_field, output_field)`) so the test file — and any future
runner — iterates the same set of dimensions.

## Pointing deepeval at Claude (the judge adapter)

deepeval defaults to OpenAI; this repo has no OpenAI key and must not let a model
grade itself. [judge.py](deepeval/judge.py) subclasses `DeepEvalBaseLLM`:

- Wraps `langchain_anthropic.ChatAnthropic` (already a runtime dep).
- Model from `JUDGE_MODEL_NAME` (default `claude-sonnet-5`) — deliberately
  **stronger than the Haiku under test**, so debates produced by Haiku are never
  graded by Haiku.
- Implements both call shapes deepeval uses: `generate(prompt)` returns text;
  `generate(prompt, schema=…)` routes through LangChain's
  `with_structured_output(schema)` for `GEval`'s structured scoring path. Async
  `a_generate` mirrors both.
- **`temperature` is intentionally unset** — it is deprecated for newer judge
  models (e.g. `claude-sonnet-5`) and setting it raises a 400.
- `_to_text()` flattens Anthropic's list-of-content-blocks responses to a string.

A single `_JUDGE = ClaudeJudge()` instance is shared across all metrics
(`metrics.py:27`); it builds the LLM lazily on first use.

## The test file — evals as parametrized pytest

[test_debate_deepeval.py](deepeval/test_debate_deepeval.py) is a 3×3 grid:
`_TOPICS` (first `EVAL_SLICE`=3 topics) × `DIMENSIONS` (3 rubrics).

```python
@pytest.mark.parametrize("dim_key,builder,input_field,output_field", DIMENSIONS, …)
@pytest.mark.parametrize("topic_row", _TOPICS, …)
def test_debate_rubric(topic_row, dim_key, builder, input_field, output_field):
    fields = _fields_for(topic_row["topic"])      # run debate once, cache per topic
    metric = builder()
    metric.measure(make_test_case(fields, input_field, output_field))
    assert metric.score >= metric.threshold, metric.reason
```

Key mechanics worth stealing:

- **Marked `eval`** + `pytest.ini`'s `addopts = -m "not eval"` → a normal `pytest`
  run and offline CI **never** hit the API. You opt in with `-m eval`.
- **`pytest.importorskip("deepeval")`** → if the optional dep isn't installed, the
  whole module skips cleanly instead of erroring at collection.
- **`skipif` on `ANTHROPIC_API_KEY`** → no key, no run.
- **`_STATE_CACHE`** (module-level dict) → each topic is debated *once* even though
  3 metrics consume it (7 agent calls per debate, so this matters).
- Each test prints `score`, `threshold`, and the judge's `reason`, so a run is
  self-documenting.

## The debate cache — the cost trick

`eval_provider.py` adds a second, on-disk cache layer
([`.debate_cache/`](.debate_cache/)) on top of the in-memory one:

- Debate *generation* (7 agent calls) dwarfs judge *scoring* in tokens, and the
  eval reruns the same handful of topics constantly. The debate outcome isn't what's
  under test — only the judge's scoring of it is — so the transcript is cached and
  reused.
- Cache key = `sha256(f"{MODEL_NAME}:{topic}")[:16]` — **keyed on the debating
  model**, so changing `MODEL_NAME` correctly misses.
- Gated by `EVAL_CACHE_DEBATES` (default on); set `=false` to force a live debate.

The captured [output/](deepeval/output/) files prove it works: cache miss **65s** →
cache hit **28s** → disabled **64s** (files 03/04/05).

## Running it

```bash
cd debate_bot
pip install -r requirements-eval.txt          # deepeval; judge is Claude via langchain-anthropic
export ANTHROPIC_API_KEY=...
export JUDGE_MODEL_NAME=claude-sonnet-5        # optional; default

deepeval test run tests/deepeval_promptfoo/deepeval/test_debate_deepeval.py -m eval
# or plain pytest:
pytest -m eval tests/deepeval_promptfoo/deepeval/test_debate_deepeval.py
# widen coverage:
EVAL_SLICE=10 pytest -m eval tests/deepeval_promptfoo/deepeval/test_debate_deepeval.py
```

deepeval also drops its own cache/telemetry under `.deepeval/`.

## What a real run looks like

From [output/02_full_run_with_scores.txt](deepeval/output/02_full_run_with_scores.txt)
— all 9 (topic × rubric) cells PASSED, each with a natural-language reason:

- `[ai-jobs] relevance: 1.00` — argues FOR, stays on-topic.
- `[ai-jobs] rebuttal_engagement: 0.90` — quotes Pro's "60-80%" stat and refutes it.
- `[winner-trap] moderator_soundness: 0.80` — names a winner, grounded in the closings.

The dataset deliberately includes teeth: `winner-trap` ("**Pro** athletes are
overpaid") stresses the brittle winner parser, and `one-word` ("Pineapple") stresses
the relevance metric with a degenerate topic.

## Transferable gotchas

- **Override the judge, always.** Out of the box deepeval grades with OpenAI. Any
  serious eval must (a) point it at a model you control and (b) ensure it isn't the
  same model under test. The `DeepEvalBaseLLM` subclass is the seam.
- **Reach for `GEval` when your task isn't QA/RAG.** Built-in relevancy/faithfulness
  metrics silently assume a shape; a wrong-shaped metric produces confident garbage.
- **Isolate the eval dependency.** deepeval lives in `requirements-eval.txt`, not
  `requirements.txt`, so the Docker/runtime image stays lean. Guard the import with
  `importorskip`.
- **Gate evals out of the default test run.** Mark them (`-m eval`) so `pytest` and
  offline CI never spend API tokens by accident.
- **Cache the expensive half.** Separate "produce the artifact" from "grade the
  artifact"; cache the produce step keyed on everything that affects it (here, the
  model name), and let scoring run fresh.
- **Score the same slices everywhere.** `as_testcase_fields()` centralizes field
  selection so deepeval and promptfoo grade identical transcript slices → numbers
  stay comparable across approaches (and against the custom-pytest Approach A).
- **`LLMTestCaseParams` is deprecated** in deepeval ≥4 (use `SingleTurnParams`) —
  harmless warning today, worth noting for upgrades.
