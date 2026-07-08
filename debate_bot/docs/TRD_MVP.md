# Technical Requirements Document: Real-Time Multi-Agent Debate Chatbot — MVP

## 1. Overview

This document defines the technical requirements for the MVP of a real-time multi-agent debate chatbot. The primary deliverable is a **Jupyter Notebook** that runs a structured, streamed debate between three LangGraph agents and demonstrates meaningful use of in-memory vector storage across debates.

---

## 2. Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Orchestration | LangGraph `StateGraph` | Deterministic node-based flow; built-in state passing |
| LLM | `claude-haiku-4-5-20251001` via `langchain-anthropic` | Low latency, low cost, sufficient for structured argument generation |
| Memory | LangChain `InMemoryVectorStore` | Zero setup; swap to ChromaDB post-MVP with one-line change |
| Embeddings | `langchain_huggingface` (`all-MiniLM-L6-v2`) | Runs locally; no extra API key required |
| Streaming | LangChain `.astream_events()` | Token-level streaming compatible with Jupyter `display()` |
| Notebook runtime | Jupyter Notebook / JupyterLab | Demo-friendly; cell-by-cell output per debate round |
| Config | `python-dotenv` | Keeps credentials out of notebook |

---

## 3. Repository Layout

```
debate_bot/
├── debate.ipynb          # Primary deliverable — runs the full debate
├── state.py              # DebateState TypedDict
├── memory.py             # InMemoryVectorStore wrapper (upsert + retrieve)
├── prompts.py            # Prompt templates per role and round
├── agents/
│   ├── moderator.py      # moderator_open, moderator_decision nodes
│   ├── pro.py            # pro_opening, pro_rebuttal, pro_closing nodes
│   └── con.py            # con_opening, con_rebuttal, con_closing nodes
├── graph.py              # StateGraph definition and node wiring
├── .env.example          # ANTHROPIC_API_KEY, MODEL_NAME
└── requirements.txt
```

`.py` modules contain all reusable logic. The notebook imports them — keeping cells clean and logic independently testable.

---

## 4. Notebook Structure

Each cell maps to one concern. The notebook is the demo; cell output IS the debate.

| Cell | Purpose |
|------|---------|
| **Cell 1 — Setup** | `%load_ext dotenv`, imports, instantiate LLM and MemoryStore |
| **Cell 2 — Topic Input** | `topic = "Should AI be used in hiring?"` — single variable to change |
| **Cell 3 — Memory Retrieval Preview** | Show top-2 past debates retrieved for this topic (empty on first run) |
| **Cell 4 — Run Debate** | Execute `graph.astream_events(...)`, stream and display each round inline |
| **Cell 5 — Moderator Decision** | Display winner declaration prominently |
| **Cell 6 — Memory Upsert Confirmation** | Show the record saved to the vector store |
| **Cell 7 — Re-run Demo (optional)** | Change topic, re-run Cell 2 onwards to demonstrate memory evolution |

---

## 5. LangGraph State

```python
# state.py
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
    memory_context: list[str]  # top-2 retrieved past debate summaries
```

---

## 6. Graph Node Sequence

The Moderator acts as a **gatekeeper between every round**. After each pair of Pro/Con turns, control returns to `moderator_checkpoint`, which reads `state["round"]` and conditionally routes to the next round's Pro node or to the final decision.

```
START
  └─► moderator_open          (sets round = "opening")
        └─► pro_opening
              └─► con_opening
                    └─► moderator_checkpoint ──── round == "opening"  ──► pro_rebuttal
                                             │                               └─► con_rebuttal
                                             │                                     └─► moderator_checkpoint ──── round == "rebuttal" ──► pro_closing
                                             │                                                              │                               └─► con_closing
                                             │                                                              │                                     └─► moderator_checkpoint
                                             │                                                              └─── round == "closing"  ──► moderator_decision
                                             │                                                                                                └─► END
                                             └─── (unused in MVP)
```

Simplified linear view of the same flow:

```
moderator_open
  → pro_opening → con_opening
  → moderator_checkpoint        [sets round = "rebuttal"]
  → pro_rebuttal → con_rebuttal
  → moderator_checkpoint        [sets round = "closing"]
  → pro_closing → con_closing
  → moderator_checkpoint        [sets round = "decision"]
  → moderator_decision
  → END
```

