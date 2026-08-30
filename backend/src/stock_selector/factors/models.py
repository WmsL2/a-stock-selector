"""Immutable inputs and auditable outputs for five generic factor families."""

from datetime import date, datetime
from enum import StrEnum

from pydantic import ValidationInfo, field_validator, model_validator

from stock_selector.models import FinancialRecord, ValuationRecord
from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    ensure_finite_float,
    ensure_nonempty_string,
    validate_symbol,
)
from stock_selector.preprocessing import UnavailableReason


class FactorFamily(StrEnum):
    QUALITY = "quality"
    VALUE = "value"
    GROWTH = "growth"
    MOMENTUM = "momentum"
    LOW_VOLATILITY = "low_volatility"


class ComponentUnavailableReason(StrEnum):
    MISSING_FINANCIAL = "missing_financial"
    MISSING_VALUATION = "missing_valuation"
    MISSING_COMPONENT_VALUE = "missing_component_value"
    MISSING_PRIOR_YEAR = "missing_prior_year"
    NONPOSITIVE_GROWTH_BASE = "nonpositive_growth_base"
    NONPOSITIVE_VALUATION_MULTIPLE = "nonpositive_valuation_multiple"
    MISSING_PRICE_SERIES = "missing_price_series"
    UNADJUSTED_PRICE_SERIES = "unadjusted_price_series"
    INSUFFICIENT_PRICE_HISTORY = "insufficient_price_history"
    MISSING_INDUSTRY = "missing_industry"
    PREPROCESSING_UNAVAILABLE = "preprocessing_unavailable"


class AdjustedClosePoint(DomainModel):
    """One explicitly corporate-action-adjusted close observation."""

    trade_date: date
    close: float

    @field_validator("close")
    @classmethod
    def validate_positive_close(cls, value: float) -> float:
        finite = ensure_finite_float(value, "close")
        if finite is None or finite <= 0:
            raise ValueError("close must be positive")
        return finite


class PriceSeriesInput(DomainModel):
    """Caller-supplied historical close series with explicit return semantics."""

    symbol: str
    as_of: datetime
    points: tuple[AdjustedClosePoint, ...]
    corporate_action_adjusted: bool
    source: str | None = None

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        return validate_symbol(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str | None) -> str | None:
        return value if value is None else ensure_nonempty_string(value, "source")

    @model_validator(mode="after")
    def validate_points(self) -> "PriceSeriesInput":
        dates = tuple(point.trade_date for point in self.points)
        if len(set(dates)) != len(dates):
            raise ValueError("price series trade dates must be unique")
        if any(point.trade_date > self.as_of.date() for point in self.points):
            raise ValueError("price series must not contain future trade dates")
        return self


class StockFactorInput(DomainModel):
    """All explicit, already-selected point-in-time inputs for one security."""

    symbol: str
    as_of: datetime
    industry_key: str | None = None
    financial_current: FinancialRecord | None = None
    financial_prior_year: FinancialRecord | None = None
    valuation: ValuationRecord | None = None
    price_series: PriceSeriesInput | None = None

    @field_validator("symbol")
    @classmethod
    def validate_canonical_symbol(cls, value: str) -> str:
        return validate_symbol(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @field_validator("industry_key")
    @classmethod
    def validate_industry_key(cls, value: str | None) -> str | None:
        return value if value is None else ensure_nonempty_string(value, "industry_key")

    @model_validator(mode="after")
    def validate_child_symbols(self) -> "StockFactorInput":
        children = (
            self.financial_current,
            self.financial_prior_year,
            self.valuation,
            self.price_series,
        )
        if any(item is not None and item.symbol != self.symbol for item in children):
            raise ValueError("factor input child symbol must match parent symbol")
        if self.price_series is not None and self.price_series.as_of != self.as_of:
            raise ValueError("price series as_of must match factor input as_of")
        return self


class FiveFactorRequest(DomainModel):
    """A caller-defined stock cross-section for five-family computation."""

    stocks: tuple[StockFactorInput, ...]


class FactorComponentResult(DomainModel):
    """Raw evidence and preprocessed score for one stable family component."""

    factor_name: str
    family: FactorFamily
    raw_value: float | None
    score: float | None
    available: bool
    raw_unavailable_reason: ComponentUnavailableReason | None
    preprocessing_unavailable_reason: UnavailableReason | None
    source: str | None = None

    @field_validator("factor_name")
    @classmethod
    def validate_factor_name(cls, value: str) -> str:
        return ensure_nonempty_string(value, "factor_name")

    @field_validator("raw_value", "score")
    @classmethod
    def validate_finite_values(
        cls, value: float | None, info: ValidationInfo
    ) -> float | None:
        return ensure_finite_float(value, info.field_name)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str | None) -> str | None:
        return value if value is None else ensure_nonempty_string(value, "source")

    @model_validator(mode="after")
    def validate_availability(self) -> "FactorComponentResult":
        if self.score is not None and not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")
        if self.available and self.score is None:
            raise ValueError("available component requires a score")
        if not self.available and self.score is not None:
            raise ValueError("unavailable component must not have a score")
        if self.raw_value is not None and self.raw_unavailable_reason is not None:
            raise ValueError("observed raw value must not have an unavailable reason")
        if self.raw_value is None and self.raw_unavailable_reason is None:
            raise ValueError("missing raw value requires an unavailable reason")
        if self.available and (
            self.raw_unavailable_reason is not None
            or self.preprocessing_unavailable_reason is not None
        ):
            raise ValueError("available component must have no unavailable reason")
        if not self.available and (
            self.raw_unavailable_reason is None
            and self.preprocessing_unavailable_reason is None
        ):
            raise ValueError("unavailable component requires an unavailable reason")
        return self


