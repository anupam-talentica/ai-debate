# debate-fastapi-surface Specification

## Purpose

Defines the HTTP behavior of the debate system: a liveness check, a synchronous full-run endpoint, a single-connection SSE stream, and a start/stream/submit-question path for running and interacting with a debate from an external client within one server process.

## Requirements

### Requirement: Health check
The system SHALL expose a liveness endpoint that responds successfully whenever the server process is able to handle requests, without identifying which node served the request.

#### Scenario: Health check succeeds while the server is up
- **WHEN** a client requests the health endpoint
- **THEN** the response indicates the service is healthy

### Requirement: Synchronous full-run invocation
The system SHALL expose an endpoint that runs a debate to completion within a single request/response cycle, given a topic and an optional pre-supplied audience question. If the debate reaches the audience-question pause without a pre-supplied question, the endpoint SHALL fail explicitly with the run's identifier rather than returning an incomplete result. If the debate does not complete within a configured timeout, the endpoint SHALL fail explicitly with a distinct error from execution failure.

#### Scenario: A pre-supplied question lets the debate complete in one call
- **WHEN** a client invokes the synchronous endpoint with a topic and an audience question
- **THEN** the response contains the completed debate, including a winner and justification, and the audience question and both sides' answers

#### Scenario: No pre-supplied question surfaces the pause as an explicit error
- **WHEN** a client invokes the synchronous endpoint with only a topic
- **AND** the debate reaches the audience-question pause
- **THEN** the endpoint responds with an error identifying that the run is awaiting a question, and includes the run's identifier

#### Scenario: Execution exceeding the timeout fails distinctly
- **WHEN** a debate invoked synchronously does not complete within the configured timeout
- **THEN** the endpoint responds with a timeout error distinct from an execution-failure error

### Requirement: Single-connection streaming of a fresh run
The system SHALL expose an endpoint that streams a newly-started debate's progress as Server-Sent Events over the requesting connection, given only a topic (no way to pre-supply an audience question on this endpoint), emitting one event per completed round turn up through the rebuttal round. Since every debate's fixed round order reaches the audience-question pause with no question available on this path, the endpoint SHALL emit an explicit event stating that this connection cannot resume the run, rather than closing silently or raising an unhandled error.

#### Scenario: A fresh run streams events up to the pause, then reports it explicitly
- **WHEN** a client opens the streaming endpoint with a topic
- **THEN** the client receives one event per completed round turn through the rebuttal round
- **AND** the client then receives an event stating the run is paused and that this connection cannot supply an answer to resume it, followed by the connection closing without error

### Requirement: Start a run and obtain its identifier
The system SHALL expose an endpoint that starts a debate running in the background and immediately returns an identifier for that run, without requiring the calling connection to remain open.

#### Scenario: Starting a run returns immediately with an identifier
- **WHEN** a client starts a debate with a topic
- **THEN** the response returns a run identifier before the debate completes
- **AND** the debate continues running after the response is returned

### Requirement: Stream an in-progress or completed run by identifier
The system SHALL expose an endpoint that streams a started run's events, by its identifier, to a connecting client — whether the client connects while the run is still in progress or after it has finished.

#### Scenario: A client streams a run that is still executing
- **WHEN** a client connects to the streaming endpoint for a run identifier that is currently executing
- **THEN** the client receives events for each round turn as they complete, until the run finishes or pauses

#### Scenario: Streaming an unknown run identifier fails
- **WHEN** a client connects to the streaming endpoint with a run identifier that was never started
- **THEN** the endpoint responds with an error indicating no such run exists

### Requirement: Submit an audience question to resume a paused run
The system SHALL expose an endpoint that accepts an audience question for a run identifier and resumes that run's execution, only when the run is currently paused awaiting a question.

#### Scenario: Submitting a question resumes a paused run to completion
- **WHEN** a client submits an audience question for a run identifier that is currently paused awaiting one
- **THEN** the run resumes, both sides answer the question, and the run proceeds to a completed verdict

#### Scenario: Submitting a question to a run that isn't awaiting one fails
- **WHEN** a client submits an audience question for a run identifier that is not currently paused awaiting a question
- **THEN** the endpoint responds with an error and does not alter the run's execution

#### Scenario: Submitting a question for an unknown run identifier fails
- **WHEN** a client submits an audience question for a run identifier that was never started
- **THEN** the endpoint responds with an error indicating no such run exists

### Requirement: Concurrent runs are isolated
The system SHALL allow more than one debate run to be started and streamed concurrently within the same server process, without one run's state or events being visible through another run's identifier.

#### Scenario: Two runs started concurrently do not interfere
- **WHEN** two debates are started concurrently with different topics
- **THEN** each run's identifier streams only that run's own events, and submitting an audience question for one run's identifier has no effect on the other's execution

### Requirement: Execution failures are reported explicitly
The system SHALL respond with an explicit execution-failure error, distinguishable from a timeout or an awaiting-input pause, whenever a debate run fails to complete for any reason other than those two cases.

#### Scenario: An execution failure is reported instead of an empty or partial success
- **WHEN** a debate run fails to complete for a reason other than a timeout or the audience-question pause
- **THEN** the client receives an explicit execution-failure error rather than a partial or empty successful result

### Requirement: Resume a run by identifier after a process restart
The system SHALL expose an endpoint that resumes a previously-started run by its identifier after a process restart, continuing its execution from its last durably-recorded point rather than restarting the debate. Resuming a run that is not currently paused SHALL cause it to continue running toward completion in the background, exactly as if it had never stopped; resuming a run that was paused awaiting an audience question SHALL leave it paused, awaiting that question, through the existing submit-question endpoint.

#### Scenario: Resuming an interrupted run continues it toward completion
- **WHEN** a client requests to resume a run identifier for a run that was terminated mid-execution and not awaiting a question
- **THEN** the run continues executing in the background from its last completed round or turn
- **AND** it can be streamed and observed the same way a freshly-started run can

#### Scenario: Resuming a paused run leaves it paused
- **WHEN** a client requests to resume a run identifier for a run that was terminated while paused awaiting an audience question
- **THEN** the resumed run is awaiting an audience question
- **AND** submitting one resumes it to a completed verdict

#### Scenario: Resuming an unknown run identifier fails
- **WHEN** a client requests to resume a run identifier that was never started
- **THEN** the endpoint responds with an error indicating no such run exists
