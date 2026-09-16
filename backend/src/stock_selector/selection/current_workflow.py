"""Pure composition of current input refresh and official daily selection."""

from datetime import datetime

from pydantic import field_validator, model_validator

from stock_selector.models.common import DomainModel, ensure_aware_datetime
from stock_selector.universe.models import UniverseSnapshot

from .current_refresh import (
    CurrentSelectionRefreshReport,
    CurrentSelectionRefreshService,
)
from .daily import DailySelectionService
from .models import DailySelectionResult


class CurrentDailySelectionWorkflowReport(DomainModel):
    """One coherent current refresh plus official selection result."""

    as_of: datetime
    refresh_report: CurrentSelectionRefreshReport
    selection_result: DailySelectionResult

    @field_validator("as_of")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @model_validator(mode="after")
    def exact_snapshots(self) -> "CurrentDailySelectionWorkflowReport":
        selection, diagnostics, refresh = (
            self.selection_result,
            self.selection_result.diagnostics,
            self.refresh_report,
        )
        if (
            refresh.as_of != self.as_of
            or selection.as_of != self.as_of
            or diagnostics.as_of != self.as_of
            or selection.selection.as_of != self.as_of
        ):
            raise ValueError("workflow reports must share one as_of")
        readiness = refresh.final_coverage.input_readiness
        if (
            len(refresh.structural_symbols) != diagnostics.structural_members
            or readiness.risk_records != diagnostics.risk_records
            or readiness.risk_complete_members != diagnostics.risk_complete_members
            or readiness.risk_eligible_members != diagnostics.risk_eligible_members
            or readiness.eligible_factor_input_covered != diagnostics.factor_input_members
        ):
            raise ValueError("refresh and official selection snapshots must agree")
        return self

    @property
    def had_collection_failures(self) -> bool:
        return self.refresh_report.had_collection_failures


class CurrentDailySelectionWorkflowService:
    """Run supplied refresh and selection services in one explicit-time context."""

    def __init__(self, refresh_service: CurrentSelectionRefreshService,
                 selection_service: DailySelectionService) -> None:
        self._refresh_service = refresh_service
        self._selection_service = selection_service

    def run(self, current_at: datetime, structural: UniverseSnapshot) -> CurrentDailySelectionWorkflowReport:
        current_at = ensure_aware_datetime(current_at, "current_at")
        refresh = self._refresh_service.refresh(current_at, structural)
        selection = self._selection_service.build(current_at)
        return CurrentDailySelectionWorkflowReport(
            as_of=current_at, refresh_report=refresh, selection_result=selection
        )