class FactorFamilyResult(DomainModel):
    """Equal-weight aggregation and component coverage for one factor family."""

    symbol: str
    as_of: datetime
    family: FactorFamily
    score: float | None
    available: bool
    available_components: int
    total_components: int
    component_coverage: float
    components: tuple[FactorComponentResult, ...]

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return validate_symbol(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @field_validator("score", "component_coverage")
    @classmethod
    def validate_finite_values(
        cls, value: float | None, info: ValidationInfo
    ) -> float | None:
        return ensure_finite_float(value, info.field_name)

    @model_validator(mode="after")
    def validate_components(self) -> "FactorFamilyResult":
        if self.score is not None and not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")
        if not 0 <= self.component_coverage <= 1:
            raise ValueError("component_coverage must be between 0 and 1")
        if self.total_components != len(self.components):
            raise ValueError("total_components must equal component count")
        if self.available_components != sum(item.available for item in self.components):
            raise ValueError("available_components must match components")
        expected_coverage = (
            self.available_components / self.total_components
            if self.total_components
            else 0.0
        )
        if self.component_coverage != expected_coverage:
            raise ValueError("component_coverage must match component counts")
        if self.available != (self.available_components > 0):
            raise ValueError("availability must match available components")
        if self.available != (self.score is not None):
            raise ValueError("availability must match score")
        if any(item.family is not self.family for item in self.components):
            raise ValueError("components must match family")
        if len({item.factor_name for item in self.components}) != len(self.components):
            raise ValueError("component factor names must be unique")
        return self


class FiveFactorStockResult(DomainModel):
    """The five family outputs for one security at one explicit time."""

    symbol: str
    as_of: datetime
    quality: FactorFamilyResult
    value: FactorFamilyResult
    growth: FactorFamilyResult
    momentum: FactorFamilyResult
    low_volatility: FactorFamilyResult

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return validate_symbol(value)

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @model_validator(mode="after")
    def validate_families(self) -> "FiveFactorStockResult":
        expected = {
            "quality": FactorFamily.QUALITY,
            "value": FactorFamily.VALUE,
            "growth": FactorFamily.GROWTH,
            "momentum": FactorFamily.MOMENTUM,
            "low_volatility": FactorFamily.LOW_VOLATILITY,
        }
        for field_name, family in expected.items():
            item = getattr(self, field_name)
            if (
                item.symbol != self.symbol
                or item.as_of != self.as_of
                or item.family is not family
            ):
                raise ValueError("family result identity must match stock result")
        return self


class FiveFactorCrossSectionResult(DomainModel):
    """Symbol-sorted five-family results with no weighted BaseScore."""

    as_of: datetime
    input_count: int
    stocks: tuple[FiveFactorStockResult, ...]

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @model_validator(mode="after")
    def validate_stocks(self) -> "FiveFactorCrossSectionResult":
        if self.input_count != len(self.stocks):
            raise ValueError("input_count must equal stock count")
        symbols = tuple(item.symbol for item in self.stocks)
        if symbols != tuple(sorted(symbols)) or len(set(symbols)) != len(symbols):
            raise ValueError("stocks must be sorted and unique")
        if any(item.as_of != self.as_of for item in self.stocks):
            raise ValueError("stocks must match cross-section as_of")
        return self
