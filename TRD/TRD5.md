# TRD5 — Epic 4: Vector Memory Integration

## Goal
Implement the in-memory vector store wrapper that persists compact debate summaries after each run and retrieves semantically similar past debates before agent turns, so arguments evolve across sessions.

---

## Deliverables

| File | Purpose |
|------|---------|
| `memory.py` | `InMemoryVectorStore` wrapper with `upsert_debate` and `retrieve_context` |

---

## Requirements

### R5.1 — Embedding Model

Use a local HuggingFace embedding model to avoid a second API dependency:

```python
from langchain_huggingface import HuggingFaceEmbeddings

embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
```

The model is downloaded once on first run and cached locally by `sentence-transformers`.

### R5.2 — Vector Store Initialisation

```python
from langchain_core.vectorstores import InMemoryVectorStore

store = InMemoryVectorStore(embedding=embeddings)
```

One global `store` instance per process. Survives for the lifetime of the notebook kernel — data is lost on kernel restart (acceptable for MVP).

### R5.3 — Upsert (`upsert_debate`)

Store a **compact summary** of each debate — not the full transcript — to keep retrieval context small.

```python
def upsert_debate(state: DebateState) -> None:
    summary = (
        f"Topic: {state['topic']} | "
        f"Pro: {state['pro_opening'][:200]} | "
        f"Con: {state['con_opening'][:200]} | "
        f"Winner: {state['winner']}"
    )
    store.add_texts(
        [summary],
        metadatas=[{"topic": state["topic"], "winner": state["winner"]}],
    )
```

- Pro and Con excerpts are capped at **200 characters each**
- Total stored record is ~450 characters (~110 tokens)
- Called once per debate, after `moderator_decision` completes

### R5.4 — Retrieval (`retrieve_context`)

```python
def retrieve_context(topic: str, k: int = 2) -> list[str]:
    docs = store.similarity_search(topic, k=k)
    return [d.page_content for d in docs]
```

- Returns `[]` when the store is empty (first run)
- `k=2` is the default; do not increase for MVP
- Called by Pro and Con opening nodes only (see TRD3)

### R5.5 — Memory Block Builder

Defined in `prompts.py` (see TRD2) but tested alongside memory:

```python
def build_memory_block(context: list[str]) -> str:
    if not context:
        return ""
    joined = "\n".join(context)
    truncated = joined[:1200]   # ~300 tokens hard cap
    return (
        "Past debate context (use to evolve your arguments, "
        "do not reference explicitly):\n" + truncated
    )
```

### R5.6 — No Persistence (MVP)

Data lives in memory only. Post-MVP swap path:

```python
# Replace InMemoryVectorStore with:
from langchain_chroma import Chroma
store = Chroma(embedding_function=embeddings, persist_directory="./chroma_db")
```

No other code changes required if the `upsert_debate` / `retrieve_context` interface is preserved.

---

## Token Budget Compliance

| Item | Limit | Enforcement |
|------|-------|-------------|
| Per stored record | ~110 tokens | 200-char excerpt cap in `upsert_debate` |
| Per injected memory block | ~300 tokens | 1200-char truncation in `build_memory_block` |
| Retrievals per agent call | top-2 docs | `k=2` in `retrieve_context` |

---

## Acceptance Criteria

- [ ] `from memory import upsert_debate, retrieve_context` imports without error
- [ ] `retrieve_context("any topic")` returns `[]` on an empty store
- [ ] After one `upsert_debate(state)` call, `retrieve_context(state["topic"])` returns 1 result
- [ ] Stored record never exceeds 500 characters
- [ ] `build_memory_block([])` returns `""`
- [ ] `build_memory_block(["a" * 2000])` returns a string ≤ 1260 characters

---

## Dependencies
- TRD1 (scaffolding)
- TRD2 (DebateState, `build_memory_block`)
