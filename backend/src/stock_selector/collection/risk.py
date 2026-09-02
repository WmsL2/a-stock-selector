"""Atomic current-day structural risk collection through a provider abstraction."""

from datetime import date, datetime

from pydantic import Field, field_validator, model_validator

from stock_selector.models.common import (
    DomainModel,
    ensure_aware_datetime,
    validate_symbol,
)
from stock_selector.providers.base import CurrentRiskStateProvider
from stock_selector.providers.requests import CurrentRiskStatesRequest
from stock_selector.risk import DatedRiskState
from stock_selector.storage import LocalMarketRepository, StorageError

from .errors import CollectionDataError, CollectionError


class CurrentRiskCollectionRequest(DomainModel):
    """One current-date, complete structural risk collection request."""

    symbols: tuple[str, ...]
    as_of: date

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("symbols must not be empty")
        for symbol in value:
            validate_symbol(symbol)
        if len(set(value)) != len(value):
            raise ValueError("symbols must not contain duplicates")
        return tuple(sorted(value))


class CurrentRiskCollectionResult(DomainModel):
    """Auditable all-or-nothing report for one persisted current-risk batch."""

    as_of: date
    requested_symbols: tuple[str, ...]
    states_received: int = Field(ge=0)
    states_persisted: int = Field(ge=0)
    st_members: int = Field(ge=0)
    suspended_members: int = Field(ge=0)
    delisting_period_members: int = Field(ge=0)
    observed_at: datetime
    source: str

    @field_validator("requested_symbols")
    @classmethod
    def validate_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("requested_symbols must not be empty")
        for symbol in value:
            validate_symbol(symbol)
        if len(set(value)) != len(value) or value != tuple(sorted(value)):
            raise ValueError("requested_symbols must be sorted and unique")
        return value

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return ensure_aware_datetime(value, "observed_at")

    @model_validator(mode="after")
    def validate_complete_result(self) -> "CurrentRiskCollectionResult":
        expected = len(self.requested_symbols)
        if self.states_received != expected or self.states_persisted != expected:
            raise ValueError("current-risk collection must receive and persist every request")
        for count in (
            self.st_members,
            self.suspended_members,
            self.delisting_period_members,
        ):
            if count > expected:
                raise ValueError("risk counts cannot exceed requested symbols")
        return self


class CurrentRiskStateCollector:
    """Validate one complete provider batch before exactly one risk-state upsert."""

    def __init__(
        self, provider: CurrentRiskStateProvider, repository: LocalMarketRepository
    ) -> None:
        self._provider = provider
        self._repository = repository

    def collect(self, request: CurrentRiskCollectionRequest) -> CurrentRiskCollectionResult:
        """Fetch, validate, and atomically persist one full current structural batch."""
        states = self._provider.get_current_risk_states(
            CurrentRiskStatesRequest(symbols=request.symbols, as_of=request.as_of)
        )
        validated = self._validate_batch(states, request)
        try:
            self._repository.upsert_risk_states(validated)
        except StorageError as exc:
            raise CollectionError("current-risk storage infrastructure failed") from exc
        return CurrentRiskCollectionResult(
            as_of=request.as_of,
            requested_symbols=request.symbols,
            states_received=len(validated),
            states_persisted=len(validated),
            st_members=sum(state.is_st is True for state in validated),
            suspended_members=sum(state.is_suspended is True for state in validated),
            delisting_period_members=sum(
                state.is_delisting_period is True for state in validated
            ),
            observed_at=validated[0].observed_at,
            source=validated[0].source,
        )

    @staticmethod
    def _validate_batch(
        states: tuple[DatedRiskState, ...], request: CurrentRiskCollectionRequest
    ) -> tuple[DatedRiskState, ...]:
        if len(states) != len(request.symbols):
            raise CollectionDataError("provider returned incomplete current-risk batch")
        symbols = tuple(state.symbol for state in states)
        if len(set(symbols)) != len(symbols) or set(symbols) != set(request.symbols):
            raise CollectionDataError("provider returned a different current-risk symbol set")
        if any(state.as_of != request.as_of for state in states):
            raise CollectionDataError("provider returned a different current-risk as_of date")
        if any(
            value is None
            for state in states
            for value in (
                state.is_st,
                state.is_suspended,
                state.is_delisting_period,
            )
        ):
            raise CollectionDataError("provider returned unknown current-risk fields")
        observed_at = {state.observed_at for state in states}
        sources = {state.source for state in states}
        if len(observed_at) != 1:
            raise CollectionDataError("provider returned mixed current-risk observation times")
        if len(sources) != 1:
            raise CollectionDataError("provider returned mixed current-risk sources")
        return tuple(sorted(states, key=lambda state: state.symbol))
