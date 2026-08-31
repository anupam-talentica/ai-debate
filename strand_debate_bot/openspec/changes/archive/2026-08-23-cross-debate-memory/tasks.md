## 1. Memory store

- [x] 1.1 Add `chromadb` to `requirements.txt`.
- [x] 1.2 Implement a Chroma-backed store satisfying `strands.memory.types.MemoryStore` (`name`, `writable`, async `search`, async `add`), using Chroma's bundled default embedding function and a local persist directory.
- [x] 1.3 Unit test: `add` then `search` on a similar query returns the added entry; `search` on an empty store returns no results.

## 2. Memory-block formatting and state

- [x] 2.1 Add a `memory_context` field to `build_invocation_state` (empty string on a fresh run).
- [x] 2.2 Add a memory-block formatting helper in `src/core/prompts.py`: joins retrieved entries, caps combined length at ~1200 characters, wraps with a "past debate context — do not reference explicitly" instruction, and returns `""` for empty input.
- [x] 2.3 Unit test the formatting helper: empty input, single entry, multiple entries exceeding the cap.

## 3. Retrieval wiring (ModeratorHub)

- [x] 3.1 On `ModeratorHub`'s `"" → "opening"` round transition, call the store's `search` with the debate topic, format the result into `invocation_state["memory_context"]`.
- [x] 3.2 Wrap the retrieval call in try/except: on any failure, set `invocation_state["memory_context"]` to `""` and log the exception; the hub's round transition still completes normally.
- [x] 3.3 Wire a `MemoryStore` instance into `ModeratorHub`'s construction (`src/core/graph.py`).
- [x] 3.4 Test: hub transition on a store with a similar prior entry populates `memory_context`; on an empty store it stays `""`; on a store whose `search` raises, it stays `""` and no exception propagates.

## 4. Injecting memory into every Pro/Con turn

- [x] 4.1 Splice `invocation_state["memory_context"]` into `pro_opening_prompt`, `con_opening_prompt`, `pro_rebuttal_prompt`, `con_rebuttal_prompt`, `pro_closing_prompt`, and `con_closing_prompt`.
- [x] 4.2 Extend `tests/test_graph.py`'s rendered-prompt assertions: when a store returns a hit, the memory block's text appears in each of the six prompts above; when it returns nothing, none of them contain a memory block.

## 5. Persisting a completed debate (ModeratorDecision)

- [x] 5.1 Build a debate summary (topic, truncated Pro/Con openings, winner) once `winner`/`justification` are set in `ModeratorDecision`.
- [x] 5.2 Call the store's `add` with that summary, exactly once per completed debate.
- [x] 5.3 Wire the same `MemoryStore` instance into `ModeratorDecision`'s construction (`src/core/graph.py`, `moderator_decision_node`).
- [x] 5.4 Test: after a debate completes, the store's `add` was called exactly once with a summary containing the topic and winner.

## 6. End-to-end acceptance

- [x] 6.1 Test (TRD Task 3's bar): run a full debate to completion against a real (or fake, in-memory) store; run a second debate on a similar topic; assert the second debate's opening/rebuttal/closing prompts contain content traceable to the first debate's persisted summary.
- [x] 6.2 Test: run a debate as the very first one against a cold, empty store; assert it completes normally with no memory block in any prompt and no error.
