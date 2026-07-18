# Test Suite Overview

This document explains **what every test in the suite does** and how the folders are organized.
It is the map for the existing pytest suite plus the three evaluation approaches that live
alongside it.

---

## 1. Directory layout

```
tests/
├── custom_pytest/            # All existing pytest tests + Approach A (evals)
│   ├── conftest.py           # Shared, reusable fixtures (mock_llm, base_state)
│   ├── core/                 # Tests of the core engine (src/core/*)
│   │   ├── test_state.py
│   │   ├── test_memory.py
│   │   └── test_graph.py
│   ├── unit_tests/           # Agent- and API-surface tests (mostly mocked)
│   │   ├── test_agents.py
│   │   ├── test_streaming.py
│   │   ├── test_edge_cases.py
│   │   ├── test_errors.py
│   │   └── test_e2e.py       # Live-server E2E (needs a running server; @pytest.mark.e2e)
│   ├── evals/                # (empty) Approach A LLM-as-judge harness lands here
│   └── PLAN.md               # Approach A implementation plan
├── lang_smith/
│   └── PLAN.md               # Approach B implementation plan
├── deepeval_promptfoo/
│   └── PLAN.md               # Approach C implementation plan
├── TESTS_OVERVIEW.md         # ← this file
└── __init__.py
```

### Why this structure

- The existing tests are all plain **pytest** tests, so they live under `custom_pytest/`.
- They split cleanly into two intents:
  - **`core/`** — exercises the core debate engine directly (`state`, `memory`, `graph`).
  - **`unit_tests/`** — exercises the agents and the HTTP/streaming API surface.
- **`evals/`** is reserved for Approach A (real-model, LLM-as-judge scoring) so the eval
  harness sits next to — but is clearly separated from — the mocked correctness tests.
- `lang_smith/` and `deepeval_promptfoo/` are the other two evaluation approaches.

### Reusable code (why there is a shared `conftest.py`)

The tests share fixtures, which is exactly why they sit under one parent package:

- **`mock_llm`** — a `MagicMock` LLM whose `ainvoke` returns `"Mock argument text."` and whose
  `astream` yields `"Mock ", "argument ", "text."`. Used by nearly every agent test so no real
  API calls happen.
- **`base_state`** — a fresh, fully-populated `DebateState` dict (topic set, all argument
  fields empty). Used as the starting state for agent-node tests.
- **`async_generator(items)`** — helper that turns a list into an async generator of
  `MagicMock(content=item)` objects, imitating `astream` output.

pytest auto-discovers `conftest.py` from the parent package, so every test under
`custom_pytest/` (in `core/`, `unit_tests/`, or `evals/`) gets these fixtures for free.

> **Known duplication (follow-up):** the `astream` helper is redefined locally as `aiter(...)`
> inside `test_graph.py`, `test_agents.py`, `test_edge_cases.py`, and `test_errors.py`. These
> are identical to `conftest.async_generator` and could be consolidated into a single shared
> fixture. Left as-is for now to keep this change a pure reorganization.

### Running the suite

```bash
cd debate_bot

# Everything except live-server E2E
pytest tests/custom_pytest -v -m "not e2e"

# Just the core engine tests
pytest tests/custom_pytest/core -v

# Just the mocked unit / API tests
pytest tests/custom_pytest/unit_tests -v -m "not e2e"

# Live E2E (requires the server running: `python server.py`)
pytest tests/custom_pytest/unit_tests/test_e2e.py -v -m e2e
```

---

## 2. What each test does

### `core/test_state.py` — DebateState schema (2 tests)

Pure, no LLM. Validates the `DebateState` TypedDict contract.

| Test | What it verifies |
|---|---|
| `test_debate_state_structure` | A fully-populated state has the right field types; `round` is one of the allowed values; `winner ∈ {"Pro","Con",""}`; `memory_context` is a list. |
| `test_debate_state_initial_empty_values` | A state can be created with all argument fields empty and the values round-trip correctly. |

