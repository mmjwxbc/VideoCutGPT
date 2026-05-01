class AIAdapterError(RuntimeError):
    """Base error raised by AI adapter implementations."""


class AIAdapterConfigError(AIAdapterError):
    """Raised when required provider configuration is missing."""


class AIAdapterResponseError(AIAdapterError):
    """Raised when a provider returns an invalid payload."""

