## Purpose

Defines the invocation contract the debate system exposes when running as an Amazon Bedrock AgentCore Runtime agent — a single dispatched endpoint and health check, and how a debate run's identity maps onto an AgentCore session so that its human-in-the-loop pause remains resumable under that platform's request model.

## ADDED Requirements

### Requirement: Single dispatched invocation endpoint
The system SHALL expose one endpoint that accepts every debate operation (starting a run, streaming a run's events, submitting an audience question, resuming a run) as a single request type, selecting the operation from a field in the request payload, without requiring the caller to know a different path per operation.

#### Scenario: Starting a debate through the dispatched endpoint
- **WHEN** a request is made to the dispatched endpoint identifying the start operation with a topic
- **THEN** a new debate run begins and the response identifies that run

#### Scenario: An unrecognized operation is rejected explicitly
- **WHEN** a request is made to the dispatched endpoint identifying an operation the system does not recognize
- **THEN** the response is an explicit error naming the problem, and no debate run is started, streamed, resumed, or altered

### Requirement: Liveness check independent of any debate run
The system SHALL expose a health check that responds successfully whenever the process is able to accept requests, independent of whether any debate run exists or is in progress.

#### Scenario: Health check succeeds with no runs in progress
- **WHEN** the health check is requested and no debate run currently exists
- **THEN** the response indicates the service is healthy

#### Scenario: Health check succeeds while runs are in progress
- **WHEN** the health check is requested while one or more debate runs are in progress
- **THEN** the response indicates the service is healthy, unaffected by those runs' state

### Requirement: A debate run is addressable by a single external session identifier
The system SHALL let a debate run be started, streamed, paused, and resumed using one externally-supplied session identifier for that run's entire lifetime, so that every request belonging to the same debate is recognizable as belonging to the same run.

#### Scenario: The same identifier addresses a run across its lifetime
- **WHEN** a debate run is started under a given session identifier
- **THEN** streaming, submitting an audience question, and resuming that run all use that same session identifier
- **AND** no other session identifier can stream, submit a question for, or resume that run

### Requirement: A paused run resumes through the same session identifier
The system SHALL, when an audience question is submitted for a run's session identifier while that run is paused awaiting one, resume that run's execution using the content already produced under that same session identifier, without requiring the content produced before the pause to be resupplied.

#### Scenario: Submitting a question resumes the run to a completed verdict
- **WHEN** a debate run under a session identifier is paused awaiting an audience question
- **AND** a question is submitted for that same session identifier
- **THEN** the run resumes and proceeds to a completed verdict using the opening and rebuttal content already produced under that identifier

### Requirement: Concurrent debate runs under different sessions remain isolated
The system SHALL ensure that two debate runs started under two different session identifiers do not observe or alter each other's state, regardless of how their requests are distributed across the running instances handling them.

#### Scenario: Two runs under different sessions do not interfere
- **WHEN** two debate runs are started under two different session identifiers
- **THEN** streaming, submitting a question for, or resuming one session identifier has no effect on the other's run
