# demo-ui Specification

## Purpose

Gives a human a way to watch a debate run and answer its audience-question pause through a browser, without polling the API by hand — a chat-style transcript view over the existing FastAPI SSE contract, with no multi-node or failover-specific presentation.

## Requirements

### Requirement: Chat-style transcript rendering
The UI SHALL render a debate's progress as a sequence of moderator round dividers and per-speaker turns, in the same order the graph actually executes them (opening, rebuttal, audience exchange, closing, verdict), sourced entirely from the debate's SSE event stream.

#### Scenario: Turns appear in execution order
- **WHEN** a debate is running and node-completion events arrive over SSE
- **THEN** each turn is appended to the transcript in the order its event arrived, grouped under the round divider it belongs to

#### Scenario: Verdict is shown once produced
- **WHEN** the stream emits the terminal completion event carrying a winner and justification
- **THEN** the UI displays the winner and justification as the final transcript entry

### Requirement: Turn reveal is animated exactly once
Each speaker turn's text SHALL be revealed progressively (a "typewriter" effect) the first time it is displayed, and SHALL render as static text on every subsequent re-render of the same turn.

#### Scenario: First display of a turn animates
- **WHEN** a turn's text is rendered for the first time
- **THEN** the text is revealed progressively rather than appearing all at once

#### Scenario: Re-rendering history does not re-animate
- **WHEN** the transcript view re-renders (e.g. on a polling refresh) after a turn has already been shown once
- **THEN** that turn's text is displayed immediately in full, without repeating the reveal animation

### Requirement: Audience-question form is gated to the pause window
The UI SHALL show an audience-question input form only while the active debate is paused waiting for a question, and SHALL accept exactly one submission per debate.

#### Scenario: Form appears at the pause
- **WHEN** the active debate's most recent event indicates it is awaiting an audience question
- **THEN** the UI displays a form for entering and submitting a question

#### Scenario: Form is hidden once a question is submitted
- **WHEN** a question has already been submitted for the active debate
- **THEN** the UI does not display the submission form again for that debate, even before the debate resumes

#### Scenario: Debate progress resumes visibly after submission
- **WHEN** a question is submitted for a paused debate
- **THEN** the UI continues to display that debate's subsequent turns (audience answers, closing round, verdict) without requiring the user to manually reconnect or refresh

### Requirement: Session-scoped debate history
The UI SHALL maintain a list of every debate started during the current UI session and SHALL let the user switch the main view between them.

#### Scenario: Starting a debate adds it to the history list
- **WHEN** a new debate is started from the UI
- **THEN** it appears in the history list and becomes the active debate shown in the main view

#### Scenario: Switching debates preserves each one's progress
- **WHEN** the user selects a different debate from the history list
- **THEN** the main view shows that debate's own transcript, and any other debate's in-progress stream continues to be received in the background

### Requirement: No multi-node or failover presentation
The UI SHALL present the debate service as a single endpoint and SHALL NOT display node identity, per-node health, or failover/resume narration of any kind.

#### Scenario: Turns never attribute a serving node
- **WHEN** any speaker turn or transcript entry is rendered
- **THEN** it contains no indication of which server or node produced it

#### Scenario: No node-health or failure UI is present
- **WHEN** the UI is displayed in any state (idle, running, paused, or complete)
- **THEN** no node-up/down indicator, failure banner, or "resumed on node X" message is shown anywhere in the view
