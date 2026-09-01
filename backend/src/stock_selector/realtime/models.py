import math
from datetime import datetime
from enum import StrEnum

from pydantic import Field, ValidationInfo, field_validator, model_validator

from stock_selector.config.models import FactorsConfig
from stock_selector.factors import (
    FactorFamily,
    FiveFactorCrossSectionResult,
    StockFactorInput,
)
from stock_selector.models import RealtimeQuote
from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    ensure_finite_float,
    validate_symbol,
)
from stock_selector.quality.models import RealtimeFreshness
from stock_selector.risk import RiskEligibilitySnapshot
from stock_selector.scoring import BaseScoreCrossSectionResult
from stock_selector.universe import UniverseSnapshot


class RealtimeCaptureScope(StrEnum):
    ALL_MARKET = "all_market"
    EXPLICIT_SYMBOLS = "explicit_symbols"


class RealtimeCaptureRequest(DomainModel):
    symbols: tuple[str, ...] | None = None
    persist_symbols: tuple[str, ...] = ()

    @field_validator("symbols")
    @classmethod
    def requested_symbols_valid(
        cls, value: tuple[str, ...] | None
    ) -> tuple[str, ...] | None:
        if value is None:
            return value
        if not value:
            raise ValueError("explicit symbols must not be empty")
        for symbol in value:
            validate_symbol(symbol)
        if len(set(value)) != len(value):
            raise ValueError("symbols must be unique")
        return tuple(sorted(value))

    @field_validator("persist_symbols")
    @classmethod
    def persist_symbols_valid(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for symbol in value:
            validate_symbol(symbol)
        if len(set(value)) != len(value):
            raise ValueError("persist symbols must be unique")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def persist_symbols_must_be_explicitly_requested(
        self,
    ) -> "RealtimeCaptureRequest":
        """Reject an explicit request that tries to persist an unrequested symbol."""
        if self.symbols is not None and not set(self.persist_symbols).issubset(
            self.symbols
        ):
            raise ValueError("persist symbols must be included in explicit symbols")
        return self


class RealtimeCaptureResult(DomainModel):
    scope: RealtimeCaptureScope
    requested_symbols: tuple[str, ...] | None
    received_quotes: int = Field(ge=0)
    received_symbols: tuple[str, ...]
    source: str
    ingested_at: datetime
    source_timestamp_available_quotes: int = Field(ge=0)
    persist_requested_symbols: tuple[str, ...]
    persisted_quotes: int = Field(ge=0)
    persisted_symbols: tuple[str, ...]
    persistence_performed: bool
    quotes: tuple[RealtimeQuote, ...]

    @field_validator("ingested_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "ingested_at")


class RealtimeMarketStatus(DomainModel):
    calculation_at: datetime
    latest_ingested_at: datetime | None
    source: str | None
    stored_quotes: int = Field(ge=0)
    source_timestamp_available_quotes: int = Field(ge=0)
    freshness: RealtimeFreshness
    age_seconds: float | None
    ranking_allowed: bool
    normal_max_seconds: int
    warning_max_seconds: int
    snapshot_scope: str = "selective_persisted"

    @field_validator("calculation_at", "latest_ingested_at")
    @classmethod
    def aware(cls, value: datetime | None) -> datetime | None:
        return None if value is None else ensure_aware_datetime(value, "timestamp")


class RealtimeCandidatePolicy(DomainModel):
    """Explicit, immutable slow-layer reduction policy for realtime candidates."""

    min_base_score: float = 70.0
    top_fraction: float = 0.20

    @field_validator("min_base_score", "top_fraction")
    @classmethod
    def finite(cls, value: float, info: ValidationInfo) -> float:
        finite = ensure_finite_float(value, info.field_name)
        assert finite is not None
        return finite

    @model_validator(mode="after")
    def validate_policy(self) -> "RealtimeCandidatePolicy":
        if not 0 <= self.min_base_score <= 100:
            raise ValueError("min_base_score must be between 0 and 100")
        if not 0 < self.top_fraction <= 1:
            raise ValueError("top_fraction must be greater than 0 and at most 1")
        return self


class RealtimeCandidateBlocker(StrEnum):
    """Stable reasons an official candidate policy cannot run."""

    NO_STRUCTURAL_MEMBERS = "no_structural_members"
    RISK_STATE_COVERAGE_INCOMPLETE = "risk_state_coverage_incomplete"
    NO_RISK_ELIGIBLE_MEMBERS = "no_risk_eligible_members"
    NO_SCOREABLE_INSTRUMENTS = "no_scoreable_instruments"


class RealtimeCandidate(DomainModel):
    """A selected slow-layer candidate with its BaseScore audit summary."""

    symbol: str
    as_of: datetime
    base_score: float
    market_rank: int = Field(gt=0)
    data_completeness: float
    confidence: float

    @field_validator("symbol")
    @classmethod
    def canonical_symbol(cls, value: str) -> str:
        return validate_symbol(value)

    @field_validator("as_of")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @field_validator("base_score", "data_completeness", "confidence")
    @classmethod
    def finite(cls, value: float, info: ValidationInfo) -> float:
        finite = ensure_finite_float(value, info.field_name)
        assert finite is not None
        return finite

    @model_validator(mode="after")
    def validate_candidate(self) -> "RealtimeCandidate":
        if not 0 <= self.base_score <= 100:
            raise ValueError("base_score must be between 0 and 100")
        if not 0 <= self.data_completeness <= 1:
            raise ValueError("data_completeness must be between 0 and 1")
        if not 0 <= self.confidence <= self.data_completeness:
            raise ValueError("confidence must be between 0 and data_completeness")
        return self


class RealtimeCandidateDiagnostics(DomainModel):
    """Auditable counts and readiness for one candidate reduction result."""

    as_of: datetime
    policy: RealtimeCandidatePolicy
    candidate_ready: bool
    blockers: tuple[RealtimeCandidateBlocker, ...]
    structural_members: int = Field(ge=0)
    risk_complete_members: int = Field(ge=0)
    risk_eligible_members: int = Field(ge=0)
    base_score_input_members: int = Field(ge=0)
    scoreable_risk_eligible_members: int = Field(ge=0)
    top_bucket_size: int = Field(ge=0)
    top_bucket_members: int = Field(ge=0)
    threshold_qualified_members: int = Field(ge=0)
    final_candidate_members: int = Field(ge=0)

    @field_validator("as_of")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @model_validator(mode="after")
    def validate_diagnostics(self) -> "RealtimeCandidateDiagnostics":
        if len(set(self.blockers)) != len(self.blockers):
            raise ValueError("candidate blockers must be unique")
        if self.risk_complete_members > self.structural_members:
            raise ValueError("risk_complete_members must not exceed structural_members")
        if self.risk_eligible_members > self.risk_complete_members:
            raise ValueError("risk_eligible_members must not exceed risk_complete_members")
        if self.scoreable_risk_eligible_members > self.risk_eligible_members:
            raise ValueError("scoreable members must not exceed risk eligible members")
        if self.top_bucket_size > self.scoreable_risk_eligible_members:
            raise ValueError("top_bucket_size must not exceed scoreable members")
        if self.top_bucket_members != self.top_bucket_size:
            raise ValueError("top_bucket_members must equal top_bucket_size")
        if self.threshold_qualified_members > self.scoreable_risk_eligible_members:
            raise ValueError("threshold members must not exceed scoreable members")
        if self.final_candidate_members > min(
            self.top_bucket_members, self.threshold_qualified_members
        ):
            raise ValueError("final candidates must satisfy both policy filters")
        return self


class RealtimeCandidateResult(DomainModel):
    """Deterministic candidate pool and its complete policy diagnostics."""

    as_of: datetime
    policy: RealtimeCandidatePolicy
    diagnostics: RealtimeCandidateDiagnostics
    candidates: tuple[RealtimeCandidate, ...]

    @field_validator("as_of")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @model_validator(mode="after")
    def validate_result(self) -> "RealtimeCandidateResult":
        if self.diagnostics.as_of != self.as_of or self.diagnostics.policy != self.policy:
            raise ValueError("candidate result identity must match diagnostics")
        symbols = tuple(candidate.symbol for candidate in self.candidates)
        if len(set(symbols)) != len(symbols):
            raise ValueError("candidate symbols must be unique")
        if tuple(candidate.market_rank for candidate in self.candidates) != tuple(
            sorted(candidate.market_rank for candidate in self.candidates)
        ):
            raise ValueError("candidates must be ordered by market_rank")
        if any(candidate.as_of != self.as_of for candidate in self.candidates):
            raise ValueError("candidate timestamps must match result")
        if self.diagnostics.final_candidate_members != len(self.candidates):
            raise ValueError("final_candidate_members must match candidates")
        if not self.diagnostics.candidate_ready and self.candidates:
            raise ValueError("blocked candidate result must be empty")
        return self


class RealtimeCandidateSnapshotBlocker(StrEnum):
    """Stable reasons a candidate-to-quote snapshot cannot be official."""

    CANDIDATE_POOL_NOT_READY = "candidate_pool_not_ready"
    REALTIME_SNAPSHOT_UNAVAILABLE = "realtime_snapshot_unavailable"
    REALTIME_FRESHNESS_NOT_ALLOWED = "realtime_freshness_not_allowed"
    CANDIDATE_QUOTE_COVERAGE_INCOMPLETE = "candidate_quote_coverage_incomplete"


class RealtimeCandidateSnapshotItem(DomainModel):
    """One unchanged candidate paired with the quote observed for that symbol."""

    candidate: RealtimeCandidate
    quote: RealtimeQuote

    @model_validator(mode="after")
    def validate_join(self) -> "RealtimeCandidateSnapshotItem":
        if self.candidate.symbol != self.quote.symbol:
            raise ValueError("candidate and quote symbols must match")
        if self.candidate.as_of > self.quote.ingested_at:
            raise ValueError("candidate as_of must not follow quote ingestion")
        return self


class RealtimeCandidateSnapshotDiagnostics(DomainModel):
    """Auditable gating state for a candidate realtime snapshot join."""

    calculation_at: datetime
    candidate_as_of: datetime
    candidate_ready: bool
    candidate_members: int = Field(ge=0)
    capture_available: bool
    capture_scope: RealtimeCaptureScope | None
    capture_source: str | None
    capture_ingested_at: datetime | None
    received_quotes: int = Field(ge=0)
    freshness: RealtimeFreshness
    age_seconds: float | None
    freshness_allowed: bool
    matched_candidate_quotes: int = Field(ge=0)
    missing_candidate_quotes: int = Field(ge=0)
    missing_candidate_symbols: tuple[str, ...]
    snapshot_ready: bool
    blockers: tuple[RealtimeCandidateSnapshotBlocker, ...]

    @field_validator("calculation_at", "candidate_as_of", "capture_ingested_at")
    @classmethod
    def aware(cls, value: datetime | None) -> datetime | None:
        return None if value is None else ensure_aware_datetime(value, "timestamp")

    @field_validator("missing_candidate_symbols")
    @classmethod
    def missing_symbols_are_canonical(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for symbol in value:
            validate_symbol(symbol)
        if len(set(value)) != len(value) or value != tuple(sorted(value)):
            raise ValueError("missing candidate symbols must be unique and sorted")
        return value

    @model_validator(mode="after")
    def validate_diagnostics(self) -> "RealtimeCandidateSnapshotDiagnostics":
        if self.candidate_as_of > self.calculation_at:
            raise ValueError("candidate_as_of must not follow calculation_at")
        if len(set(self.blockers)) != len(self.blockers):
            raise ValueError("snapshot blockers must be unique")
        if self.capture_available != (self.capture_scope is not None):
            raise ValueError("capture scope must match capture availability")
        if self.capture_available != (self.capture_source is not None):
            raise ValueError("capture source must match capture availability")
        if self.capture_available != (self.capture_ingested_at is not None):
            raise ValueError("capture ingestion must match capture availability")
        if not self.capture_available and self.received_quotes:
            raise ValueError("missing capture cannot have received quotes")
        if self.matched_candidate_quotes + self.missing_candidate_quotes != self.candidate_members:
            raise ValueError("candidate quote coverage counts must match candidate members")
        if self.missing_candidate_quotes != len(self.missing_candidate_symbols):
            raise ValueError("missing candidate symbol count must match diagnostics")
        return self


class RealtimeCandidateSnapshotResult(DomainModel):
    """Official complete join result, or an auditable blocked/ready-empty state."""

    as_of: datetime
    diagnostics: RealtimeCandidateSnapshotDiagnostics
    items: tuple[RealtimeCandidateSnapshotItem, ...]

    @field_validator("as_of")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @model_validator(mode="after")
    def validate_result(self) -> "RealtimeCandidateSnapshotResult":
        if self.as_of != self.diagnostics.candidate_as_of:
            raise ValueError("result as_of must match candidate_as_of")
        symbols = tuple(item.candidate.symbol for item in self.items)
        if len(set(symbols)) != len(symbols):
            raise ValueError("snapshot item symbols must be unique")
        ranks = tuple(item.candidate.market_rank for item in self.items)
        if ranks != tuple(sorted(ranks)):
            raise ValueError("snapshot items must preserve candidate market rank")
        if not self.diagnostics.snapshot_ready and self.items:
            raise ValueError("blocked snapshot result must not expose partial items")
        if self.diagnostics.snapshot_ready and len(self.items) != self.diagnostics.candidate_members:
            raise ValueError("ready snapshot items must cover all candidates")
        return self


class RealtimeLightScanPolicy(DomainModel):
    """Explicit thresholds for deterministic per-quote descriptive flags."""

    strong_move_pct: float = 3.0
    high_turnover_rate_pct: float = 3.0
    high_volume_ratio: float = 1.5

    @field_validator(
        "strong_move_pct", "high_turnover_rate_pct", "high_volume_ratio"
    )
    @classmethod
    def positive_finite(cls, value: float, info: ValidationInfo) -> float:
        finite = ensure_finite_float(value, info.field_name)
        assert finite is not None
        if finite <= 0:
            raise ValueError(f"{info.field_name} must be greater than zero")
        return finite


class RealtimeLightSignals(DomainModel):
    """The six unrounded Task 17 quote observations in their source units."""

    change_pct: float | None
    price_vs_open_pct: float | None
    price_vs_prev_close_pct: float | None
    session_range_pct: float | None
    turnover_rate_pct: float | None
    volume_ratio: float | None

    @field_validator(
        "change_pct",
        "price_vs_open_pct",
        "price_vs_prev_close_pct",
        "session_range_pct",
        "turnover_rate_pct",
        "volume_ratio",
    )
    @classmethod
    def finite(cls, value: float | None, info: ValidationInfo) -> float | None:
        return ensure_finite_float(value, info.field_name)

    @model_validator(mode="after")
    def validate_non_negative_activity_values(self) -> "RealtimeLightSignals":
        if self.turnover_rate_pct is not None and self.turnover_rate_pct < 0:
            raise ValueError("turnover_rate_pct must not be negative")
        if self.volume_ratio is not None and self.volume_ratio < 0:
            raise ValueError("volume_ratio must not be negative")
        return self


class RealtimeLightFlag(StrEnum):
    STRONG_UP_MOVE = "strong_up_move"
    STRONG_DOWN_MOVE = "strong_down_move"
    HIGH_TURNOVER = "high_turnover"
    HIGH_VOLUME_RATIO = "high_volume_ratio"


class RealtimeLightScanBlocker(StrEnum):
    """The scanner has one downstream readiness dependency."""

    CANDIDATE_SNAPSHOT_NOT_READY = "candidate_snapshot_not_ready"


_REALTIME_LIGHT_FLAG_ORDER = (
    RealtimeLightFlag.STRONG_UP_MOVE,
    RealtimeLightFlag.STRONG_DOWN_MOVE,
    RealtimeLightFlag.HIGH_TURNOVER,
    RealtimeLightFlag.HIGH_VOLUME_RATIO,
)


class RealtimeLightScanItem(DomainModel):
    """One unchanged Task 16 item annotated with observations and flags."""

    snapshot_item: RealtimeCandidateSnapshotItem
    signals: RealtimeLightSignals
    flags: tuple[RealtimeLightFlag, ...]
    available_signals: int = Field(ge=0, le=6)
    signal_completeness: float

    @field_validator("signal_completeness")
    @classmethod
    def finite_completeness(cls, value: float) -> float:
        finite = ensure_finite_float(value, "signal_completeness")
        assert finite is not None
        if not 0 <= finite <= 1:
            raise ValueError("signal_completeness must be between 0 and 1")
        return finite

    @model_validator(mode="after")
    def validate_item(self) -> "RealtimeLightScanItem":
        if len(set(self.flags)) != len(self.flags):
            raise ValueError("light scan flags must be unique")
        expected_flags = tuple(flag for flag in _REALTIME_LIGHT_FLAG_ORDER if flag in self.flags)
        if self.flags != expected_flags:
            raise ValueError("light scan flags must follow semantic order")
        actual_available = sum(value is not None for value in self.signals.model_dump().values())
        if self.available_signals != actual_available:
            raise ValueError("available_signals must match non-missing signals")
        if self.signal_completeness != self.available_signals / 6:
            raise ValueError("signal_completeness must match available_signals")
        return self


class RealtimeLightScanDiagnostics(DomainModel):
    """Auditable availability and readiness information for one light scan."""

    calculation_at: datetime
    candidate_as_of: datetime
    upstream_snapshot_ready: bool
    upstream_blockers: tuple[RealtimeCandidateSnapshotBlocker, ...]
    input_items: int = Field(ge=0)
    output_items: int = Field(ge=0)
    scan_ready: bool
    blockers: tuple[RealtimeLightScanBlocker, ...]
    flagged_items: int = Field(ge=0)
    change_pct_available_items: int = Field(ge=0)
    price_vs_open_available_items: int = Field(ge=0)
    price_vs_prev_close_available_items: int = Field(ge=0)
    session_range_available_items: int = Field(ge=0)
    turnover_rate_available_items: int = Field(ge=0)
    volume_ratio_available_items: int = Field(ge=0)
    available_signal_values: int = Field(ge=0)
    total_signal_slots: int = Field(ge=0)
    overall_signal_coverage: float | None

    @field_validator("calculation_at", "candidate_as_of")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "timestamp")

    @field_validator("overall_signal_coverage")
    @classmethod
    def finite_coverage(cls, value: float | None) -> float | None:
        finite = ensure_finite_float(value, "overall_signal_coverage")
        if finite is not None and not 0 <= finite <= 1:
            raise ValueError("overall_signal_coverage must be between 0 and 1")
        return finite

    @model_validator(mode="after")
    def validate_diagnostics(self) -> "RealtimeLightScanDiagnostics":
        if self.candidate_as_of > self.calculation_at:
            raise ValueError("candidate_as_of must not follow calculation_at")
        if len(set(self.upstream_blockers)) != len(self.upstream_blockers):
            raise ValueError("upstream blockers must be unique")
        if len(set(self.blockers)) != len(self.blockers):
            raise ValueError("scan blockers must be unique")
        if self.flagged_items > self.output_items:
            raise ValueError("flagged_items must not exceed output_items")
        if self.total_signal_slots != self.input_items * 6:
            raise ValueError("total_signal_slots must equal input_items times six")
        if self.available_signal_values > self.total_signal_slots:
            raise ValueError("available_signal_values must not exceed total_signal_slots")
        if self.input_items == 0 and self.overall_signal_coverage is not None:
            raise ValueError("empty scans must not report signal coverage")
        if self.input_items and self.overall_signal_coverage != (
            self.available_signal_values / self.total_signal_slots
        ):
            raise ValueError("overall_signal_coverage must match availability")
        expected_blockers = (
            ()
            if self.upstream_snapshot_ready
            else (RealtimeLightScanBlocker.CANDIDATE_SNAPSHOT_NOT_READY,)
        )
        if self.blockers != expected_blockers or self.scan_ready != self.upstream_snapshot_ready:
            raise ValueError("scan readiness must follow upstream snapshot readiness")
        if not self.scan_ready and (self.output_items or self.flagged_items):
            raise ValueError("blocked scans must not expose output items")
        return self


class RealtimeLightScanResult(DomainModel):
    """A deterministic Task 17 annotation result, never a new ranking."""

    as_of: datetime
    policy: RealtimeLightScanPolicy
    diagnostics: RealtimeLightScanDiagnostics
    items: tuple[RealtimeLightScanItem, ...]

    @field_validator("as_of")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @model_validator(mode="after")
    def validate_result(self) -> "RealtimeLightScanResult":
        if self.as_of != self.diagnostics.candidate_as_of:
            raise ValueError("result as_of must match candidate_as_of")
        if self.diagnostics.output_items != len(self.items):
            raise ValueError("output_items must match scan items")
        symbols = tuple(item.snapshot_item.candidate.symbol for item in self.items)
        if len(set(symbols)) != len(symbols):
            raise ValueError("scan item symbols must be unique")
        ranks = tuple(item.snapshot_item.candidate.market_rank for item in self.items)
        if ranks != tuple(sorted(ranks)):
            raise ValueError("scan items must preserve candidate market rank")
        if self.diagnostics.scan_ready and len(self.items) != self.diagnostics.input_items:
            raise ValueError("ready scans must retain every input item")
        if not self.diagnostics.scan_ready and self.items:
            raise ValueError("blocked scans must not expose items")
        return self


class RealtimeSignalPercentiles(DomainModel):
    """Independent raw-magnitude percentiles, never investment desirability scores."""

    change_pct_percentile: float | None
    price_vs_open_pct_percentile: float | None
    price_vs_prev_close_pct_percentile: float | None
    session_range_pct_percentile: float | None
    turnover_rate_pct_percentile: float | None
    volume_ratio_percentile: float | None

    @field_validator(
        "change_pct_percentile",
        "price_vs_open_pct_percentile",
        "price_vs_prev_close_pct_percentile",
        "session_range_pct_percentile",
        "turnover_rate_pct_percentile",
        "volume_ratio_percentile",
    )
    @classmethod
    def finite_range(cls, value: float | None, info: ValidationInfo) -> float | None:
        finite = ensure_finite_float(value, info.field_name)
        if finite is not None and not 0 <= finite <= 100:
            raise ValueError(f"{info.field_name} must be between 0 and 100")
        return finite


class RealtimeSignalNormalizationBlocker(StrEnum):
    LIGHT_SCAN_NOT_READY = "light_scan_not_ready"


class RealtimeSignalNormalizationItem(DomainModel):
    """One unchanged Task 17 item plus its six signal-local percentiles."""

    scan_item: RealtimeLightScanItem
    percentiles: RealtimeSignalPercentiles
    available_percentiles: int = Field(ge=0, le=6)
    percentile_completeness: float

    @field_validator("percentile_completeness")
    @classmethod
    def finite_completeness(cls, value: float) -> float:
        finite = ensure_finite_float(value, "percentile_completeness")
        assert finite is not None
        if not 0 <= finite <= 1:
            raise ValueError("percentile_completeness must be between 0 and 1")
        return finite

    @model_validator(mode="after")
    def validate_item(self) -> "RealtimeSignalNormalizationItem":
        actual_available = sum(
            value is not None for value in self.percentiles.model_dump().values()
        )
        if self.available_percentiles != actual_available:
            raise ValueError("available_percentiles must match non-missing percentiles")
        if self.percentile_completeness != self.available_percentiles / 6:
            raise ValueError("percentile_completeness must match available_percentiles")
        return self


class RealtimeSignalNormalizationDiagnostics(DomainModel):
    """Auditable signal-local cross-sectional availability and readiness."""

    calculation_at: datetime
    candidate_as_of: datetime
    upstream_scan_ready: bool
    upstream_blockers: tuple[RealtimeLightScanBlocker, ...]
    input_items: int = Field(ge=0)
    output_items: int = Field(ge=0)
    normalization_ready: bool
    blockers: tuple[RealtimeSignalNormalizationBlocker, ...]
    change_pct_ranked_items: int = Field(ge=0)
    price_vs_open_ranked_items: int = Field(ge=0)
    price_vs_prev_close_ranked_items: int = Field(ge=0)
    session_range_ranked_items: int = Field(ge=0)
    turnover_rate_ranked_items: int = Field(ge=0)
    volume_ratio_ranked_items: int = Field(ge=0)
    available_percentile_values: int = Field(ge=0)
    total_percentile_slots: int = Field(ge=0)
    overall_percentile_coverage: float | None

    @field_validator("calculation_at", "candidate_as_of")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "timestamp")

    @field_validator("overall_percentile_coverage")
    @classmethod
    def finite_coverage(cls, value: float | None) -> float | None:
        finite = ensure_finite_float(value, "overall_percentile_coverage")
        if finite is not None and not 0 <= finite <= 1:
            raise ValueError("overall_percentile_coverage must be between 0 and 1")
        return finite

    @model_validator(mode="after")
    def validate_diagnostics(self) -> "RealtimeSignalNormalizationDiagnostics":
        if self.candidate_as_of > self.calculation_at:
            raise ValueError("candidate_as_of must not follow calculation_at")
        if len(set(self.upstream_blockers)) != len(self.upstream_blockers):
            raise ValueError("upstream blockers must be unique")
        if len(set(self.blockers)) != len(self.blockers):
            raise ValueError("normalization blockers must be unique")
        if self.total_percentile_slots != self.input_items * 6:
            raise ValueError("total_percentile_slots must equal input_items times six")
        if self.available_percentile_values > self.total_percentile_slots:
            raise ValueError("available percentiles must not exceed total slots")
        if self.input_items == 0 and self.overall_percentile_coverage is not None:
            raise ValueError("empty normalization must not report coverage")
        if self.input_items and self.overall_percentile_coverage != (
            self.available_percentile_values / self.total_percentile_slots
        ):
            raise ValueError("overall_percentile_coverage must match availability")
        expected_blockers = (
            ()
            if self.upstream_scan_ready
            else (RealtimeSignalNormalizationBlocker.LIGHT_SCAN_NOT_READY,)
        )
        if (
            self.blockers != expected_blockers
            or self.normalization_ready != self.upstream_scan_ready
        ):
            raise ValueError("normalization readiness must follow light scan readiness")
        if not self.normalization_ready and self.output_items:
            raise ValueError("blocked normalization must not expose output items")
        return self


class RealtimeSignalNormalizationResult(DomainModel):
    """Task 18 output retaining separate realtime and slow-layer timestamps."""

    calculation_at: datetime
    candidate_as_of: datetime
    diagnostics: RealtimeSignalNormalizationDiagnostics
    items: tuple[RealtimeSignalNormalizationItem, ...]

    @field_validator("calculation_at", "candidate_as_of")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "timestamp")

    @model_validator(mode="after")
    def validate_result(self) -> "RealtimeSignalNormalizationResult":
        if (
            self.calculation_at != self.diagnostics.calculation_at
            or self.candidate_as_of != self.diagnostics.candidate_as_of
        ):
            raise ValueError("result timestamps must match diagnostics")
        if self.diagnostics.output_items != len(self.items):
            raise ValueError("output_items must match normalization items")
        ranks = tuple(item.scan_item.snapshot_item.candidate.market_rank for item in self.items)
        if ranks != tuple(sorted(ranks)):
            raise ValueError("normalization items must preserve candidate market rank")
        symbols = tuple(item.scan_item.snapshot_item.candidate.symbol for item in self.items)
        if len(set(symbols)) != len(symbols):
            raise ValueError("normalization item symbols must be unique")
        if self.diagnostics.normalization_ready and len(self.items) != self.diagnostics.input_items:
            raise ValueError("ready normalization must retain every input item")
        if not self.diagnostics.normalization_ready and self.items:
            raise ValueError("blocked normalization must not expose items")
        return self


