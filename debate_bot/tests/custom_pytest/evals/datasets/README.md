# Debate topics dataset (`topics.jsonl`)

The shared source of truth for both eval approaches (A: local pytest,
B: hosted LangSmith). One JSON object per line:

```json
{"id": "rebuttal-chain", "topic": "Social media does more harm than good", "note": "..."}
```

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Stable business key. Used to upsert into LangSmith without duplicating rows, and to reference a case in reports. **Never reuse or renumber** — it's the identity across runs. |
| `topic` | yes | The debate motion fed to `run_debate(topic)`. |
| `note` | no | *Why this row exists* — the hypothesis it tests (see below). |
| `expects_winner_parse` | no | Optional per-case expectation flag read by scorers. |

## The dataset is two tiers, on purpose

**1. Probes (rows with a `note`)** — adversarial cases, each targeting one known
weak spot in the pipeline. The `note` is the hypothesis being tested.

**2. Baseline / generalization set (rows with no `note`)** — ordinary,
well-formed motions (`ubi`, `four-day-week`, `space-exploration`, `self-driving`,
`homework`, `crypto`, `gene-editing`, `standardized-tests`). These are **not**
probes and need no note. Their job is to measure *typical-case* quality and catch
regressions on the common path — a change that fixes a probe shouldn't quietly
degrade normal debates. A dataset made only of adversarial cases would overfit
your scorers to edge behavior and tell you nothing about everyday quality.

Rule of thumb: **a topic needs a note only when it's in the set for a reason
other than "a normal debate."** If it's there to represent the common case, no
note is the correct signal.

## How to design a weak-spot (probe) topic — you derive it, you don't guess

A `note` is not a guaranteed assertion — with two AI agents nothing is
guaranteed on a single run. It's a **stressor**: an input chosen to *raise the
probability* that a specific weakness becomes visible, which you then confirm by
**measuring a scorer across the dataset**, not by asserting on one run. That
stressor-topic + aggregate-scorer split is what makes this an eval, not a unit
test.

To write one:

1. **Trace the information flow.** Read the graph edges (`src/core/graph.py`) and
   — more importantly — *what each prompt template actually receives*
   (`src/core/prompts.py`). Every `{placeholder}` a node is missing is a
   candidate weak spot ("this node is blind to X").
2. **Name the failure hypothesis.** e.g. "the closing can't reference the opening
   because the opening text isn't in its prompt."
3. **Pick a topic that maximizes exposure** — subject matter where that missing
   information matters most.
4. **Write the note as hypothesis + evidence** (ideally `file:line`) so a future
   reader knows *why* the topic is in the set.
5. **Point it at a scorer** that measures whether the failure actually happened.

## Current probe map

| `id` | Weak spot it stresses | Evidence | Measured by |
|---|---|---|---|
| `ai-jobs` | baseline well-formed topic (sanity) | — | all metrics |
| `one-word` | degenerate/short topic stresses relevance | `topic="Pineapple"` | `relevance` (judge) |
| `winner-trap` | brittle winner parser (topic contains "Pro") | winner scan in `src/agents/moderator.py` | `winner_valid` |
| `con-trap` | fallback winner scan (topic contains "Con") | same parser | `winner_valid` |
| `closing-ref` | closings get no transcript — can't reference the opening | `prompts.py` `PRO/CON_CLOSING` take only `{memory_block}` | `relevance` (judge) |
| `opening-decisive` | moderator only sees closings, misses opening points | `prompts.py` `MODERATOR_DECISION` takes only `{pro/con_closing}` | `moderator_soundness` |
| `rebuttal-chain` | no true chaining — Con rebuts Pro's *opening*, not rebuttal | `prompts.py` `CON_REBUTTAL` takes `{pro_opening}` | `rebuttal_engagement` |

## Notes

- Keep the two eval approaches reading *this* file — don't fork the dataset.
- When adding a probe, add its row to the map above so the intent stays discoverable.
- See `tests/lang_smith/LANGSMITH_EVALS_LEARNING.md` for the general eval concepts
  (dataset → target → evaluators → experiment) these topics feed into.
</content>
