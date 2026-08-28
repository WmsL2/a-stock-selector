"""Small, context-safe exception hierarchy for provider implementations."""


class ProviderError(Exception):
    """Base error for a provider operation without sensitive request context."""

    def __init__(self, provider: str, operation: str, message: str) -> None:
        """Store only human-readable provider, operation, and error message."""
        self.provider = provider
        self.operation = operation
        self.message = message
        super().__init__(f"{provider}.{operation}: {message}")


class ProviderConnectionError(ProviderError):
    """Raised when a provider service cannot be reached."""


class ProviderDataError(ProviderError):
    """Raised when provider output cannot satisfy domain-model requirements."""


class ProviderNotSupportedError(ProviderError):
    """Raised when a provider does not implement a requested capability."""