class RealtimeIntradayFactorFamily(StrEnum):
    RELATIVE_STRENGTH = "relative_strength"
    ACTIVITY_LIQUIDITY = "activity_liquidity"
    VWAP_TREND = "vwap_trend"
    SHORT_MOMENTUM = "short_momentum"
    RISK_STABILITY = "risk_stability"


class RealtimeIntradayComponentTransformation(StrEnum):
    IDENTITY = "identity"
    ONE_HUNDRED_MINUS = "one_hundred_minus"


class RealtimeIntradayComponentUnavailableReason(StrEnum):
    MISSING_NORMALIZED_SIGNAL = "missing_normalized_signal"
    MINUTE_DATA_NOT_AVAILABLE = "minute_data_not_available"


class RealtimeIntradayComponentResult(DomainModel):
    component_name: str
    family: RealtimeIntradayFactorFamily
    source_percentile_name: str | None
    source_percentile: float | None
    transformation: RealtimeIntradayComponentTransformation
    score: float | None
    available: bool
    unavailable_reason: RealtimeIntradayComponentUnavailableReason | None

    @field_validator("source_percentile", "score")
    @classmethod
    def finite_score(cls, value: float | None, info: ValidationInfo) -> float | None:
        finite = ensure_finite_float(value, info.field_name)
        if finite is not None and not 0 <= finite <= 100:
            raise ValueError(f"{info.field_name} must be between 0 and 100")
        return finite

    @model_validator(mode="after")
    def validate_component(self) -> "RealtimeIntradayComponentResult":
        minute_reason = RealtimeIntradayComponentUnavailableReason.MINUTE_DATA_NOT_AVAILABLE
        missing_reason = RealtimeIntradayComponentUnavailableReason.MISSING_NORMALIZED_SIGNAL
        if self.source_percentile_name is None:
            if (
                self.source_percentile is not None
                or self.score is not None
                or self.available
                or self.unavailable_reason is not minute_reason
            ):
                raise ValueError("minute placeholders must use minute-data unavailability")
            return self
        if self.source_percentile is None:
            if (
                self.score is not None
                or self.available
                or self.unavailable_reason is not missing_reason
            ):
                raise ValueError("missing Task18 signals must remain unavailable")
            return self
        expected_score = (
            self.source_percentile
            if self.transformation is RealtimeIntradayComponentTransformation.IDENTITY
            else 100.0 - self.source_percentile
        )
        if (
            not self.available
            or self.unavailable_reason is not None
            or self.score != expected_score
        ):
            raise ValueError("available Task18 components must match transformation")
        return self


