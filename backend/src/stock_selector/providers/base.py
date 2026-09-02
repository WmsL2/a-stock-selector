"""Capability-based synchronous interfaces for normalized data providers."""

from abc import ABC, abstractmethod

from pydantic import field_validator

from stock_selector.models import (
    DailyBar,
    FinancialRecord,
    IndustryRecord,
    Instrument,
    MinuteBar,
    RealtimeQuote,
    ValuationRecord,
)
from stock_selector.models.common import DomainModel, ensure_nonempty_string
from stock_selector.providers.requests import (
    CurrentRiskStatesRequest,
    DailyBarsRequest,
    FinancialRecordsRequest,
    IndustryRecordsRequest,
    MinuteBarsRequest,
    RealtimeQuotesRequest,
    ValuationRecordsRequest,
)
from stock_selector.risk import DatedRiskState


class ProviderInfo(DomainModel):
    """Stable, non-sensitive identity for a concrete provider implementation."""

    name: str
    version: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Require a nonempty provider name."""
        return ensure_nonempty_string(value, "name")


class InstrumentProvider(ABC):
    """Capability for normalized security-instrument metadata."""

    @property
    @abstractmethod
    def info(self) -> ProviderInfo:
        """Return non-sensitive provider identity."""

    @abstractmethod
    def get_instruments(self) -> tuple[Instrument, ...]:
        """Return the provider's available instrument metadata batch."""


class DailyMarketDataProvider(ABC):
    """Capability for normalized daily bars.

    Concrete implementations must return bars ordered by ascending ``trade_date``.
    """

    @property
    @abstractmethod
    def info(self) -> ProviderInfo:
        """Return non-sensitive provider identity."""

    @abstractmethod
    def get_daily_bars(self, request: DailyBarsRequest) -> tuple[DailyBar, ...]:
        """Return one symbol's normalized daily-bar batch."""


class RealtimeMarketDataProvider(ABC):
    """Capability for normalized real-time quote batches."""

    @property
    @abstractmethod
    def info(self) -> ProviderInfo:
        """Return non-sensitive provider identity."""

    @abstractmethod
    def get_realtime_quotes(
        self, request: RealtimeQuotesRequest
    ) -> tuple[RealtimeQuote, ...]:
        """Return requested quotes; ``None`` symbols requests all supported quotes."""


class CurrentRiskStateProvider(ABC):
    """Capability for a complete current-day structural risk observation batch."""

    @property
    @abstractmethod
    def info(self) -> ProviderInfo:
        """Return non-sensitive provider identity."""

    @abstractmethod
    def get_current_risk_states(
        self, request: CurrentRiskStatesRequest
    ) -> tuple[DatedRiskState, ...]:
        """Return one complete current-date risk state for every requested symbol."""


class MinuteMarketDataProvider(ABC):
    """Capability for normalized timezone-aware minute bars."""

    @property
    @abstractmethod
    def info(self) -> ProviderInfo:
        """Return non-sensitive provider identity."""

    @abstractmethod
    def get_minute_bars(self, request: MinuteBarsRequest) -> tuple[MinuteBar, ...]:
        """Return one symbol's normalized minute-bar batch."""


class FundamentalDataProvider(ABC):
    """Capability for normalized financial and valuation records."""

    @property
    @abstractmethod
    def info(self) -> ProviderInfo:
        """Return non-sensitive provider identity."""

    @abstractmethod
    def get_financial_records(
        self, request: FinancialRecordsRequest
    ) -> tuple[FinancialRecord, ...]:
        """Return point-in-time financial records without factor filtering."""

    @abstractmethod
    def get_valuation_records(
        self, request: ValuationRecordsRequest
    ) -> tuple[ValuationRecord, ...]:
        """Return point-in-time valuation records without value-factor filtering."""


class IndustryDataProvider(ABC):
    """Capability for historical normalized industry-classification records."""

    @property
    @abstractmethod
    def info(self) -> ProviderInfo:
        """Return non-sensitive provider identity."""

    @abstractmethod
    def get_industry_records(
        self, request: IndustryRecordsRequest
    ) -> tuple[IndustryRecord, ...]:
        """Return industry records preserving effective date intervals."""
