# Demo: Core Debate Graph (Task 2)

Steps to verify the Pro/Con/Moderator round state machine built in the
`core-debate-graph` change (archived under
`openspec/changes/archive/2026-08-23-core-debate-graph/`).

## 1. Set up the environment

```bash
cd strand_debate_bot
source .venv/bin/activate
pip install -r requirements.txt
```

No `.env` / API key is needed for step 2 (it runs against a mocked model).
It is needed for step 3 (a real debate).

## 2. Run the automated test suite (no API key, no cost)

```bash
python -m pytest tests/ -v
```

Expect all 4 tests to pass:

- `test_full_debate_runs_end_to_end` — the graph runs opening → rebuttal →
  audience → closing → verdict in exactly that order (TRD Task 2's stated
  test).
- `test_con_opening_and_rebuttal_see_pro_opening` — Con's opening and
  rebuttal prompts actually contain Pro's opening argument text (confirms
  the `invocation_state`-based data flow, not just that *something* ran).
- `test_audience_round_leaves_fields_unset` — the audience round is a
  no-op stub for now: it completes without pausing and leaves
  `audience_question`/`pro_audience_answer`/`con_audience_answer` empty
  (real behavior lands in a later change).
- `test_verdict_is_structured_and_terminal` — the final verdict is a
  structured `winner` (`"Pro"`/`"Con"`) + `justification`, and no node
  runs after it (exactly 13 node executions, matching the design doc).

These tests use `tests/fakes.py::FakeModel`, a stand-in that implements
Strands' `Model` interface directly, so no network calls or API key are
involved.

## 3. Run a real debate end-to-end (optional, uses your API key)

```bash
cp .env.example .env   # then fill in ANTHROPIC_API_KEY
```

```bash
python - <<'EOF'
import asyncio
from src.core.graph import build_graph
from src.core.state import build_invocation_state

async def main():
    graph = build_graph()  # no model arg -> real Anthropic model from .env
    state = build_invocation_state("Remote work is better than office work")
    result = await graph.invoke_async("run", invocation_state=state)

    print("status:", result.status)
    for round_name in ["pro_opening", "con_opening", "pro_rebuttal", "con_rebuttal", "pro_closing", "con_closing"]:
        print(f"\n--- {round_name} ---\n{state[round_name]}")
    print(f"\n--- verdict ---\nwinner: {state['winner']}\njustification: {state['justification']}")

asyncio.run(main())
EOF
```

This makes real LLM calls (7 total) and prints the full transcript plus the
structured verdict. Confirm the debate reads coherently round to round and
that Con's arguments actually engage with what Pro said.

## What this does *not* cover yet

- The audience round doesn't really pause for a question (stubbed; next change).
- No cross-debate memory injection (a later change).
- No FastAPI/HTTP surface — this is graph-level only, driven directly in Python.
