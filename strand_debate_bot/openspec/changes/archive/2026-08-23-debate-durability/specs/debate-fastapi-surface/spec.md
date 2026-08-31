## ADDED Requirements

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
