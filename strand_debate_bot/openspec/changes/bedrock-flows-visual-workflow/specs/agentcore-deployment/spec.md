## MODIFIED Requirements

### Requirement: Single dispatched invocation endpoint
The system SHALL expose one endpoint that accepts every debate operation (starting a run, streaming a run's events, submitting an audience question, resuming a run, querying a run's status) as a single request type, selecting the operation from a field in the request payload, without requiring the caller to know a different path per operation.

#### Scenario: Starting a debate through the dispatched endpoint
- **WHEN** a request is made to the dispatched endpoint identifying the start operation with a topic
- **THEN** a new debate run begins and the response identifies that run

#### Scenario: An unrecognized operation is rejected explicitly
- **WHEN** a request is made to the dispatched endpoint identifying an operation the system does not recognize
- **THEN** the response is an explicit error naming the problem, and no debate run is started, streamed, resumed, altered, or queried

## ADDED Requirements

### Requirement: Run status can be queried without consuming its event stream
The system SHALL let a caller query a run's current status — running, awaiting an audience question, done, or failed — by its session identifier, without opening or affecting that run's event stream, and regardless of whether the run is currently live in this process or was resumed from durable storage. When the run is done, the response SHALL include the completed debate's content. When the run has failed, the response SHALL include the failure detail.

#### Scenario: Querying an in-progress run
- **WHEN** a run's status is queried while it is still executing
- **THEN** the response indicates it is running, without emitting any of the run's events

#### Scenario: Querying a run awaiting an audience question
- **WHEN** a run's status is queried while it is paused awaiting an audience question
- **THEN** the response indicates it is awaiting a question

#### Scenario: Querying a completed run returns its content
- **WHEN** a run's status is queried after it has reached a completed verdict
- **THEN** the response indicates it is done and includes the completed debate's content

#### Scenario: Querying a failed run returns the failure detail
- **WHEN** a run's status is queried after it has failed
- **THEN** the response indicates it has failed and includes the failure detail

#### Scenario: Querying status does not require the run to be live in this process
- **WHEN** a run's status is queried for a session identifier whose run was resumed from durable storage rather than currently held in memory
- **THEN** the response reflects that run's persisted status correctly

#### Scenario: Querying an unknown run identifier fails
- **WHEN** a run's status is queried for a session identifier that was never started
- **THEN** the response is an explicit error indicating no such run exists
