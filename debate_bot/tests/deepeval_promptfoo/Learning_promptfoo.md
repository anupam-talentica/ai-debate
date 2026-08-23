# promptfoo — the transferable concept + how this project uses it

A project-agnostic cheat sheet, then the concrete wiring in
`tests/deepeval_promptfoo/promptfoo/`. promptfoo is the **documented alternative**
to deepeval in this repo: a **declarative, YAML-driven** eval runner (a Node CLI,
`npx promptfoo`) that ships a polished local HTML report.

## The mental model (this is the whole thing)

promptfoo reframes eval as a **matrix**: `providers × tests × asserts`. You declare
what to run and what "good" means in a config file; the CLI fills the grid and
renders it.

| Part | What it is | In this project |
|---|---|---|
| **Provider** | The system under test: something that takes vars and returns an `output` | `python:eval_provider.py` → runs a real debate |
| **Test** | One row of input `vars` (+ optional per-row asserts) | 3 topics under `tests:` |
| **Assert** | A check applied to the output → pass/fail (+ score) | 3 `llm-rubric` + 3 `javascript`, in `defaultTest` |
| **Grader** | The model behind `llm-rubric` (defaults to OpenAI — you override) | `anthropic:messages:claude-sonnet-5` |
| **Transform** | JS expression that reshapes `output` before an assert sees it | focuses each rubric on one transcript slice |
| **Report** | `npx promptfoo view` → local HTML grid, stored for diffing | topics × asserts, with grader rationale |

```
promptfooconfig.yaml
   providers: python:eval_provider.py  ──►  run_debate(topic) ──► JSON state
   tests:     [topic, topic, topic]
   asserts:   llm-rubric×3 (Claude grader) + javascript×3 (deterministic)
                              │
                       grid: topics × asserts  ──►  npx promptfoo view
```

## The Python provider — bridging YAML to `run_debate`

promptfoo is JS-first, but a debate is a Python LangGraph. The bridge is a Python
provider, [promptfoo/eval_provider.py](promptfoo/eval_provider.py):

```python
def call_api(prompt, options, context):
    topic = context["vars"]["topic"]      # promptfoo passes test vars here
    state = run_debate_sync(topic)         # the SHARED seam (same as deepeval)
    slim = {k: state.get(k) for k in (...)}  # JSON-serializable graded fields only
    return {"output": json.dumps(slim)}
```

Details that matter:

- **`prompt` is ignored on purpose.** promptfoo's model is "one prompt → one
  completion," but a debate is a *graph*, not a single prompt. So the provider reads
  the `topic` var and drives the whole graph itself.
- **`sys.path` fix-up.** promptfoo runs the file from its own CWD, so the provider
  inserts `debate_bot/` (`parents[3]`) on `sys.path` to import the shared
  `run_debate_sync`.
- **Same seam as deepeval.** It calls the very same `eval_provider.run_debate_sync`
  — same debate, same `.debate_cache/`, same `EVAL_CACHE_DEBATES` gate — so
  promptfoo and deepeval numbers are comparable.
- Output is the full state serialized to a JSON string; asserts pick fields out of
  it.

## The config — asserts as the rubric

[promptfooconfig.yaml](promptfoo/promptfooconfig.yaml) puts the whole rubric in
`defaultTest.assert` (so it applies to every topic), mirroring deepeval's three
dimensions plus the deterministic checks:

**LLM-graded rubrics** (`llm-rubric`, graded by Claude via `options.provider`):

| Assert | `transform` (what the grader sees) | Rubric |
|---|---|---|
| relevance | `JSON.parse(output).pro_opening` | argues FOR the topic, stays on-topic |
| rebuttal engagement | Pro opening **+** Con rebuttal, concatenated | rebuttal engages ≥1 specific Pro point |
| moderator soundness | Pro+Con closings **+** moderator summary | decision justified, names a clear winner |

**Deterministic checks** (`javascript`, identical *intent* to Approach A for
comparability):

- `['Pro','Con'].includes(JSON.parse(output).winner)` — winner is valid.
- `pro_opening` ≤ 250 words; `pro_closing` ≤ 100 words — word caps.

The `transform` is the promptfoo counterpart of deepeval's field projection: it
narrows the big JSON blob down to exactly the slice each rubric should judge.

## Pointing the grader at Claude (not OpenAI)

By default `llm-rubric` grades with OpenAI. `defaultTest.options.provider` overrides
it for every rubric:

```yaml
defaultTest:
  options:
    provider:
      id: anthropic:messages:claude-sonnet-5
```

Same principle as the deepeval judge adapter: grade with a **stronger** model than
the Haiku under test, and never require an OpenAI key.

## The dataset — a slice with teeth

`tests:` mirrors a slice of the shared dataset
(`../../custom_pytest/evals/datasets/topics.jsonl`), and deliberately includes the
**winner-parser trap** (`"Pro athletes are overpaid"` — the `'Pro'` substring
stresses the brittle winner parser) so the eval has teeth, matching Approach A.

## Running it

```bash
cd debate_bot/tests/deepeval_promptfoo/promptfoo
export ANTHROPIC_API_KEY=...
npx promptfoo@latest eval        # runs debates + asserts (no pip install — it's a Node CLI)
npx promptfoo@latest view        # opens the local HTML report
```

## Reading the report

`npx promptfoo view` renders a **grid** (topics × asserts) with per-cell pass/fail,
the grader's rationale for each `llm-rubric` cell, and pass/fail for the JS checks.
Results are stored, so you can **diff across runs** to catch regressions.

## Transferable gotchas

- **Provider = adapter, not prompt.** When the system under test isn't a single
  prompt (agents, graphs, pipelines), ignore promptfoo's `prompt` and drive your
  system from `context.vars` in the provider. Return `{"output": …}`.
- **`sys.path` when embedding Python.** promptfoo runs providers from its own CWD;
  add your project root explicitly or imports fail.
- **Override the grader.** `llm-rubric` silently defaults to OpenAI. Set
  `options.provider` to the model you actually want (and it must differ from the
  model under test).
- **`transform` focuses the judge.** Feed each rubric only the transcript slice it
  should grade; grading the whole blob dilutes the signal.
- **Keep deterministic checks in the same config.** Mixing `javascript` asserts with
  `llm-rubric` gives you cheap, exact guardrails (enums, length caps) alongside the
  fuzzy judged scores — and lets you keep them identical to your other approaches.
- **No pip, but Node required.** promptfoo is `npx`-only; it won't appear in
  `requirements*.txt`. That's a feature (zero Python-dep bloat) and a caveat (a
  Node toolchain must exist wherever the eval runs — e.g. CI).
- **YAML is the source of truth.** Great for non-Python reviewers and quick edits;
  the flip side is less programmatic control than deepeval's pytest (loops,
  fixtures, dynamic parametrization live in JS/YAML, not Python).
