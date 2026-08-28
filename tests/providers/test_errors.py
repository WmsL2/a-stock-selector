"""Tests for the deliberately small provider error hierarchy."""

import pytest

from stock_selector.providers import (
    ProviderConnectionError,
    ProviderDataError,
    ProviderError,
    ProviderNotSupportedError,
)


@pytest.mark.parametrize(
    "error_type",
    [ProviderConnectionError, ProviderDataError, ProviderNotSupportedError],
)
def test_provider_errors_retain_safe_human_readable_context(
    error_type: type[ProviderError],
) -> None:
    """All provider errors retain only provider, operation, and message context."""
    error = error_type("example", "get_quotes", "service unavailable")
    assert isinstance(error, ProviderError)
    rendered = str(error)
    assert "example" in rendered
    assert "get_quotes" in rendered
    assert "service unavailable" in rendered
