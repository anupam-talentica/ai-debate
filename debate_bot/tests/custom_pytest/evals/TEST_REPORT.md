# Debate Bot — Eval Test Report

## 1. Objective

Verify that the LangGraph debate pipeline (opening → rebuttal → closing → moderator decision) produces complete, well-formed, on-topic debates across a range of topics, including adversarial edge cases designed to stress known weak points (winner parsing, word-count enforcement, argument continuity).

## 2. Test Environment

- Debate model under test: `claude-haiku-4-5-20251001`
- Judge model (grades quality, never the same model that debated): `claude-sonnet-5`
- Harness: `python -m tests.custom_pytest.evals.run_evals`
- Topics run this pass: **3**

## 3. Test Data

One dataset topic = one test case. `note` records why the topic is in the dataset (baseline coverage vs. a specific edge case being stressed).

| id | topic | why this topic exists |
|---|---|---|
| ai-jobs | AI will replace software engineers | baseline well-formed topic |
| one-word | Pineapple | degenerate/short topic — stresses relevance |
| winner-trap | Pro athletes are overpaid | topic contains 'Pro' substring — stresses the brittle winner parser (moderator.py:40-53) |

## 4. Results Overview

Judge success rate: **100%** (judge calls that returned parseable scores)

| check | pass-rate |
|---|---|
| Winner resolves to Pro/Con | 0% |
| All transcript fields populated | 100% |
| Opening statements within word cap | 100% |
| Rebuttals within word cap | 33% |
| Closings within word cap | 100% |
| Moderator summary is structurally complete | 100% |

| quality axis | mean (1-5) |
|---|---|
| relevance | 5.0 |
| persuasiveness | 4.0 |
| rebuttal_engagement | 4.0 |
| moderator_soundness | 1.0 |

## 5. Detailed Test Case Results

### Test case: `ai-jobs`

**Objective:** baseline well-formed topic

**Test data (input topic):** "AI will replace software engineers"

**Method:** ran a full debate via `app.run_debate(topic)` through the LangGraph pipeline, then scored the resulting state deterministically and via the LLM judge.

**Assertions (deterministic):**

| check | expected | actual | result | why |
|---|---|---|---|---|
| Winner resolves to Pro/Con | winner is exactly 'Pro' or 'Con' | winner = 'Con**' | ❌ | does not exactly match 'Pro' or 'Con' — likely leftover formatting (e.g. markdown bold) from the raw model output. |
| All transcript fields populated | all 6 transcript fields non-empty | all fields present | ✅ | every stage produced output. |
| Opening statements within word cap | both sides <= 250w | Pro 215w / Con n/a (older run — con-side count not captured) (cap 250w) | ✅ | both sides stayed within the cap. |
| Rebuttals within word cap | both sides <= 130w | Pro 137w / Con n/a (older run — con-side count not captured) (cap 130w) | ❌ | Pro exceeds by 7w |
| Closings within word cap | both sides <= 100w | Pro 68w / Con n/a (older run — con-side count not captured) (cap 100w) | ✅ | both sides stayed within the cap. |
| Moderator summary is structurally complete | summary mentions Pro, mentions Con, and declares a winner | all 3 parts present | ✅ | — |

**Quality ratings (LLM judge, 1-5):**

| axis | rubric | score | verdict |
|---|---|---|---|
| relevance | Do the arguments stay on the stated topic? | 5 | Good |
| persuasiveness | Are the arguments specific, well-reasoned, and compelling? | 4 | Good |
| rebuttal_engagement | Does the rebuttal address the other side's actual points? | 4 | Good |
| moderator_soundness | Is the moderator's decision justified by the debate transcript? | 1 | Poor |

### Test case: `one-word`

**Objective:** degenerate/short topic — stresses relevance

**Test data (input topic):** "Pineapple"

**Method:** ran a full debate via `app.run_debate(topic)` through the LangGraph pipeline, then scored the resulting state deterministically and via the LLM judge.

**Assertions (deterministic):**

