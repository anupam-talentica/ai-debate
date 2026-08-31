# strands-graph-spike Specification

## Purpose

Proves, with a minimal deterministic graph, that Strands supports the three mechanics the debate-bot migration's architecture depends on: a cyclic hub revisit, graph-node interrupt/resume with external input, and state accumulation across revisits.

## Requirements

### Requirement: Cyclic hub revisit
The spike graph SHALL route through a single hub node that is revisited multiple times in one run, with each revisit dispatching a different one of three turns (Adder, human choice, Subtracter) in a fixed order, driven by a round counter rather than separate hardcoded nodes per round.

#### Scenario: Hub dispatches all three turns in order
- **WHEN** the spike graph is run to completion
- **THEN** the hub is visited before each of the Adder, human-choice, and Subtracter turns, and once more at the end to report the result

### Requirement: Graph-node interrupt/resume with external input
The spike graph SHALL pause execution at the human-choice node and resume only when externally supplied an operation ("add 2" or "subtract 2"), with that value becoming part of the graph's state for subsequent nodes.

#### Scenario: Run pauses until external input is supplied
- **WHEN** the graph reaches the human-choice node
- **THEN** execution halts and does not proceed to the Subtracter turn until an operation is externally supplied

#### Scenario: Resumed value affects the running total
- **WHEN** the run is resumed with "add 2"
- **THEN** the total after the human-choice turn increases by 2
- **WHEN** the run is resumed with "subtract 2" instead
- **THEN** the total after the human-choice turn decreases by 2

### Requirement: Cross-revisit state accumulation
The spike graph SHALL make each prior turn's contribution readable at the final hub visit, not only the most recently completed turn's output.

#### Scenario: Deterministic end-to-end totals
- **WHEN** the run starts at 10, Adder applies +5, the human choice is "add 2", and Subtracter applies -3
- **THEN** the final reported total is exactly 14
- **WHEN** the same run instead uses a human choice of "subtract 2"
- **THEN** the final reported total is exactly 10

#### Scenario: Final trace lists every turn
- **WHEN** the run completes
- **THEN** the final hub visit reports a trace listing the Adder, human-choice, and Subtracter operations in the order they occurred
