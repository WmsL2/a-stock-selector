"""Point-in-time financial, valuation, and industry history records."""

from datetime import date, datetime

from pydantic import ValidationInfo, field_validator, model_validator

from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    ensure_finite_float,
    ensure_nonempty_string,
    validate_symbol,
)


class FinancialRecord(DomainModel):
    """Financial data with explicit publication availability for point-in-time use."""

    symbol: str
    report_period: date
    announcement_date: date
    available_at: datetime
    roe: float | None = None
    roa: float | None = None
    gross_margin: float | None = None
    net_margin: float | None = None
    revenue: float | None = None
    net_profit: float | None = None
    deducted_net_profit: float | None = None
    operating_cash_flow: float | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None
    source: str

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        """Require the shared internal symbol form."""
        return validate_symbol(value)

    @field_validator("available_at")
    @classmethod
    def validate_available_at(cls, value: datetime) -> datetime:
        """Require explicit time semantics for data availability."""
        return ensure_aware_datetime(value, "available_at")

    @field_validator(
        "roe",
        "roa",
        "gross_margin",
        "net_margin",
        "revenue",
        "net_profit",
        "deducted_net_profit",
        "operating_cash_flow",
        "total_assets",
        "total_liabilities",
    )
    @classmethod
    def validate_finite_values(
        cls, value: float | None, info: ValidationInfo
    ) -> float | None:
        """Allow signed financial values but reject non-finite numbers."""
        return ensure_finite_float(value, info.field_name)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        """Require data provenance."""
        return ensure_nonempty_string(value, "source")

    @model_validator(mode="after")
    def validate_temporal_semantics(self) -> "FinancialRecord":
        """Preserve announcement and availability chronology without clock overreach."""
        if self.announcement_date < self.report_period:
            raise ValueError("announcement_date must not precede report_period")
        if self.available_at.date() < self.announcement_date:
            raise ValueError("available_at date must not precede announcement_date")
        return self


class ValuationRecord(DomainModel):
    """Point-in-time valuation values, retaining legitimate negative multiples.

    ``dividend_yield`` uses percentage units, so ``3.0`` denotes 3%.
    """

    symbol: str
    as_of: datetime
    pe: float | None = None
    pb: float | None = None
    ps: float | None = None
    pcf: float | None = None
    dividend_yield: float | None = None
    total_market_cap: float | None = None
    float_market_cap: float | None = None
    source: str

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        """Require the shared internal symbol form."""
        return validate_symbol(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        """Require explicit valuation timing."""
        return ensure_aware_datetime(value, "as_of")

    @field_validator(
        "pe",
        "pb",
        "ps",
        "pcf",
        "dividend_yield",
        "total_market_cap",
        "float_market_cap",
    )
    @classmethod
    def validate_finite_values(
        cls, value: float | None, info: ValidationInfo
    ) -> float | None:
        """Reject non-finite valuation values."""
        return ensure_finite_float(value, info.field_name)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        """Require data provenance."""
        return ensure_nonempty_string(value, "source")

    @model_validator(mode="after")
    def validate_nonnegative_values(self) -> "ValuationRecord":
        """Constrain values that cannot be negative while retaining negative multiples."""
        for field_name in ("dividend_yield", "total_market_cap", "float_market_cap"):
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must not be negative")
        return self


class IndustryRecord(DomainModel):
    """A historical industry classification interval for one security."""

    symbol: str
    industry_code: str
    industry_name: str
    classification: str
    effective_from: date
    effective_to: date | None = None
    source: str

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        """Require the shared internal symbol form."""
        return validate_symbol(value)

    @field_validator("industry_code", "industry_name", "classification", "source")
    @classmethod
    def validate_required_strings(cls, value: str, info: ValidationInfo) -> str:
        """Require names, codes, classifications, and sources."""
        return ensure_nonempty_string(value, info.field_name)

    @model_validator(mode="after")
    def validate_effective_range(self) -> "IndustryRecord":
        """Prevent a historical classification interval from ending before it begins."""
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not precede effective_from")
        return self