| check | expected | actual | result | why |
|---|---|---|---|---|
| Winner resolves to Pro/Con | winner is exactly 'Pro' or 'Con' | winner = 'Con**' | ❌ | does not exactly match 'Pro' or 'Con' — likely leftover formatting (e.g. markdown bold) from the raw model output. |
| All transcript fields populated | all 6 transcript fields non-empty | all fields present | ✅ | every stage produced output. |
| Opening statements within word cap | both sides <= 250w | Pro 206w / Con n/a (older run — con-side count not captured) (cap 250w) | ✅ | both sides stayed within the cap. |
| Rebuttals within word cap | both sides <= 130w | Pro 112w / Con n/a (older run — con-side count not captured) (cap 130w) | ✅ | both sides stayed within the cap. |
| Closings within word cap | both sides <= 100w | Pro 77w / Con n/a (older run — con-side count not captured) (cap 100w) | ✅ | both sides stayed within the cap. |
| Moderator summary is structurally complete | summary mentions Pro, mentions Con, and declares a winner | all 3 parts present | ✅ | — |

**Quality ratings (LLM judge, 1-5):**

| axis | rubric | score | verdict |
|---|---|---|---|
| relevance | Do the arguments stay on the stated topic? | 5 | Good |
| persuasiveness | Are the arguments specific, well-reasoned, and compelling? | 4 | Good |
| rebuttal_engagement | Does the rebuttal address the other side's actual points? | 4 | Good |
| moderator_soundness | Is the moderator's decision justified by the debate transcript? | 1 | Poor |

### Test case: `winner-trap`

**Objective:** topic contains 'Pro' substring — stresses the brittle winner parser (moderator.py:40-53)

**Test data (input topic):** "Pro athletes are overpaid"

**Method:** ran a full debate via `app.run_debate(topic)` through the LangGraph pipeline, then scored the resulting state deterministically and via the LLM judge.

**Assertions (deterministic):**

| check | expected | actual | result | why |
|---|---|---|---|---|
| Winner resolves to Pro/Con | winner is exactly 'Pro' or 'Con' | winner = 'Pro**' | ❌ | does not exactly match 'Pro' or 'Con' — likely leftover formatting (e.g. markdown bold) from the raw model output. |
| All transcript fields populated | all 6 transcript fields non-empty | all fields present | ✅ | every stage produced output. |
| Opening statements within word cap | both sides <= 250w | Pro 211w / Con n/a (older run — con-side count not captured) (cap 250w) | ✅ | both sides stayed within the cap. |
| Rebuttals within word cap | both sides <= 130w | Pro 131w / Con n/a (older run — con-side count not captured) (cap 130w) | ❌ | Pro exceeds by 1w |
| Closings within word cap | both sides <= 100w | Pro 77w / Con n/a (older run — con-side count not captured) (cap 100w) | ✅ | both sides stayed within the cap. |
| Moderator summary is structurally complete | summary mentions Pro, mentions Con, and declares a winner | all 3 parts present | ✅ | — |

**Quality ratings (LLM judge, 1-5):**

| axis | rubric | score | verdict |
|---|---|---|---|
| relevance | Do the arguments stay on the stated topic? | 5 | Good |
| persuasiveness | Are the arguments specific, well-reasoned, and compelling? | 4 | Good |
| rebuttal_engagement | Does the rebuttal address the other side's actual points? | 4 | Good |
| moderator_soundness | Is the moderator's decision justified by the debate transcript? | 1 | Poor |

## 6. Defects Found

### Winner resolves to Pro/Con — failed 3/3 (100%)

Affected test cases: `ai-jobs`, `one-word`, `winner-trap`

**Likely root cause:** moderator.py:40-53 extracts the winner with a keyword/regex scan but never strips markdown emphasis or trailing punctuation from the raw LLM output (e.g. '**Con**' survives as 'Con**'), so the result rarely matches 'Pro'/'Con' exactly.

### Rebuttals within word cap — failed 2/3 (67%)

Affected test cases: `ai-jobs`, `winner-trap`

**Likely root cause:** the rebuttal prompt's 130-word cap (prompts.py) is a soft instruction to the model, not an enforced truncation — the model regularly overshoots it.

## 7. Conclusion

**Overall: FAIL.** `winner_valid` is below the 90% CI gate (`test_evals.py`) — this pipeline is not ready to rely on the moderator's winner field until the parser is fixed.
