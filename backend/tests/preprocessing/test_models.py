"""Validation tests for immutable preprocessing models and diagnostics."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from stock_selector.preprocessing import (
    FactorPreprocessingRequest,
    MissingValuePolicy,
    PreprocessedFactorObservation,
    PreprocessingResult,
    RawFactorObservation,
    UnavailableReason,
    ValueOrigin,
)

_AS_OF = datetime(2026, 1, 2, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


def _raw(**changes: object) -> RawFactorObservation:
    values: dict[str, object] = {
        "symbol": "600519.SH",
        "as_of": _AS_OF,
        "factor_name": "generic_metric",
        "factor_group": "generic",
        "raw_value": 10.0,
        "industry_key": "A",
        "source": "fixture",
    }
    values.update(changes)
    return RawFactorObservation(**values)


def _prepared(**changes: object) -> PreprocessedFactorObservation:
    values: dict[str, object] = {
        "symbol": "600519.SH",
        "as_of": _AS_OF,
        "factor_name": "generic_metric",
        "factor_group": "generic",
        "raw_value": 10.0,
        "prepared_value": 10.0,
        "winsorized_value": 10.0,
        "score": 50.0,
        "available": True,
        "imputed": False,
        "winsorized": False,
        "industry_key": "A",
        "value_origin": ValueOrigin.OBSERVED,
        "unavailable_reason": None,
        "source": "fixture",
    }
    values.update(changes)
    return PreprocessedFactorObservation(**values)


def test_raw_observation_validates_domain_boundaries() -> None:
    assert _raw().symbol == "600519.SH"
    for changes in (
        {"symbol": "600519"},
        {"as_of": _AS_OF.replace(tzinfo=None)},
        {"factor_name": ""},
        {"factor_group": ""},
        {"raw_value": float("nan")},
        {"industry_key": ""},
        {"source": ""},
    ):
        with pytest.raises(ValidationError):
            _raw(**changes)


def test_preprocessed_availability_and_imputation_metadata_are_consistent() -> None:
    assert _prepared().available is True
    unavailable = _prepared(
        raw_value=None,
        prepared_value=None,
        winsorized_value=None,
        score=None,
        available=False,
        value_origin=ValueOrigin.MISSING,
        unavailable_reason=UnavailableReason.MISSING_VALUE,
    )
    assert unavailable.unavailable_reason is UnavailableReason.MISSING_VALUE
    for changes in (
        {"score": 101.0},
        {"available": False},
        {"available": True, "score": None},
        {"imputed": True},
        {"prepared_value": None, "winsorized_value": 10.0},
    ):
        with pytest.raises(ValidationError):
            _prepared(**changes)


def test_request_and_result_validate_multiplier_and_diagnostic_counts() -> None:
    with pytest.raises(ValidationError):
        FactorPreprocessingRequest(observations=(_raw(),), mad_multiplier=0.0)
    value = _prepared()
    result = PreprocessingResult(
        as_of=_AS_OF,
        factor_name="generic_metric",
        factor_group="generic",
        input_count=1,
        observed_count=1,
        imputed_count=0,
        available_count=1,
        unavailable_count=0,
        winsorized_count=0,
        missing_policy=MissingValuePolicy.KEEP_MISSING,
        direction="higher_is_better",
        neutralization="none",
        values=(value,),
    )
    assert result.values == (value,)
    with pytest.raises(ValidationError):
        PreprocessingResult(**{**result.model_dump(), "available_count": 0})
