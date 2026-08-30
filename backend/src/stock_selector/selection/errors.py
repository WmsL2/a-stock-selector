"""Small errors for read-only daily selection orchestration."""


class SelectionError(Exception):
    """Base error for a selection operation."""


class SelectionDataError(SelectionError):
    """Raised when local data cannot satisfy an explicit selection contract."""
