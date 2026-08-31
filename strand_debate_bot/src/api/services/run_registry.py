"""In-process run registry: bridges the HTTP request/response boundary across
a single background run's lifetime within this process. It is not a
durability layer -- surviving a process restart is the Durability change's
job (design.md, Goals/Non-Goals); this only exists because nothing below the
API layer keeps `invocation_state` alive across separate HTTP calls
(design.md, Decision 1)."""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal

RunStatus = Literal["running", "waiting_for_input", "done", "failed"]


@dataclass
class RunEntry:
    invocation_state: dict[str, Any]
    # The same Graph instance that started (or paused) this run. Resuming a
    # paused Strands graph reuses the exact object that raised the interrupt
    # -- resume-state lives on the Graph instance itself, not just in
    # invocation_state (confirmed by audience-question-hitl's own test:
    # the same `graph` variable is reused across the interrupt-then-resume
    # `invoke_async` calls) -- so a fresh Graph cannot stand in for it.
    graph: Any = None
    status: RunStatus = "running"
    task: "asyncio.Task[Any] | None" = None
    event_queue: "asyncio.Queue[dict[str, Any] | None]" = field(default_factory=asyncio.Queue)
    interrupt_id: str | None = None
    error: str | None = None


class RunRegistry:
    """run_id -> RunEntry. Each run_id maps to its own entry; nothing here
    ever reads or writes across entries, which is what keeps concurrent runs
    isolated from one another (design.md, "Concurrent runs are isolated")."""

    def __init__(self) -> None:
        self._entries: dict[str, RunEntry] = {}

    def create(self, run_id: str, invocation_state: dict[str, Any]) -> RunEntry:
        entry = RunEntry(invocation_state=invocation_state)
        self._entries[run_id] = entry
        return entry

    def get(self, run_id: str) -> RunEntry | None:
        return self._entries.get(run_id)
