# TRD2 — Epic 1: Shared State & Prompt Templates

## Goal
Define the single shared data contract (`DebateState`) that flows through the LangGraph graph, and centralise all prompt templates so agent logic never contains hardcoded strings.

---

## Deliverables

| File | Purpose |
|------|---------|
| `state.py` | `DebateState` TypedDict — the only state object in the system |
| `prompts.py` | All prompt templates, one per role × round combination |

---

## Requirements

### R2.1 — DebateState Schema (`state.py`)

```python
from typing import TypedDict

class DebateState(TypedDict):
    topic: str
    round: str                 # "opening" | "rebuttal" | "closing" | "decision"
    pro_opening: str
    con_opening: str
    pro_rebuttal: str
    con_rebuttal: str
    pro_closing: str
    con_closing: str
    moderator_summary: str
    winner: str
    memory_context: list[str]  # top-2 retrieved past debate summaries (empty list on first run)
```

- All string fields default to `""` when not yet populated
- `memory_context` defaults to `[]`
- No additional fields may be added without updating this document

### R2.2 — Prompt Templates (`prompts.py`)

One template constant per agent turn. Each template:
- Is a plain Python string with `{named_placeholders}`
- Explicitly states the target word count
- Includes a `{memory_block}` placeholder (resolves to `""` when no past debates exist)

#### Required templates

| Constant | Agent | Round | Word Target |
|----------|-------|-------|-------------|
| `MODERATOR_OPEN` | Moderator | Open | — (control message, no word limit) |
| `PRO_OPENING` | Pro | Opening | ~200 words |
| `CON_OPENING` | Con | Opening | ~200 words |
| `PRO_REBUTTAL` | Pro | Rebuttal | ~100 words |
| `CON_REBUTTAL` | Con | Rebuttal | ~100 words |
| `PRO_CLOSING` | Pro | Closing | ~75 words |
| `CON_CLOSING` | Con | Closing | ~75 words |
| `MODERATOR_DECISION` | Moderator | Decision | ~150 words |

#### Memory block injection rule
```python
def build_memory_block(context: list[str]) -> str:
    if not context:
        return ""
    joined = "\n".join(context)
    # Hard cap: 300 tokens ≈ 1200 characters
    truncated = joined[:1200]
    return f"Past debate context (use to evolve your arguments, do not reference explicitly):\n{truncated}"
```

---

## Example Templates

```python
PRO_OPENING = """\
You are the Pro debater. Argue in favour of: "{topic}".
Write approximately 200 words. Be specific and assertive. Do not exceed 250 words.

{memory_block}
"""

CON_REBUTTAL = """\
You are the Con debater. Counter the following Pro argument in approximately 100 words.
Reference at least one specific point Pro made. Do not exceed 130 words.

Pro's opening argument:
{pro_opening}

{memory_block}
"""

MODERATOR_DECISION = """\
You are the Moderator. Review both sides and declare a winner.
Write approximately 150 words. Structure your response as:
1. One-sentence summary of Pro's strongest point.
2. One-sentence summary of Con's strongest point.
3. Winner declaration with a one-paragraph justification.

Pro closing: {pro_closing}
Con closing: {con_closing}
"""
```

---

## Acceptance Criteria

- [ ] `from state import DebateState` imports without error
- [ ] All 8 prompt template constants exist in `prompts.py`
- [ ] `build_memory_block([])` returns `""`
- [ ] `build_memory_block(["long string..."])` never exceeds 1200 characters output

---

## Dependencies
- TRD1 (scaffolding) must be complete
