"""Read-only forward-return labels for persisted official selection snapshots."""

from datetime import date, datetime
from enum import StrEnum

from pydantic import field_validator, model_validator

from stock_selector.models.common import DomainModel, ensure_aware_datetime
from stock_selector.models.market import AdjustedDailyReturn
from stock_selector.storage import LocalMarketRepository

from .research import SelectionResearchSnapshot


class SelectionResearchReturnAvailability(StrEnum):
    """Whether one fixed-horizon return label has trustworthy local evidence."""

    AVAILABLE = "available"
    ANCHOR_UNAVAILABLE = "anchor_unavailable"
    INSUFFICIENT_FUTURE_RETURNS = "insufficient_future_returns"
    NON_CONTIGUOUS_RETURN_EVIDENCE = "non_contiguous_return_evidence"


class SelectionResearchReturnLabel(DomainModel):
    """One deterministic return label without performance interpretation."""

    horizon_sessions: int
    availability: SelectionResearchReturnAvailability
    return_fraction: float | None
    endpoint_trade_date: date | None
    endpoint_observed_at: datetime | None

    @field_validator("endpoint_observed_at")
    @classmethod
    def aware_endpoint(cls, value: datetime | None) -> datetime | None:
        return (
            ensure_aware_datetime(value, "endpoint_observed_at")
            if value is not None
            else None
        )

    @model_validator(mode="after")
    def exact_availability(self) -> "SelectionResearchReturnLabel":
        if self.horizon_sessions not in (5, 20, 60):
            raise ValueError("return horizon must be one of 5, 20, or 60 sessions")
        fields_present = (
            self.return_fraction is not None,
            self.endpoint_trade_date is not None,
            self.endpoint_observed_at is not None,
        )
        if self.availability is SelectionResearchReturnAvailability.AVAILABLE:
            if not all(fields_present):
                raise ValueError("available return label requires complete endpoint evidence")
        elif any(fields_present):
            raise ValueError("unavailable return label must not fabricate endpoint evidence")
        return self


class SelectionResearchReturnItem(DomainModel):
    """Fixed-horizon labels for one already-ranked official selection item."""

    rank: int
    symbol: str
    labels: tuple[SelectionResearchReturnLabel, ...]

    @model_validator(mode="after")
    def fixed_horizons(self) -> "SelectionResearchReturnItem":
        if tuple(label.horizon_sessions for label in self.labels) != (5, 20, 60):
            raise ValueError("return labels must retain the fixed 5, 20, 60 horizon order")
        return self


class SelectionResearchReturnReport(DomainModel):
    """A deterministic forward-return research projection of one snapshot."""

    schema_version: int = 1
    snapshot_as_of: datetime
    evaluated_at: datetime
    anchor_date: date
    items: tuple[SelectionResearchReturnItem, ...]

    @field_validator("snapshot_as_of", "evaluated_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "research return timestamp")

    @model_validator(mode="after")
    def exact_report(self) -> "SelectionResearchReturnReport":
        if self.schema_version != 1:
            raise ValueError("unsupported selection research return schema version")
        if self.evaluated_at < self.snapshot_as_of:
            raise ValueError("evaluated_at must not precede snapshot_as_of")
        if self.anchor_date != self.snapshot_as_of.date():
            raise ValueError("anchor_date must equal snapshot_as_of date")
        if len({item.symbol for item in self.items}) != len(self.items):
            raise ValueError("return report symbols must be unique")
        if len({item.rank for item in self.items}) != len(self.items):
            raise ValueError("return report ranks must be unique")
        return self


class SelectionResearchReturnLabeler:
    """Label a persisted snapshot from local, point-in-time HFQ return evidence only."""

    _horizons = (5, 20, 60)

    def __init__(self, repository: LocalMarketRepository) -> None:
        self._repository = repository

    def label(
        self, snapshot: SelectionResearchSnapshot, evaluated_at: datetime
    ) -> SelectionResearchReturnReport:
        """Return fixed-horizon evidence labels without selection recomputation."""
        ensure_aware_datetime(evaluated_at, "evaluated_at")
        if evaluated_at < snapshot.as_of:
            raise ValueError("evaluated_at must not precede snapshot.as_of")
        anchor_date = snapshot.as_of.date()
        return SelectionResearchReturnReport(
            snapshot_as_of=snapshot.as_of,
            evaluated_at=evaluated_at,
            anchor_date=anchor_date,
            items=tuple(
                SelectionResearchReturnItem(
                    rank=item.rank,
                    symbol=item.symbol,
                    labels=self._labels(item.symbol, anchor_date, evaluated_at),
                )
                for item in snapshot.items
            ),
        )

    def _labels(
        self, symbol: str, anchor_date: date, evaluated_at: datetime
    ) -> tuple[SelectionResearchReturnLabel, ...]:
        points = self._repository.load_latest_adjusted_daily_returns_as_of(
            symbol, evaluated_at, start_date=anchor_date
        )
        chain, availability = _contiguous_chain(points, anchor_date)
        return tuple(
            _label_for_horizon(horizon, chain, availability)
            for horizon in self._horizons
        )


def _contiguous_chain(
    points: tuple[AdjustedDailyReturn, ...], anchor_date: date
) -> tuple[tuple[AdjustedDailyReturn, ...], SelectionResearchReturnAvailability]:
    """Follow only exact previous-trade-date links; never infer missing sessions."""
    by_previous: dict[date, list[AdjustedDailyReturn]] = {}
    for point in points:
        by_previous.setdefault(point.previous_trade_date, []).append(point)
    first_successors = by_previous.get(anchor_date, [])
    if not first_successors:
        return (), SelectionResearchReturnAvailability.ANCHOR_UNAVAILABLE
    if len(first_successors) > 1:
        return (), SelectionResearchReturnAvailability.NON_CONTIGUOUS_RETURN_EVIDENCE
    chain = [first_successors[0]]
    while len(chain) < 60:
        successors = by_previous.get(chain[-1].trade_date, [])
        if len(successors) > 1:
            return (
                tuple(chain),
                SelectionResearchReturnAvailability.NON_CONTIGUOUS_RETURN_EVIDENCE,
            )
        if not successors:
            has_later_evidence = any(
                point.trade_date > chain[-1].trade_date
                for point in points
            )
            return (
                tuple(chain),
                SelectionResearchReturnAvailability.NON_CONTIGUOUS_RETURN_EVIDENCE
                if has_later_evidence
                else SelectionResearchReturnAvailability.INSUFFICIENT_FUTURE_RETURNS,
            )
        chain.append(successors[0])
    return tuple(chain), SelectionResearchReturnAvailability.AVAILABLE


def _label_for_horizon(
    horizon: int, chain: tuple[AdjustedDailyReturn, ...],
    unavailable: SelectionResearchReturnAvailability,
) -> SelectionResearchReturnLabel:
    if len(chain) < horizon:
        return SelectionResearchReturnLabel(
            horizon_sessions=horizon,
            availability=unavailable,
            return_fraction=None,
            endpoint_trade_date=None,
            endpoint_observed_at=None,
        )
    endpoint = chain[horizon - 1]
    compounded = 1.0
    for point in chain[:horizon]:
        compounded *= 1 + point.return_fraction
    return SelectionResearchReturnLabel(
        horizon_sessions=horizon,
        availability=SelectionResearchReturnAvailability.AVAILABLE,
        return_fraction=compounded - 1,
        endpoint_trade_date=endpoint.trade_date,
        endpoint_observed_at=endpoint.observed_at,
    )
