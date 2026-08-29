"""Behavioral tests for deterministic generic cross-sectional preprocessing."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from stock_selector.preprocessing import (
    FactorDirection,
    FactorPreprocessingDataError,
    FactorPreprocessingEngine,
    FactorPreprocessingRequest,
    MissingValuePolicy,
    NeutralizationMode,
    RawFactorObservation,
    UnavailableReason,
    ValueOrigin,
)

_AS_OF = datetime(2026, 1, 2, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


def _observation(
    symbol: str, value: float | None, industry: str | None = "A", **changes: object
) -> RawFactorObservation:
    values: dict[str, object] = {
        "symbol": symbol,
        "as_of": _AS_OF,
        "factor_name": "generic_metric",
        "factor_group": "generic",
        "raw_value": value,
        "industry_key": industry,
        "source": "fixture",
    }
    values.update(changes)
    return RawFactorObservation(**values)


def _result(*observations: RawFactorObservation, **changes: object):
    values: dict[str, object] = {"observations": observations}
    values.update(changes)
    return FactorPreprocessingEngine().preprocess(FactorPreprocessingRequest(**values))


def _by_symbol(result):
    return {item.symbol: item for item in result.values}


@pytest.mark.parametrize(
    "observations",
    [
        (),
        (_observation("600519.SH", 1.0), _observation("600519.SH", 2.0)),
        (
            _observation("600519.SH", 1.0),
            _observation("000001.SZ", 2.0, as_of=_AS_OF + timedelta(days=1)),
        ),
        (
            _observation("600519.SH", 1.0),
            _observation("000001.SZ", 2.0, factor_name="other"),
        ),
        (
            _observation("600519.SH", 1.0),
            _observation("000001.SZ", 2.0, factor_group="other"),
        ),
    ],
)
def test_cross_section_invariants_fail_explicitly(observations) -> None:
    with pytest.raises(FactorPreprocessingDataError):
        _result(*observations)


def test_keep_missing_preserves_raw_data_and_is_deterministic() -> None:
    observations = (
        _observation("600519.SH", 10.0),
        _observation("000001.SZ", None),
        _observation("601398.SH", 30.0),
    )
    first = _result(*observations)
    reversed_result = _result(*reversed(observations))
    values = _by_symbol(first)
    missing = values["000001.SZ"]
    assert (missing.prepared_value, missing.winsorized_value, missing.score) == (
        None,
        None,
        None,
    )
    assert (
        missing.available,
        missing.imputed,
        missing.value_origin,
        missing.unavailable_reason,
    ) == (False, False, ValueOrigin.MISSING, UnavailableReason.MISSING_VALUE)
    assert values["600519.SH"].score == 0.0
    assert values["601398.SH"].score == 100.0
    assert first.values == reversed_result.values
    assert observations[0].raw_value == 10.0
    assert (
        first.observed_count,
        first.imputed_count,
        first.available_count,
        first.unavailable_count,
    ) == (2, 0, 2, 1)


def test_market_median_imputes_or_remains_unavailable_without_source() -> None:
    result = _result(
        _observation("600519.SH", 10.0),
        _observation("000001.SZ", None),
        _observation("601398.SH", 30.0),
        missing_policy=MissingValuePolicy.MARKET_MEDIAN,
    )
    imputed = _by_symbol(result)["000001.SZ"]
    assert (
        imputed.prepared_value,
        imputed.imputed,
        imputed.value_origin,
        imputed.available,
    ) == (20.0, True, ValueOrigin.MARKET_MEDIAN_IMPUTED, True)
    all_missing = _result(
        _observation("600519.SH", None),
        _observation("000001.SZ", None),
        missing_policy=MissingValuePolicy.MARKET_MEDIAN,
    )
    assert all(
        item.unavailable_reason is UnavailableReason.NO_IMPUTATION_SOURCE
        for item in all_missing.values
    )


def test_industry_median_has_no_market_fallback() -> None:
    result = _result(
        _observation("600519.SH", 10.0, "A"),
        _observation("000001.SZ", None, "A"),
        _observation("601398.SH", 30.0, "A"),
        _observation("600000.SH", 100.0, "B"),
        _observation("600036.SH", None, "B"),
        _observation("600030.SH", None, "C"),
        _observation("000333.SZ", None, None),
        missing_policy=MissingValuePolicy.INDUSTRY_MEDIAN,
    )
    values = _by_symbol(result)
    assert values["000001.SZ"].prepared_value == 20.0
    assert values["600036.SH"].prepared_value == 100.0
    assert (
        values["600030.SH"].unavailable_reason is UnavailableReason.NO_IMPUTATION_SOURCE
    )
    assert values["000333.SZ"].unavailable_reason is UnavailableReason.MISSING_INDUSTRY


def test_scaled_mad_winsorization_and_degenerate_policies() -> None:
    result = _result(
        _observation("600519.SH", 10.0),
        _observation("000001.SZ", 11.0),
        _observation("601398.SH", 12.0),
        _observation("600000.SH", 100.0),
    )
    outlier = _by_symbol(result)["600000.SH"]
    assert outlier.winsorized is True
    assert outlier.winsorized_value == pytest.approx(15.9478)
    assert result.winsorized_count == 1
    equal = _result(_observation("600519.SH", 10.0), _observation("000001.SZ", 10.0))
    assert all(not item.winsorized for item in equal.values)
    disabled = _result(
        _observation("600519.SH", 10.0),
        _observation("000001.SZ", 100.0),
        winsorize=False,
    )
    assert all(
        item.winsorized_value == item.prepared_value and not item.winsorized
        for item in disabled.values
    )


def test_percentiles_ties_all_equal_and_direction_are_explicit() -> None:
    observations = (
        _observation("600519.SH", 10.0),
        _observation("000001.SZ", 20.0),
        _observation("601398.SH", 30.0),
    )
    higher = _by_symbol(_result(*observations))
    lower = _by_symbol(
        _result(*observations, direction=FactorDirection.LOWER_IS_BETTER)
    )
    assert [
        higher[symbol].score for symbol in ("600519.SH", "000001.SZ", "601398.SH")
    ] == [0.0, 50.0, 100.0]
    assert [
        lower[symbol].score for symbol in ("600519.SH", "000001.SZ", "601398.SH")
    ] == [100.0, 50.0, 0.0]
    tied = _by_symbol(
        _result(
            _observation("600519.SH", 10.0),
            _observation("000001.SZ", 20.0),
            _observation("601398.SH", 20.0),
            _observation("600000.SH", 30.0),
        )
    )
    assert tied["000001.SZ"].score == tied["601398.SH"].score == pytest.approx(50.0)
    equal = _result(
        _observation("600519.SH", 10.0),
        _observation("000001.SZ", 10.0),
        _observation("601398.SH", 10.0),
    )
    assert all(item.score == 50.0 for item in equal.values)


def test_industry_percentiles_do_not_compare_raw_magnitudes_across_groups() -> None:
    result = _by_symbol(
        _result(
            _observation("600519.SH", 1.0, "Bank"),
            _observation("000001.SZ", 2.0, "Bank"),
            _observation("601398.SH", 3.0, "Bank"),
            _observation("600000.SH", 100.0, "Tech"),
            _observation("600036.SH", 200.0, "Tech"),
            _observation("600030.SH", 300.0, "Tech"),
            neutralization=NeutralizationMode.INDUSTRY_PERCENTILE,
        )
    )
    assert result["600519.SH"].score == result["600000.SH"].score == 0.0
    assert result["601398.SH"].score == result["600030.SH"].score == 100.0


def test_industry_neutralization_requires_industry_and_handles_singletons() -> None:
    result = _by_symbol(
        _result(
            _observation("600519.SH", 100.0, None),
            _observation("000001.SZ", 20.0, "Only"),
            neutralization=NeutralizationMode.INDUSTRY_PERCENTILE,
        )
    )
    assert result["600519.SH"].available is False
    assert result["600519.SH"].unavailable_reason is UnavailableReason.MISSING_INDUSTRY
    assert result["000001.SZ"].score == 50.0
