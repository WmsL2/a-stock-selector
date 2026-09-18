"""Read-only chronological labeling of persisted selection research snapshots."""

from datetime import date, datetime

from pydantic import field_validator, model_validator

from stock_selector.models.common import DomainModel, ensure_aware_datetime

from .research import SelectionResearchArtifactStore
from .research_returns import (
    SelectionResearchReturnLabeler,
    SelectionResearchReturnReport,
)


class SelectionResearchReturnHistory(DomainModel):
    """One evaluated-at-consistent sequence of persisted snapshot labels."""

    schema_version: int = 1
    evaluated_at: datetime
    start_date: date | None = None
    end_date: date | None = None
    reports: tuple[SelectionResearchReturnReport, ...]

    @field_validator("evaluated_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "evaluated_at")

    @model_validator(mode="after")
    def exact_history(self) -> "SelectionResearchReturnHistory":
        if self.schema_version != 1:
            raise ValueError("unsupported selection research return history schema version")
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("start_date must not follow end_date")
        snapshot_dates = tuple(report.snapshot_as_of.date() for report in self.reports)
        if snapshot_dates != tuple(sorted(snapshot_dates)):
            raise ValueError("history reports must be chronological")
        if len(set(snapshot_dates)) != len(snapshot_dates):
            raise ValueError("history reports must use unique snapshot dates")
        for report in self.reports:
            if report.evaluated_at != self.evaluated_at:
                raise ValueError("history reports must share evaluated_at")
            snapshot_date = report.snapshot_as_of.date()
            if self.start_date is not None and snapshot_date < self.start_date:
                raise ValueError("history report precedes start_date")
            if self.end_date is not None and snapshot_date > self.end_date:
                raise ValueError("history report follows end_date")
        return self


class SelectionResearchReturnHistoryBuilder:
    """Label persisted snapshots only; never reconstruct or evaluate selection history."""

    def __init__(
        self,
        artifact_store: SelectionResearchArtifactStore,
        return_labeler: SelectionResearchReturnLabeler,
    ) -> None:
        self._artifact_store = artifact_store
        self._return_labeler = return_labeler

    def build(
        self,
        evaluated_at: datetime,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> SelectionResearchReturnHistory:
        """Label all eligible canonical snapshots at one explicit evaluation instant."""
        ensure_aware_datetime(evaluated_at, "evaluated_at")
        _validate_range(start_date, end_date)
        reports = tuple(
            self._return_labeler.label(snapshot, evaluated_at)
            for snapshot in self._artifact_store.load_all()
            if _included(snapshot.as_of, evaluated_at, start_date, end_date)
        )
        return SelectionResearchReturnHistory(
            evaluated_at=evaluated_at,
            start_date=start_date,
            end_date=end_date,
            reports=reports,
        )


def _validate_range(start_date: date | None, end_date: date | None) -> None:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date must not follow end_date")


def _included(
    snapshot_as_of: datetime,
    evaluated_at: datetime,
    start_date: date | None,
    end_date: date | None,
) -> bool:
    snapshot_date = snapshot_as_of.date()
    return (
        snapshot_as_of <= evaluated_at
        and (start_date is None or snapshot_date >= start_date)
        and (end_date is None or snapshot_date <= end_date)
    )