### Routing Logic

```python
def route_after_checkpoint(state: DebateState) -> str:
    if state["round"] == "rebuttal":
        return "pro_rebuttal"
    elif state["round"] == "closing":
        return "pro_closing"
    else:
        return "moderator_decision"
```

`moderator_checkpoint` advances `state["round"]` before the router runs:

| Incoming round | Sets round to | Routes to |
|----------------|---------------|-----------|
| `"opening"` | `"rebuttal"` | `pro_rebuttal` |
| `"rebuttal"` | `"closing"` | `pro_closing` |
| `"closing"` | `"decision"` | `moderator_decision` |

---

## 7. Memory Design

```python
# memory.py
store = InMemoryVectorStore(embedding=HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2"))

def upsert_debate(state: DebateState) -> None:
    # Stores a compact summary — NOT full transcripts — to cap token usage
    summary = (
        f"Topic: {state['topic']} | "
        f"Pro key point: {state['pro_opening'][:200]} | "
        f"Con key point: {state['con_opening'][:200]} | "
        f"Winner: {state['winner']}"
    )
    store.add_texts([summary], metadatas=[{"topic": state["topic"]}])

def retrieve_context(topic: str, k: int = 2) -> list[str]:
    docs = store.similarity_search(topic, k=k)
    return [d.page_content for d in docs]
```

**Token budget for memory injection:** max 300 tokens of retrieved context per agent prompt. Enforced by truncating the joined summaries before injection.

---

## 8. Prompt Design

```python
# prompts.py — one template per role × round combination

PRO_OPENING = """
You are the Pro debater. Argue in favour of: "{topic}".
Write approximately 200 words. Be specific and assertive.

{memory_block}
"""

CON_REBUTTAL = """
You are the Con debater. Counter the following Pro argument in ~100 words.
Be direct. Reference at least one specific point made by Pro.

Pro's opening: {pro_opening}

{memory_block}
"""
# ... etc.
```

`{memory_block}` is either:
- `"Past debate context (use to evolve your arguments, do not reference explicitly):\n<summaries>"` — when retrievals exist
- `""` — on first run (no past debates)

---

## 9. Token Optimisation Requirements

| Technique | Requirement |
|-----------|-------------|
| Compact memory records | Store only 200-char excerpts of pro/con openings, not full transcripts |
| Memory injection cap | Hard cap of 300 tokens on `memory_block` injected per prompt |
| Word-limit instructions | Every prompt explicitly states the target word count |
| No redundant system prompt | Role instructions are set once per agent instance, not rebuilt per call |

---

## 10. Streaming Display in Notebook

```python
async for event in graph.astream_events(initial_state, version="v2"):
    if event["event"] == "on_chain_start":
        display(Markdown(f"---\n### {event['name']}"))
    if event["event"] == "on_llm_stream":
        chunk = event["data"]["chunk"].content
        print(chunk, end="", flush=True)
```

Each round's output streams token-by-token inside its cell output. No full-text delay.

---

## 11. Configuration

**`.env.example`**
```
ANTHROPIC_API_KEY=sk-ant-...
MODEL_NAME=claude-haiku-4-5-20251001
```

The notebook loads these with `%load_ext dotenv` / `load_dotenv()`. If `ANTHROPIC_API_KEY` is missing the LangChain client raises a descriptive error before the graph runs.

---

## 12. Dependencies

```
# requirements.txt
langgraph>=0.2
langchain-anthropic>=0.2
langchain-core>=0.3
langchain-huggingface>=0.1
sentence-transformers>=3.0       # backs all-MiniLM-L6-v2
python-dotenv>=1.0
jupyter>=1.0
```

---

## 13. Converting Notebook to Script (Post-MVP)

When a CLI entrypoint is needed:

```bash
jupyter nbconvert --to script debate.ipynb --output main
python main.py   # or wire argparse into the exported script
```

No code changes required in the `.py` modules — they are already importable.

---

## 14. Out of Scope (MVP)

- Persistent vector store (ChromaDB / Pinecone)
- Web UI or REST API
- Moderator memory-relevance filtering
- Automated test suite
- Structured logging
- Word-count enforcement beyond prompt instructions