class RealtimeIntradayFamilyResult(DomainModel):
    family: RealtimeIntradayFactorFamily
    score: float | None
    available: bool
    available_components: int = Field(ge=0)
    total_components: int = Field(gt=0)
    component_coverage: float
    components: tuple[RealtimeIntradayComponentResult, ...]

    @field_validator("score", "component_coverage")
    @classmethod
    def finite_values(cls, value: float | None, info: ValidationInfo) -> float | None:
        finite = ensure_finite_float(value, info.field_name)
        upper_bound = 100 if info.field_name == "score" else 1
        if finite is not None and not 0 <= finite <= upper_bound:
            raise ValueError(f"{info.field_name} is out of range")
        return finite

    @model_validator(mode="after")
    def validate_family(self) -> "RealtimeIntradayFamilyResult":
        if self.total_components != len(self.components):
            raise ValueError("total_components must match components")
        if self.available_components != sum(item.available for item in self.components):
            raise ValueError("available_components must match components")
        if self.component_coverage != self.available_components / self.total_components:
            raise ValueError("component_coverage must match components")
        if self.available != (self.available_components > 0) or self.available != (
            self.score is not None
        ):
            raise ValueError("family availability must match components and score")
        if any(item.family is not self.family for item in self.components):
            raise ValueError("components must match family")
        if len({item.component_name for item in self.components}) != len(self.components):
            raise ValueError("component names must be unique")
        if self.available and self.score != sum(
            item.score for item in self.components if item.score is not None
        ) / self.available_components:
            raise ValueError("family score must mean available components")
        return self


