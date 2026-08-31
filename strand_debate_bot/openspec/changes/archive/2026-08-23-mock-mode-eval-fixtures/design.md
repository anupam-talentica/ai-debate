## Context

See proposal.md for motivation. Relevant current-state facts that shape this design:

- Debate-turn nodes are `MultiAgentBase` objects built by per-role factories (`pro_opening_node`, `con_rebuttal_node`, etc., in `src/agents/pro.py` / `src/agents/con.py`), each an `AgentTurnNode` (`src/core/nodes.py`) that builds a prompt from `invocation_state`, calls a real Strands `Agent`, and writes the result back under a fixed `store_key`. `build_graph()` (`src/core/graph.py`) wires these node objects and the graph edges between them; the edges themselves are structural only, not data flow (design.md of `core-debate-graph`).
- The moderator hub (`ModeratorHub`, `src/agents/moderator.py`) makes no LLM call — it only advances the round counter and performs memory retrieval — so it is never a mock-mode concern.
- The terminal decision node (`ModeratorDecision`) calls the model with `structured_output_model=Verdict`, where `Verdict = {winner: Literal["Pro","Con"], justification: str}`. This structured output was a deliberate improvement over the old system's regex-based winner-parsing heuristic (PRD capability-mapping table) and must not be compromised by mock mode.
- The old system's cached transcripts (`debate_bot/tests/deepeval_promptfoo/.debate_cache/*.json`) store `topic`, `pro_opening`, `con_opening`, `pro_rebuttal`, `con_rebuttal`, `pro_closing`, `con_closing`, plus a free-text `moderator_summary` and a dirty `winner` string (e.g. `"Con**"`) — a fossil of that same old heuristic. They have no `justification` field and no audience-question fields.

## Goals / Non-Goals

**Goals:**
- Reuse the two existing cached transcripts verbatim (byte-for-byte) as this change's only fixture data.
- Keep the real (non-mock) code paths — `AgentTurnNode`, `ModeratorDecision`, the real `Verdict` model — completely unmodified.
- Match the old system's mock-mode behavior (topic-matching + fallback, per-turn artificial delay) except where explicitly changed below.

**Non-Goals:**
- Porting or reimplementing the `deepeval`/`promptfoo` eval harness that originally produced the cached transcripts.
- Generating new or additional cached transcripts.
- Changing the real decision node's `Verdict` shape or the real memory/durability/HITL flows.

## Decisions

**Decision 1: Swap node objects at graph-build time, not the model.** `build_graph()` gains a `mock: bool` (or reads `MOCK_LLM` internally) that, when true, constructs a `MockTurnNode` in place of `AgentTurnNode` for the six argument-turn nodes (pro/con × opening/rebuttal/closing) and a `MockModeratorDecision` in place of `ModeratorDecision`, leaving `ModeratorHub`, `AudienceQuestionStub`, and the two audience-question responder nodes untouched. Both mock node types satisfy the exact same `invoke_async(task, invocation_state) -> MultiAgentResult` contract their real counterparts do, so no graph-edge or invocation_state-consumer code needs to know mock mode exists.
- Alternative considered: swap at the `Model` layer (a shared `MockModel` implementing Strands' `Model` interface, similar to `tests/fakes.py::FakeModel`). Rejected: a single `Model` instance is shared across every turn's `Agent`, and `Model.stream()` has no node-id to key its lookup on — it would have to infer "which turn is this" from call order, which is fragile and diverges from the old system's per-node, per-field replay. Node-level swap also directly matches the PRD's own capability-mapping guidance ("swap node executors at graph-build time").

**Decision 2: One shared transcript-lookup helper, ported near-verbatim from `debate_bot/src/agents/mock.py`.** A single function loads and caches the list of transcript JSON files, matches by case-insensitive exact `topic` string, and falls back to the filename-sorted first file with a logged warning if nothing matches — same behavior as the old `_load_transcript`. Each `MockTurnNode` calls it once per invocation and reads its own `store_key` out of the result, same as the old `_mock_field` pattern.

**Decision 3: Verdict compatibility is handled entirely inside `MockModeratorDecision`.** On the cached transcript's fields: `winner` is normalized by stripping any characters other than the letters that spell "Pro"/"Con" (e.g. trailing `**`) and matching case-insensitively against `{"pro", "con"}`; `justification` is set to the transcript's `moderator_summary` field verbatim. This keeps the transformation a one-time, mock-only concern — the fixture JSON files are never edited, and the real `ModeratorDecision`/`Verdict` are untouched. If a transcript's `winner` cannot be normalized to `"Pro"` or `"Con"` (e.g. the field is missing or unrecognizable), `MockModeratorDecision` raises rather than silently guessing — this is fixture-authoring feedback, not a runtime condition a real debate can hit.
- Alternative considered: regenerate fixtures directly in the new structured shape. Rejected per explicit instruction to reuse the same JSON files as-is.
- Alternative considered: leave `ModeratorDecision` un-mocked (always real). Rejected: violates TRD Task 7's exit criterion of zero live API calls for a full mock-mode run.

**Decision 4: Drop the old system's `con_rebuttal`-only 10-second hardcoded sleep.** `debate_bot/src/agents/mock.py`'s `con_rebuttal` has an extra unconditional `await asyncio.sleep(10)` on top of the normal per-field delay, with no comment explaining it — read as leftover debug cruft rather than an intentional demo beat. All six mocked turns and the mocked decision use one uniform delay, `MOCK_LLM_DELAY_SECONDS` (default 1.5s, matching the old default), satisfying FR-11's "configurable artificial delay" without carrying the anomaly forward.

**Decision 5: Config flags live in `src/core/config.py`, parallel to existing patterns.** `MOCK_LLM` (bool, default false) and `MOCK_LLM_DELAY_SECONDS` (float, default 1.5) are added the same way `MODEL_NAME`/`SESSION_STORAGE_DIRECTORY` already are — env-var-backed module constants, no new config framework.

**Decision 6: Fixtures are copied into this project's test tree verbatim.** The two cached transcript files move to a project-local cache directory (mirroring the old system's location convention, e.g. `tests/mock_cache/`) with unchanged filenames and byte-identical content — no regeneration, no edits, including the pre-existing quirk that both files share identical debate body text under different `topic` fields (called out in proposal.md; not fixed here since fixing it would mean generating new content, which is explicitly out of scope).

## Risks / Trade-offs

- [Risk] Both cached transcripts contain identical debate body text under different topics, so mock mode will visibly replay an off-topic debate for any topic that doesn't match `"AI will replace software engineers"` or `"Pro athletes are overpaid"` exactly (which is every topic, given the fallback path always fires for a novel topic). → Mitigation: acceptable for this change's purpose (demo/UI iteration at zero cost, not topical realism); the fallback logs a warning so this is visible, not silent.
- [Risk] `winner`-normalization in `MockModeratorDecision` reintroduces a small string-cleaning step, echoing the exact kind of heuristic the real system deliberately moved away from. → Mitigation: scoped strictly to two known fixture files with a known dirty value (`"Con**"`); raises loudly rather than guessing on unrecognized input; never runs on the real (non-mock) decision path.
- [Trade-off] No `justification`-quality guarantee: the old `moderator_summary` free-text blob was never written to satisfy a `justification` field's expectations. Accepted as sufficient for mock mode's purpose.
