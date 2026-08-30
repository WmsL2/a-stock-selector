"""Offline behavioral tests for Task 14 realtime CLI commands."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from stock_selector import cli, providers, storage
from stock_selector.config import Settings
from stock_selector.models import RealtimeQuote
from stock_selector.providers.requests import RealtimeQuotesRequest


def test_realtime_status_is_offline_and_uses_project_timezone(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repository = FakeRepository(
        (_quote("600519.SH", ingested_at=datetime.now(UTC)),)
    )
    _patch_realtime_dependencies(monkeypatch, repository, ProviderMustNotConstruct())
    monkeypatch.setattr(cli, "load_settings", lambda _paths: Settings())
    monkeypatch.setattr(
        providers,
        "AKShareProvider",
        lambda: (_ for _ in ()).throw(AssertionError("provider constructed")),
    )

    assert cli.main(["realtime", "status"]) == 0
    output = capsys.readouterr().out
    assert "Freshness:" in output
    assert "Calculation at:" in output
    assert "+08:00" in output
    assert "Stored quotes: 1" in output
    assert "Ranking allowed:" in output
    assert "Snapshot scope: selective_persisted" in output
    assert repository.saved == []


def test_realtime_all_market_capture_uses_one_provider_call_without_persistence(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    provider = FakeProvider((_quote("600519.SH"), _quote("000001.SZ")))
    repository = FakeRepository(())
    _patch_realtime_dependencies(monkeypatch, repository, provider)

    assert cli.main(["realtime", "capture", "--all-market"]) == 0
    assert provider.requests == [RealtimeQuotesRequest()]
    assert repository.saved == []
    output = capsys.readouterr().out
    assert "Received quotes: 2" in output
    assert "Persisted quotes: 0" in output


def test_realtime_explicit_capture_uses_one_provider_call_without_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider((_quote("600519.SH"), _quote("000001.SZ")))
    repository = FakeRepository(())
    _patch_realtime_dependencies(monkeypatch, repository, provider)

    assert (
        cli.main(
            [
                "realtime",
                "capture",
                "--symbol",
                "600519.SH",
                "--symbol",
                "000001.SZ",
            ]
        )
        == 0
    )
    assert provider.requests == [
        RealtimeQuotesRequest(symbols=("000001.SZ", "600519.SH"))
    ]
    assert repository.saved == []


def test_realtime_explicit_capture_persists_only_requested_symbol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeProvider((_quote("600519.SH"),))
    repository = FakeRepository(())
    _patch_realtime_dependencies(monkeypatch, repository, provider)

    assert (
        cli.main(
            ["realtime", "capture", "--symbol", "600519.SH", "--persist"]
        )
        == 0
    )
    assert provider.requests == [RealtimeQuotesRequest(symbols=("600519.SH",))]
    assert repository.saved == [(_quote("600519.SH"),)]


def test_realtime_all_market_persist_rejects_before_any_runtime_access(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        cli.AppPaths,
        "from_project_root",
        staticmethod(lambda: (_ for _ in ()).throw(AssertionError("paths accessed"))),
    )

    assert cli.main(["realtime", "capture", "--all-market", "--persist"]) == 2
    assert "--persist requires one or more --symbol" in capsys.readouterr().err


def _patch_realtime_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    repository: "FakeRepository",
    provider: "FakeProvider | ProviderMustNotConstruct",
) -> None:
    monkeypatch.setattr(
        cli.AppPaths,
        "from_project_root",
        staticmethod(lambda: SimpleNamespace(config_dir=None)),
    )
    monkeypatch.setattr(cli, "load_settings", lambda _paths: Settings())
    monkeypatch.setattr(storage, "LocalMarketRepository", lambda _paths: repository)
    monkeypatch.setattr(providers, "AKShareProvider", lambda: provider)


class FakeProvider:
    def __init__(self, quotes: tuple[RealtimeQuote, ...]) -> None:
        self._quotes = quotes
        self.requests: list[RealtimeQuotesRequest] = []

    def get_realtime_quotes(
        self, request: RealtimeQuotesRequest
    ) -> tuple[RealtimeQuote, ...]:
        self.requests.append(request)
        return self._quotes


class ProviderMustNotConstruct:
    def get_realtime_quotes(
        self, _request: RealtimeQuotesRequest
    ) -> tuple[RealtimeQuote, ...]:
        raise AssertionError("provider must not be called")


class FakeRepository:
    def __init__(self, quotes: tuple[RealtimeQuote, ...]) -> None:
        self._quotes = quotes
        self.saved: list[tuple[RealtimeQuote, ...]] = []

    def initialize(self) -> None:
        return None

    def load_latest_realtime_snapshot(self) -> tuple[RealtimeQuote, ...]:
        return self._quotes

    def save_realtime_snapshot(self, quotes: tuple[RealtimeQuote, ...]) -> None:
        self.saved.append(quotes)


def _quote(
    symbol: str, *, ingested_at: datetime = datetime(2026, 8, 30, 10, tzinfo=UTC)
) -> RealtimeQuote:
    return RealtimeQuote(
        symbol=symbol,
        price=10,
        ingested_at=ingested_at,
        source="fake:realtime",
    )
