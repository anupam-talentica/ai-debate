# Approach A — Custom pytest + LLM-as-judge harness

> **Status:** ✅ Implemented. Harness lives in `tests/custom_pytest/evals/`.
> **Goal:** A self-contained `evals/` harness that runs the **real** model over a dataset of
> topics and scores debate behavior with (1) deterministic Python checks and (2) an
> LLM-as-judge, then emits a scorecard. Zero new dependencies.

---

## 1. Why this approach

- **Zero new deps** — reuses the existing `pytest` + `langchain-anthropic` stack.
- **Fully self-contained** — a reviewer runs one command and sees a scorecard. No account,
  no hosted UI, no network beyond the Anthropic API.
- **Total control** — you own every metric, the exact judge prompt, and the dataset.
- **Covers all four eval dimensions** (see `docs/EVALUATION_APPROACHES.md §2`):
  argument quality, correctness/robustness, coherence, performance/streaming.

The single integration seam every scorer uses:

```python
from app import run_debate          # app.py:14-31
final_state = await run_debate(topic)
# → {topic, round, pro_opening, con_opening, pro_rebuttal, con_rebuttal,
#    pro_closing, con_closing, moderator_summary, winner, memory_context}
```

Judge model rule: debates run on `claude-haiku-4-5-20251001` (default `MODEL_NAME`); judge with
a **stronger** model via `JUDGE_MODEL_NAME` (e.g. `claude-sonnet-5`) so a model never grades
itself.

---

## 2. Target layout (lands in `tests/custom_pytest/evals/`)

```
tests/custom_pytest/evals/
├── __init__.py
├── datasets/
│   └── topics.jsonl            # golden topics incl. weak-spot triggers
├── scorers/
│   ├── __init__.py
│   ├── deterministic.py        # winner-valid, word caps, structure, all-fields
│   └── llm_judge.py            # Claude judge → 1–5 rubric scores (JSON)
├── report.py                   # scorecard formatting (markdown table + JSON dump)
├── run_evals.py                # CLI: run_debate() over dataset → aggregate scorecard
└── test_evals.py               # pytest wrapper w/ thresholds (opt-in marker)
```

---

## 3. Dataset design (`datasets/topics.jsonl`)

~10–20 topics, one JSON object per line. **Deliberately include the known weak-spot triggers**
so the eval surfaces real gaps:

```jsonl
{"id": "ai-jobs", "topic": "AI will replace software engineers", "expects_winner_parse": true}
{"id": "one-word", "topic": "Pineapple", "note": "degenerate/short topic — stresses relevance"}
{"id": "winner-trap", "topic": "Pro athletes are overpaid", "note": "topic contains 'Pro' → stresses the brittle winner parser"}
{"id": "closing-ref", "topic": "Remote work beats office work", "note": "a good closing must reference the opening"}
{"id": "ubi", "topic": "Universal basic income should be implemented"}
```

Fields per row: `id` (stable key), `topic` (the debate input), optional `note`, and optional
per-row expectations. Keep it a plain JSONL file checked into the repo.

### Prime targets to design the dataset around (from `EVALUATION_APPROACHES.md §2`)

1. Brittle winner parser (`src/agents/moderator.py:40-53`) — include a topic with "Pro"/"Con"
   as a substring.
2. Moderator sees only closings — include a topic where the decisive point is made in openings.
3. Closings get no transcript — include a topic where a good closing must echo the opening.
4. Con rebuttal targets Pro's opening (not Pro's rebuttal) — include a topic where the
   rebuttal chain matters.
5. Word-count caps (`~250 / ~130 / ~100` words in `src/core/prompts.py`) — checkable on any row.

---

## 4. Metrics

### 4a. Deterministic (`scorers/deterministic.py`) — no LLM

```python
ARG_FIELDS = ["pro_opening","con_opening","pro_rebuttal","con_rebuttal","pro_closing","con_closing"]

def score_deterministic(s: dict) -> dict:
    return {
        "winner_valid":  s["winner"] in ("Pro", "Con"),          # moderator.py:40-53
        "all_fields":    all(s[f] for f in ARG_FIELDS),
        "opening_wc_ok": word_count(s["pro_opening"]) <= 250,     # prompts.py caps
        "rebuttal_wc_ok": word_count(s["pro_rebuttal"]) <= 130,
        "closing_wc_ok": word_count(s["pro_closing"]) <= 100,
        "mod_3part":     has_pro_point_con_point_and_winner(s["moderator_summary"]),
    }
```

