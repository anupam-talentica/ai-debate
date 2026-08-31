## Purpose

Defines what a debate run must guarantee about surviving a process restart: its execution progress and its accumulated content are both recoverable, and resuming continues from where it left off rather than starting over.

## ADDED Requirements

### Requirement: A run's execution progress survives a process restart
The system SHALL durably record, as a debate run proceeds, which rounds and turns have completed, such that this information is recoverable after the server process restarts.

#### Scenario: Progress recorded before a restart is present after it
- **WHEN** a debate run completes one or more rounds
- **AND** the server process then restarts
- **THEN** the rounds and turns that had completed before the restart are still recorded as completed afterward

### Requirement: A run's accumulated content survives a process restart
The system SHALL durably record each round's produced content (both sides' opening, rebuttal, audience-question exchange, and closing text, plus the current round) as a debate run proceeds, such that this content is recoverable after the server process restarts, not only which steps completed.

#### Scenario: Content recorded before a restart is available for the rounds that follow it
- **WHEN** a debate run completes one or more rounds
- **AND** the server process restarts
- **AND** the run resumes
- **THEN** every round that runs after the restart is generated using the actual content of every round that completed before the restart, not empty or placeholder content

### Requirement: Resuming continues from the last completed step, not from the beginning
The system SHALL, when a run is resumed after a process restart, continue execution from the point immediately following its last completed round or turn, without re-running any round or turn that had already completed.

#### Scenario: A run killed mid-debate resumes without repeating finished rounds
- **WHEN** a debate run is terminated after completing at least the opening round but before completing the debate
- **AND** the server process restarts
- **AND** the run is resumed
- **THEN** the debate reaches a completed verdict
- **AND** no round that had already completed before termination runs a second time

### Requirement: A run that was paused awaiting an audience question resumes paused
The system SHALL, when a run is resumed after a process restart and that run had not yet received its audience question at the time of termination, resume in the same paused, awaiting-a-question state — not completed, not failed, and not silently skipping the audience round.

#### Scenario: A run killed while paused stays resumable in that paused state
- **WHEN** a debate run is terminated while paused awaiting an audience question
- **AND** the server process restarts
- **AND** the run is resumed
- **THEN** the resumed run is still awaiting an audience question
- **AND** supplying one lets the run proceed to a completed verdict

### Requirement: A run is resumable as soon as its identifier has been issued
The system SHALL ensure that any run identifier a client has received is resumable after a restart, even if the process terminates before any round of that run has completed.

#### Scenario: A run terminated immediately after starting is still resumable
- **WHEN** a debate run is started and its identifier is returned to the client
- **AND** the server process terminates before any round of that run completes
- **AND** the server process restarts
- **THEN** that run's identifier can be resumed, continuing the debate from its beginning
