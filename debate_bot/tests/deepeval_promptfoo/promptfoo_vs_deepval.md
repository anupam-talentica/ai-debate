# promptfoo vs deepeval — comparison (as implemented here)

Both tools score the **same debate system** over the **same dataset** through the
**same seam** (`eval_provider.run_debate_sync`), graded by the **same Claude judge**
(`claude-sonnet-5`, stronger than the Haiku under test). They differ only in *how*
you declare and run the eval. This doc compares them as they are actually wired in
`tests/deepeval_promptfoo/` — see [learning_deepval.md](learning_deepval.md) and
[Learning_promptfoo.md](Learning_promptfoo.md) for each in depth.

> **This repo's choice: deepeval** — it stays inside the existing pytest stack, so
> evals share the runner, markers, fixtures, and CI with every other test.
> **promptfoo** is kept as a documented, working alternative for its report and its
> config-driven ergonomics.

## The shared foundation (why the numbers are comparable)

```
                     eval_provider.run_debate_sync(topic)   ← ONE seam
                     .debate_cache/  +  EVAL_CACHE_DEBATES   ← ONE cache
                     topics.jsonl (custom_pytest/evals)      ← ONE dataset
                     claude-sonnet-5                          ← ONE judge model
                     3 rubrics + winner-valid + word-caps     ← SAME dimensions
                    ┌──────────────────┴──────────────────┐
              deepeval (C1)                          promptfoo (C2)
        GEval rubrics in pytest              llm-rubric asserts in YAML
```

Neither tool forks the dataset or the debate runner. That is deliberate: it keeps
Approach C's scores directly comparable with Approach A (custom pytest) and B.

## Side-by-side

| Dimension | **deepeval** (chosen) | **promptfoo** (alternative) |
|---|---|---|
| Language / format | Python, pytest tests | YAML config + a small Python provider |
| Install | `pip install -r requirements-eval.txt` | `npx promptfoo@latest` (Node CLI, no pip) |
| Runs inside | Existing pytest stack (`-m eval`) | Its own CLI runner |
| System-under-test hookup | Direct import of `run_debate_sync` in the test | `python:eval_provider.py` provider (`call_api`) |
| Rubric definition | `GEval(criteria=…)` in [metrics.py](deepeval/metrics.py) | `llm-rubric` `value:` strings in the YAML |
| Field focusing | `as_testcase_fields()` + `input/output_field` | `transform:` JS expressions |
| Deterministic checks | (would be `assert`s / imported from Approach A) | `javascript` asserts in the same config |
| Judge override | `ClaudeJudge(DeepEvalBaseLLM)` in [judge.py](deepeval/judge.py) | `options.provider: anthropic:messages:claude-sonnet-5` |
| Score shape | 0–1 `score` + `reason` per metric | pass/fail (+ score) per assert, with rationale |
| Report | pytest output + `.deepeval/` cache; per-test reason printed | `npx promptfoo view` HTML grid, stored for diffing |
| Coverage knob | `EVAL_SLICE` (topics) × `DIMENSIONS` grid | rows under `tests:` |
| CI fit | Excellent — one runner, gated by `-m "not eval"` | Needs a Node toolchain alongside Python |
| Best at | Programmatic control (loops, fixtures, parametrize) | Declarative matrices + a shareable visual report |

## Where each one wins

**deepeval is better when…**
- You already have pytest and want evals to be *just tests* — same command, same
  markers (`-m eval`), same `importorskip`/`skipif` guards, same CI. This is the
  deciding factor for this repo.
- You need programmatic control: caching debates in a module dict, parametrizing a
  topic × rubric grid, computing thresholds, reusing Python fixtures.
- You want the judge to be a first-class Python object you can unit-test and reuse
  (`ClaudeJudge`), with full control over structured vs prose output.

**promptfoo is better when…**
- You want a **shareable visual report** out of the box (`promptfoo view`) and
  run-to-run diffing without building it yourself.
- Non-Python teammates should read or edit the eval — the rubric is plain YAML.
- You're comparing *multiple providers/prompts* head-to-head (promptfoo's matrix is
  built for that), even though this project uses a single provider.
- You don't want to add a Python eval dependency at all (it's `npx`).

## Shared design decisions (true of both, worth copying)

- **Custom rubrics over built-ins.** Both avoid stock relevancy/faithfulness metrics
  (which assume single-turn QA/RAG) in favor of rubrics whose criteria describe a
  *debate transcript*. Same reasoning drives `GEval` and `llm-rubric` here.
- **Override the grader to a stronger, different model.** Out of the box both grade
  with OpenAI; both are repointed at `claude-sonnet-5` so Haiku never grades itself
  and no OpenAI key is needed.
- **Separate "generate" from "grade" and cache the expensive half.** The
  `.debate_cache/` layer (keyed on `MODEL_NAME:topic`) makes reruns cheap for both;
  the captured runs show 65s→28s on a cache hit.
- **Keep deterministic checks identical to Approach A.** winner-valid + word caps
  run alongside the fuzzy rubrics in both, so C's numbers line up with A and B.
- **Isolate the dependency.** deepeval lives in `requirements-eval.txt` (not the
  runtime image); promptfoo is `npx` (no pip at all). Neither bloats production.

## Bottom line

They are two front-ends over one eval. deepeval won here on **stack cohesion**
(pytest-native, one runner, CI-clean); promptfoo remains valuable for its
**report and declarative config**. Because both sit on the shared seam, dataset, and
judge, you can run either — or both — and trust the scores are measuring the same
thing.
