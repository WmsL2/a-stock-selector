"""Small errors for bounded local collection pipelines."""


class CollectionError(Exception):
    """Base error for a collection run that cannot be safely completed."""


class CollectionDataError(CollectionError):
    """Raised when a provider batch violates the collector boundary contract."""


class CollectionNotSupportedError(CollectionError):
    """Raised when a requested collection capability is intentionally unavailable."""
