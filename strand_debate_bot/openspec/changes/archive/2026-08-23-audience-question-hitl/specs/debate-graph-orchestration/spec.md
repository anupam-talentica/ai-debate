## MODIFIED Requirements

### Requirement: Audience round is an inert placeholder
The audience round SHALL pause debate execution to wait for an externally-submitted audience question, unless a question was already supplied before the run started, in which case the round SHALL proceed without pausing. In either case, once a question is available, the round SHALL populate the audience question and both sides' audience answers before the debate proceeds to the closing round.

#### Scenario: Audience round pauses when no question is supplied
- **WHEN** a debate reaches the audience round with no audience question already supplied
- **THEN** the round pauses and the debate does not proceed to the closing round until an audience question is supplied
- **AND** once supplied, the audience question and both sides' audience answers are populated before the closing round begins

#### Scenario: Audience round proceeds without pausing when pre-supplied
- **WHEN** a debate reaches the audience round with an audience question already supplied
- **THEN** the round completes without pausing, and the audience question and both sides' audience answers are populated before the debate proceeds to the closing round
