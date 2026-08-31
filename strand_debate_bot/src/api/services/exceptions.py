"""Typed exceptions for the debate API's service layer, adapted from the old
(LangGraph) system's hierarchy (proposal.md, What Changes)."""


class DebateError(Exception):
    """Base exception for debate-related errors."""


class DebateExecutionError(DebateError):
    """Raised when a debate run fails -- either an exception propagated out of
    the graph call, or the graph returned Status.FAILED without raising
    (design.md, Decision 4)."""


class DebateTimeoutError(DebateError):
    """Raised when a synchronous debate run exceeds its configured timeout."""


class DebateAwaitingInputError(DebateError):
    """Raised when a synchronous debate call reaches the audience-question
    pause without one pre-supplied -- signals "paused, not failed" distinctly
    from DebateExecutionError. Carries the run_id so the caller can resume it
    through the start/stream/submit-question endpoints instead."""

    def __init__(self, run_id: str, message: str) -> None:
        self.run_id = run_id
        super().__init__(message)
