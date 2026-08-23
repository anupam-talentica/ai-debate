## Purpose

Lets a human participate mid-debate by injecting a single audience question after the rebuttal round that both debaters must address, and that factors into the moderator's final verdict, without breaking existing synchronous or streaming API contracts.

## ADDED Requirements

### Requirement: Debate Pauses For An Audience Question
After both debaters have delivered their rebuttals, the system SHALL pause debate execution and wait to receive exactly one audience question before proceeding to closing arguments.

#### Scenario: Debate reaches rebuttal completion
- **WHEN** both the Pro and Con rebuttals have been generated
- **THEN** the debate pauses and does not proceed to closing arguments until an audience question is supplied

#### Scenario: Debate does not pause before rebuttals complete
- **WHEN** the debate is still in the opening or rebuttal round (either debater has not yet finished their rebuttal)
- **THEN** the debate does not pause for an audience question

### Requirement: Both Debaters Address The Audience Question
Once an audience question is supplied, the system SHALL have both the Pro and Con debater produce a response addressing that question before closing arguments are generated.

#### Scenario: Audience question is supplied
- **WHEN** an audience question is submitted for a paused debate
- **THEN** the system generates a Pro response and a Con response to that question
- **AND** closing arguments are only generated after both responses exist

### Requirement: Moderator Verdict Weighs The Audience Q&A
The moderator's final verdict SHALL take into account how each debater addressed the audience question, in addition to their closing statements.

#### Scenario: Verdict is generated after an audience question was addressed
- **WHEN** the moderator produces its final decision for a debate that included an audience question
- **THEN** the verdict's reasoning reflects both debaters' closing statements and their responses to the audience question

### Requirement: Submitting An Audience Question Resumes A Paused Debate
The system SHALL provide a way to submit an audience question for a specific paused debate, which resumes that debate's execution from where it paused.

#### Scenario: Question submitted for a paused, known debate
- **WHEN** an audience question is submitted for a debate that is currently paused waiting for one
- **THEN** the debate resumes and proceeds through both debaters' responses, closing arguments, and the final verdict

#### Scenario: Question submitted for a debate that is not paused
- **WHEN** an audience question is submitted for a debate that has already received one, already completed, or does not exist
- **THEN** the system rejects the submission with an error identifying why, and does not alter that debate's state

### Requirement: Only One Audience Question Per Debate
The system SHALL accept at most one audience question per debate.

#### Scenario: Second question attempted after the first was accepted
- **WHEN** a second audience question is submitted for a debate whose one allowed question has already been accepted
- **THEN** the system rejects the second submission and does not re-pause the debate or regenerate the debaters' responses

### Requirement: A Paused Debate Persists Until Answered
A debate paused waiting for an audience question SHALL remain resumable indefinitely, regardless of how much time passes or whether the process that started it is still running.

#### Scenario: Question arrives after a long delay
- **WHEN** an audience question is submitted for a debate that has been paused for an extended period, including after a server restart
- **THEN** the debate resumes normally from the point it paused

#### Scenario: No question arrives
- **WHEN** a debate is paused waiting for an audience question and none is submitted
- **THEN** the debate remains paused indefinitely rather than expiring, erroring out, or proceeding on its own

### Requirement: Synchronous Debate Execution Does Not Silently Return An Incomplete Result
When a debate executed via the synchronous (non-streaming) endpoint pauses for an audience question that was not pre-supplied, the system SHALL NOT return a response that appears to represent a completed debate.

#### Scenario: Synchronous call reaches the pause point without a pre-supplied question
- **WHEN** a debate is started via the synchronous endpoint without an audience question included in the request, and execution reaches the pause point
- **THEN** the system returns an explicit error rather than a response with empty closing arguments, empty verdict, and no winner
- **AND** the error identifies the paused debate so it can be resumed through the debate-streaming and question-submission capability

### Requirement: Synchronous Debate Execution Accepts A Pre-Supplied Audience Question
The synchronous (non-streaming) endpoint SHALL accept an optional audience question as part of its request, which the debate uses in place of pausing to wait for one.

#### Scenario: Synchronous call includes an audience question up front
- **WHEN** a debate is started via the synchronous endpoint with an audience question included in the request
- **THEN** the debate does not pause, both debaters address the supplied question, and the endpoint returns a single complete response including the verdict
