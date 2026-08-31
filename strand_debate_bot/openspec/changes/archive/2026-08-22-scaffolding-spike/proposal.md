## Why

The Strands migration's core design (PRD Section 5: a single `moderator` hub revisited via cyclic graph edges) and its human-in-the-loop audience-question feature (FR-5) both depend on three unconfirmed Strands mechanics: graph-node-level interrupt/resume with arbitrary external input, `GraphBuilder` cyclic/conditional edges for a revisited hub node, and invocation-state accumulation across those revisits (PRD Section 9, Open Questions 1, 2, 4). Building the real debate graph before confirming these risks discovering a blocking limitation mid-implementation, when the fallback (splitting into separately-invoked sub-graphs around the pause point) would require redesigning work already built. This change resolves that risk cheaply with a minimal throwaway harness, and stands up the local project scaffolding needed to run it.

## What Changes

- Add local project scaffolding: Strands SDK dependency, `.env`-based Anthropic API key config, and skeleton directories mirroring the target `src/core|agents|api` layout.
- Add a throwaway "Running Total" spike graph: a `hub` node revisited across three rounds via cyclic edges, dispatching an `Adder` node (always +5), a `human_choice` node that interrupts and resumes with an externally-submitted operation, and a `Subtracter` node (always −3), with a final hub visit reporting the total and a trace of all three operations.
- Produce a written finding (pass/fail per open question, with any workaround needed) that Task 2 (core debate graph) and Task 4 (audience-question HITL) can build on.

## Capabilities

### New Capabilities
- `strands-graph-spike`: A minimal, deterministic Strands graph proving graph-node interrupt/resume, cyclic/conditional hub revisits, and cross-revisit state accumulation, per the "Running Total" scenario.

### Modified Capabilities
(none — this is the first change in this project)

## Impact

- New local project structure (dependencies, env config, skeleton dirs) that later tasks (core graph, memory, HITL, API, durability, mock mode, UI) will build inside.
- No production code paths affected — this change's graph/agents are throwaway and are not wired into the debate bot itself.
- Findings from this spike may require revisiting the PRD's Section 5 architecture (the single cyclic hub) or Section 9 Open Question 1's fallback (split sub-graphs) if any mechanic doesn't hold.
