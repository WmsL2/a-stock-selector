"""Offline capability-contract tests for provider interfaces."""

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from stock_selector.models import (
    Board,
    DailyBar,
    Exchange,
    FinancialRecord,
    IndustryRecord,
    Instrument,
    MinuteBar,
    RealtimeQuote,
    ValuationRecord,
)
from stock_selector.providers import (
    DailyBarsRequest,
    DailyMarketDataProvider,
    FinancialRecordsRequest,
    FundamentalDataProvider,
    IndustryDataProvider,
    IndustryRecordsRequest,
    InstrumentProvider,
    MinuteBarsRequest,
    MinuteMarketDataProvider,
    ProviderInfo,
    RealtimeMarketDataProvider,
    RealtimeQuotesRequest,
    ValuationRecordsRequest,
)


def _as_of() -> datetime:
    """Return one shared provider-contract timestamp."""
    return datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


class FakeProvider(
    InstrumentProvider,
    DailyMarketDataProvider,
    RealtimeMarketDataProvider,
    MinuteMarketDataProvider,
    FundamentalDataProvider,
    IndustryDataProvider,
):
    """Offline test implementation covering independent provider capabilities."""

    @property
    def info(self) -> ProviderInfo:
        """Return fixed fake-provider metadata."""
        return ProviderInfo(name="fake", version="test")

    def get_instruments(self) -> tuple[Instrument, ...]:
        """Return one normalized instrument."""
        return (
            Instrument(
                symbol="600519.SH",
                name="测试证券",
                exchange=Exchange.SSE,
                board=Board.SH_MAIN,
                listing_date=date(2001, 8, 27),
            ),
        )

    def get_daily_bars(self, request: DailyBarsRequest) -> tuple[DailyBar, ...]:
        """Return one normalized daily bar."""
        return (
            DailyBar(
                symbol=request.symbol,
                trade_date=request.start_date,
                adjustment=request.adjustment,
                open=10,
                high=11,
                low=9,
                close=10,
                volume=100,
                amount=1000,
                source="fake",
            ),
        )

    def get_realtime_quotes(
        self, request: RealtimeQuotesRequest
    ) -> tuple[RealtimeQuote, ...]:
        """Return one normalized quote for the requested or default symbol."""
        symbol = request.symbols[0] if request.symbols is not None else "600519.SH"
        return (
            RealtimeQuote(
                symbol=symbol,
                price=10,
                ingested_at=_as_of(),
                source="fake",
            ),
        )

    def get_minute_bars(self, request: MinuteBarsRequest) -> tuple[MinuteBar, ...]:
        """Return one normalized minute bar."""
        return (
            MinuteBar(
                symbol=request.symbol,
                timestamp=request.start_at,
                open=10,
                high=11,
                low=9,
                close=10,
                volume=100,
                amount=1000,
                source="fake",
            ),
        )

    def get_financial_records(
        self, request: FinancialRecordsRequest
    ) -> tuple[FinancialRecord, ...]:
        """Return one normalized point-in-time financial record."""
        return (
            FinancialRecord(
                symbol=request.symbols[0],
                report_period=date(2025, 12, 31),
                announcement_date=date(2026, 1, 1),
                available_at=_as_of(),
                source="fake",
            ),
        )

    def get_valuation_records(
        self, request: ValuationRecordsRequest
    ) -> tuple[ValuationRecord, ...]:
        """Return one normalized valuation record."""
        return (
            ValuationRecord(
                symbol=request.symbols[0],
                as_of=request.as_of or _as_of(),
                source="fake",
            ),
        )

    def get_industry_records(
        self, request: IndustryRecordsRequest
    ) -> tuple[IndustryRecord, ...]:
        """Return one normalized historical industry record."""
        return (
            IndustryRecord(
                symbol=request.symbols[0],
                industry_code="C15",
                industry_name="白酒",
                classification="test",
                effective_from=date(2020, 1, 1),
                source="fake",
            ),
        )


def test_abstract_provider_cannot_be_instantiated() -> None:
    """ABC interfaces enforce implementation of required capabilities."""
    with pytest.raises(TypeError):
        InstrumentProvider()


def test_fake_provider_returns_typed_domain_batches() -> None:
    """A concrete provider supplies immutable tuple batches of domain records."""
    provider = FakeProvider()
    assert provider.info == ProviderInfo(name="fake", version="test")
    assert isinstance(provider.get_instruments(), tuple)
    daily_bars = provider.get_daily_bars(
        DailyBarsRequest(
            symbol="600519.SH", start_date=date(2026, 1, 2), end_date=date(2026, 1, 2)
        )
    )
    assert isinstance(daily_bars, tuple)
    assert isinstance(provider.get_realtime_quotes(RealtimeQuotesRequest()), tuple)
    assert isinstance(
        provider.get_minute_bars(
            MinuteBarsRequest(
                symbol="600519.SH", start_at=_as_of(), end_at=_as_of()
            )
        ),
        tuple,
    )
    assert isinstance(
        provider.get_financial_records(FinancialRecordsRequest(symbols=("600519.SH",))),
        tuple,
    )
    assert isinstance(
        provider.get_valuation_records(ValuationRecordsRequest(symbols=("600519.SH",))),
        tuple,
    )
    assert isinstance(
        provider.get_industry_records(IndustryRecordsRequest(symbols=("600519.SH",))),
        tuple,
    )


def test_provider_abstractions_do_not_depend_on_data_source_packages() -> None:
    """The abstract provider layer remains independent of concrete data sources."""
    providers_dir = Path(__file__).resolve().parents[2] / "src" / "stock_selector" / "providers"
    forbidden_modules = ("akshare", "pandas", "numpy", "streamlit", "duckdb", "pyarrow")
    for filename in ("base.py", "errors.py", "requests.py"):
        path = providers_dir / filename
        contents = path.read_text(encoding="utf-8")
        for module in forbidden_modules:
            assert f"import {module}" not in contents
            assert f"from {module}" not in contents
