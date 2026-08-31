# cross-debate-memory Specification

## Purpose

Lets a new debate retrieve and build on the arguments and outcome of prior debates on similar topics, and lets a completed debate contribute to that memory for future debates.

## Requirements

### Requirement: Retrieval before a debate's arguments are generated
Before any Pro or Con turn is generated for a debate, the system SHALL retrieve up to 2 semantically similar summaries of prior completed debates, combined and capped at approximately 1200 characters, exactly once per debate run.

#### Scenario: A similar prior debate exists
- **WHEN** a new debate starts and a prior debate with a semantically similar topic has been completed
- **THEN** up to 2 of the most similar prior-debate summaries are retrieved before any Pro or Con turn is generated, combined and capped at approximately 1200 characters

#### Scenario: No prior debate has been persisted yet
- **WHEN** a new debate starts and no prior debate has been persisted (including the very first debate ever run)
- **THEN** retrieval yields no context and the debate proceeds normally with no past-debate context available to any turn

### Requirement: Retrieved context is available, non-explicitly, to every turn
Whatever context is retrieved for a debate SHALL be made available to every Pro and Con turn generated for the rest of that debate — opening, rebuttal, and closing — framed so that a turn's output does not cite or name it as coming from a prior debate.

#### Scenario: Context reaches every turn, not only the opening
- **WHEN** context was retrieved for a debate
- **THEN** each of Pro's and Con's opening, rebuttal, and closing turns is generated with that same context available, and none of those turns' output explicitly references a "past debate" or similar

#### Scenario: A second debate visibly builds on the first
- **WHEN** a debate is run on a topic similar to an already-completed debate's topic
- **THEN** the second debate's turns are generated with access to the first debate's persisted summary, observable in the content made available to those turns

### Requirement: Memory retrieval failure never blocks a debate
If retrieving past-debate context fails for any reason, the debate SHALL proceed exactly as if no similar prior debate existed, without surfacing an error to the debate's output or preventing the debate from completing.

#### Scenario: The memory store is unavailable
- **WHEN** a new debate starts and retrieving past-debate context fails
- **THEN** the debate proceeds with no past-debate context available to any turn, and no error is surfaced in the debate's output or execution

### Requirement: A completed debate's summary is persisted for future retrieval
When a debate reaches a verdict, the system SHALL persist a summary of that debate — at minimum its topic, a condensed form of each side's opening position, and the winner — so that future debates can retrieve it.

#### Scenario: A completed debate becomes available to future retrieval
- **WHEN** a debate reaches a verdict
- **THEN** a summary of that debate's topic, condensed opening positions, and winner is persisted exactly once, and becomes eligible for retrieval by subsequent debates on similar topics
