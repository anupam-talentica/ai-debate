# Architecture: Real-Time Multi-Agent Debate Chatbot — MVP

## Stack
| Layer | Choice |
|-------|--------|
| Orchestration | LangGraph (StateGraph) |
| LLM | Anthropic Claude (claude-haiku-4-5-20251001) via `langchain-anthropic` |
| Memory | LangChain `InMemoryVectorStore` + `OpenAIEmbeddings` or `HuggingFaceEmbeddings` |
| Streaming | LangChain `.astream_events()` |
| CLI | Python `argparse` |

---

## High-Level Component Diagram

```
User (CLI)
    │
    ▼
main.py  ──── argparse ──── --topic "..."
    │
    ▼
DebateGraph (LangGraph StateGraph)
    │
    ├── [node] moderator_open        → sets round = "opening", no LLM call
    ├── [node] pro_opening           → ~200-word opening argument
    ├── [node] con_opening           → ~200-word opening argument
    ├── [node] moderator_checkpoint  → advances round, conditional branch (×3, no LLM call)
    ├── [node] pro_rebuttal          → ~100-word rebuttal (reads con_opening)
    ├── [node] con_rebuttal          → ~100-word rebuttal (reads pro_opening)
    ├── [node] pro_closing           → ~75-word closing
    ├── [node] con_closing           → ~75-word closing
    └── [node] moderator_decision    → summary + winner declaration
            │
            ▼
    MemoryStore (InMemoryVectorStore)
        • upsert debate record after moderator_decision
        • query top-2 similar past debates before pro/con nodes
```

---

## LangGraph State Schema

```python
class DebateState(TypedDict):
    topic: str
    round: str                    # "opening" | "rebuttal" | "closing" | "decision"
    pro_opening: str
    con_opening: str
    pro_rebuttal: str
    con_rebuttal: str
    pro_closing: str
    con_closing: str
    moderator_summary: str
    winner: str
    memory_context: list[str]     # retrieved past debate snippets
```

---

## Graph Edge Flow

The Moderator acts as a **gatekeeper between every round**. `moderator_checkpoint` is a single node visited 3 times — it advances `state["round"]` and uses a conditional edge to route to the correct next node.

```
START
  └─► moderator_open              (sets round = "opening")
        └─► pro_opening
              └─► con_opening
                    └─► moderator_checkpoint ──► (round → "rebuttal") ──► pro_rebuttal
                                                                                └─► con_rebuttal
                                                                                      └─► moderator_checkpoint ──► (round → "closing") ──► pro_closing
                                                                                                                                                └─► con_closing
                                                                                                                                                      └─► moderator_checkpoint ──► (round → "decision") ──► moderator_decision
                                                                                                                                                                                                                    └─► END
```

Simplified linear view:

```
moderator_open
  → pro_opening → con_opening
  → moderator_checkpoint        [round: "opening" → "rebuttal"]
  → pro_rebuttal → con_rebuttal
  → moderator_checkpoint        [round: "rebuttal" → "closing"]
  → pro_closing → con_closing
  → moderator_checkpoint        [round: "closing" → "decision"]
  → moderator_decision
  → END
```

### Conditional Routing

```python
def route_after_checkpoint(state: DebateState) -> str:
    if state["round"] == "rebuttal":  return "pro_rebuttal"
    if state["round"] == "closing":   return "pro_closing"
    return "moderator_decision"
```

| Checkpoint visit | round before | sets round to | routes to |
|-----------------|--------------|---------------|-----------|
| 1st | `"opening"` | `"rebuttal"` | `pro_rebuttal` |
| 2nd | `"rebuttal"` | `"closing"` | `pro_closing` |
| 3rd | `"closing"` | `"decision"` | `moderator_decision` |

---

## Memory Design

```
InMemoryVectorStore
  │
  ├── Document per debate:
  │     content : "<topic> | Pro: <pro_opening> | Con: <con_opening> | Winner: <winner>"
  │     metadata: { topic, winner, timestamp }
  │
  └── Retrieval:
        query  = current topic string
        top_k  = 2
        inject = prepended to system prompt of pro/con nodes as "Past debate context:"
```

No persistence across process restarts in MVP — swap `InMemoryVectorStore` for ChromaDB to add persistence (one-line change behind an interface).

---

## Streaming

Each LangGraph node calls the LLM with streaming enabled. The CLI runner uses `.astream_events()` and prints:

1. A **status label** when a node starts (`on_chain_start` event)
2. **Token chunks** as they arrive (`on_llm_stream` event)

```
─────────────────────────────────────
Pro Agent — Opening Round
─────────────────────────────────────
AI has the potential to transform hiring by...  ← tokens stream here

─────────────────────────────────────
Con Agent — Opening Round
─────────────────────────────────────
While efficiency gains are real, the risks...
```

---

## Project Layout

```
debate_bot/
├── main.py              # CLI entrypoint, runs the graph
├── graph.py             # LangGraph StateGraph definition + node wiring
├── agents/
│   ├── moderator.py     # moderator_open, moderator_checkpoint, moderator_decision nodes
│   ├── pro.py           # pro_opening, pro_rebuttal, pro_closing nodes
│   └── con.py           # con_opening, con_rebuttal, con_closing nodes
├── memory.py            # InMemoryVectorStore wrapper (upsert + retrieve)
├── state.py             # DebateState TypedDict
├── prompts.py           # System/human prompt templates per role & round
├── .env.example         # ANTHROPIC_API_KEY, MODEL_NAME
└── requirements.txt
```

---

## Key Dependencies

```
langgraph
langchain-anthropic
langchain-core
python-dotenv
```

---

## Data Flow per Agent Node

```
1. Retrieve top-2 past debates from MemoryStore (by topic similarity)
2. Build prompt:
     system = role instructions + past debate context (if any)
     human  = topic + prior turns relevant to this round
3. Stream LLM response → print tokens to stdout
4. Write completed text back to DebateState
```

After `moderator_decision` completes, the full debate is upserted into MemoryStore.

---

## Configuration (`.env`)

```
ANTHROPIC_API_KEY=sk-...
MODEL_NAME=claude-haiku-4-5-20251001
```

App exits with a descriptive error if either var is missing.
