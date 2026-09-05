"""Pure raw component formulas; no ranking or external data access."""

from dataclasses import dataclass
from math import sqrt
from statistics import pstdev

from stock_selector.models import AdjustedDailyReturn

from .models import ComponentUnavailableReason, PriceSeriesInput, StockFactorInput


@dataclass(frozen=True)
class RawComponent:
    value: float | None
    reason: ComponentUnavailableReason | None
    source: str | None


def financial_components(stock: StockFactorInput) -> dict[str, RawComponent]:
    record = stock.financial_current
    fields = {
        "quality_roe": "roe",
        "quality_roa": "roa",
        "quality_gross_margin": "gross_margin",
        "quality_net_margin": "net_margin",
    }
    if record is None:
        return {
            name: RawComponent(None, ComponentUnavailableReason.MISSING_FINANCIAL, None)
            for name in fields
        }
    return {
        name: RawComponent(
            getattr(record, field),
            None
            if getattr(record, field) is not None
            else ComponentUnavailableReason.MISSING_COMPONENT_VALUE,
            record.source,
        )
        for name, field in fields.items()
    }


def value_components(stock: StockFactorInput) -> dict[str, RawComponent]:
    record = stock.valuation
    fields = {
        "value_earnings_yield": "pe",
        "value_book_to_price": "pb",
        "value_cashflow_yield": "pcf",
    }
    if record is None:
        return {
            name: RawComponent(None, ComponentUnavailableReason.MISSING_VALUATION, None)
            for name in fields
        }
    return {
        name: RawComponent(1 / value, None, record.source)
        if (value := getattr(record, field)) is not None and value > 0
        else RawComponent(
            None,
            ComponentUnavailableReason.NONPOSITIVE_VALUATION_MULTIPLE
            if value is not None
            else ComponentUnavailableReason.MISSING_COMPONENT_VALUE,
            record.source,
        )
        for name, field in fields.items()
    }


def growth_components(stock: StockFactorInput) -> dict[str, RawComponent]:
    current, prior = stock.financial_current, stock.financial_prior_year
    fields = {
        "growth_revenue_yoy": "revenue",
        "growth_net_profit_yoy": "net_profit",
        "growth_deducted_net_profit_yoy": "deducted_net_profit",
    }
    if current is None:
        return {
            name: RawComponent(None, ComponentUnavailableReason.MISSING_FINANCIAL, None)
            for name in fields
        }
    if prior is None or (
        prior.report_period.month,
        prior.report_period.day,
        prior.report_period.year,
    ) != (
        current.report_period.month,
        current.report_period.day,
        current.report_period.year - 1,
    ):
        return {
            name: RawComponent(
                None, ComponentUnavailableReason.MISSING_PRIOR_YEAR, current.source
            )
            for name in fields
        }
    result = {}
    for name, field in fields.items():
        value, base = getattr(current, field), getattr(prior, field)
        reason = (
            ComponentUnavailableReason.MISSING_COMPONENT_VALUE
            if value is None or base is None
            else ComponentUnavailableReason.NONPOSITIVE_GROWTH_BASE
            if base <= 0
            else None
        )
        result[name] = RawComponent(
            None if reason else (value - base) / abs(base) * 100, reason, current.source
        )
    return result


def price_components(stock: StockFactorInput) -> dict[str, RawComponent]:
    if stock.adjusted_return_series is not None:
        return _adjusted_return_price_components(stock)
    series = stock.price_series
    names = ("momentum_20d", "momentum_60d", "low_volatility_20d", "low_volatility_60d")
    if series is None:
        return {
            name: RawComponent(
                None, ComponentUnavailableReason.MISSING_PRICE_SERIES, None
            )
            for name in names
        }
    if not series.corporate_action_adjusted:
        return {
            name: RawComponent(
                None, ComponentUnavailableReason.UNADJUSTED_PRICE_SERIES, series.source
            )
            for name in names
        }
    closes = [
        point.close
        for point in sorted(series.points, key=lambda point: point.trade_date)
    ]
    return {
        "momentum_20d": _momentum(closes, 20, series),
        "momentum_60d": _momentum(closes, 60, series),
        "low_volatility_20d": _volatility(closes, 20, series),
        "low_volatility_60d": _volatility(closes, 60, series),
    }


def _adjusted_return_price_components(stock: StockFactorInput) -> dict[str, RawComponent]:
    series = stock.adjusted_return_series
    assert series is not None
    points = sorted(series.points, key=lambda item: item.trade_date)
    suffix = [points[-1]]
    for item in reversed(points[:-1]):
        if suffix[0].previous_trade_date != item.trade_date:
            break
        suffix.insert(0, item)
    return {
        "momentum_20d": _return_momentum(suffix, 20),
        "momentum_60d": _return_momentum(suffix, 60),
        "low_volatility_20d": _return_volatility(suffix, 20),
        "low_volatility_60d": _return_volatility(suffix, 60),
    }


def _return_momentum(points: list[AdjustedDailyReturn], window: int) -> RawComponent:
    if len(points) < window:
        return RawComponent(
            None, ComponentUnavailableReason.INSUFFICIENT_PRICE_HISTORY, _window_source(points)
        )
    selected = points[-window:]
    result = 1.0
    for point in selected:
        result *= 1 + point.return_fraction
    return RawComponent((result - 1) * 100, None, _window_source(selected))


def _return_volatility(points: list[AdjustedDailyReturn], window: int) -> RawComponent:
    if len(points) < window:
        return RawComponent(
            None, ComponentUnavailableReason.INSUFFICIENT_PRICE_HISTORY, _window_source(points)
        )
    selected = points[-window:]
    return RawComponent(
        pstdev(point.return_fraction for point in selected) * sqrt(252) * 100,
        None,
        _window_source(selected),
    )


def _window_source(points: list[AdjustedDailyReturn]) -> str | None:
    sources = {point.source for point in points}
    return next(iter(sources)) if len(sources) == 1 else None


def _momentum(
    closes: list[float], window: int, series: PriceSeriesInput
) -> RawComponent:
    if len(closes) < window + 1:
        return RawComponent(
            None, ComponentUnavailableReason.INSUFFICIENT_PRICE_HISTORY, series.source
        )
    return RawComponent(
        (closes[-1] / closes[-(window + 1)] - 1) * 100, None, series.source
    )


def _volatility(
    closes: list[float], window: int, series: PriceSeriesInput
) -> RawComponent:
    if len(closes) < window + 1:
        return RawComponent(
            None, ComponentUnavailableReason.INSUFFICIENT_PRICE_HISTORY, series.source
        )
    selected = closes[-(window + 1) :]
    returns = [
        selected[index] / selected[index - 1] - 1 for index in range(1, len(selected))
    ]
    return RawComponent(pstdev(returns) * sqrt(252) * 100, None, series.source)
