# agent_builder_poc

Scratch codebase for the 20-minute `agent-builder` + `swarm` evaluation.
See [PRD.md](PRD.md) for the plan and exact commands.

This directory intentionally starts empty besides the PRD — the point of the
POC is to see what `strands` (agent-builder) scaffolds on its own, rather than
hand-writing the agent files first.

## Quickstart
```bash
pipx install strands-agents-builder
export ANTHROPIC_API_KEY=<your-key>
strands --version
```
Then run the prompt in [PRD.md](PRD.md#exact-command-to-run).
