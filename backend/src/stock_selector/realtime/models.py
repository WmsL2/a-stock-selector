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