class RealtimeIntradayFactorBlocker(StrEnum):
    SIGNAL_NORMALIZATION_NOT_READY = "signal_normalization_not_ready"


class RealtimeIntradayFactorItem(DomainModel):
    normalization_item: RealtimeSignalNormalizationItem
    relative_strength: RealtimeIntradayFamilyResult
    activity_liquidity: RealtimeIntradayFamilyResult
    vwap_trend: RealtimeIntradayFamilyResult
    short_momentum: RealtimeIntradayFamilyResult
    risk_stability: RealtimeIntradayFamilyResult
    available_families: int = Field(ge=0, le=5)
    total_families: int = Field(default=5, frozen=True)
    family_coverage: float

    @field_validator("family_coverage")
    @classmethod
    def finite_coverage(cls, value: float) -> float:
        finite = ensure_finite_float(value, "family_coverage")
        assert finite is not None
        if not 0 <= finite <= 1:
            raise ValueError("family_coverage must be between 0 and 1")
        return finite

    @model_validator(mode="after")
    def validate_item(self) -> "RealtimeIntradayFactorItem":
        families = (
            self.relative_strength,
            self.activity_liquidity,
            self.vwap_trend,
            self.short_momentum,
            self.risk_stability,
        )
        expected = tuple(RealtimeIntradayFactorFamily)
        if tuple(item.family for item in families) != expected:
            raise ValueError("factor fields must use canonical family identities")
        if self.total_families != 5:
            raise ValueError("total_families must equal five")
        if self.available_families != sum(item.available for item in families):
            raise ValueError("available_families must match families")
        if self.family_coverage != self.available_families / 5:
            raise ValueError("family_coverage must match families")
        return self


class RealtimeIntradayFactorDiagnostics(DomainModel):
    calculation_at: datetime
    candidate_as_of: datetime
    upstream_normalization_ready: bool
    upstream_blockers: tuple[RealtimeSignalNormalizationBlocker, ...]
    input_items: int = Field(ge=0)
    output_items: int = Field(ge=0)
    factor_ready: bool
    blockers: tuple[RealtimeIntradayFactorBlocker, ...]
    relative_strength_available_items: int = Field(ge=0)
    activity_liquidity_available_items: int = Field(ge=0)
    vwap_trend_available_items: int = Field(ge=0)
    short_momentum_available_items: int = Field(ge=0)
    risk_stability_available_items: int = Field(ge=0)
    available_family_values: int = Field(ge=0)
    total_family_slots: int = Field(ge=0)
    overall_family_coverage: float | None

    @field_validator("calculation_at", "candidate_as_of")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "timestamp")

    @model_validator(mode="after")
    def validate_diagnostics(self) -> "RealtimeIntradayFactorDiagnostics":
        if self.total_family_slots != self.input_items * 5:
            raise ValueError("total_family_slots must equal input_items times five")
        if self.available_family_values > self.total_family_slots:
            raise ValueError("available families must not exceed total slots")
        if self.input_items == 0 and self.overall_family_coverage is not None:
            raise ValueError("empty factors must not report coverage")
        if self.input_items and self.overall_family_coverage != (
            self.available_family_values / self.total_family_slots
        ):
            raise ValueError("overall_family_coverage must match availability")
        expected = () if self.upstream_normalization_ready else (
            RealtimeIntradayFactorBlocker.SIGNAL_NORMALIZATION_NOT_READY,
        )
        if self.blockers != expected or self.factor_ready != self.upstream_normalization_ready:
            raise ValueError("factor readiness must follow normalization readiness")
        return self


class RealtimeIntradayFactorResult(DomainModel):
    calculation_at: datetime
    candidate_as_of: datetime
    diagnostics: RealtimeIntradayFactorDiagnostics
    items: tuple[RealtimeIntradayFactorItem, ...]

    @model_validator(mode="after")
    def validate_result(self) -> "RealtimeIntradayFactorResult":
        if self.diagnostics.output_items != len(self.items):
            raise ValueError("output_items must match factor items")
        ranks = tuple(item.normalization_item.scan_item.snapshot_item.candidate.market_rank for item in self.items)
        if ranks != tuple(sorted(ranks)):
            raise ValueError("factor items must preserve candidate market rank")
        if self.diagnostics.factor_ready and len(self.items) != self.diagnostics.input_items:
            raise ValueError("ready factors must retain every input item")
        if not self.diagnostics.factor_ready and self.items:
            raise ValueError("blocked factors must not expose items")
        return self


class RealtimeIntradayFamilyWeight(DomainModel):
    enabled: bool = True
    weight: float

    @field_validator("weight")
    @classmethod
    def valid_weight(cls, value: float) -> float:
        finite = ensure_finite_float(value, "weight")
        assert finite is not None
        if not 0 <= finite <= 1:
            raise ValueError("weight must be between 0 and 1")
        return finite

    @model_validator(mode="after")
    def enabled_weight_is_positive(self) -> "RealtimeIntradayFamilyWeight":
        if self.enabled and self.weight <= 0:
            raise ValueError("enabled family weight must be greater than zero")
        return self


