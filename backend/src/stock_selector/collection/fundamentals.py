"""Explicit, per-symbol collectors for point-in-time fundamentals domains."""

from collections.abc import Callable, Hashable
from dataclasses import dataclass
from datetime import date, datetime

from stock_selector.models import FinancialRecord, IndustryRecord, ValuationRecord
from stock_selector.models.common import validate_symbol
from stock_selector.providers.base import FundamentalDataProvider, IndustryDataProvider
from stock_selector.providers.errors import ProviderError
from stock_selector.providers.requests import (
    FinancialRecordsRequest,
    IndustryRecordsRequest,
    ValuationRecordsRequest,
)
from stock_selector.storage import LocalMarketRepository, StorageError

from .errors import CollectionDataError, CollectionError


@dataclass(frozen=True)
class FundamentalsCollectionReport:
    """Compact, auditable outcome for one explicit bounded collector invocation."""

    requested_symbols: tuple[str, ...]
    succeeded_symbols: int
    empty_symbols: int
    failed_symbols: int
    rows_persisted: int


class FinancialCollector:
    """Collect explicit periods only, isolating provider failures by requested symbol."""

    def __init__(
        self, provider: FundamentalDataProvider, repository: LocalMarketRepository
    ) -> None:
        self._provider = provider
        self._repository = repository

    def collect(
        self, symbols: tuple[str, ...], start_period: date, end_period: date
    ) -> FundamentalsCollectionReport:
        return _collect_per_symbol(
            symbols,
            lambda symbol: self._provider.get_financial_records(
                FinancialRecordsRequest(
                    symbols=(symbol,), start_period=start_period, end_period=end_period
                )
            ),
            lambda requested_symbol, records: _validate_financial(
                requested_symbol, records, start_period, end_period
            ),
            self._repository.upsert_financial_records,
        )


class ValuationCollector:
    """Collect explicit symbols no later than a declared as-of instant."""

    def __init__(
        self, provider: FundamentalDataProvider, repository: LocalMarketRepository
    ) -> None:
        self._provider = provider
        self._repository = repository

    def collect(
        self, symbols: tuple[str, ...], as_of: datetime
    ) -> FundamentalsCollectionReport:
        return _collect_per_symbol(
            symbols,
            lambda symbol: self._provider.get_valuation_records(
                ValuationRecordsRequest(symbols=(symbol,), as_of=as_of)
            ),
            lambda requested_symbol, records: _validate_valuations(
                requested_symbol, records, as_of
            ),
            self._repository.upsert_valuation_records,
        )


class IndustryCollector:
    """Collect explicit symbols with provider-declared effective intervals only."""

    def __init__(
        self, provider: IndustryDataProvider, repository: LocalMarketRepository
    ) -> None:
        self._provider = provider
        self._repository = repository

    def collect(
        self, symbols: tuple[str, ...], as_of: date
    ) -> FundamentalsCollectionReport:
        return _collect_per_symbol(
            symbols,
            lambda symbol: self._provider.get_industry_records(
                IndustryRecordsRequest(symbols=(symbol,), as_of=as_of)
            ),
            lambda requested_symbol, records: _validate_industries(
                requested_symbol, records, as_of
            ),
            self._repository.upsert_industry_records,
        )


def _collect_per_symbol[TRecord: (FinancialRecord, ValuationRecord, IndustryRecord)](
    symbols: tuple[str, ...],
    fetch: Callable[[str], tuple[TRecord, ...]],
    validate: Callable[[str, tuple[TRecord, ...]], tuple[TRecord, ...]],
    persist: Callable[[tuple[TRecord, ...]], None],
) -> FundamentalsCollectionReport:
    requested_symbols = _validate_requested_symbols(symbols)
    succeeded = empty = failed = persisted_rows = 0
    for symbol in requested_symbols:
        try:
            records = fetch(symbol)
            valid = validate(symbol, records)
        except (ProviderError, CollectionDataError):
            failed += 1
            continue
        if not valid:
            empty += 1
            continue
        try:
            persist(valid)
        except StorageError as exc:
            raise CollectionError("fundamentals storage infrastructure failed") from exc
        succeeded += 1
        persisted_rows += len(valid)
    return FundamentalsCollectionReport(
        requested_symbols, succeeded, empty, failed, persisted_rows
    )


def _validate_financial(
    requested_symbol: str,
    records: tuple[FinancialRecord, ...],
    start_period: date,
    end_period: date,
) -> tuple[FinancialRecord, ...]:
    return _validate_records(
        requested_symbol,
        records,
        lambda item: (
            start_period <= item.report_period <= end_period
            and item.available_at.date() >= item.announcement_date
        ),
        lambda item: (item.report_period, item.available_at),
    )


def _validate_valuations(
    requested_symbol: str, records: tuple[ValuationRecord, ...], as_of: datetime
) -> tuple[ValuationRecord, ...]:
    return _validate_records(
        requested_symbol,
        records,
        lambda item: item.as_of <= as_of,
        lambda item: item.as_of,
    )


def _validate_industries(
    requested_symbol: str, records: tuple[IndustryRecord, ...], as_of: date
) -> tuple[IndustryRecord, ...]:
    return _validate_records(
        requested_symbol,
        records,
        lambda item: item.effective_from <= as_of,
        lambda item: (item.classification, item.effective_from),
    )


def _validate_records[TRecord: (FinancialRecord, ValuationRecord, IndustryRecord)](
    requested_symbol: str,
    records: tuple[TRecord, ...],
    predicate: Callable[[TRecord], bool],
    key: Callable[[TRecord], Hashable],
) -> tuple[TRecord, ...]:
    if not records:
        return ()
    if any(item.symbol != requested_symbol for item in records):
        raise CollectionDataError("provider returned a different symbol")
    if any(not predicate(item) for item in records):
        raise CollectionDataError(
            "provider returned an out-of-range point-in-time record"
        )
    if len({key(item) for item in records}) != len(records):
        raise CollectionDataError("provider returned duplicate logical keys")
    if len({item.source for item in records}) != 1:
        raise CollectionDataError("provider returned mixed sources")
    return records


def _validate_requested_symbols(symbols: tuple[str, ...]) -> tuple[str, ...]:
    """Reject ambiguous collector inputs before any provider or storage call."""
    if not symbols:
        raise CollectionDataError("at least one explicit symbol is required")
    try:
        canonical_symbols = tuple(validate_symbol(symbol) for symbol in symbols)
    except ValueError as exc:
        raise CollectionDataError("symbols must be canonical") from exc
    if canonical_symbols != symbols:
        raise CollectionDataError("symbols must be canonical")
    if len(set(canonical_symbols)) != len(canonical_symbols):
        raise CollectionDataError("symbols must be unique")
    return tuple(sorted(canonical_symbols))
