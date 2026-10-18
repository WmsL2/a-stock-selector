"""Offline tests for context-local provider Requests timeout injection."""

import inspect
from contextvars import Context
from typing import Any

import pytest
import requests

from stock_selector.providers import request_timeout as timeout_module
from stock_selector.providers.request_timeout import (
    DEFAULT_PROVIDER_REQUEST_TIMEOUT_SECONDS,
    provider_request_timeout,
)


def _capture_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_request(
        session: requests.Session, *args: Any, **kwargs: Any
    ) -> requests.Response:
        del session, args
        calls.append(kwargs.copy())
        return requests.Response()

    monkeypatch.setattr(timeout_module, "_ORIGINAL_SESSION_REQUEST", fake_request)
    return calls


def test_timeout_adapter_passes_through_outside_provider_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _capture_requests(monkeypatch)

    requests.Session().request("GET", "https://example.invalid")

    assert calls == [{}]


@pytest.mark.parametrize("supplied", [pytest.param(False, id="absent"), None])
def test_timeout_adapter_injects_default_for_absent_or_none(
    monkeypatch: pytest.MonkeyPatch, supplied: bool | None
) -> None:
    calls = _capture_requests(monkeypatch)

    with provider_request_timeout():
        if supplied is False:
            requests.Session().request("GET", "https://example.invalid")
        else:
            requests.Session().request(
                "GET", "https://example.invalid", timeout=supplied
            )

    assert calls == [{"timeout": DEFAULT_PROVIDER_REQUEST_TIMEOUT_SECONDS}]


@pytest.mark.parametrize("explicit_timeout", [2.5, 15])
def test_timeout_adapter_preserves_explicit_non_none_timeout(
    monkeypatch: pytest.MonkeyPatch, explicit_timeout: float
) -> None:
    calls = _capture_requests(monkeypatch)

    with provider_request_timeout(9.0):
        requests.Session().request(
            "GET", "https://example.invalid", timeout=explicit_timeout
        )

    assert calls == [{"timeout": explicit_timeout}]


def test_nested_timeout_scope_restores_outer_then_no_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _capture_requests(monkeypatch)
    session = requests.Session()

    with provider_request_timeout(3.0):
        session.request("GET", "https://example.invalid/outer-before")
        with provider_request_timeout(7.0):
            session.request("GET", "https://example.invalid/inner")
        session.request("GET", "https://example.invalid/outer-after")
    session.request("GET", "https://example.invalid/outside")

    assert [call.get("timeout") for call in calls] == [3.0, 7.0, 3.0, None]


def test_timeout_scope_restores_context_after_delegate_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_request(
        session: requests.Session, *args: Any, **kwargs: Any
    ) -> requests.Response:
        del session, args
        calls.append(kwargs.copy())
        if len(calls) == 1:
            raise requests.Timeout("synthetic")
        return requests.Response()

    monkeypatch.setattr(timeout_module, "_ORIGINAL_SESSION_REQUEST", fake_request)
    session = requests.Session()

    with pytest.raises(requests.Timeout, match="synthetic"), provider_request_timeout():
        session.request("GET", "https://example.invalid/fails")
    session.request("GET", "https://example.invalid/outside")

    assert calls[0]["timeout"] == DEFAULT_PROVIDER_REQUEST_TIMEOUT_SECONDS
    assert "timeout" not in calls[1]


def test_timeout_adapter_installation_is_idempotent_and_delegates_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _capture_requests(monkeypatch)
    installed = requests.sessions.Session.request

    timeout_module._install_request_timeout_adapter()
    timeout_module._install_request_timeout_adapter()
    requests.Session().request("GET", "https://example.invalid")

    assert requests.sessions.Session.request is installed
    assert len(calls) == 1


def test_timeout_values_are_isolated_between_contexts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _capture_requests(monkeypatch)
    session = requests.Session()

    def make_request(timeout: float, suffix: str) -> None:
        with provider_request_timeout(timeout):
            session.request("GET", f"https://example.invalid/{suffix}")

    Context().run(make_request, 4.0, "context-a")
    Context().run(make_request, 8.0, "context-b")
    session.request("GET", "https://example.invalid/outside")

    assert [call.get("timeout") for call in calls] == [4.0, 8.0, None]


def test_timeout_utility_adds_no_retry_or_background_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fail_once(
        session: requests.Session, *args: Any, **kwargs: Any
    ) -> requests.Response:
        nonlocal calls
        del session, args, kwargs
        calls += 1
        raise requests.Timeout("synthetic")

    monkeypatch.setattr(timeout_module, "_ORIGINAL_SESSION_REQUEST", fail_once)
    with pytest.raises(requests.Timeout, match="synthetic"), provider_request_timeout():
        requests.Session().request("GET", "https://example.invalid")

    source = inspect.getsource(timeout_module)
    assert calls == 1
    assert all(
        forbidden not in source
        for forbidden in ("threading", "multiprocessing", "subprocess", "sleep(")
    )
