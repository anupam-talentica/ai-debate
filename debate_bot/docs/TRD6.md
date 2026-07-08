# TRD6 — Epic 5: Streaming Output

## Goal
Implement token-level streaming so the debate output appears progressively in the notebook, with clear status labels before each agent turn.

---

## Deliverables

Streaming logic lives inside `debate.ipynb` Cell 4 (see TRD7). This task defines the streaming specification and the helper used by that cell.

| Concern | Location |
|---------|---------|
| Streaming event loop | `debate.ipynb` Cell 4 |
| Display helper | Inline in notebook (no separate file needed) |

---

## Requirements

### R6.1 — Streaming Method

Use `.astream_events()` with `version="v2"`:

```python
async for event in debate_graph.astream_events(initial_state, version="v2"):
    ...
```

Do **not** use `.astream()` — it returns state diffs, not token chunks.

### R6.2 — Status Label on Node Start

When a node begins execution, print a formatted header before any tokens appear:

```python
NODE_LABELS = {
    "moderator_open":     None,                         # silent — control node
    "pro_opening":        "Pro Agent — Opening Round",
    "con_opening":        "Con Agent — Opening Round",
    "pro_rebuttal":       "Pro Agent — Rebuttal",
    "con_rebuttal":       "Con Agent — Rebuttal",
    "pro_closing":        "Pro Agent — Closing Remarks",
    "con_closing":        "Con Agent — Closing Remarks",
    "moderator_decision": "Moderator — Final Decision",
}

if event["event"] == "on_chain_start":
    node = event.get("name", "")
    label = NODE_LABELS.get(node)
    if label:
        display(Markdown(f"\n---\n### {label}\n"))
```

### R6.3 — Token-Level Streaming

Print each token chunk immediately as it arrives:

```python
if event["event"] == "on_llm_stream":
    chunk = event["data"]["chunk"]
    if hasattr(chunk, "content") and chunk.content:
        print(chunk.content, end="", flush=True)
```

`flush=True` is required — without it, Jupyter buffers output until the cell finishes.

### R6.4 — Round Separator

After each agent turn completes (`on_chain_end` for a labelled node), print a blank line:

```python
if event["event"] == "on_chain_end":
    node = event.get("name", "")
    if node in NODE_LABELS and NODE_LABELS[node]:
        print("\n")
```

### R6.5 — Full Streaming Cell

The complete streaming cell in the notebook:

```python
import asyncio
from IPython.display import display, Markdown

async def run_debate(topic: str):
    initial_state = {
        "topic": topic, "round": "", "pro_opening": "", "con_opening": "",
        "pro_rebuttal": "", "con_rebuttal": "", "pro_closing": "", "con_closing": "",
        "moderator_summary": "", "winner": "", "memory_context": [],
    }

    async for event in debate_graph.astream_events(initial_state, version="v2"):
        kind = event["event"]
        node = event.get("name", "")

        if kind == "on_chain_start" and node in NODE_LABELS and NODE_LABELS[node]:
            display(Markdown(f"\n---\n### {NODE_LABELS[node]}\n"))

        if kind == "on_llm_stream":
            chunk = event["data"]["chunk"]
            if hasattr(chunk, "content") and chunk.content:
                print(chunk.content, end="", flush=True)

        if kind == "on_chain_end" and node in NODE_LABELS and NODE_LABELS[node]:
            print("\n")

    # Upsert after stream exhausted
    final_state = await debate_graph.ainvoke(initial_state)
    upsert_debate(final_state)
    return final_state

final_state = await run_debate(topic)
```

> **Note:** `debate_graph.ainvoke` is called a second time after streaming only to get the final state object for upsert. A cleaner approach (collect state from stream events) can be added post-MVP.

---

## Expected Notebook Output

```
---
### Pro Agent — Opening Round

AI has the potential to transform hiring by eliminating...  ← streams token by token


---
### Con Agent — Opening Round

While efficiency gains are real, the systemic risks...


---
### Pro Agent — Rebuttal
...

---
### Moderator — Final Decision

Pro presented a compelling case for scalability...
**Winner: Pro**
```

---

## Acceptance Criteria

- [ ] Status label appears before each agent's output
- [ ] Tokens stream progressively — no full-text delay visible in notebook
- [ ] `moderator_open` node produces no output (silent control node)
- [ ] A blank line separates each agent's turn
- [ ] `upsert_debate` is called exactly once after the stream completes

---

## Dependencies
- TRD1 (scaffolding)
- TRD4 (compiled `debate_graph`)
- TRD5 (`upsert_debate`)
