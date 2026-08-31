## Purpose

Defines the observable behavior of a debate run end-to-end: the fixed round order, Con's adversarial awareness of Pro within each round, the audience round's inert placeholder behavior, and the final structured verdict.

## ADDED Requirements

### Requirement: Fixed round order
The system SHALL run a debate through the rounds opening, rebuttal, audience, and closing, in that fixed order, with each round's turns completing before the next round begins, and SHALL produce a verdict after the closing round completes.

#### Scenario: Full debate runs to a verdict
- **WHEN** a debate is run to completion for a given topic
- **THEN** the opening, rebuttal, audience, and closing rounds each complete exactly once, in that order, followed by a verdict

### Requirement: Adversarial coupling within a round
Con's opening argument SHALL be generated with Pro's opening argument as context, and Con's rebuttal SHALL be generated with Pro's opening argument as context.

#### Scenario: Con's opening responds to Pro's opening
- **WHEN** the opening round runs
- **THEN** Con's opening argument is generated only after Pro's opening argument exists, and reflects awareness of it

### Requirement: Audience round is an inert placeholder
The audience round SHALL complete without pausing for external input, and SHALL leave the audience question and both sides' audience answers unset.

#### Scenario: Audience round completes without pausing
- **WHEN** a debate reaches the audience round
- **THEN** the round completes immediately, the debate proceeds to the closing round without waiting for external input, and the audience question and both sides' audience answers remain unset

### Requirement: Structured verdict
The system SHALL produce a final verdict that identifies exactly one winner, Pro or Con, together with a justification, without relying on free-text pattern matching to determine the winner.

#### Scenario: Verdict names a single winner
- **WHEN** the closing round completes
- **THEN** the verdict identifies exactly one of Pro or Con as the winner, with an accompanying justification, and no round or turn is described as unresolved

### Requirement: Debate terminates after the verdict
The system SHALL not run any further rounds or turns once the verdict has been produced.

#### Scenario: Run ends at the verdict
- **WHEN** the verdict is produced
- **THEN** the debate run ends and no additional round begins
