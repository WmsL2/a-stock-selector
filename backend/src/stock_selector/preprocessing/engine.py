"""Deterministic, standard-library-only cross-sectional preprocessing engine."""

from collections import defaultdict
from dataclasses import dataclass
from math import isclose
from statistics import median

from .errors import FactorPreprocessingDataError
from .models import (
    FactorDirection,
    FactorPreprocessingRequest,
    MissingValuePolicy,
    NeutralizationMode,
    PreprocessedFactorObservation,
    PreprocessingResult,
    RawFactorObservation,
    UnavailableReason,
    ValueOrigin,
)

_MAD_SCALE = 1.4826


@dataclass(frozen=True)
class _Prepared:
    observation: RawFactorObservation
    prepared_value: float | None
    imputed: bool
    value_origin: ValueOrigin
    unavailable_reason: UnavailableReason | None


class FactorPreprocessingEngine:
    """Apply caller-selected preprocessing without data access, clocks, or mutation."""

    def preprocess(self, request: FactorPreprocessingRequest) -> PreprocessingResult:
        """Return a symbol-sorted, fully audited result for one valid cross-section."""
        observations = _validate_cross_section(request.observations)
        prepared = _prepare_values(observations, request.missing_policy)
        winsorized = _winsorize(prepared, request.winsorize, request.mad_multiplier)
        ranked = _rank_values(
            prepared, winsorized, request.direction, request.neutralization
        )
        values = tuple(
            PreprocessedFactorObservation(
                symbol=item.observation.symbol,
                as_of=item.observation.as_of,
                factor_name=item.observation.factor_name,
                factor_group=item.observation.factor_group,
                raw_value=item.observation.raw_value,
                prepared_value=item.prepared_value,
                winsorized_value=winsorized[item.observation.symbol][0],
                score=ranked[item.observation.symbol],
                available=ranked[item.observation.symbol] is not None,
                imputed=item.imputed,
                winsorized=winsorized[item.observation.symbol][1],
                industry_key=item.observation.industry_key,
                value_origin=item.value_origin,
                unavailable_reason=_unavailable_reason(
                    item, ranked[item.observation.symbol], request.neutralization
                ),
                source=item.observation.source,
            )
            for item in prepared
        )
        first = observations[0]
        return PreprocessingResult(
            as_of=first.as_of,
            factor_name=first.factor_name,
            factor_group=first.factor_group,
            input_count=len(values),
            observed_count=sum(item.raw_value is not None for item in values),
            imputed_count=sum(item.imputed for item in values),
            available_count=sum(item.available for item in values),
            unavailable_count=sum(not item.available for item in values),
            winsorized_count=sum(item.winsorized for item in values),
            missing_policy=request.missing_policy,
            direction=request.direction,
            neutralization=request.neutralization,
            values=values,
        )


def _validate_cross_section(
    observations: tuple[RawFactorObservation, ...],
) -> tuple[RawFactorObservation, ...]:
    if not observations:
        raise FactorPreprocessingDataError("observations must not be empty")
    first = observations[0]
    if len({item.symbol for item in observations}) != len(observations):
        raise FactorPreprocessingDataError("symbols must be unique")
    if any(item.as_of != first.as_of for item in observations):
        raise FactorPreprocessingDataError("observations must use one as_of")
    if any(item.factor_name != first.factor_name for item in observations):
        raise FactorPreprocessingDataError("observations must use one factor_name")
    if any(item.factor_group != first.factor_group for item in observations):
        raise FactorPreprocessingDataError("observations must use one factor_group")
    return tuple(sorted(observations, key=lambda item: item.symbol))


def _prepare_values(
    observations: tuple[RawFactorObservation, ...], policy: MissingValuePolicy
) -> tuple[_Prepared, ...]:
    observed = tuple(
        item.raw_value for item in observations if item.raw_value is not None
    )
    market_median = median(observed) if observed else None
    industry_values: dict[str, tuple[float, ...]] = {}
    by_industry: defaultdict[str, list[float]] = defaultdict(list)
    for item in observations:
        if item.industry_key is not None and item.raw_value is not None:
            by_industry[item.industry_key].append(item.raw_value)
    for industry_key, values in by_industry.items():
        industry_values[industry_key] = tuple(values)

    prepared: list[_Prepared] = []
    for item in observations:
        if item.raw_value is not None:
            prepared.append(
                _Prepared(item, item.raw_value, False, ValueOrigin.OBSERVED, None)
            )
        elif policy is MissingValuePolicy.KEEP_MISSING:
            prepared.append(
                _Prepared(
                    item,
                    None,
                    False,
                    ValueOrigin.MISSING,
                    UnavailableReason.MISSING_VALUE,
                )
            )
        elif policy is MissingValuePolicy.MARKET_MEDIAN:
            prepared.append(_market_median_prepared(item, market_median))
        else:
            prepared.append(_industry_median_prepared(item, industry_values))
    return tuple(prepared)