class RealtimeIntradayScorePolicy(DomainModel):
    relative_strength: RealtimeIntradayFamilyWeight = RealtimeIntradayFamilyWeight(weight=0.30)
    activity_liquidity: RealtimeIntradayFamilyWeight = RealtimeIntradayFamilyWeight(weight=0.25)
    vwap_trend: RealtimeIntradayFamilyWeight = RealtimeIntradayFamilyWeight(weight=0.20)
    short_momentum: RealtimeIntradayFamilyWeight = RealtimeIntradayFamilyWeight(weight=0.15)
    risk_stability: RealtimeIntradayFamilyWeight = RealtimeIntradayFamilyWeight(weight=0.10)

    @model_validator(mode="after")
    def validate_enabled_weights(self) -> "RealtimeIntradayScorePolicy":
        groups = tuple(getattr(self, family.value) for family in RealtimeIntradayFactorFamily)
        enabled = tuple(group for group in groups if group.enabled)
        if not enabled:
            raise ValueError("at least one intraday family must be enabled")
        if not math.isclose(sum(group.weight for group in enabled), 1.0, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("enabled intraday family weights must sum to one")
        return self


class RealtimeIntradayFamilyWeightContribution(DomainModel):
    family: RealtimeIntradayFactorFamily
    enabled: bool
    configured_weight: float
    family_score: float | None
    family_component_coverage: float
    available: bool
    renormalized_weight: float
    weighted_contribution: float | None

    @field_validator("configured_weight", "family_score", "family_component_coverage", "renormalized_weight", "weighted_contribution")
    @classmethod
    def finite(cls, value: float | None, info: ValidationInfo) -> float | None:
        return ensure_finite_float(value, info.field_name)

    @model_validator(mode="after")
    def validate_contribution(self) -> "RealtimeIntradayFamilyWeightContribution":
        if not 0 <= self.configured_weight <= 1 or not 0 <= self.family_component_coverage <= 1 or not 0 <= self.renormalized_weight <= 1:
            raise ValueError("contribution weights and coverage must be between 0 and 1")
        if self.family_score is not None and not 0 <= self.family_score <= 100:
            raise ValueError("family_score must be between 0 and 100")
        if self.weighted_contribution is not None and not 0 <= self.weighted_contribution <= 100:
            raise ValueError("weighted_contribution must be between 0 and 100")
        if self.available != (self.enabled and self.family_score is not None):
            raise ValueError("availability must match enabled family score")
        if not self.available and (self.renormalized_weight != 0 or self.weighted_contribution is not None):
            raise ValueError("unavailable contribution must be unweighted")
        if self.available and self.weighted_contribution is None:
            raise ValueError("available contribution requires weighted_contribution")
        if self.available:
            assert self.weighted_contribution is not None and self.family_score is not None
            if not math.isclose(self.weighted_contribution, self.family_score * self.renormalized_weight, rel_tol=1e-9, abs_tol=1e-9):
                raise ValueError("weighted_contribution must match family score and weight")
        return self


class RealtimeIntradayScoreBlocker(StrEnum):
    INTRADAY_FACTORS_NOT_READY = "intraday_factors_not_ready"


class RealtimeIntradayScoreItem(DomainModel):
    factor_item: RealtimeIntradayFactorItem
    intraday_score: float | None
    data_completeness: float
    confidence: float
    confidence_adjusted_score: float | None
    available_family_weight: float
    enabled_family_weight: float
    available_families: int = Field(ge=0, le=5)
    enabled_families: int = Field(ge=0, le=5)
    contributions: tuple[RealtimeIntradayFamilyWeightContribution, ...]

    @field_validator("intraday_score", "data_completeness", "confidence", "confidence_adjusted_score", "available_family_weight", "enabled_family_weight")
    @classmethod
    def finite_score_values(cls, value: float | None, info: ValidationInfo) -> float | None:
        return ensure_finite_float(value, info.field_name)

    @model_validator(mode="after")
    def validate_score_item(self) -> "RealtimeIntradayScoreItem":
        for name in ("intraday_score", "confidence_adjusted_score"):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= 100:
                raise ValueError(f"{name} must be between 0 and 100")
        for name in ("data_completeness", "confidence", "available_family_weight", "enabled_family_weight"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.confidence > self.data_completeness:
            raise ValueError("confidence must not exceed data_completeness")
        if tuple(item.family for item in self.contributions) != tuple(RealtimeIntradayFactorFamily):
            raise ValueError("contributions must use canonical family order")
        for contribution in self.contributions:
            family = getattr(self.factor_item, contribution.family.value)
            if (
                contribution.family_score != family.score
                or contribution.family_component_coverage != family.component_coverage
            ):
                raise ValueError("contributions must match retained factor families")
        if self.enabled_families != sum(item.enabled for item in self.contributions) or self.available_families != sum(item.available for item in self.contributions):
            raise ValueError("family counts must match contributions")
        enabled = sum(item.configured_weight for item in self.contributions if item.enabled)
        available = sum(item.configured_weight for item in self.contributions if item.available)
        if not math.isclose(self.enabled_family_weight, enabled, rel_tol=1e-9, abs_tol=1e-9) or not math.isclose(self.available_family_weight, available, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("family weights must match contributions")
        if not math.isclose(self.data_completeness, available / enabled if enabled else 0.0, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("data_completeness must match family weights")
        confidence = sum(item.configured_weight * item.family_component_coverage for item in self.contributions if item.available) / enabled if enabled else 0.0
        if not math.isclose(self.confidence, confidence, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("confidence must match component coverage")
        if available and not math.isclose(sum(item.renormalized_weight for item in self.contributions), 1.0, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("available renormalized weights must sum to one")
        score = sum(item.weighted_contribution or 0 for item in self.contributions)
        if (available == 0) != (self.intraday_score is None):
            raise ValueError("intraday_score availability must match available family weight")
        if self.intraday_score is not None and not math.isclose(self.intraday_score, score, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("intraday_score must match contributions")
        if self.intraday_score is None and self.confidence_adjusted_score is not None:
            raise ValueError("missing intraday_score requires missing adjusted score")
        if self.intraday_score is not None and not math.isclose(self.confidence_adjusted_score or 0, self.intraday_score * self.confidence, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("confidence_adjusted_score must match intraday_score")
        return self


class RealtimeIntradayScoreDiagnostics(DomainModel):
    calculation_at: datetime
    candidate_as_of: datetime
    upstream_factor_ready: bool
    upstream_blockers: tuple[RealtimeIntradayFactorBlocker, ...]
    input_items: int = Field(ge=0)
    output_items: int = Field(ge=0)
    score_ready: bool
    blockers: tuple[RealtimeIntradayScoreBlocker, ...]
    intraday_score_available_items: int = Field(ge=0)
    intraday_score_unavailable_items: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_diagnostics(self) -> "RealtimeIntradayScoreDiagnostics":
        expected = () if self.upstream_factor_ready else (RealtimeIntradayScoreBlocker.INTRADAY_FACTORS_NOT_READY,)
        if self.score_ready != self.upstream_factor_ready or self.blockers != expected:
            raise ValueError("score readiness must follow intraday factors")
        if self.score_ready and self.input_items != self.output_items:
            raise ValueError("ready score result must retain all factor items")
        if not self.score_ready and self.output_items:
            raise ValueError("blocked score result must not expose items")
        if self.intraday_score_available_items + self.intraday_score_unavailable_items != self.output_items:
            raise ValueError("score availability counts must match output items")
        return self


class RealtimeIntradayScoreResult(DomainModel):
    calculation_at: datetime
    candidate_as_of: datetime
    policy: RealtimeIntradayScorePolicy
    diagnostics: RealtimeIntradayScoreDiagnostics
    items: tuple[RealtimeIntradayScoreItem, ...]

    @model_validator(mode="after")
    def validate_result(self) -> "RealtimeIntradayScoreResult":
        if self.calculation_at != self.diagnostics.calculation_at or self.candidate_as_of != self.diagnostics.candidate_as_of:
            raise ValueError("result timestamps must match diagnostics")
        if self.diagnostics.output_items != len(self.items):
            raise ValueError("output_items must match score items")
        if self.diagnostics.score_ready and len(self.items) != self.diagnostics.input_items:
            raise ValueError("ready result must retain every factor item")
        if not self.diagnostics.score_ready and self.items:
            raise ValueError("blocked score result must expose zero items")
        symbols = tuple(
            item.factor_item.normalization_item.scan_item.snapshot_item.candidate.symbol
            for item in self.items
        )
        if len(set(symbols)) != len(symbols):
            raise ValueError("score item symbols must be unique")
        ranks = tuple(
            item.factor_item.normalization_item.scan_item.snapshot_item.candidate.market_rank
            for item in self.items
        )
        if ranks != tuple(sorted(ranks)):
            raise ValueError("score items must preserve candidate market rank")
        for item in self.items:
            for contribution in item.contributions:
                group = getattr(self.policy, contribution.family.value)
                if contribution.enabled != group.enabled or contribution.configured_weight != group.weight:
                    raise ValueError("contributions must match result policy")
        return self


class RealtimeScoreLayer(StrEnum):
    BASE_SCORE = "base_score"
    INTRADAY_SCORE = "intraday_score"


class RealtimeScorePolicy(DomainModel):
    """Immutable two-layer composition policy for the official RealTimeScore."""

    base_weight: float = 0.75
    intraday_weight: float = 0.25

    @field_validator("base_weight", "intraday_weight")
    @classmethod
    def finite(cls, value: float, info: ValidationInfo) -> float:
        finite = ensure_finite_float(value, info.field_name)
        assert finite is not None
        if not 0 < finite < 1:
            raise ValueError(f"{info.field_name} must be greater than zero and less than one")
        return finite

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "RealtimeScorePolicy":
        if not math.isclose(
            self.base_weight + self.intraday_weight, 1.0, rel_tol=1e-9, abs_tol=1e-9
        ):
            raise ValueError("realtime score policy weights must sum to one")
        return self


class RealtimeScoreLayerContribution(DomainModel):
    layer: RealtimeScoreLayer
    configured_weight: float
    source_score: float | None
    source_data_completeness: float
    source_confidence: float
    available: bool
    renormalized_weight: float
    weighted_contribution: float | None

    @field_validator(
        "configured_weight", "source_score", "source_data_completeness",
        "source_confidence", "renormalized_weight", "weighted_contribution",
    )
    @classmethod
    def finite(cls, value: float | None, info: ValidationInfo) -> float | None:
        return ensure_finite_float(value, info.field_name)

    @model_validator(mode="after")
    def validate_contribution(self) -> "RealtimeScoreLayerContribution":
        if not 0 <= self.configured_weight <= 1 or not 0 <= self.renormalized_weight <= 1:
            raise ValueError("layer weights must be between 0 and 1")
        if self.source_score is not None and not 0 <= self.source_score <= 100:
            raise ValueError("source_score must be between 0 and 100")
        if self.weighted_contribution is not None and not 0 <= self.weighted_contribution <= 100:
            raise ValueError("weighted_contribution must be between 0 and 100")
        if not 0 <= self.source_data_completeness <= 1:
            raise ValueError("source_data_completeness must be between 0 and 1")
        if not 0 <= self.source_confidence <= self.source_data_completeness:
            raise ValueError("source_confidence must not exceed source_data_completeness")
        if self.layer is RealtimeScoreLayer.BASE_SCORE:
            if self.source_score is None or not self.available:
                raise ValueError("base score contribution must always be available")
        elif self.available != (self.source_score is not None):
            raise ValueError("intraday availability must match source_score")
        if not self.available:
            if self.renormalized_weight != 0 or self.weighted_contribution is not None:
                raise ValueError("unavailable contribution must be unweighted")
        else:
            if self.weighted_contribution is None or self.source_score is None:
                raise ValueError("available contribution requires score and weighted contribution")
            if not math.isclose(
                self.weighted_contribution,
                self.source_score * self.renormalized_weight,
                rel_tol=1e-9,
                abs_tol=1e-9,
            ):
                raise ValueError("weighted_contribution must match source score and weight")
        return self


class RealtimeScoreBlocker(StrEnum):
    INTRADAY_SCORE_NOT_READY = "intraday_score_not_ready"


class RealtimeScoreItem(DomainModel):
    intraday_score_item: RealtimeIntradayScoreItem
    realtime_score: float
    data_completeness: float
    confidence: float
    confidence_adjusted_score: float
    available_layer_weight: float
    available_layers: int = Field(ge=0, le=2)
    total_layers: int = Field(default=2, frozen=True)
    contributions: tuple[RealtimeScoreLayerContribution, ...]

    @field_validator(
        "realtime_score", "data_completeness", "confidence",
        "confidence_adjusted_score", "available_layer_weight",
    )
    @classmethod
    def finite(cls, value: float, info: ValidationInfo) -> float:
        finite = ensure_finite_float(value, info.field_name)
        assert finite is not None
        return finite

    @model_validator(mode="after")
    def validate_item(self) -> "RealtimeScoreItem":
        if self.total_layers != 2 or len(self.contributions) != 2:
            raise ValueError("realtime score items require exactly two layers")
        if tuple(item.layer for item in self.contributions) != tuple(RealtimeScoreLayer):
            raise ValueError("contributions must use canonical layer order")
        if not 0 <= self.realtime_score <= 100 or not 0 <= self.confidence_adjusted_score <= 100:
            raise ValueError("score values must be between 0 and 100")
        if not 0 <= self.data_completeness <= 1 or not 0 <= self.confidence <= self.data_completeness:
            raise ValueError("confidence must be between 0 and data_completeness")
        if not 0 <= self.available_layer_weight <= 1:
            raise ValueError("available_layer_weight must be between 0 and 1")
        candidate = self.intraday_score_item.factor_item.normalization_item.scan_item.snapshot_item.candidate
        base, intraday = self.contributions
        expected_sources = (
            (candidate.base_score, candidate.data_completeness, candidate.confidence),
            (
                self.intraday_score_item.intraday_score,
                self.intraday_score_item.data_completeness,
                self.intraday_score_item.confidence,
            ),
        )
        for contribution, expected in zip(self.contributions, expected_sources, strict=True):
            if (
                contribution.source_score != expected[0]
                or contribution.source_data_completeness != expected[1]
                or contribution.source_confidence != expected[2]
            ):
                raise ValueError("contributions must match retained upstream score evidence")
        if not base.available:
            raise ValueError("base score contribution must be available")
        if self.available_layers != sum(item.available for item in self.contributions):
            raise ValueError("available_layers must match contributions")
        if self.available_layers != (2 if intraday.source_score is not None else 1):
            raise ValueError("available_layers must follow intraday score availability")
        available_weight = sum(item.configured_weight for item in self.contributions if item.available)
        if not math.isclose(self.available_layer_weight, available_weight, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("available_layer_weight must match available contributions")
        if available_weight <= 0:
            raise ValueError("base score makes available_layer_weight positive")
        if not math.isclose(
            sum(item.renormalized_weight for item in self.contributions), 1.0,
            rel_tol=1e-9, abs_tol=1e-9,
        ):
            raise ValueError("available renormalized weights must sum to one")
        score = sum(item.weighted_contribution or 0.0 for item in self.contributions)
        if not math.isclose(self.realtime_score, score, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("realtime_score must match weighted contributions")
        configured_weight = sum(item.configured_weight for item in self.contributions)
        if configured_weight <= 0:
            raise ValueError("configured layer weight must be positive")
        completeness = sum(
            item.configured_weight * item.source_data_completeness
            for item in self.contributions
        ) / configured_weight
        confidence = sum(
            item.configured_weight * item.source_confidence for item in self.contributions
        ) / configured_weight
        if not math.isclose(self.data_completeness, completeness, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("data_completeness must match configured layer evidence")
        if not math.isclose(self.confidence, confidence, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("confidence must match configured layer evidence")
        if not math.isclose(
            self.confidence_adjusted_score, self.realtime_score * self.confidence,
            rel_tol=1e-9, abs_tol=1e-9,
        ):
            raise ValueError("confidence_adjusted_score must match realtime_score")
        return self


class RealtimeScoreDiagnostics(DomainModel):
    calculation_at: datetime
    candidate_as_of: datetime
    upstream_intraday_score_ready: bool
    upstream_blockers: tuple[RealtimeIntradayScoreBlocker, ...]
    input_items: int = Field(ge=0)
    output_items: int = Field(ge=0)
    realtime_score_ready: bool
    blockers: tuple[RealtimeScoreBlocker, ...]
    blended_items: int = Field(ge=0)
    base_only_items: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_diagnostics(self) -> "RealtimeScoreDiagnostics":
        expected = () if self.upstream_intraday_score_ready else (RealtimeScoreBlocker.INTRADAY_SCORE_NOT_READY,)
        if self.realtime_score_ready != self.upstream_intraday_score_ready or self.blockers != expected:
            raise ValueError("realtime score readiness must follow intraday score")
        if self.realtime_score_ready and self.input_items != self.output_items:
            raise ValueError("ready realtime score result must retain every input item")
        if not self.realtime_score_ready and self.output_items:
            raise ValueError("blocked realtime score result must not expose items")
        if self.blended_items + self.base_only_items != self.output_items:
            raise ValueError("layer availability counts must match output items")
        return self


class RealtimeScoreResult(DomainModel):
    calculation_at: datetime
    candidate_as_of: datetime
    policy: RealtimeScorePolicy
    diagnostics: RealtimeScoreDiagnostics
    items: tuple[RealtimeScoreItem, ...]

    @model_validator(mode="after")
    def validate_result(self) -> "RealtimeScoreResult":
        if self.calculation_at != self.diagnostics.calculation_at or self.candidate_as_of != self.diagnostics.candidate_as_of:
            raise ValueError("result timestamps must match diagnostics")
        if self.diagnostics.output_items != len(self.items):
            raise ValueError("output_items must match realtime score items")
        if self.diagnostics.realtime_score_ready and len(self.items) != self.diagnostics.input_items:
            raise ValueError("ready result must retain every intraday score item")
        if not self.diagnostics.realtime_score_ready and self.items:
            raise ValueError("blocked result must expose zero items")
        symbols = tuple(item.intraday_score_item.factor_item.normalization_item.scan_item.snapshot_item.candidate.symbol for item in self.items)
        ranks = tuple(item.intraday_score_item.factor_item.normalization_item.scan_item.snapshot_item.candidate.market_rank for item in self.items)
        if len(set(symbols)) != len(symbols):
            raise ValueError("realtime score item symbols must be unique")
        if ranks != tuple(sorted(ranks)):
            raise ValueError("realtime score items must preserve candidate market rank")
        expected_weights = (self.policy.base_weight, self.policy.intraday_weight)
        for item in self.items:
            if tuple(contribution.configured_weight for contribution in item.contributions) != expected_weights:
                raise ValueError("contributions must match result policy")
        return self


class RealtimeSelectionPolicy(DomainModel):
    """Immutable, explicit ranking policy for an already-built realtime score result."""

    min_intraday_score: float = 65.0
    top_n: int = Field(default=100, gt=0)

    @field_validator("min_intraday_score")
    @classmethod
    def finite_threshold(cls, value: float) -> float:
        finite = ensure_finite_float(value, "min_intraday_score")
        assert finite is not None
        if not 0 <= finite <= 100:
            raise ValueError("min_intraday_score must be between 0 and 100")
        return finite


class RealtimeSelectionBlocker(StrEnum):
    REALTIME_SCORE_NOT_READY = "realtime_score_not_ready"


class RealtimeSelectionItem(DomainModel):
    score_item: RealtimeScoreItem
    realtime_rank: int = Field(gt=0)


class RealtimeSelectionDiagnostics(DomainModel):
    calculation_at: datetime
    candidate_as_of: datetime
    upstream_realtime_score_ready: bool
    upstream_blockers: tuple[RealtimeScoreBlocker, ...]
    input_items: int = Field(ge=0)
    intraday_score_available_items: int = Field(ge=0)
    intraday_score_missing_items: int = Field(ge=0)
    intraday_threshold_qualified_items: int = Field(ge=0)
    intraday_threshold_rejected_items: int = Field(ge=0)
    ranking_universe_items: int = Field(ge=0)
    selected_items: int = Field(ge=0)
    selection_ready: bool
    blockers: tuple[RealtimeSelectionBlocker, ...]

    @model_validator(mode="after")
    def validate_diagnostics(self) -> "RealtimeSelectionDiagnostics":
        expected = (
            ()
            if self.upstream_realtime_score_ready
            else (RealtimeSelectionBlocker.REALTIME_SCORE_NOT_READY,)
        )
        if self.selection_ready != self.upstream_realtime_score_ready or self.blockers != expected:
            raise ValueError("selection readiness must follow realtime score readiness")
        if self.intraday_score_available_items + self.intraday_score_missing_items != self.input_items:
            raise ValueError("intraday availability counts must match input items")
        if self.intraday_threshold_qualified_items + self.intraday_threshold_rejected_items != self.intraday_score_available_items:
            raise ValueError("threshold counts must match available intraday scores")
        if self.ranking_universe_items != self.intraday_threshold_qualified_items:
            raise ValueError("ranking universe must equal threshold-qualified items")
        if not self.selection_ready and self.selected_items:
            raise ValueError("blocked selection must not expose items")
        if self.selected_items > self.ranking_universe_items:
            raise ValueError("selected items cannot exceed ranking universe")
        return self


class RealtimeSelectionResult(DomainModel):
    calculation_at: datetime
    candidate_as_of: datetime
    policy: RealtimeSelectionPolicy
    diagnostics: RealtimeSelectionDiagnostics
    items: tuple[RealtimeSelectionItem, ...]

    @model_validator(mode="after")
    def validate_result(self) -> "RealtimeSelectionResult":
        if self.calculation_at != self.diagnostics.calculation_at or self.candidate_as_of != self.diagnostics.candidate_as_of:
            raise ValueError("result timestamps must match diagnostics")
        if self.diagnostics.selected_items != len(self.items):
            raise ValueError("selected_items must match selection items")
        if self.diagnostics.selection_ready:
            expected_count = min(self.diagnostics.ranking_universe_items, self.policy.top_n)
            if len(self.items) != expected_count:
                raise ValueError("ready selection must include the policy-sized ranking result")
        elif self.items:
            raise ValueError("blocked selection must expose zero items")
        if len(self.items) > self.policy.top_n:
            raise ValueError("selection cannot exceed policy top_n")
        symbols = tuple(
            item.score_item.intraday_score_item.factor_item.normalization_item.scan_item.snapshot_item.candidate.symbol
            for item in self.items
        )
        if len(set(symbols)) != len(symbols):
            raise ValueError("selected candidate symbols must be unique")
        if tuple(item.realtime_rank for item in self.items) != tuple(range(1, len(self.items) + 1)):
            raise ValueError("realtime ranks must be sequential")
        for item in self.items:
            intraday_score = item.score_item.intraday_score_item.intraday_score
            if intraday_score is None or intraday_score < self.policy.min_intraday_score:
                raise ValueError("selected items must satisfy the intraday threshold")
        ordered = tuple(
            sorted(
                self.items,
                key=lambda item: (
                    -item.score_item.realtime_score,
                    item.score_item.intraday_score_item.factor_item.normalization_item.scan_item.snapshot_item.candidate.symbol,
                ),
            )
        )
        if self.items != ordered:
            raise ValueError("selection items must be ordered by realtime score then symbol")
        return self


class RealtimeSelectionPipelinePolicy(DomainModel):
    """Explicit immutable policy bundle for the Task15-to-Task22 pipeline."""

    candidate_policy: RealtimeCandidatePolicy = Field(default_factory=RealtimeCandidatePolicy)
    freshness_normal_max_seconds: int = 60
    freshness_warning_max_seconds: int = 120
    light_scan_policy: RealtimeLightScanPolicy = Field(default_factory=RealtimeLightScanPolicy)
    intraday_score_policy: RealtimeIntradayScorePolicy = Field(default_factory=RealtimeIntradayScorePolicy)
    realtime_score_policy: RealtimeScorePolicy = Field(default_factory=RealtimeScorePolicy)
    selection_policy: RealtimeSelectionPolicy = Field(default_factory=RealtimeSelectionPolicy)

    @model_validator(mode="after")
    def validate_freshness_policy(self) -> "RealtimeSelectionPipelinePolicy":
        if self.freshness_normal_max_seconds <= 0 or self.freshness_warning_max_seconds <= 0:
            raise ValueError("freshness thresholds must be greater than zero")
        if self.freshness_warning_max_seconds < self.freshness_normal_max_seconds:
            raise ValueError("warning freshness threshold must not precede normal threshold")
        return self


class RealtimeSelectionPipelineResult(DomainModel):
    """Full auditable output of the canonical Task15-to-Task22 orchestration."""

    calculation_at: datetime
    candidate_as_of: datetime
    policy: RealtimeSelectionPipelinePolicy
    candidates: RealtimeCandidateResult
    snapshot: RealtimeCandidateSnapshotResult
    scan: RealtimeLightScanResult
    normalization: RealtimeSignalNormalizationResult
    factors: RealtimeIntradayFactorResult
    intraday_score: RealtimeIntradayScoreResult
    realtime_score: RealtimeScoreResult
    selection: RealtimeSelectionResult

    @field_validator("calculation_at", "candidate_as_of")
    @classmethod
    def aware(cls, value: datetime, info: ValidationInfo) -> datetime:
        return ensure_aware_datetime(value, info.field_name)

    @model_validator(mode="after")
    def validate_pipeline(self) -> "RealtimeSelectionPipelineResult":
        if self.candidate_as_of != self.candidates.as_of:
            raise ValueError("pipeline candidate_as_of must match candidates")
        candidate_as_of_values = (
            self.snapshot.as_of,
            self.scan.as_of,
            self.normalization.candidate_as_of,
            self.factors.candidate_as_of,
            self.intraday_score.candidate_as_of,
            self.realtime_score.candidate_as_of,
            self.selection.candidate_as_of,
        )
        if any(value != self.candidate_as_of for value in candidate_as_of_values):
            raise ValueError("pipeline candidate_as_of must match every stage")
        calculation_values = (
            self.snapshot.diagnostics.calculation_at,
            self.scan.diagnostics.calculation_at,
            self.normalization.calculation_at,
            self.normalization.diagnostics.calculation_at,
            self.factors.calculation_at,
            self.factors.diagnostics.calculation_at,
            self.intraday_score.calculation_at,
            self.intraday_score.diagnostics.calculation_at,
            self.realtime_score.calculation_at,
            self.realtime_score.diagnostics.calculation_at,
            self.selection.calculation_at,
            self.selection.diagnostics.calculation_at,
        )
        if any(value != self.calculation_at for value in calculation_values):
            raise ValueError("pipeline calculation_at must match every downstream stage")
        if (
            self.candidates.policy != self.policy.candidate_policy
            or self.scan.policy != self.policy.light_scan_policy
            or self.intraday_score.policy != self.policy.intraday_score_policy
            or self.realtime_score.policy != self.policy.realtime_score_policy
            or self.selection.policy != self.policy.selection_policy
        ):
            raise ValueError("pipeline stages must match bundled policies")
        adjacency = (
            (
                self.scan.diagnostics.upstream_snapshot_ready,
                self.snapshot.diagnostics.snapshot_ready,
                self.scan.diagnostics.upstream_blockers,
                self.snapshot.diagnostics.blockers,
            ),
            (
                self.normalization.diagnostics.upstream_scan_ready,
                self.scan.diagnostics.scan_ready,
                self.normalization.diagnostics.upstream_blockers,
                self.scan.diagnostics.blockers,
            ),
            (
                self.factors.diagnostics.upstream_normalization_ready,
                self.normalization.diagnostics.normalization_ready,
                self.factors.diagnostics.upstream_blockers,
                self.normalization.diagnostics.blockers,
            ),
            (
                self.intraday_score.diagnostics.upstream_factor_ready,
                self.factors.diagnostics.factor_ready,
                self.intraday_score.diagnostics.upstream_blockers,
                self.factors.diagnostics.blockers,
            ),
            (
                self.realtime_score.diagnostics.upstream_intraday_score_ready,
                self.intraday_score.diagnostics.score_ready,
                self.realtime_score.diagnostics.upstream_blockers,
                self.intraday_score.diagnostics.blockers,
            ),
            (
                self.selection.diagnostics.upstream_realtime_score_ready,
                self.realtime_score.diagnostics.realtime_score_ready,
                self.selection.diagnostics.upstream_blockers,
                self.realtime_score.diagnostics.blockers,
            ),
        )
        if any(ready != upstream_ready or blockers != upstream_blockers for ready, upstream_ready, blockers, upstream_blockers in adjacency):
            raise ValueError("pipeline adjacent stage readiness and blockers must agree")
        if self.snapshot.diagnostics.snapshot_ready and tuple(item.candidate for item in self.snapshot.items) != self.candidates.candidates:
            raise ValueError("ready snapshot items must retain pipeline candidates")
        if self.scan.diagnostics.scan_ready and tuple(item.snapshot_item for item in self.scan.items) != self.snapshot.items:
            raise ValueError("scan items must retain snapshot items")
        if self.normalization.diagnostics.normalization_ready and tuple(item.scan_item for item in self.normalization.items) != self.scan.items:
            raise ValueError("normalization items must retain scan items")
        if self.factors.diagnostics.factor_ready and tuple(item.normalization_item for item in self.factors.items) != self.normalization.items:
            raise ValueError("factor items must retain normalization items")
        if self.intraday_score.diagnostics.score_ready and tuple(item.factor_item for item in self.intraday_score.items) != self.factors.items:
            raise ValueError("intraday score items must retain factor items")
        if self.realtime_score.diagnostics.realtime_score_ready and tuple(item.intraday_score_item for item in self.realtime_score.items) != self.intraday_score.items:
            raise ValueError("realtime score items must retain intraday score items")
        upstream_scores = {
            item.intraday_score_item.factor_item.normalization_item.scan_item.snapshot_item.candidate.symbol: item
            for item in self.realtime_score.items
        }
        for item in self.selection.items:
            symbol = item.score_item.intraday_score_item.factor_item.normalization_item.scan_item.snapshot_item.candidate.symbol
            if upstream_scores.get(symbol) != item.score_item:
                raise ValueError("selection items must retain matching realtime score items")
        return self


class RealtimeSlowInputDiagnostics(DomainModel):
    """Auditable local PIT coverage for one realtime slow-input assembly."""

    as_of: datetime
    input_instruments: int = Field(ge=0)
    structural_members: int = Field(ge=0)
    risk_records: int = Field(ge=0)
    risk_complete_members: int = Field(ge=0)
    risk_eligible_members: int = Field(ge=0)
    risk_coverage_ratio: float
    risk_ready: bool
    factor_input_members: int = Field(ge=0)
    financial_current_available_members: int = Field(ge=0)
    financial_prior_year_available_members: int = Field(ge=0)
    valuation_available_members: int = Field(ge=0)
    industry_available_members: int = Field(ge=0)
    base_score_input_members: int = Field(ge=0)
    base_score_available_members: int = Field(ge=0)
    price_factors_operational: bool

    @field_validator("as_of")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @field_validator("risk_coverage_ratio")
    @classmethod
    def finite(cls, value: float) -> float:
        finite = ensure_finite_float(value, "risk_coverage_ratio")
        assert finite is not None
        return finite

    @model_validator(mode="after")
    def validate_diagnostics(self) -> "RealtimeSlowInputDiagnostics":
        if self.input_instruments < self.structural_members:
            raise ValueError("input_instruments must cover structural_members")
        if self.risk_complete_members > self.structural_members:
            raise ValueError("risk_complete_members must not exceed structural_members")
        if self.risk_eligible_members > self.risk_complete_members:
            raise ValueError("risk_eligible_members must not exceed risk_complete_members")
        expected_coverage = (
            self.risk_complete_members / self.structural_members
            if self.structural_members
            else 0.0
        )
        if not math.isclose(
            self.risk_coverage_ratio, expected_coverage, rel_tol=1e-9, abs_tol=1e-9
        ):
            raise ValueError("risk_coverage_ratio must match risk counts")
        expected_ready = (
            self.structural_members > 0
            and self.risk_complete_members == self.structural_members
        )
        if self.risk_ready != expected_ready:
            raise ValueError("risk_ready must match complete structural risk coverage")
        if self.factor_input_members > self.risk_eligible_members:
            raise ValueError("factor_input_members must not exceed risk_eligible_members")
        for field_name in (
            "financial_current_available_members",
            "financial_prior_year_available_members",
            "valuation_available_members",
            "industry_available_members",
        ):
            if getattr(self, field_name) > self.factor_input_members:
                raise ValueError(f"{field_name} must not exceed factor_input_members")
        if self.base_score_input_members != self.factor_input_members:
            raise ValueError("base_score_input_members must equal factor_input_members")
        if self.base_score_available_members > self.base_score_input_members:
            raise ValueError("base_score_available_members must not exceed base_score_input_members")
        if self.price_factors_operational:
            raise ValueError("Task24 price factors must remain unavailable")
        if not self.risk_ready and any(
            (
                self.factor_input_members,
                self.base_score_input_members,
                self.base_score_available_members,
            )
        ):
            raise ValueError("risk-incomplete assembly must not contain factor or score inputs")
        return self


class RealtimeSlowInputResult(DomainModel):
    """Read-only PIT slow inputs retained for the Task23 realtime application."""

    as_of: datetime
    structural: UniverseSnapshot
    risk: RiskEligibilitySnapshot
    factor_inputs: tuple[StockFactorInput, ...]
    factors: FiveFactorCrossSectionResult | None
    factor_config: FactorsConfig
    base_scores: BaseScoreCrossSectionResult
    diagnostics: RealtimeSlowInputDiagnostics

    @field_validator("as_of")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "as_of")

    @model_validator(mode="after")
    def validate_result(self) -> "RealtimeSlowInputResult":
        if self.diagnostics.as_of != self.as_of or self.base_scores.as_of != self.as_of:
            raise ValueError("slow-input timestamps must match result as_of")
        if self.structural.as_of != self.as_of.date():
            raise ValueError("structural as_of must match result date")
        if self.risk.as_of != self.as_of.date():
            raise ValueError("risk as_of must match result date")
        if self.structural.input_count != self.diagnostics.input_instruments:
            raise ValueError("structural input_count must match diagnostics")
        if len(self.structural.members) != self.diagnostics.structural_members:
            raise ValueError("structural member count must match diagnostics")
        if self.risk.structural_members != self.diagnostics.structural_members:
            raise ValueError("risk structural count must match diagnostics")
        if self.risk.risk_records != self.diagnostics.risk_records:
            raise ValueError("risk record count must match diagnostics")
        if self.risk.risk_complete_members != self.diagnostics.risk_complete_members:
            raise ValueError("risk complete count must match diagnostics")
        if len(self.risk.eligible_members) != self.diagnostics.risk_eligible_members:
            raise ValueError("risk eligible count must match diagnostics")
        if tuple(item.symbol for item in self.risk.decisions) != self.structural.members:
            raise ValueError("risk decisions must match structural members")
        factor_symbols = tuple(item.symbol for item in self.factor_inputs)
        if len(set(factor_symbols)) != len(factor_symbols) or factor_symbols != tuple(
            sorted(factor_symbols)
        ):
            raise ValueError("factor input symbols must be unique and sorted")
        if not set(factor_symbols).issubset(self.risk.eligible_members):
            raise ValueError("factor input symbols must be risk eligible")
        if any(item.as_of != self.as_of for item in self.factor_inputs):
            raise ValueError("factor input timestamps must match result as_of")
        if any(item.price_series is not None for item in self.factor_inputs):
            raise ValueError("Task24 factor inputs must not include price series")
        if len(self.factor_inputs) != self.diagnostics.factor_input_members:
            raise ValueError("factor input count must match diagnostics")
        availability_counts = (
            sum(item.financial_current is not None for item in self.factor_inputs),
            sum(item.financial_prior_year is not None for item in self.factor_inputs),
            sum(item.valuation is not None for item in self.factor_inputs),
            sum(item.industry_key is not None for item in self.factor_inputs),
        )
        if availability_counts != (
            self.diagnostics.financial_current_available_members,
            self.diagnostics.financial_prior_year_available_members,
            self.diagnostics.valuation_available_members,
            self.diagnostics.industry_available_members,
        ):
            raise ValueError("factor availability counts must match retained inputs")
        if not self.factor_inputs and self.factors is not None:
            raise ValueError("empty factor inputs require missing factor evidence")
        if self.factor_inputs and self.factors is None:
            raise ValueError("factor inputs require retained factor evidence")
        if self.factors is not None:
            if self.factors.as_of != self.as_of:
                raise ValueError("factor evidence timestamp must match result as_of")
            if self.factors.input_count != len(self.factor_inputs):
                raise ValueError("factor evidence input_count must match factor inputs")
            if tuple(item.symbol for item in self.factors.stocks) != factor_symbols:
                raise ValueError("factor evidence symbols must match factor input symbols")
        if self.base_scores.input_count != len(self.factor_inputs):
            raise ValueError("base score input_count must match factor inputs")
        if tuple(item.symbol for item in self.base_scores.stocks) != factor_symbols:
            raise ValueError("base score symbols must match factor input symbols")
        if self.diagnostics.base_score_available_members != sum(
            item.base_score is not None for item in self.base_scores.stocks
        ):
            raise ValueError("base score availability count must match score results")
        if self.factors is not None:
            factors_by_symbol = {item.symbol: item for item in self.factors.stocks}
            for score_item in self.base_scores.stocks:
                factor_item = factors_by_symbol[score_item.symbol]
                factor_families = (
                    factor_item.quality,
                    factor_item.value,
                    factor_item.growth,
                    factor_item.momentum,
                    factor_item.low_volatility,
                )
                for contribution, family, evidence in zip(
                    score_item.contributions, FactorFamily, factor_families, strict=True
                ):
                    group = getattr(self.factor_config, family.value)
                    if contribution.family is not family:
                        raise ValueError("base score contribution family must match factor evidence")
                    if contribution.family_score != evidence.score:
                        raise ValueError("base score family score must match factor evidence")
                    if contribution.family_component_coverage != evidence.component_coverage:
                        raise ValueError("base score coverage must match factor evidence")
                    if contribution.enabled != group.enabled:
                        raise ValueError("base score enablement must match factor configuration")
                    if contribution.configured_weight != group.weight:
                        raise ValueError("base score weight must match factor configuration")
        return self