### `core/test_memory.py` — MemoryStore (3 tests)

Exercises the in-memory retrieval store directly (no LLM).

| Test | What it verifies |
|---|---|
| `test_upsert_and_retrieve` | After upserting one debate, `retrieve_context` returns a relevant result for a related query. |
| `test_empty_store_returns_empty_list` | An empty store returns `[]`. |
| `test_multiple_debates_retrieved` | With two debates stored, top-k retrieval returns at most `k` results. |

### `core/test_graph.py` — LangGraph workflow (2 tests)

Builds the real graph with a **mocked** `ChatAnthropic` and runs it end-to-end.

| Test | What it verifies |
|---|---|
| `test_full_graph_runs_to_completion` | The full graph populates `pro_opening`, `con_opening`, `moderator_summary` and carries `memory_context`. |
| `test_graph_includes_memory_context` | Graph execution always includes a `memory_context` key. |

### `unit_tests/test_agents.py` — Agent nodes (9 tests)

Tests each agent node function in isolation with `mock_llm`.

| Test | What it verifies |
|---|---|
| `test_pro_opening_populates_state` | Pro produces a non-empty opening. |
| `test_con_opening_reads_pro_argument` | Con opening runs given the Pro opening as context. |
| `test_pro_rebuttal_responds_to_con` | Pro rebuttal is produced from the Con opening. |
| `test_con_rebuttal_responds_to_pro` | Con rebuttal is produced from the Pro opening. |
| `test_moderator_decision_sets_winner` | Moderator returns a `winner ∈ {"Pro","Con"}` and a non-empty summary. |
| `test_moderator_open_sets_round` | `moderator_open` sets `round == "opening"`. |
| `test_moderator_checkpoint_transitions_round` | Checkpoint advances round: opening→rebuttal→closing→decision. |
| `test_pro_closing_generates_argument` | Pro closing is non-empty. |
| `test_con_closing_generates_argument` | Con closing is non-empty. |

### `unit_tests/test_streaming.py` — SSE streaming endpoint (13 tests)

Uses FastAPI `TestClient` with `app.graph.astream` patched to a fake event generator.

| Test | What it verifies |
|---|---|
| `test_streaming_debate_receives_all_events` | `/debate/stream` returns 200 and `text/event-stream`. |
| `test_streaming_response_format` | Each SSE line is `data: {json}` and carries `node`/`error`. |
| `test_streaming_completion_event` | Stream contains a completion marker / data lines. |
| `test_streaming_with_client_disconnect` | A slow/disconnecting client doesn't crash the server. |
| `test_streaming_error_event_on_exception` | An exception mid-stream surfaces error info. |
| `test_streaming_with_empty_topic` | Empty `topic` query fails validation (422). |
| `test_streaming_cache_control_headers` | Response sets `Cache-Control: no-cache` and `X-Accel-Buffering: no`. |
| `test_streaming_multiple_concurrent_debates` | Multiple concurrent stream requests all return 200. |
| `test_streaming_state_updates_sequentially` | Multiple events are emitted in order. |
| `test_streaming_with_large_state_object` | Large state objects stream without error. |
| `test_streaming_memory_upsert_after_completion` | Memory upsert path runs without crashing. |
| `test_streaming_json_serialization_error` | Non-serializable state is handled gracefully. |
| `test_streaming_heartbeat_on_long_processing` | Long processing does not time out the response. |
| `test_streaming_response_preserves_state_field_order` | Full state serializes into ≥1 event. |

### `unit_tests/test_edge_cases.py` — Robustness / adversarial inputs (18 tests)

Odd, hostile, and boundary inputs against agents, memory, state, and HTTP.

