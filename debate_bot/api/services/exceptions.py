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


class DebateValidationError(DebateError):
    """Raised when debate state validation fails."""
    pass


class LLMError(DebateError):
    """Raised when LLM call fails."""
    pass


class MemoryStoreError(DebateError):
    """Raised when memory store operations fail."""
    pass
