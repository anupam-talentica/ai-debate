## Purpose

Lets a debate run entirely from cached transcripts instead of a live model, so local development, UI iteration, and demos can proceed with zero API spend while still exercising the full debate graph.

## ADDED Requirements

### Requirement: Mock mode replaces LLM-calling turns with cached replay
When mock mode is enabled, the system SHALL replace every debate-turn node that would otherwise call a live model — opening, rebuttal, and closing, for both Pro and Con — with a replay of a cached transcript, except the audience-question responder turns, which SHALL always call the live model.

#### Scenario: Full debate run makes zero live API calls
- **WHEN** a full debate is run with mock mode enabled
- **THEN** every opening, rebuttal, and closing turn's content comes from a cached transcript and no live model call is made for those turns

#### Scenario: Audience-question turns are never mocked
- **WHEN** a debate reaches the audience-question round with mock mode enabled
- **THEN** both Pro's and Con's answers to the audience question are produced by a live model call, since the question is novel each run and has no cached answer

### Requirement: Cached transcript lookup by topic with fallback
The system SHALL select a cached transcript by matching the debate's topic against each cached transcript's recorded topic, case-insensitively. If no cached transcript's topic matches, the system SHALL fall back to a deterministic cached transcript and SHALL log that no exact match was found.

#### Scenario: Exact topic match
- **WHEN** mock mode is enabled and a cached transcript exists whose recorded topic matches the debate's topic (case-insensitive)
- **THEN** that transcript is replayed for the debate

#### Scenario: No topic match falls back without failing
- **WHEN** mock mode is enabled and no cached transcript's topic matches the debate's topic
- **THEN** the debate still completes by replaying a deterministically-chosen cached transcript, and a warning is logged noting the fallback

### Requirement: Mock mode verdict is structurally compatible with the real verdict
When mock mode replays the decision turn, the system SHALL still produce a verdict in the same structured shape the live decision path produces: a winner value of exactly `"Pro"` or `"Con"`, and a justification string, regardless of how the underlying cached transcript represents that information.

#### Scenario: Verdict fields are well-formed after replay
- **WHEN** mock mode replays the decision turn from a cached transcript
- **THEN** the resulting winner is exactly `"Pro"` or `"Con"` and the justification is a non-empty string

### Requirement: Configurable artificial delay
The system SHALL apply one configurable artificial delay to each mocked turn, to simulate realistic response timing during demos.

#### Scenario: Default delay applies uniformly
- **WHEN** mock mode is enabled and no delay override is configured
- **THEN** every mocked turn (opening, rebuttal, closing, decision) waits the same default delay before returning its cached content

#### Scenario: Delay is configurable
- **WHEN** mock mode is enabled with a non-default delay configured
- **THEN** every mocked turn uses that configured delay instead of the default
