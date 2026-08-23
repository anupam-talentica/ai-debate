## Why

The debate bot currently runs Pro vs. Con to a scripted conclusion with no way for a human to participate mid-debate. Adding a human-in-the-loop pause after the rebuttal round — where a user can inject an "audience question" both sides must address before closing — makes the debate interactive and lets the final verdict account for how well each side thinks on its feet, not just their prepared arguments.

## What Changes

- Insert a pause point into the debate graph after the rebuttal round (`con_rebuttal`), implemented with LangGraph's `interrupt()`, that waits for a single audience question to be submitted.
- Add two new agent steps, run after the question is received, where Pro and Con each address the audience question before closing arguments.
- Extend the moderator's final verdict to weigh how well each side handled the audience question, not just their closing statements.
- Add a new endpoint to submit the audience question and resume a paused debate.
- Add a new SSE event so streaming clients can detect that a debate is paused awaiting a question.
- **BREAKING**: `POST /debate/invoke` (the synchronous, non-streaming endpoint) will now raise an explicit error instead of returning a misleadingly "complete" response when a debate pauses for the audience question, since a single blocking request/response cannot support injecting the question mid-call. Existing callers of `/invoke` that don't supply a question up front will receive an error where they previously received (an unintentionally incomplete) HTTP 200.
- Extend `/invoke`'s request to optionally accept the audience question up front, letting single-shot callers who already know their question skip the pause entirely.
- Extend the run-ownership model with a new status distinguishing "paused, waiting for human input" from "actively running" and "finished," so automatic failover doesn't mistake a paused run for a crashed one and doesn't repeatedly re-trigger the same pause while waiting.

## Capabilities

### New Capabilities
- `audience-question-interrupt`: Pausing a debate after the rebuttal round to accept a human-submitted audience question, requiring both debaters to address it, factoring it into the moderator's verdict, and resuming execution — across both the synchronous and streaming/background API paths.

### Modified Capabilities
(none — no existing specs predate this change)

## Impact

- **Graph**: `src/core/graph.py` — reroutes `con_rebuttal -> moderator_checkpoint` through three new nodes.
- **State**: `src/core/state.py` — three new fields (`audience_question`, `pro_audience_answer`, `con_audience_answer`).
- **Agents**: `src/agents/pro.py`, `src/agents/con.py` — two new node functions; a new interrupt-triggering node (moderator module or new module).
- **Prompts**: `src/core/prompts.py` — two new prompt templates; `MODERATOR_DECISION` extended with new inputs.
- **API**: `src/api/routes/debates.py`, `src/api/services/debate_service.py` — new endpoint to submit the question and resume; `/invoke` gains an explicit-error guard and an optional pre-supplied-question field.
- **Schemas**: `src/api/schemas.py` — new/extended request and response models.
- **Ownership/failover**: `deployment/app_ext/ownership.py` — new run status and changed staleness semantics for that status.
- No changes to `src/core/memory.py` or the moderator's opening/checkpoint transition logic beyond what's listed above.