Covers the **correctness/robustness** dimension. All booleans/numbers, cheap, reproducible.

### 4b. LLM-as-judge (`scorers/llm_judge.py`)

```python
JUDGE = ChatAnthropic(model=os.getenv("JUDGE_MODEL_NAME", "claude-sonnet-5"))

async def score_quality(s: dict) -> dict:
    prompt = f'''Score this debate 1-5 on each axis. Return ONLY JSON.
    Topic: {s["topic"]}
    Pro opening: {s["pro_opening"]}
    Con opening: {s["con_opening"]}
    Con rebuttal (should engage Pro): {s["con_rebuttal"]}
    Moderator decision: {s["moderator_summary"]}
    Axes: relevance, persuasiveness, rebuttal_engagement, moderator_soundness'''
    resp = await JUDGE.ainvoke(prompt)
    return json.loads(resp.content)   # {"relevance":4, "persuasiveness":3, ...}
```

Covers **argument quality** and (combined with string checks) **coherence**. Parse defensively
(strip code fences, retry once on JSON error) — the judge occasionally wraps JSON in prose.

### 4c. Performance / streaming (optional, instrument `stream_debate`)

Wrap `DebateService.stream_debate` (`src/api/services/debate_service.py:52-127`), record
per-node timestamps and event ordering, assert `COMPLETE`/`ERROR` events present, capture
end-to-end duration. Lower priority than 4a/4b.

---

## 5. Runner + scorecard

`run_evals.py` (sketch):

```python
async def main():
    topics = [json.loads(l) for l in open("datasets/topics.jsonl")]
    rows = []
    for t in topics:
        state = await run_debate(t["topic"])
        det   = score_deterministic(state)     # dict of bool/number
        judge = await score_quality(state)      # dict of 1–5 scores
        rows.append({**t, **det, **judge})
    print_scorecard(rows)   # markdown table + averages; also write results.json
```

`report.py`: render a markdown table (one row per topic, columns per metric), print
per-metric averages / pass-rates, and dump `results.json` for CI diffing.

Run:
```bash
cd debate_bot
export ANTHROPIC_API_KEY=...          # required
export JUDGE_MODEL_NAME=claude-sonnet-5
python -m tests.custom_pytest.evals.run_evals
```

`test_evals.py`: a thin pytest wrapper (behind a `@pytest.mark.eval` marker, deselected by
default) that runs a small slice and asserts thresholds, e.g. `winner_valid` pass-rate ≥ 0.9 and
mean `relevance` ≥ 3.5 — turning the eval into a CI gate when desired.

---

## 6. Implementation steps (do NOT start yet)

1. **Prereq fix** — repair the invalid line `from app import src.core.graph as graph` in
   `unit_tests/test_edge_cases.py` and `unit_tests/test_errors.py`, and confirm the agent
   import path (`agents.*` vs `src.agents.*`) so `run_debate` imports cleanly.
2. Create `evals/datasets/topics.jsonl` with ~10–20 rows incl. all 5 weak-spot triggers.
3. Implement `scorers/deterministic.py` (+ `word_count`, `has_pro_point_con_point_and_winner`).
4. Implement `scorers/llm_judge.py` with defensive JSON parsing and `JUDGE_MODEL_NAME`.
5. Implement `report.py` (markdown scorecard + `results.json`).
6. Implement `run_evals.py` wiring the above over `run_debate`.
7. Add `test_evals.py` with `@pytest.mark.eval` thresholds; register the marker in pytest config.
8. Document the run command in `docs/` and `QUICKSTART`.

## 7. Acceptance criteria

- `python -m tests.custom_pytest.evals.run_evals` prints a scorecard and writes `results.json`.
- Deterministic metrics computed for every topic with no LLM cost.
- Judge scores present for every topic; run degrades gracefully if a judge call fails.
- The weak-spot topics visibly move at least one metric (proves the eval has teeth).
- No new dependency added to `requirements.txt`.

## 8. Cost

≈ `N topics × (1 debate on Haiku + 1 judge call on Sonnet/Opus)`. A 20-topic run is cheap; keep
the judge prompt tight and batch nothing that isn't needed.
