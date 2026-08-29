"""Small application-level errors exposed through stable HTTP responses."""


class APIResourceNotFound(Exception):
    """Raised when a requested local resource does not exist."""
