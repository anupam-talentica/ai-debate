# PRD: Agent Builder + Swarm — 20-Minute POC

## Objective
Decide, in one timeboxed sitting, whether `strands-agents-builder` (the `strands` CLI)
and the `swarm` tool can scaffold a Pro/Con/Moderator debate loop faster and at
comparable quality to the hand-built `strand_debate_bot` graph — so future spikes
default to it instead of hand-writing `GraphBuilder` wiring from scratch.

## Background
`strand_debate_bot` was built by hand: custom `Agent` instances per role
(`src/agents/pro.py`, `con.py`, `moderator.py`), a manually wired
`strands.multiagent.GraphBuilder` with conditional edges (`src/core/graph.py`),
and a throwaway spike script to prove the graph mechanics before committing.
`agent-builder` claims to do the scaffolding/prototyping part of that
interactively from the terminal. This POC tests that claim on the smallest
possible slice: three agents, one topic, two rounds, a winner call.

## Non-goals (explicitly out of scope for this timebox)
- FastAPI/Streamlit surface, streaming, WebSockets
- Memory persistence (Chroma), session durability, resume/interrupt
- Mock mode, eval fixtures, tests
- Production error handling / retries
- Anything beyond one topic, two rounds, one moderator verdict

## Success criteria — questions this POC must answer
1. **Setup speed**: can `strands` be installed and produce *something runnable*
   in under 5 minutes?
2. **Scaffold quality**: is the generated agent/tool code structurally close to
   `src/agents/pro.py`'s style (one `Agent` per role, clear system prompt), or
   does it produce something harder to read/extend?
3. **Coordination**: does the `swarm` tool give correct turn order
   (pro → con → moderator decides) out of the box, or does it free-run agents
   in an order you can't control — meaning you'd still need `GraphBuilder`-style
   explicit edges for anything with strict turn discipline (like a debate)?
4. **Extensibility signal**: how much hand-editing of generated output is needed
   to add a third round (rebuttal) — a proxy for how much this would actually
   save on the real migration.

## Timebox plan (20 minutes)

| Time | Step |
|---|---|
| 0–3 min | Install: `pipx install strands-agents-builder`; verify `strands --version`; export `ANTHROPIC_API_KEY` (reuse from `strand_debate_bot/.env`) |
| 3–9 min | Run the one-shot scaffold prompt below from `agent_builder_poc/` |
| 9–14 min | Execute the generated agent/swarm; capture the transcript output verbatim |
| 14–18 min | Open the generated files; compare structure against `strand_debate_bot/src/agents/pro.py` and `src/core/graph.py` |
| 18–20 min | Fill in `notes/findings.md` with a go/no-go call against the 4 success criteria above |

## Exact command to run

From `agent_builder_poc/`:

```bash
export ANTHROPIC_API_KEY=<your-key>   # or: source ../strand_debate_bot/.env

strands "Build three Strands agents — Pro, Con, and Moderator — for a debate \
on 'remote work improves productivity'. Use the swarm tool to coordinate them \
so Pro speaks, then Con speaks, then Moderator declares a winner with a one \
paragraph rationale. Run it once and show me the full transcript. Save the \
agent/tool code as separate files in the current directory."
```

If `swarm` doesn't respect turn order on the first try, one follow-up prompt is
in-budget:

```bash
strands "The turn order wasn't respected — Pro then Con then Moderator only, \
no interruptions. Fix the swarm coordination and re-run."
```

## Deliverable
`notes/findings.md`, filled in with:
- What got generated (file list, one-line description each)
- Answers to the 4 success-criteria questions
- Go / no-go: use `agent-builder` for the *next* scaffolding spike, or keep
  hand-writing `GraphBuilder` wiring as `strand_debate_bot` did

## Explicitly deferred (only if time remains / a follow-up session)
- Adding a rebuttal round
- Comparing `swarm` vs `agent_graph` tool for this same task
- Wiring in a real memory store
