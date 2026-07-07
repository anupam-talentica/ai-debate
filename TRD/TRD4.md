# TRD4 — Epic 3: LangGraph Debate Flow

## Goal
Wire all agent nodes into a `StateGraph` where the Moderator acts as a **gatekeeper between every round**, using conditional edges to advance the debate through Opening → Rebuttal → Closing → Decision in an iterative loop pattern.

---

## Deliverables

| File | Purpose |
|------|---------|
| `graph.py` | `StateGraph` definition, node registration, conditional edge routing, compiled `debate_graph` export |

---

## Flow Design

The Moderator does not just open and close — it checkpoints between every round. After each pair of Pro/Con turns, control returns to `moderator_checkpoint`, which advances `state["round"]` and conditionally routes to the next round.

```
moderator_open              (sets round = "opening")
  → pro_opening → con_opening
  → moderator_checkpoint    (sets round = "rebuttal", routes → pro_rebuttal)
  → pro_rebuttal → con_rebuttal
  → moderator_checkpoint    (sets round = "closing",  routes → pro_closing)
  → pro_closing → con_closing
  → moderator_checkpoint    (sets round = "decision", routes → moderator_decision)
  → moderator_decision
  → END
```

---

## Requirements

### R4.1 — Graph Definition

```python
# graph.py
from langgraph.graph import StateGraph, END
from state import DebateState
from agents.moderator import moderator_open, moderator_checkpoint, moderator_decision
from agents.pro import pro_opening, pro_rebuttal, pro_closing
from agents.con import con_opening, con_rebuttal, con_closing

def route_after_checkpoint(state: DebateState) -> str:
    """Read state["round"] (already advanced by moderator_checkpoint) and route."""
    if state["round"] == "rebuttal":
        return "pro_rebuttal"
    elif state["round"] == "closing":
        return "pro_closing"
    else:  # "decision"
        return "moderator_decision"

def build_graph() -> StateGraph:
    g = StateGraph(DebateState)

    # Register nodes
    g.add_node("moderator_open",        moderator_open)
    g.add_node("pro_opening",           pro_opening)
    g.add_node("con_opening",           con_opening)
    g.add_node("moderator_checkpoint",  moderator_checkpoint)
    g.add_node("pro_rebuttal",          pro_rebuttal)
    g.add_node("con_rebuttal",          con_rebuttal)
    g.add_node("pro_closing",           pro_closing)
    g.add_node("con_closing",           con_closing)
    g.add_node("moderator_decision",    moderator_decision)

    # Entry point
    g.set_entry_point("moderator_open")

    # Round 1 — Opening
    g.add_edge("moderator_open",       "pro_opening")
    g.add_edge("pro_opening",          "con_opening")
    g.add_edge("con_opening",          "moderator_checkpoint")

    # Moderator checkpoint: conditional branch
    g.add_conditional_edges(
        "moderator_checkpoint",
        route_after_checkpoint,
        {
            "pro_rebuttal":      "pro_rebuttal",
            "pro_closing":       "pro_closing",
            "moderator_decision": "moderator_decision",
        },
    )

    # Round 2 — Rebuttal (loops back to checkpoint)
    g.add_edge("pro_rebuttal",         "con_rebuttal")
    g.add_edge("con_rebuttal",         "moderator_checkpoint")

    # Round 3 — Closing (loops back to checkpoint)
    g.add_edge("pro_closing",          "con_closing")
    g.add_edge("con_closing",          "moderator_checkpoint")

    # Round 4 — Decision
    g.add_edge("moderator_decision",   END)

    return g

debate_graph = build_graph().compile()
```

### R4.2 — `moderator_checkpoint` Node

Defined in `agents/moderator.py`. Advances `state["round"]` — no LLM call needed:

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

The router function `route_after_checkpoint` reads the **already-updated** `state["round"]` to decide the next node.

### R4.3 — Routing Table

| `state["round"]` when checkpoint runs | Checkpoint sets round to | Router sends to |
|----------------------------------------|--------------------------|-----------------|
| `"opening"` | `"rebuttal"` | `pro_rebuttal` |
| `"rebuttal"` | `"closing"` | `pro_closing` |
| `"closing"` | `"decision"` | `moderator_decision` |

### R4.4 — Initial State

```python
initial_state: DebateState = {
    "topic": topic,
    "round": "opening",       # must be "opening" — drives first checkpoint transition
    "pro_opening": "",
    "con_opening": "",
    "pro_rebuttal": "",
    "con_rebuttal": "",
    "pro_closing": "",
    "con_closing": "",
    "moderator_summary": "",
    "winner": "",
    "memory_context": [],
}
```

> **Important:** `round` must be initialised to `"opening"` (not `""`). The checkpoint reads this value to determine the transition.

### R4.5 — Graph Invocation Interface

| Mode | Method | Used by |
|------|--------|---------|
| Streaming (primary) | `debate_graph.astream_events(initial_state, version="v2")` | Notebook (TRD6) |
| Blocking (debug) | `await debate_graph.ainvoke(initial_state)` | Quick verification |

### R4.6 — Post-Graph Memory Upsert

```python
final_state = await debate_graph.ainvoke(initial_state)
upsert_debate(final_state)   # defined in memory.py (TRD5)
```

For streaming mode, upsert is called after the event stream is exhausted.

---

## Acceptance Criteria

- [ ] `from graph import debate_graph` imports without error
- [ ] `await debate_graph.ainvoke(initial_state)` returns a complete `DebateState` with all fields populated
- [ ] All 9 nodes are registered (`moderator_checkpoint` is new vs prior design)
- [ ] `moderator_checkpoint` is visited exactly 3 times during a full debate run
- [ ] Node execution order matches: open → pro/con opening → checkpoint → pro/con rebuttal → checkpoint → pro/con closing → checkpoint → decision
- [ ] Changing `initial_state["round"]` to `"rebuttal"` skips the opening round and starts at rebuttal (useful for debugging)

---

## Dependencies
- TRD1 (scaffolding)
- TRD2 (DebateState — `round` field must support `"opening"`, `"rebuttal"`, `"closing"`, `"decision"`)
- TRD3 (all agent nodes including `moderator_checkpoint`)
