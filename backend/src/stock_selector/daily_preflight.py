"""Strictly read-only daily upstream-input preflight orchestration."""

from datetime import datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from pydantic import field_validator

from stock_selector.config.models import Settings
from stock_selector.config.paths import AppPaths
from stock_selector.models.common import DomainModel, ensure_aware_datetime
from stock_selector.risk import RiskError
from stock_selector.risk.evaluator import RiskEligibilityEvaluator
from stock_selector.selection import (
    CurrentSelectionCoverageAuditor,
    CurrentSelectionCoverageRequest,
    SelectionBlocker,
)
from stock_selector.storage import LocalMarketRepository, StorageError
from stock_selector.universe import CurrentUniverseService, UniverseError


class DailyPreflightOutcome(StrEnum):
    """Operator-facing terminal state for a read-only preflight."""

    READY = "READY"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


class DailyPreflightStorageState(StrEnum):
    """Local storage state observed without creating or repairing anything."""

    COLD = "cold"
    AVAILABLE = "available"
    ERROR = "error"


class DailyPreflightResult(DomainModel):
    """Truthful, non-executing daily preflight report."""

    as_of: datetime
    configured_timezone: str
    outcome: DailyPreflightOutcome
    local_storage_state: DailyPreflightStorageState
    structural_members: int | None
    risk_complete_members: int | None
    risk_eligible_members: int | None
    eligible_factor_input_covered: int | None
    eligible_factor_input_missing: int | None
    upstream_inputs_ready: bool | None
    readiness_blockers: tuple[str, ...]
    recommended_next_operator_action: str
    provider_unchecked: bool = True
    current_risk_timezone_note: str | None = None
    error: str | None = None

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")


class DailyPreflightService:
    """Read local evidence once and reuse the authoritative readiness auditors."""

    def __init__(self, paths: AppPaths, settings: Settings) -> None:
        self._paths = paths
        self._settings = settings

    def run(self, as_of: datetime) -> DailyPreflightResult:
        """Return one explicit-time result without providers, mutations, or scoring."""
        as_of = ensure_aware_datetime(as_of, "as_of")
        try:
            repository = LocalMarketRepository.open_read_only(self._paths)
            return self._evaluate(repository, as_of)
        except (RiskError, StorageError, UniverseError, ValueError) as exc:
            return self._error(as_of, str(exc))

    def _evaluate(
        self, repository: LocalMarketRepository, as_of: datetime
    ) -> DailyPreflightResult:
        structural = CurrentUniverseService(repository, self._settings).build_current(
            as_of.date()
        )
        if not structural.members:
            return DailyPreflightResult(
                as_of=as_of,
                configured_timezone=self._settings.app.timezone,
                outcome=DailyPreflightOutcome.BLOCKED,
                local_storage_state=DailyPreflightStorageState(
                    repository.read_only_storage_state
                ),
                structural_members=0,
                risk_complete_members=0,
                risk_eligible_members=0,
                eligible_factor_input_covered=0,
                eligible_factor_input_missing=0,
                upstream_inputs_ready=False,
                readiness_blockers=(SelectionBlocker.NO_STRUCTURAL_MEMBERS.value,),
                recommended_next_operator_action=(
                    "Initialize or repair the instrument master through the OPS04 runbook, "
                    "then rerun daily-preflight."
                ),
                current_risk_timezone_note=self._timezone_note(as_of),
            )

        risk_states = repository.load_risk_states(as_of.date(), structural.members)
        risk = RiskEligibilityEvaluator().evaluate(
            structural, risk_states, self._settings.universe
        )
        report = CurrentSelectionCoverageAuditor().audit(
            CurrentSelectionCoverageRequest(
                as_of=as_of,
                structural_symbols=structural.members,
                risk_record_symbols=tuple(item.symbol for item in risk_states),
                risk_complete_symbols=tuple(
                    item.symbol for item in risk.decisions if item.risk_complete
                ),
                risk_eligible_symbols=risk.eligible_members,
                financial_symbols=repository.load_financial_symbols(),
                valuation_symbols=repository.load_valuation_symbols(),
                industry_symbols=repository.load_industry_symbols(),
                factor_input_symbols=repository.load_factor_input_symbols(),
                adjusted_return_symbols=repository.load_adjusted_return_symbols(),
            )
        )
        readiness = report.input_readiness
        outcome = (
            DailyPreflightOutcome.READY
            if readiness.upstream_inputs_ready
            else DailyPreflightOutcome.BLOCKED
        )
        return DailyPreflightResult(
            as_of=as_of,
            configured_timezone=self._settings.app.timezone,
            outcome=outcome,
            local_storage_state=DailyPreflightStorageState(
                repository.read_only_storage_state
            ),
            structural_members=readiness.structural_members,
            risk_complete_members=readiness.risk_complete_members,
            risk_eligible_members=readiness.risk_eligible_members,
            eligible_factor_input_covered=readiness.eligible_factor_input_covered,
            eligible_factor_input_missing=readiness.eligible_factor_input_missing,
            upstream_inputs_ready=readiness.upstream_inputs_ready,
            readiness_blockers=tuple(item.value for item in readiness.blockers),
            recommended_next_operator_action=self._recommendation(
                readiness.blockers, readiness.upstream_inputs_ready
            ),
            current_risk_timezone_note=self._timezone_note(as_of),
        )

    def _error(self, as_of: datetime, error: str) -> DailyPreflightResult:
        return DailyPreflightResult(
            as_of=as_of,
            configured_timezone=self._settings.app.timezone,
            outcome=DailyPreflightOutcome.ERROR,
            local_storage_state=DailyPreflightStorageState.ERROR,
            structural_members=None,
            risk_complete_members=None,
            risk_eligible_members=None,
            eligible_factor_input_covered=None,
            eligible_factor_input_missing=None,
            upstream_inputs_ready=None,
            readiness_blockers=(),
            recommended_next_operator_action=(
                "Inspect local configuration and storage; do not repair or collect automatically."
            ),
            current_risk_timezone_note=self._timezone_note(as_of),
            error=error,
        )

    @staticmethod
    def _recommendation(blockers: tuple[object, ...], ready: bool) -> str:
        if ready:
            return (
                "Upstream inputs are ready. Obtain explicit human approval before "
                "running official selection."
            )
        values = tuple(getattr(blocker, "value", blocker) for blocker in blockers)
        if values == ("risk_state_coverage_incomplete",):
            return (
                "Exact-date risk evidence is incomplete. Resolve the data/provider path "
                "outside preflight, then rerun daily-preflight."
            )
        if values == ("no_risk_eligible_members",):
            return (
                "All structural members are risk-ineligible after complete evidence; "
                "do not run official selection."
            )
        return (
            "Eligible factor-input evidence is incomplete. An operator may run a bounded "
            "refresh, then rerun daily-preflight."
        )

    def _timezone_note(self, as_of: datetime) -> str | None:
        shanghai_date = as_of.astimezone(ZoneInfo("Asia/Shanghai")).date()
        if shanghai_date == as_of.date():
            return None
        return (
            "Current-risk providers use Asia/Shanghai dates; the configured-timezone "
            f"date {as_of.date().isoformat()} differs from Shanghai date {shanghai_date.isoformat()}."
        )
