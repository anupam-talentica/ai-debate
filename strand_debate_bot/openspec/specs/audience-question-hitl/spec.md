# audience-question-hitl Specification

## Purpose

Lets a human participate mid-debate by injecting a single audience question after the rebuttal round that both debaters must address, and that factors into the moderator's final verdict.

## Requirements

### Requirement: Debate Pauses For An Audience Question
After both debaters have delivered their rebuttals, the system SHALL pause debate execution and wait to receive an audience question before proceeding to closing arguments, unless a question was already supplied before the run started.

#### Scenario: Debate reaches the audience round with no question supplied
- **WHEN** both the Pro and Con rebuttals have been generated and no audience question was supplied at the start of the run
- **THEN** the debate pauses and does not proceed to closing arguments until an audience question is supplied

#### Scenario: Debate does not pause before rebuttals complete
- **WHEN** the debate is still in the opening or rebuttal round (either debater has not yet finished their rebuttal)
- **THEN** the debate does not pause for an audience question

### Requirement: A Pre-Supplied Audience Question Skips The Pause
If an audience question is already present when the debate reaches the audience round, the system SHALL proceed directly to having both debaters address it, without pausing.

#### Scenario: Audience question supplied at the start of the run
- **WHEN** a debate run starts with an audience question already provided
- **THEN** the debate does not pause when it reaches the audience round, and both debaters address the supplied question

### Requirement: Both Debaters Address The Audience Question
Once an audience question is available, the system SHALL have both the Pro and Con debater produce a response addressing that question before closing arguments are generated.

#### Scenario: Audience question is supplied
- **WHEN** an audience question is submitted for a paused debate
- **THEN** the system generates a Pro response and a Con response to that question
- **AND** closing arguments are only generated after both responses exist

### Requirement: Moderator Verdict Weighs The Audience Q&A
The moderator's final verdict SHALL take into account how each debater addressed the audience question, in addition to their closing statements.

#### Scenario: Verdict is generated after an audience question was addressed
- **WHEN** the moderator produces its final decision for a debate that included an audience question
- **THEN** the verdict's reasoning reflects both debaters' closing statements and their responses to the audience question

### Requirement: Resuming A Paused Debate Requires The Question And The Run's Accumulated State
The system SHALL provide a way to resume a paused debate by supplying the audience question together with the same accumulated debate state the run paused with, and the resumed run SHALL continue through both debaters' responses, closing arguments, and the final verdict.

#### Scenario: Question submitted for a paused run
- **WHEN** an audience question is submitted for a debate that is currently paused waiting for one, along with that run's accumulated state
- **THEN** the debate resumes and proceeds through both debaters' responses, closing arguments, and the final verdict