def _market_median_prepared(
    item: RawFactorObservation, market_median: float | None
) -> _Prepared:
    if market_median is None:
        return _Prepared(
            item,
            None,
            False,
            ValueOrigin.MISSING,
            UnavailableReason.NO_IMPUTATION_SOURCE,
        )
    return _Prepared(item, market_median, True, ValueOrigin.MARKET_MEDIAN_IMPUTED, None)


def _industry_median_prepared(
    item: RawFactorObservation, industry_values: dict[str, tuple[float, ...]]
) -> _Prepared:
    if item.industry_key is None:
        return _Prepared(
            item,
            None,
            False,
            ValueOrigin.MISSING,
            UnavailableReason.MISSING_INDUSTRY,
        )
    values = industry_values.get(item.industry_key, ())
    if not values:
        return _Prepared(
            item,
            None,
            False,
            ValueOrigin.MISSING,
            UnavailableReason.NO_IMPUTATION_SOURCE,
        )
    return _Prepared(
        item,
        median(values),
        True,
        ValueOrigin.INDUSTRY_MEDIAN_IMPUTED,
        None,
    )


def _winsorize(
    prepared: tuple[_Prepared, ...], enabled: bool, multiplier: float
) -> dict[str, tuple[float | None, bool]]:
    usable = tuple(
        item.prepared_value for item in prepared if item.prepared_value is not None
    )
    values = {
        item.observation.symbol: (item.prepared_value, False) for item in prepared
    }
    if not enabled or len(usable) < 2:
        return values
    center = median(usable)
    mad = median(tuple(abs(value - center) for value in usable))
    if isclose(mad, 0.0, abs_tol=0.0):
        return values
    spread = multiplier * _MAD_SCALE * mad
    lower, upper = center - spread, center + spread
    return {
        item.observation.symbol: _clip(item.prepared_value, lower, upper)
        for item in prepared
    }


def _clip(value: float | None, lower: float, upper: float) -> tuple[float | None, bool]:
    if value is None:
        return None, False
    clipped = min(max(value, lower), upper)
    return clipped, clipped != value


def _rank_values(
    prepared: tuple[_Prepared, ...],
    winsorized: dict[str, tuple[float | None, bool]],
    direction: FactorDirection,
    neutralization: NeutralizationMode,
) -> dict[str, float | None]:
    scores: dict[str, float | None] = {symbol: None for symbol in winsorized}
    groups: defaultdict[str, list[tuple[str, float]]] = defaultdict(list)
    for item in prepared:
        value = winsorized[item.observation.symbol][0]
        if value is None or item.unavailable_reason is not None:
            continue
        industry = item.observation.industry_key
        if (
            neutralization is NeutralizationMode.INDUSTRY_PERCENTILE
            and industry is None
        ):
            continue
        group = ""
        if neutralization is NeutralizationMode.INDUSTRY_PERCENTILE:
            assert industry is not None
            group = industry
        groups[group].append((item.observation.symbol, value))
    for group_values in groups.values():
        for symbol, score in _percentile_scores(group_values, direction).items():
            scores[symbol] = score
    return scores


def _percentile_scores(
    values: list[tuple[str, float]], direction: FactorDirection
) -> dict[str, float]:
    ordered = sorted(values, key=lambda item: (item[1], item[0]))
    if len(ordered) == 1:
        return {ordered[0][0]: 50.0}
    scores: dict[str, float] = {}
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        average_rank = ((start + 1) + end) / 2
        higher_score = (average_rank - 1) / (len(ordered) - 1) * 100
        score = (
            higher_score
            if direction is FactorDirection.HIGHER_IS_BETTER
            else 100 - higher_score
        )
        score = min(100.0, max(0.0, score))
        for symbol, _value in ordered[start:end]:
            scores[symbol] = score
        start = end
    return scores


def _unavailable_reason(
    prepared: _Prepared, score: float | None, neutralization: NeutralizationMode
) -> UnavailableReason | None:
    if score is not None:
        return None
    if prepared.unavailable_reason is not None:
        return prepared.unavailable_reason
    if neutralization is NeutralizationMode.INDUSTRY_PERCENTILE:
        return UnavailableReason.MISSING_INDUSTRY
    raise AssertionError("rankable prepared value did not receive a score")
