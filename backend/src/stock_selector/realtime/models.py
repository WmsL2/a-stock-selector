from datetime import datetime
from enum import StrEnum

from pydantic import Field, ValidationInfo, field_validator, model_validator

from stock_selector.models import RealtimeQuote
from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    ensure_finite_float,
    validate_symbol,
)
from stock_selector.quality.models import RealtimeFreshness


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
