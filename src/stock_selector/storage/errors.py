"""Small error hierarchy for local storage boundaries."""


class StorageError(Exception):
    """Base class for storage-layer failures."""


class StorageDataError(StorageError):
    """Persisted or supplied data violates a storage contract."""


class StorageIOError(StorageError):
    """Filesystem or embedded-catalog input/output failed."""
