# TRD7 — Epic 6: Jupyter Notebook Assembly

## Goal
Assemble all modules into `debate.ipynb` — the primary deliverable. Each cell has a single responsibility. The notebook must run top-to-bottom without errors and serve as a self-contained demo.

---

## Deliverables

| File | Purpose |
|------|---------|
| `debate.ipynb` | Primary deliverable — full end-to-end debate demo |

---

## Notebook Cell Specification

### Cell 1 — Environment Setup
**Purpose:** Load credentials, imports, instantiate shared objects.

```python
# Cell 1: Setup
import os
from dotenv import load_dotenv
from IPython.display import display, Markdown

load_dotenv()

if not os.getenv("ANTHROPIC_API_KEY"):
    raise EnvironmentError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill in your key.")

from graph import debate_graph
from memory import upsert_debate, retrieve_context

print("Setup complete. Model:", os.getenv("MODEL_NAME", "claude-haiku-4-5-20251001"))
```

**Expected output:** `Setup complete. Model: claude-haiku-4-5-20251001`

---

### Cell 2 — Topic Input
**Purpose:** Single variable the user changes to run a different debate.

```python
# Cell 2: Set debate topic
topic = "Should AI be used in hiring?"
print(f"Topic: {topic}")
```

**Note:** This is the only cell that needs editing between runs.

---

### Cell 3 — Memory Retrieval Preview
**Purpose:** Show what past debates (if any) will inform this run. Makes memory behaviour visible.

```python
# Cell 3: Preview memory context
context = retrieve_context(topic)

if context:
    display(Markdown("### Memory Context (retrieved for this topic)"))
    for i, c in enumerate(context, 1):
        display(Markdown(f"**Past debate {i}:**\n> {c}"))
else:
    display(Markdown("_No past debates found. Agents will argue from scratch._"))
```

**Expected output (first run):** `No past debates found. Agents will argue from scratch.`
**Expected output (subsequent runs):** Displays top-2 matching past debate summaries.

---

### Cell 4 — Run Debate (Streaming)
**Purpose:** Execute the graph and stream the full debate to the notebook output.

```python
# Cell 4: Run the debate (streaming)
NODE_LABELS = {
    "moderator_open":     None,
    "pro_opening":        "Pro Agent — Opening Round",
    "con_opening":        "Con Agent — Opening Round",
    "pro_rebuttal":       "Pro Agent — Rebuttal",
    "con_rebuttal":       "Con Agent — Rebuttal",
    "pro_closing":        "Pro Agent — Closing Remarks",
    "con_closing":        "Con Agent — Closing Remarks",
    "moderator_decision": "Moderator — Final Decision",
}

initial_state = {
    "topic": topic, "round": "", "pro_opening": "", "con_opening": "",
    "pro_rebuttal": "", "con_rebuttal": "", "pro_closing": "", "con_closing": "",
    "moderator_summary": "", "winner": "", "memory_context": [],
}

async def stream_debate():
    async for event in debate_graph.astream_events(initial_state, version="v2"):
        kind = event["event"]
        node = event.get("name", "")

        if kind == "on_chain_start" and NODE_LABELS.get(node):
            display(Markdown(f"\n---\n### {NODE_LABELS[node]}\n"))

        if kind == "on_llm_stream":
            chunk = event["data"]["chunk"]
            if hasattr(chunk, "content") and chunk.content:
                print(chunk.content, end="", flush=True)

        if kind == "on_chain_end" and NODE_LABELS.get(node):
            print("\n")

await stream_debate()
```

---

### Cell 5 — Moderator Decision Summary
**Purpose:** Display the winner prominently after the stream.

```python
# Cell 5: Winner declaration
final_state = await debate_graph.ainvoke(initial_state)

display(Markdown("---"))
display(Markdown(f"## Winner: {final_state['winner']}"))
display(Markdown(f"**Moderator's Justification:**\n\n{final_state['moderator_summary']}"))
```

---

### Cell 6 — Save to Memory
**Purpose:** Upsert the debate record and confirm it was saved.

```python
# Cell 6: Save debate to memory
upsert_debate(final_state)

display(Markdown("---"))
display(Markdown("**Debate saved to memory.**"))
display(Markdown(
    f"- **Topic:** {final_state['topic']}  \n"
    f"- **Winner:** {final_state['winner']}  \n"
    f"- **Pro excerpt:** {final_state['pro_opening'][:100]}…  \n"
    f"- **Con excerpt:** {final_state['con_opening'][:100]}…"
))
```

---

### Cell 7 — Re-run Instructions (Markdown)
**Purpose:** Guide the user on how to run a second debate to observe memory evolution.

```markdown
## How to demonstrate memory

1. Go back to **Cell 2** and change `topic` to a related topic (e.g., `"Should AI replace recruiters?"`)
2. Re-run cells **2 → 6** in order
3. In **Cell 3** you will now see the first debate retrieved as context
4. Notice how Pro and Con arguments in Cell 4 evolve beyond the generic points made in the first debate
```

---

## Cell Execution Order

```
Cell 1 (once per kernel session)
  └─► Cell 2 (change topic here to re-run)
        └─► Cell 3 (preview memory)
              └─► Cell 4 (stream debate)
                    └─► Cell 5 (winner display)
                          └─► Cell 6 (save to memory)
                                └─► Cell 7 (static instructions)
```

---

## Acceptance Criteria

- [ ] Notebook runs top-to-bottom without errors on a clean kernel
- [ ] Cell 1 raises `EnvironmentError` if `ANTHROPIC_API_KEY` is missing
- [ ] Cell 3 shows "No past debates found" on the first run
- [ ] Cell 4 streams tokens progressively with labelled headers per turn
- [ ] Cell 5 displays the winner name and moderator justification
- [ ] Cell 6 confirms the upsert with a summary of what was saved
- [ ] On second run with a related topic, Cell 3 displays the first debate as context

---

## Dependencies
- TRD1 (scaffolding)
- TRD2 (state, prompts)
- TRD3 (agent nodes)
- TRD4 (compiled graph)
- TRD5 (memory upsert/retrieve)
- TRD6 (streaming specification)
