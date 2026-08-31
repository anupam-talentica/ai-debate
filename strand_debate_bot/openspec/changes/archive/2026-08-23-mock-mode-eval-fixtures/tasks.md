## 1. Fixtures

- [x] 1.1 Create a project-local cache directory for mocked transcripts (e.g. `tests/mock_cache/`).
- [x] 1.2 Copy `debate_bot/tests/deepeval_promptfoo/.debate_cache/05a64aa1dcc2376a.json` and `30893746daef3c17.json` into it verbatim (unchanged filenames, byte-identical content, no edits).

## 2. Config

- [x] 2.1 Add `MOCK_LLM` (bool, default `false`) and `MOCK_LLM_DELAY_SECONDS` (float, default `1.5`) to `src/core/config.py`, following the existing env-var-backed constant pattern (`MODEL_NAME`, `SESSION_STORAGE_DIRECTORY`).

## 3. Transcript Lookup

- [x] 3.1 Add a transcript-lookup helper (new module, e.g. `src/core/mock_transcripts.py`) that: loads all JSON files from the mock cache directory, matches one by case-insensitive exact `topic` string, and falls back to the filename-sorted first file with a logged warning if no match is found (mirrors `debate_bot/src/agents/mock.py::_load_transcript`).
- [x] 3.2 Unit test: exact topic match returns that transcript.
- [x] 3.3 Unit test: no topic match falls back to the deterministic default and logs a warning (spec: "No topic match falls back without failing").

## 4. Mock Turn Node

- [x] 4.1 Add a `MockTurnNode` (or similar) satisfying the same `invoke_async(task, invocation_state) -> MultiAgentResult` contract as `AgentTurnNode` (`src/core/nodes.py`): looks up the cached transcript via Task 3.1's helper, waits `MOCK_LLM_DELAY_SECONDS`, and writes the transcript's field for its `store_key` into `invocation_state`.
- [x] 4.2 Unit test: a `MockTurnNode` for each of the six argument turns (pro/con × opening/rebuttal/closing) writes the correct cached field to `invocation_state` under its own `store_key`.
- [x] 4.3 Unit test: `MockTurnNode` waits approximately `MOCK_LLM_DELAY_SECONDS` before returning, and honors a non-default configured value (spec: "Configurable artificial delay").

## 5. Mock Moderator Decision

- [x] 5.1 Add a `MockModeratorDecision` node: looks up the cached transcript, normalizes its `winner` field (strip non-letter characters, case-insensitive match) to exactly `"Pro"` or `"Con"`, sets `justification` to the transcript's `moderator_summary` verbatim, and writes both into `invocation_state` — matching the real `ModeratorDecision`'s output shape (`src/agents/moderator.py`'s `Verdict`). Raise (do not silently guess) if `winner` cannot be normalized.
- [x] 5.2 Unit test: replaying each of the two fixture transcripts produces `winner` exactly `"Pro"` or `"Con"` and a non-empty `justification` (spec: "Mock mode verdict is structurally compatible with the real verdict").
- [x] 5.3 Unit test: `MockModeratorDecision` also applies the configured artificial delay, matching the other mocked turns.

## 6. Graph Wiring

- [x] 6.1 Update `build_graph()` (`src/core/graph.py`) to construct `MockTurnNode`/`MockModeratorDecision` instead of the real `AgentTurnNode`/`ModeratorDecision` for the six argument turns and the decision node when `MOCK_LLM` is enabled, leaving `ModeratorHub`, `AudienceQuestionStub`, and both audience-question responder nodes unchanged in either mode.
- [x] 6.2 Unit test: with `MOCK_LLM` enabled and no model/API key configured, a full debate run (opening → rebuttal → audience → closing → verdict) completes successfully using only cached content, except the audience-question answers.
- [x] 6.3 Unit test: with `MOCK_LLM` disabled (default), `build_graph()` wires the real nodes exactly as before (no regression to the non-mock path).

## 7. Exit Criterion

- [x] 7.1 Manual/integration check per TRD Task 7: run a full demo debate with `MOCK_LLM` enabled and confirm zero live Anthropic API calls are made (e.g. no `ANTHROPIC_API_KEY` required, or a network-call assertion/mock at the model layer proving it's never invoked for the mocked turns).
  - Delivered as `tests/test_mock_mode.py::test_mock_graph_completes_without_calling_the_model_for_mocked_turns`: builds the real graph with `mock=True` and asserts the model is called exactly twice (only the two always-real audience-question turns) across a full opening→rebuttal→audience→closing→verdict run — the six argument turns and the decision never touch it. No Demo UI exists yet (TRD Task 8, not started), so a literal manual UI run isn't possible yet; this is the graph-level equivalent, and per FR-11 the audience-question turns are never claimed to be cost-free.