| Test | What it verifies |
|---|---|
| `test_debate_with_empty_topic` | Empty topic is rejected by `DebateRequest` validation. |
| `test_debate_with_very_long_topic` | A 10k-char topic still produces output. |
| `test_debate_with_special_characters` | Special chars / emoji in topic are handled. |
| `test_debate_with_unicode_characters` | Unicode (CJK) topic is handled. |
| `test_debate_with_sql_injection_attempt` | SQL-injection-looking topic is treated as plain text. |
| `test_debate_with_prompt_injection` | Prompt-injection topic doesn't hijack behavior. |
| `test_debate_with_whitespace_only_topic` | Whitespace-only topic is rejected by validation. |
| `test_debate_with_newlines_in_topic` | Newlines in topic are handled. |
| `test_debate_with_very_short_llm_response` | A one-char LLM response still completes. |
| `test_debate_with_empty_memory_context` | Debate works with empty memory context. |
| `test_debate_with_large_memory_context` | Very large memory context doesn't crash. |
| `test_debate_with_null_values_in_state` | None values in state are exercised (see note). |
| `test_http_request_with_missing_topic_parameter` | `/debate/stream` without topic → 422. |
| `test_http_request_with_empty_topic_query` | `/debate/stream?topic=` → 422. |
| `test_http_post_debate_invoke_with_empty_body` | `POST /debate/invoke {}` → 422. |
| `test_state_with_mismatched_field_types` | Wrong field types documented against `DebateState`. |
| `test_moderator_decision_with_both_closings_empty` | Moderator still decides with empty closings. |
| `test_memory_store_with_special_characters_in_debate` | Memory store handles special chars in content. |

### `unit_tests/test_errors.py` — Failure handling (12 tests)

Injects timeouts, network errors, rate limits, and unparseable responses.

| Test | What it verifies |
|---|---|
| `test_pro_opening_llm_timeout` | Pro opening propagates a `TimeoutError`. |
| `test_con_opening_llm_network_error` | Con opening propagates a network error. |
| `test_moderator_decision_llm_rate_limit` | Moderator propagates a 429 rate-limit error. |
| `test_pro_opening_memory_retrieval_fails` | Memory-retrieval failure propagates. |
| `test_con_opening_memory_upsert_fails` | Con opening still returns despite memory issues. |
| `test_graph_execution_with_invalid_state` | Invalid state raises during graph execution. |
| `test_moderator_decision_cannot_extract_winner` | Unparseable winner → still returns a string `winner` + summary. |
| `test_streaming_response_with_llm_failure` | LLM failure mid-stream is handled gracefully. |
| `test_debate_invoke_with_execution_timeout` | `run_debate` timeout propagates. |
| `test_memory_store_chroma_fallback` | Memory store falls back to in-memory when Chroma is missing. |
| `test_concurrent_debate_execution_limit` | Concurrent debates complete without total failure. |

### `unit_tests/test_e2e.py` — Live server E2E (4 tests, `@pytest.mark.e2e`)

Real HTTP calls against a running server at `http://localhost:8000`. **Requires the server up
and a valid `ANTHROPIC_API_KEY`.** Not run in the default (mocked) suite.

| Test | What it verifies |
|---|---|
| `test_health_endpoint` | `GET /health` returns 200 and `status: healthy`. |
| `test_debate_endpoint_invoke_returns_full_state` | `POST /debate/invoke` returns a full, populated debate state. |
| `test_debate_endpoint_rejects_empty_topic` | Empty topic → 400. |
| `test_debate_stream_endpoint` | `GET /debate/stream` streams ≥1 SSE event. |

---

## 3. Known issues to be aware of

These are documented in `docs/EVALUATION_APPROACHES.md` and affect a few tests:

1. **Invalid import syntax** — `test_edge_cases.py` and `test_errors.py` contain the line
   `from app import src.core.graph as graph`, which is not valid Python and will error if those
   test bodies execute. Left untouched here (reorganization only); the eval plans note the fix.
2. **Agent patch targets** — agent tests patch `agents.pro` / `agents.con` / `agents.moderator`
   rather than `src.agents.*`. Import paths depend on how the app exposes these modules.

These are intentionally **not** fixed as part of the reorganization; see the three `PLAN.md`
documents for how each evaluation approach handles them.
