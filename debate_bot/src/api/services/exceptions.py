"""Custom exception types for debate service."""


class DebateError(Exception):
    """Base exception for debate-related errors."""
    pass


class DebateExecutionError(DebateError):
    """Raised when debate execution fails."""
    pass


class DebateTimeoutError(DebateError):
    """Raised when debate execution exceeds timeout."""
    pass


class DebateAwaitingInputError(DebateError):
    """Raised when a synchronous debate call reaches the audience-question
    pause without one pre-supplied — /invoke cannot inject an answer
    interactively, so this signals "paused, not failed" distinctly from
    DebateExecutionError. Carries the run_id so the caller can resume it
    through the streaming + audience-question endpoints instead."""

    def __init__(self, run_id: str, message: str):
        self.run_id = run_id
        super().__init__(message)


class DebateValidationError(DebateError):
    """Raised when debate state validation fails."""
    pass


class LLMError(DebateError):
    """Raised when LLM call fails."""
    pass


class MemoryStoreError(DebateError):
    """Raised when memory store operations fail."""
    pass
