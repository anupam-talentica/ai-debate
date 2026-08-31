## Why

Every local debate run currently costs real Anthropic API calls (7 LLM calls per full debate), which slows down UI/demo iteration and burns budget on repeated manual testing. The old `debate_bot` system solved this with a `MOCK_LLM` replay mode backed by cached debate transcripts; TRD Task 7 calls for porting that same capability onto the new Strands graph, reusing the old system's cached transcript fixtures rather than regenerating them, so demo/UI work can proceed with zero live API calls.

## What Changes

- Add a `MOCK_LLM` config flag (`src/core/config.py`) that, when enabled, makes `build_graph()` construct mock replay nodes in place of the real Agent-backed ones for every debate-turn node except the two audience-question responder nodes (which always call the real model, since the audience question is novel each run).
- Add a mock node implementation mirroring the old `debate_bot/src/agents/mock.py`: looks up a cached transcript by case-insensitive exact `topic` match, falling back (with a logged warning) to whichever cached file sorts first by filename if no topic matches; applies one uniform, configurable artificial delay (`MOCK_LLM_DELAY_SECONDS`, default 1.5s) per replayed turn.
- Add a mock variant of the `ModeratorDecision` node that produces the same structured `Verdict` (`winner: Literal["Pro","Con"]`, `justification: str`) the real decision node produces, sourced from the cached transcript's free-text fields: `winner` is normalized (stripped of stray characters like trailing `**`) to exactly `"Pro"` or `"Con"`, and `justification` is copied verbatim from the cached `moderator_summary` field. This normalization lives only in the mock node — it does not touch the fixture files or the real decision path.
- Copy the two existing cached transcripts from `debate_bot/tests/deepeval_promptfoo/.debate_cache/` (`05a64aa1dcc2376a.json`, `30893746daef3c17.json`) into this project's test fixtures verbatim, byte-for-byte — no regeneration, no content edits.
- No new dependency is added: this only replays already-generated JSON transcripts, and does not port or reimplement the `deepeval`/`promptfoo` eval harness that originally produced them.

## Capabilities

### New Capabilities
- `mock-replay-mode`: A configuration-gated mode that replaces every LLM-calling debate-turn node (except the audience-question responders) with a cached-transcript replay, including topic-matching/fallback lookup, a configurable artificial delay, and a compatible mapping from the cached transcript's free-text verdict fields onto the real system's structured `Verdict` output.

### Modified Capabilities
(none — this is purely additive; no existing capability's requirements change)

## Impact

- `src/core/config.py`: new `MOCK_LLM` / `MOCK_LLM_DELAY_SECONDS` config vars.
- `src/core/graph.py`: `build_graph()` branches on `MOCK_LLM` to construct mock nodes instead of real ones.
- New module for mock node implementations (mirroring `src/core/nodes.py`'s `AgentTurnNode` contract) and transcript-lookup logic (mirroring `debate_bot/src/agents/mock.py`).
- `src/agents/moderator.py`: no changes to the real `ModeratorDecision`/`Verdict`; a mock counterpart is added elsewhere.
- Test fixtures: two JSON transcript files copied in verbatim from `debate_bot/tests/deepeval_promptfoo/.debate_cache/`.
- No changes to `requirements.txt`, the API surface, memory, durability, or the audience-question HITL flow.
