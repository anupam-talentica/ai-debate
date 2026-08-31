## Purpose

Lets a person drive a debate to a guarded verdict through a visual AWS Bedrock Flow, without writing code against the REST or AgentCore surfaces, by having the Flow trigger and observe the already-deployed debate agent on its behalf.

## ADDED Requirements

### Requirement: Flow triggers a debate from a topic
The Flow SHALL accept a topic as input and, from it, start a debate run against the deployed debate agent.

#### Scenario: A topic starts a debate
- **WHEN** the Flow is run with a topic
- **THEN** a debate run is started for that topic against the deployed debate agent

### Requirement: Flow surfaces the audience-question pause as a human input step
The Flow SHALL, when the triggered debate pauses awaiting an audience question, present a step that collects a question from whoever is running the Flow, and SHALL resume the debate with that question once supplied.

#### Scenario: The Flow waits for a person to supply the audience question
- **WHEN** a debate triggered by the Flow reaches its audience-question pause
- **THEN** the Flow presents a step asking for the audience question and does not proceed until one is supplied

#### Scenario: Supplying the question resumes the debate toward a verdict
- **WHEN** a question is supplied at the Flow's human-input step for a paused debate
- **THEN** the debate resumes and the Flow proceeds toward producing a verdict

### Requirement: Flow output passes through a guardrail before reaching the caller
The Flow SHALL apply a guardrail check to the debate's completed verdict before returning it as the Flow's output, and SHALL apply a guardrail check to the topic before using it to start a debate.

#### Scenario: A completed verdict is guarded before being returned
- **WHEN** a debate triggered by the Flow reaches a completed verdict
- **THEN** the verdict passes through a guardrail check before the Flow returns it as output

#### Scenario: A topic is guarded before starting a debate
- **WHEN** the Flow is run with a topic
- **THEN** the topic passes through a guardrail check before any debate is started

### Requirement: Flow reports failure explicitly
The Flow SHALL produce a distinct, explicit failure output whenever the debate it triggered does not reach a completed verdict for any reason other than the audience-question pause — including guardrail rejection, debate execution failure, or the Flow's own inability to observe the debate reach a settled state.

#### Scenario: A guardrail-rejected topic is reported as a failure
- **WHEN** a topic supplied to the Flow is rejected by the input guardrail
- **THEN** the Flow's output explicitly identifies a failure, and no debate is started

#### Scenario: A failed debate is reported as a failure
- **WHEN** a debate triggered by the Flow fails to complete for a reason other than the audience-question pause
- **THEN** the Flow's output explicitly identifies a failure, distinguishable from a completed verdict

### Requirement: Concurrent Flow executions are isolated
The Flow SHALL ensure that two of its executions, triggered independently, drive and observe independent debate runs, with no execution's human-input step or output affected by another execution's debate.

#### Scenario: Two Flow executions do not interfere
- **WHEN** two Flow executions are triggered with different topics
- **THEN** each execution's human-input step and output correspond only to the debate it triggered
