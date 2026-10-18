"""Context-local Requests timeout injection for provider-owned network calls."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Final

import requests

DEFAULT_PROVIDER_REQUEST_TIMEOUT_SECONDS: Final = 15.0

_NO_PROVIDER_TIMEOUT: Final = None
_PROVIDER_REQUEST_TIMEOUT: ContextVar[float | None] = ContextVar(
    "stock_selector_provider_request_timeout",
    default=_NO_PROVIDER_TIMEOUT,
)
_TIMEOUT_POSITIONAL_INDEX: Final = 8
_ADAPTER_MARKER: Final = "__stock_selector_provider_timeout_adapter__"
_ORIGINAL_SESSION_REQUEST = requests.sessions.Session.request


def _provider_aware_request(
    session: requests.Session, *args: Any, **kwargs: Any
) -> requests.Response:
    """Delegate one request, injecting only the active provider timeout."""
    provider_timeout = _PROVIDER_REQUEST_TIMEOUT.get()
    if provider_timeout is not None:
        if len(args) > _TIMEOUT_POSITIONAL_INDEX:
            if args[_TIMEOUT_POSITIONAL_INDEX] is None:
                args = (
                    *args[:_TIMEOUT_POSITIONAL_INDEX],
                    provider_timeout,
                    *args[_TIMEOUT_POSITIONAL_INDEX + 1 :],
                )
        elif kwargs.get("timeout") is None:
            kwargs["timeout"] = provider_timeout
    return _ORIGINAL_SESSION_REQUEST(session, *args, **kwargs)


def _install_request_timeout_adapter() -> None:
    """Install the process-wide, context-gated adapter exactly once."""
    current_request = requests.sessions.Session.request
    if getattr(current_request, _ADAPTER_MARKER, False):
        return
    setattr(_provider_aware_request, _ADAPTER_MARKER, True)
    setattr(  # noqa: B010 - avoids mypy's method-assignment rejection
        requests.sessions.Session, "request", _provider_aware_request
    )


@contextmanager
def provider_request_timeout(
    timeout: float = DEFAULT_PROVIDER_REQUEST_TIMEOUT_SECONDS,
) -> Iterator[None]:
    """Apply a default Requests timeout within one provider call context."""
    token = _PROVIDER_REQUEST_TIMEOUT.set(timeout)
    try:
        yield
    finally:
        _PROVIDER_REQUEST_TIMEOUT.reset(token)


_install_request_timeout_adapter()
