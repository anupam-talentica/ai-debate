# Technical Requirements Document: Real-Time Multi-Agent Debate Chatbot — MVP

## Overview

This document defines the technical requirements for the MVP of a real-time multi-agent debate chatbot. The primary deliverable is a **Jupyter Notebook** that runs a structured, streamed debate between three LangGraph agents and demonstrates meaningful use of in-memory vector storage across debates.

---

## Technology Stack

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

## Task Index

Each task below implements one Epic. Tasks are designed to be completed sequentially — each builds on the previous.

| Task File | Epic | Description |
|-----------|------|-------------|
| [TRD1.md](TRD1.md) | Epic 0: Repository Scaffolding | Project structure, dependencies, config, and dev environment |
| [TRD2.md](TRD2.md) | Epic 1: Shared State & Prompt Templates | DebateState schema and all prompt templates |
| [TRD3.md](TRD3.md) | Epic 2: Core Agent Setup | Moderator, Pro, and Con agent nodes |
| [TRD4.md](TRD4.md) | Epic 3: LangGraph Debate Flow | StateGraph wiring and full round sequencing |
| [TRD5.md](TRD5.md) | Epic 4: Vector Memory Integration | InMemoryVectorStore upsert and retrieval |
| [TRD6.md](TRD6.md) | Epic 5: Streaming Output | Token-level streaming and Jupyter display |
| [TRD7.md](TRD7.md) | Epic 6: Jupyter Notebook Assembly | Final notebook wiring all modules together |

---

## Repository Layout

```
debate_bot/
├── TRD/                   # This document and all task files
│   ├── TRD.md
│   ├── TRD1.md … TRD7.md
├── debate.ipynb           # Primary deliverable
├── state.py               # DebateState TypedDict         (→ TRD2)
├── prompts.py             # Prompt templates              (→ TRD2)
├── memory.py              # InMemoryVectorStore wrapper   (→ TRD5)
├── graph.py               # StateGraph definition         (→ TRD4)
├── agents/
│   ├── __init__.py
│   ├── moderator.py       # moderator_open, moderator_decision  (→ TRD3)
│   ├── pro.py             # pro_opening, pro_rebuttal, pro_closing (→ TRD3)
│   └── con.py             # con_opening, con_rebuttal, con_closing (→ TRD3)
├── .env.example
└── requirements.txt
```

---

## Token Optimisation Rules (apply across all tasks)

| Rule | Requirement |
|------|-------------|
| Compact memory records | Store only 200-char excerpts of pro/con openings, not full transcripts |
| Memory injection cap | Hard cap of 300 tokens on `memory_block` injected per prompt |
| Word-limit instructions | Every prompt explicitly states the target word count |
| No redundant system prompt | Role instructions set once per agent instance, not rebuilt per call |

---

## Out of Scope (MVP)

- Persistent vector store (ChromaDB / Pinecone)
- Web UI or REST API
- Moderator memory-relevance filtering
- Automated test suite
- Structured logging
- Word-count enforcement beyond prompt instructions
