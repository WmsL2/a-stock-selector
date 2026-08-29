"""Shared local-only application fixtures for API tests."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from stock_selector.api.app import create_app
from stock_selector.config import Settings
from stock_selector.config.paths import AppPaths
from stock_selector.models import Board, Exchange, Instrument, RealtimeQuote
from stock_selector.storage import LocalMarketRepository


@pytest.fixture
def client(tmp_path) -> TestClient:  # type: ignore[no-untyped-def]
    """Create one isolated app with its lifespan-managed local repository."""
    application = create_app(AppPaths.from_project_root(tmp_path), settings=Settings())
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def repository(client: TestClient) -> LocalMarketRepository:
    """Return the test client's initialized, local-only repository."""
    return client.app.state.repository  # type: ignore[no-any-return]


def instrument(
    symbol: str = "600519.SH",
    name: str = "贵州茅台",
) -> Instrument:
    """Build a valid local instrument record."""
    exchange = Exchange(symbol.rsplit(".", maxsplit=1)[1])
    board = {
        Exchange.SSE: Board.SH_MAIN,
        Exchange.SZSE: Board.SZ_MAIN,
        Exchange.BSE: Board.BSE,
    }[exchange]
    return Instrument(
        symbol=symbol,
        name=name,
        exchange=exchange,
        board=board,
        listing_date=date(2001, 8, 27),
    )


def quote(
    symbol: str = "600519.SH",
    at: datetime | None = None,
) -> RealtimeQuote:
    """Build a quote with deliberately distinct source and ingestion timestamps."""
    ingested_at = at or datetime(2026, 8, 28, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    return RealtimeQuote(
        symbol=symbol,
        price=10.0,
        open=9.0,
        high=11.0,
        low=8.0,
        prev_close=9.5,
        volume=100.0,
        amount=1000.0,
        change_pct=5.26,
        turnover_rate=1.2,
        volume_ratio=0.8,
        source_timestamp=ingested_at - timedelta(minutes=1),
        ingested_at=ingested_at,
        source="test:local",
    )
