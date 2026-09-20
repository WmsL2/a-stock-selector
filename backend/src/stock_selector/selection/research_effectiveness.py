"""Pure descriptive effectiveness metrics for already-labeled selection history."""

import math
import statistics
from datetime import date, datetime

from pydantic import Field, ValidationInfo, field_validator, model_validator

from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    ensure_finite_float,
)

from .research_return_history import SelectionResearchReturnHistory
from .research_returns import (
    SelectionResearchReturnAvailability,
    SelectionResearchReturnLabel,
)


class SelectionResearchHorizonEffectiveness(DomainModel):
    """Descriptive item-observation metrics for one fixed return horizon."""

    horizon_sessions: int
    total_labels: int = Field(ge=0)
    available_labels: int = Field(ge=0)
    anchor_unavailable_labels: int = Field(ge=0)
    insufficient_future_returns_labels: int = Field(ge=0)
    non_contiguous_return_evidence_labels: int = Field(ge=0)
    availability_rate: float | None
    positive_return_labels: int = Field(ge=0)
    zero_return_labels: int = Field(ge=0)
    negative_return_labels: int = Field(ge=0)
    positive_return_rate: float | None
    mean_return_fraction: float | None
    median_return_fraction: float | None

    @field_validator(
        "availability_rate",
        "positive_return_rate",
        "mean_return_fraction",
        "median_return_fraction",
    )
    @classmethod
    def finite_metrics(
        cls, value: float | None, info: ValidationInfo
    ) -> float | None:
        return ensure_finite_float(value, info.field_name)

    @model_validator(mode="after")
    def exact_counts(self) -> "SelectionResearchHorizonEffectiveness":
        if self.horizon_sessions not in (5, 20, 60):
            raise ValueError("effectiveness horizon must be one of 5, 20, or 60 sessions")
        if self.total_labels != (
            self.available_labels
            + self.anchor_unavailable_labels
            + self.insufficient_future_returns_labels
            + self.non_contiguous_return_evidence_labels
        ):
            raise ValueError("availability counts must partition total labels")
        if self.available_labels != (
            self.positive_return_labels
            + self.zero_return_labels
            + self.negative_return_labels
        ):
            raise ValueError("return direction counts must partition available labels")
        expected_availability = (
            self.available_labels / self.total_labels if self.total_labels else None
        )
        if self.availability_rate != expected_availability:
            raise ValueError("availability_rate must match availability counts")
        expected_positive = (
            self.positive_return_labels / self.available_labels
            if self.available_labels
            else None
        )
        if self.positive_return_rate != expected_positive:
            raise ValueError("positive_return_rate must match available labels")
        metrics_present = (
            self.mean_return_fraction is not None,
            self.median_return_fraction is not None,
        )
        if self.available_labels == 0 and any(metrics_present):
            raise ValueError("return metrics require available labels")
        if self.available_labels > 0 and not all(metrics_present):
            raise ValueError("available labels require return metrics")
        return self


class SelectionResearchEffectivenessReport(DomainModel):
    """Pure aggregate description of one Task49 history, never an investment result."""

    schema_version: int = 1
    evaluated_at: datetime
    start_date: date | None
    end_date: date | None
    snapshot_count: int = Field(ge=0)
    empty_snapshot_count: int = Field(ge=0)
    item_observation_count: int = Field(ge=0)
    horizons: tuple[SelectionResearchHorizonEffectiveness, ...]

    @field_validator("evaluated_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "evaluated_at")

    @model_validator(mode="after")
    def exact_report(self) -> "SelectionResearchEffectivenessReport":
        if self.schema_version != 1:
            raise ValueError("unsupported selection research effectiveness schema version")
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("start_date must not follow end_date")
        if self.empty_snapshot_count > self.snapshot_count:
            raise ValueError("empty snapshots must not exceed snapshots")
        if tuple(item.horizon_sessions for item in self.horizons) != (5, 20, 60):
            raise ValueError("effectiveness horizons must retain fixed 5, 20, 60 order")
        if any(item.total_labels != self.item_observation_count for item in self.horizons):
            raise ValueError("each horizon total must equal item observations")
        return self


class SelectionResearchEffectivenessAnalyzer:
    """Compute deterministic descriptive metrics from labels already present in history."""

    _horizons = (5, 20, 60)

    def analyze(
        self, history: SelectionResearchReturnHistory
    ) -> SelectionResearchEffectivenessReport:
        """Describe label availability and returns without evaluating a strategy."""
        item_count = sum(len(report.items) for report in history.reports)
        empty_count = sum(not report.items for report in history.reports)
        labels_by_horizon: dict[int, list[SelectionResearchReturnLabel]] = {
            horizon: [] for horizon in self._horizons
        }
        for report in history.reports:
            for item in report.items:
                for label in item.labels:
                    labels_by_horizon[label.horizon_sessions].append(label)
        return SelectionResearchEffectivenessReport(
            evaluated_at=history.evaluated_at,
            start_date=history.start_date,
            end_date=history.end_date,
            snapshot_count=len(history.reports),
            empty_snapshot_count=empty_count,
            item_observation_count=item_count,
            horizons=tuple(
                _effectiveness(horizon, labels_by_horizon[horizon])
                for horizon in self._horizons
            ),
        )


def _effectiveness(
    horizon: int, labels: list[SelectionResearchReturnLabel]
) -> SelectionResearchHorizonEffectiveness:
    available = [
        label.return_fraction
        for label in labels
        if label.availability is SelectionResearchReturnAvailability.AVAILABLE
    ]
    returns = [value for value in available if value is not None]
    total = len(labels)
    available_count = len(returns)
    return SelectionResearchHorizonEffectiveness(
        horizon_sessions=horizon,
        total_labels=total,
        available_labels=available_count,
        anchor_unavailable_labels=sum(
            label.availability is SelectionResearchReturnAvailability.ANCHOR_UNAVAILABLE
            for label in labels
        ),
        insufficient_future_returns_labels=sum(
            label.availability
            is SelectionResearchReturnAvailability.INSUFFICIENT_FUTURE_RETURNS
            for label in labels
        ),
        non_contiguous_return_evidence_labels=sum(
            label.availability
            is SelectionResearchReturnAvailability.NON_CONTIGUOUS_RETURN_EVIDENCE
            for label in labels
        ),
        availability_rate=available_count / total if total else None,
        positive_return_labels=sum(value > 0 for value in returns),
        zero_return_labels=sum(value == 0 for value in returns),
        negative_return_labels=sum(value < 0 for value in returns),
        positive_return_rate=(
            sum(value > 0 for value in returns) / available_count
            if available_count
            else None
        ),
        mean_return_fraction=math.fsum(returns) / available_count if available_count else None,
        median_return_fraction=statistics.median(returns) if returns else None,
    )
