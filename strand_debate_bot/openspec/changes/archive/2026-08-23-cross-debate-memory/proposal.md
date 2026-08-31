## Why

The debate bot's Strands rewrite currently runs a full debate with no memory of any prior debate (PRD G2, TRD Task 3) — every topic starts cold, even a near-repeat of one already debated. The old LangGraph system's cross-debate RAG memory is the parity bar this change restores, but rebuilt to fit Strands' primitives and this graph's stateless-per-turn node design rather than ported as-is.

## What Changes

- Add a custom Chroma-backed store implementing `strands.memory.types.MemoryStore` (`search` + `add`), using Chroma's bundled default embedding function (ONNX MiniLM) rather than the old `langchain_huggingface`/`sentence-transformers` dependency, to keep the local footprint small.
- Call the store's `search`/`add` directly from node code. `strands.memory.MemoryManager`'s tool/injection machinery is not used — it assumes one `Agent` deciding for itself, mid-conversation, when to recall/store facts about "the user," which does not fit a deterministic once-per-debate retrieve/write driven by `invocation_state["topic"]`, and a model-visible `search_memory` tool would contradict the requirement that retrieved context not be referenced explicitly.
- Retrieve up to 2 semantically similar past-debate summaries once per run, inside the `moderator` hub's one-time `"" → "opening"` round transition, capped at ~1200 characters combined, and store the formatted block in `invocation_state["memory_context"]`. The call is wrapped so any store failure degrades to an empty context rather than blocking the debate — memory is best-effort, matching the old system's normal cold-start behavior (empty store → empty context).
- Thread `invocation_state["memory_context"]` through every Pro/Con opening/rebuttal/closing prompt builder for the rest of the run, not just the opening — each turn's `Agent` is freshly constructed and stateless, so nothing carries over unless each prompt builder explicitly splices the block in.
- Persist a debate summary (topic, truncated Pro/Con openings, winner) after the verdict, from a single write site: inside `moderator_decision_node`, immediately after `winner`/`justification` are computed — replacing the old system's pattern of calling the write from every API/service call site that could complete a debate.

## Capabilities

### New Capabilities
- `cross-debate-memory`: Retrieval of similar past-debate context before a new debate's arguments are generated, non-explicit injection of that context into every Pro/Con turn, and persistence of a completed debate's summary for future retrieval.

### Modified Capabilities
(none — round order, adversarial coupling, and verdict structure in `debate-graph-orchestration` are unchanged; memory retrieval/write are additional effects on existing nodes, not changes to their documented behavior)

## Impact

- New module implementing the Chroma-backed `MemoryStore` (search/add, embedding setup, on-disk persistence directory).
- `src/core/state.py`: `build_invocation_state` gains a `memory_context` field (empty string on a fresh run).
- `src/agents/moderator.py`: `ModeratorHub` performs the one retrieval call on the opening transition; `ModeratorDecision` performs the one write call after the verdict.
- `src/core/prompts.py`: every Pro/Con opening/rebuttal/closing prompt builder splices `memory_context` in; a `format_memory_block`-equivalent helper (1200-char cap, "do not reference explicitly" instruction) is added.
- `requirements.txt`: add `chromadb`.
- Test coverage: extends the existing rendered-prompt-assertion test idiom (`tests/test_graph.py`) to cover memory-block presence/content across turns, plus store-level tests for retrieval, cap, and failure degradation.
