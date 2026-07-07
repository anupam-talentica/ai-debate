# TRD3 — Epic 2: Core Agent Setup

## Goal
Implement the three agent modules (Moderator, Pro, Con) as LangGraph-compatible async node functions. Each function reads from `DebateState`, calls the LLM, and returns a partial state update.

---

## Deliverables

| File | Nodes defined |
|------|--------------|
| `agents/moderator.py` | `moderator_open`, `moderator_checkpoint`, `moderator_decision` |
| `agents/pro.py` | `pro_opening`, `pro_rebuttal`, `pro_closing` |
| `agents/con.py` | `con_opening`, `con_rebuttal`, `con_closing` |

---

## Requirements

### R3.1 — LLM Instantiation

Each agent module instantiates the LLM once at module level (not per call):

```python
import os
from langchain_anthropic import ChatAnthropic

llm = ChatAnthropic(
    model=os.getenv("MODEL_NAME", "claude-haiku-4-5-20251001"),
    streaming=True,
)
```

`streaming=True` is required on all instances — this enables `.astream_events()` in the graph.

### R3.2 — Node Function Signature

Every node function must follow this signature:

```python
async def node_name(state: DebateState) -> dict:
    ...
    return {"field_name": result_text}
```

Return value is a **partial state dict** — only the fields this node writes. LangGraph merges it into the full state automatically.

### R3.3 — Node Responsibilities

#### `agents/moderator.py`

**`moderator_open(state)`**
- Sets `state["round"] = "opening"`
- Returns `{"round": "opening"}` — no LLM call needed

**`moderator_checkpoint(state)`**
- Advances `state["round"]` to the next round using a fixed transition table — no LLM call needed
- Called after every pair of Pro/Con turns; visited exactly 3 times per debate
- Returns a partial state dict with the updated `round` value only

```python
ROUND_TRANSITIONS = {
    "opening":  "rebuttal",
    "rebuttal": "closing",
    "closing":  "decision",
}

async def moderator_checkpoint(state: DebateState) -> dict:
    next_round = ROUND_TRANSITIONS.get(state["round"], "decision")
    return {"round": next_round}
```

The `route_after_checkpoint` function in `graph.py` reads the already-updated `round` value and branches accordingly.

**`moderator_decision(state)`**
- Builds prompt from `MODERATOR_DECISION` template
- Calls LLM with `pro_closing` and `con_closing` as input
- Parses winner from response (look for "Winner:" label or first proper noun after justification)
- Returns `{"moderator_summary": <full text>, "winner": <extracted winner>}`

#### `agents/pro.py`

**`pro_opening(state)`**
- Retrieves `memory_context` from state
- Builds prompt from `PRO_OPENING` template
- Returns `{"pro_opening": <text>}`

**`pro_rebuttal(state)`**
- Injects `state["con_opening"]` into `PRO_REBUTTAL` template
- Returns `{"pro_rebuttal": <text>}`

**`pro_closing(state)`**
- Injects `state["con_rebuttal"]` into `PRO_CLOSING` template
- Returns `{"pro_closing": <text>}`

#### `agents/con.py`
Mirror of `agents/pro.py` — same pattern, opposite role and opposing turn references.

### R3.4 — Memory Context Usage

Pro and Con opening nodes must call `retrieve_context` from `memory.py` before building their prompt:

```python
from memory import retrieve_context

async def pro_opening(state: DebateState) -> dict:
    context = retrieve_context(state["topic"])
    memory_block = build_memory_block(context)
    prompt = PRO_OPENING.format(topic=state["topic"], memory_block=memory_block)
    response = await llm.ainvoke(prompt)
    return {"pro_opening": response.content, "memory_context": context}
```

Rebuttal and closing nodes do **not** re-retrieve memory — context is already in state.

### R3.5 — No Side Effects

Agent nodes must not write to the vector store. Upsert is handled exclusively in `memory.py` and called after `moderator_decision` completes (see TRD5).

---

## Acceptance Criteria

- [ ] Each node function is `async` and returns a `dict`
- [ ] LLM is instantiated once per module, not per call
- [ ] `streaming=True` is set on all LLM instances
- [ ] `moderator_checkpoint` makes no LLM call and returns only `{"round": <next>}`
- [ ] Pro and Con opening nodes call `retrieve_context`
- [ ] Rebuttal nodes include the opposing agent's prior turn in the prompt
- [ ] No node writes to the vector store directly

---

## Dependencies
- TRD1 (scaffolding)
- TRD2 (state schema and prompt templates)
