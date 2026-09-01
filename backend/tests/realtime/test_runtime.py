"""Task25 one-shot runtime orchestration regressions with fake providers only."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

import stock_selector.realtime.runtime as runtime_module
from stock_selector.config import AppPaths, Settings
from stock_selector.models import (
    Board,
    Exchange,
    FinancialRecord,
    IndustryRecord,
    Instrument,
    RealtimeQuote,
    ValuationRecord,
)
from stock_selector.providers.base import ProviderInfo, RealtimeMarketDataProvider
from stock_selector.providers.errors import ProviderConnectionError
from stock_selector.providers.requests import RealtimeQuotesRequest
from stock_selector.realtime import (
    RealtimeCandidatePolicy,
    RealtimeCaptureScope,
    RealtimeCollectionError,
    RealtimeDataError,
    RealtimeSelectionPipelinePolicy,
    RealtimeSelectionPolicy,
    RealtimeSelectionRuntimeResult,
    RealtimeSelectionRuntimeService,
)
from stock_selector.risk import DatedRiskState
from stock_selector.storage import LocalMarketRepository, StorageError

AS_OF = datetime(2026, 3, 31, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
CAPTURE_AT = AS_OF + timedelta(seconds=10)
CALCULATION_AT = CAPTURE_AT + timedelta(seconds=10)
CLASSIFICATION = "证监会行业分类标准（2012）"


class FakeRealtimeProvider(RealtimeMarketDataProvider):
    def __init__(
        self, response: tuple[RealtimeQuote, ...] | Exception, events: list[str] | None = None
    ) -> None:
        self.response = response
        self.events = events
        self.requests: list[RealtimeQuotesRequest] = []

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="fake")

    def get_realtime_quotes(
        self, request: RealtimeQuotesRequest
    ) -> tuple[RealtimeQuote, ...]:
        self.requests.append(request)
        if self.events is not None:
            self.events.append("provider")
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _repository(
    tmp_path, symbols: tuple[str, ...] = ("600519.SH",)
) -> LocalMarketRepository:  # type: ignore[no-untyped-def]
    repository = LocalMarketRepository(AppPaths.from_project_root(tmp_path))
    repository.initialize()
    repository.save_instruments(tuple(_instrument(symbol) for symbol in symbols))
    return repository


def _instrument(symbol: str) -> Instrument:
    exchange = Exchange(symbol.rsplit(".", maxsplit=1)[1])
    return Instrument(
        symbol=symbol,
        name=f"name-{symbol}",
        exchange=exchange,
        board=Board.SZ_MAIN if exchange is Exchange.SZSE else Board.SH_MAIN,
        listing_date=date(2000, 1, 1),
    )


def _seed(repository: LocalMarketRepository, symbols: tuple[str, ...]) -> None:
    for symbol in symbols:
        repository.upsert_financial_records(
            (
                FinancialRecord(symbol=symbol, report_period=date(2024, 12, 31), announcement_date=date(2025, 3, 1), available_at=AS_OF - timedelta(days=20), roe=10, roa=10, gross_margin=10, net_margin=10, revenue=100, net_profit=100, deducted_net_profit=100, source="test"),
                FinancialRecord(symbol=symbol, report_period=date(2025, 12, 31), announcement_date=date(2026, 3, 1), available_at=AS_OF - timedelta(days=20), roe=20, roa=20, gross_margin=20, net_margin=20, revenue=120, net_profit=120, deducted_net_profit=120, source="test"),
            )
        )
        repository.upsert_valuation_records((ValuationRecord(symbol=symbol, as_of=AS_OF - timedelta(days=1), pe=10, pb=2, pcf=5, source="test"),))
        repository.upsert_industry_records((IndustryRecord(symbol=symbol, industry_code="C15", industry_name="test", classification=CLASSIFICATION, effective_from=date(2020, 1, 1), source="test"),))
    repository.upsert_risk_states(tuple(_risk(symbol) for symbol in symbols))


def _risk(symbol: str, **changes: bool | None) -> DatedRiskState:
    values: dict[str, object] = {
        "symbol": symbol,
        "as_of": AS_OF.date(),
        "is_st": False,
        "is_suspended": False,
        "is_delisting_period": False,
        "observed_at": AS_OF,
        "source": "test",
    }
    values.update(changes)
    return DatedRiskState(**values)


def _quote(symbol: str, *, price: float = 11, ingested_at: datetime = CAPTURE_AT) -> RealtimeQuote:
    return RealtimeQuote(
        symbol=symbol,
        price=price,
        open=10,
        high=12,
        low=9,
        prev_close=10,
        volume=100,
        amount=1100,
        change_pct=10,
        turnover_rate=3,
        volume_ratio=2,
        ingested_at=ingested_at,
        source="fake:realtime",
    )


def _policy() -> RealtimeSelectionPipelinePolicy:
    return RealtimeSelectionPipelinePolicy(
        candidate_policy=RealtimeCandidatePolicy(min_base_score=0, top_fraction=1),
        freshness_normal_max_seconds=30,
        freshness_warning_max_seconds=90,
        selection_policy=RealtimeSelectionPolicy(min_intraday_score=0, top_n=100),
    )


def _run(
    repository: LocalMarketRepository,
    provider: FakeRealtimeProvider,
    *,
    calculation_at: datetime = CALCULATION_AT,
    policy: RealtimeSelectionPipelinePolicy | None = None,
    settings: Settings | None = None,
):
    return RealtimeSelectionRuntimeService(repository, settings or Settings(), provider).run(
        AS_OF, calculation_at=calculation_at, policy=policy
    )


def test_full_runtime_is_one_shot_read_only_and_retains_all_market_capture(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    _seed(repository, ("600519.SH",))
    provider = FakeRealtimeProvider((_quote("600519.SH"), _quote("000001.SZ", price=8)))
    before = repository.get_stats()

    result = _run(repository, provider, policy=_policy())

    assert repository.get_stats() == before
    assert provider.requests == [RealtimeQuotesRequest(symbols=None)]
    assert result.capture.scope is RealtimeCaptureScope.ALL_MARKET
    assert result.capture.requested_symbols is None
    assert result.capture.persist_requested_symbols == ()
    assert result.capture.persisted_quotes == 0
    assert result.capture.persisted_symbols == ()
    assert result.capture.persistence_performed is False
    assert result.pipeline.selection.diagnostics.selection_ready
    assert result.pipeline.selection.items
    assert tuple(quote.symbol for quote in result.capture.quotes) == ("000001.SZ", "600519.SH")
    assert tuple(item.candidate.symbol for item in result.pipeline.snapshot.items) == ("600519.SH",)
    assert result.pipeline.snapshot.items[0].quote == _quote("600519.SH")


def test_runtime_default_freshness_uses_settings_and_custom_policy_is_retained(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    _seed(repository, ("600519.SH",))
    settings = Settings(realtime={"freshness_normal_max_seconds": 30, "freshness_warning_max_seconds": 90})
    provider = FakeRealtimeProvider((_quote("600519.SH"),))
    warning = _run(repository, provider, calculation_at=CAPTURE_AT + timedelta(seconds=45), settings=settings)
    custom = _policy()
    supplied = _run(repository, provider, policy=custom, settings=settings)

    assert warning.pipeline.snapshot.diagnostics.freshness.value == "warning"
    assert warning.pipeline.policy.freshness_normal_max_seconds == 30
    assert warning.pipeline.policy.freshness_warning_max_seconds == 90
    assert supplied.pipeline_policy == custom == supplied.pipeline.policy


def test_risk_incomplete_and_ready_empty_still_capture_once(tmp_path) -> None:  # type: ignore[no-untyped-def]
    incomplete = _repository(tmp_path / "incomplete")
    _seed(incomplete, ("600519.SH",))
    incomplete.upsert_risk_states((_risk("600519.SH", is_st=None),))
    blocked_provider = FakeRealtimeProvider((_quote("600519.SH"),))
    blocked = _run(incomplete, blocked_provider)
    assert len(blocked_provider.requests) == 1
    assert not blocked.pipeline.selection.diagnostics.selection_ready
    assert blocked.pipeline.snapshot.diagnostics.capture_available

    empty = _repository(tmp_path / "empty")
    _seed(empty, ("600519.SH",))
    empty_provider = FakeRealtimeProvider((_quote("600519.SH"),))
    ready_empty = _run(empty, empty_provider)
    assert len(empty_provider.requests) == 1
    assert ready_empty.pipeline.candidates.candidates == ()
    assert ready_empty.pipeline.selection.diagnostics.selection_ready
    assert ready_empty.pipeline.selection.items == ()


def test_slow_failure_and_naive_times_prevent_provider_capture(tmp_path) -> None:  # type: ignore[no-untyped-def]
    uninitialized = LocalMarketRepository(AppPaths.from_project_root(tmp_path / "uninitialized"))
    provider = FakeRealtimeProvider((_quote("600519.SH"),))
    service = RealtimeSelectionRuntimeService(uninitialized, Settings(), provider)
    with pytest.raises(StorageError):
        service.run(AS_OF, calculation_at=CALCULATION_AT)
    assert provider.requests == []
    initialized = _repository(tmp_path / "initialized")
    naive_provider = FakeRealtimeProvider((_quote("600519.SH"),))
    with pytest.raises(ValueError, match="timezone-aware"):
        RealtimeSelectionRuntimeService(initialized, Settings(), naive_provider).run(
            AS_OF.replace(tzinfo=None), calculation_at=CALCULATION_AT
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        RealtimeSelectionRuntimeService(initialized, Settings(), naive_provider).run(
            AS_OF, calculation_at=CALCULATION_AT.replace(tzinfo=None)
        )
    assert naive_provider.requests == []


def test_provider_and_task23_errors_propagate_without_runtime_translation(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    _seed(repository, ("600519.SH",))
    provider_error = FakeRealtimeProvider(ProviderConnectionError("fake", "quotes", "offline"))
    with pytest.raises(RealtimeCollectionError):
        _run(repository, provider_error)
    assert len(provider_error.requests) == 1
    programming_error = FakeRealtimeProvider(RuntimeError("bug"))
    with pytest.raises(RuntimeError, match="bug"):
        _run(repository, programming_error)
    late = FakeRealtimeProvider((_quote("600519.SH", ingested_at=CAPTURE_AT),))
    with pytest.raises(RealtimeDataError):
        _run(repository, late, calculation_at=AS_OF)


def test_explicit_and_system_calculation_time_follow_required_order(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    _seed(repository, ("600519.SH",))
    events: list[str] = []
    provider = FakeRealtimeProvider((_quote("600519.SH"),), events)
    clock_at = CAPTURE_AT + timedelta(seconds=5)
    monkeypatch.setattr(runtime_module, "_system_calculation_at", lambda _timezone: events.append("clock") or clock_at)
    implicit = RealtimeSelectionRuntimeService(repository, Settings(), provider).run(AS_OF, policy=_policy())
    assert implicit.calculation_at == clock_at
    assert events == ["provider", "clock"]

    monkeypatch.setattr(runtime_module, "_system_calculation_at", lambda _timezone: pytest.fail("clock called"))
    explicit = _run(repository, provider, calculation_at=CALCULATION_AT, policy=_policy())
    assert explicit.calculation_at == CALCULATION_AT


def test_runtime_calls_task24_collector_and_task23_once_in_canonical_order(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    _seed(repository, ("600519.SH",))
    provider = FakeRealtimeProvider((_quote("600519.SH"),))
    events: list[str] = []
    slow_build = runtime_module.RealtimeSlowInputService.build
    capture = runtime_module.RealtimeSnapshotCollector.capture
    pipeline_run = runtime_module.RealtimeSelectionApplicationService.run

    def tracked_slow(self, as_of: datetime):  # type: ignore[no-untyped-def]
        events.append("slow")
        return slow_build(self, as_of)

    def tracked_capture(self, request):  # type: ignore[no-untyped-def]
        events.append("capture")
        return capture(self, request)

    def tracked_pipeline(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        events.append("pipeline")
        return pipeline_run(self, *args, **kwargs)

    monkeypatch.setattr(runtime_module.RealtimeSlowInputService, "build", tracked_slow)
    monkeypatch.setattr(runtime_module.RealtimeSnapshotCollector, "capture", tracked_capture)
    monkeypatch.setattr(runtime_module.RealtimeSelectionApplicationService, "run", tracked_pipeline)

    _run(repository, provider, policy=_policy())

    assert events == ["slow", "capture", "pipeline"]
    assert len(provider.requests) == 1


def test_explicit_time_runs_are_deterministic_and_enabled_flag_is_not_a_gate(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    _seed(repository, ("600519.SH",))
    provider = FakeRealtimeProvider((_quote("600519.SH"),))
    settings = Settings(realtime={"enabled": False, "snapshot_interval_seconds": 5})
    first = _run(repository, provider, policy=_policy(), settings=settings)
    second = _run(repository, provider, policy=_policy(), settings=settings)
    assert first == second
    assert len(provider.requests) == 2


def test_normal_runtime_result_construction_rejects_cross_stage_mismatches(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repository = _repository(tmp_path)
    _seed(repository, ("600519.SH",))
    first = _run(repository, FakeRealtimeProvider((_quote("600519.SH", price=11),)), policy=_policy())
    other = _run(repository, FakeRealtimeProvider((_quote("600519.SH", price=12),)), policy=_policy())
    changed_score = first.slow_inputs.base_scores.stocks[0].model_copy(update={"base_score": 1.0})
    changed_slow = first.slow_inputs.model_copy(
        update={"base_scores": first.slow_inputs.base_scores.model_copy(update={"stocks": (changed_score,)})}
    )
    explicit_capture = first.capture.model_copy(
        update={"scope": RealtimeCaptureScope.EXPLICIT_SYMBOLS, "requested_symbols": ("600519.SH",)}
    )
    persisted_capture = first.capture.model_copy(
        update={"persist_requested_symbols": ("600519.SH",), "persisted_quotes": 1, "persisted_symbols": ("600519.SH",), "persistence_performed": True}
    )
    mismatched_snapshot = first.pipeline.snapshot.model_copy(
        update={"diagnostics": first.pipeline.snapshot.diagnostics.model_copy(update={"capture_source": "other"})}
    )
    mismatched_pipeline = first.pipeline.model_copy(update={"snapshot": mismatched_snapshot})
    for update in (
        {"as_of": AS_OF + timedelta(days=1)},
        {"calculation_at": CALCULATION_AT + timedelta(days=1)},
        {"pipeline_policy": _policy().model_copy(update={"freshness_normal_max_seconds": 20, "freshness_warning_max_seconds": 40})},
        {"capture": explicit_capture},
        {"capture": persisted_capture},
        {"pipeline": mismatched_pipeline},
        {"capture": other.capture},
        {"slow_inputs": changed_slow},
    ):
        with pytest.raises(ValidationError):
            _normal_runtime(first, **update)


def test_cross_run_slow_input_evidence_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    symbols = ("000001.SZ", "600519.SH")
    repository = _repository(tmp_path, symbols)
    _seed(repository, symbols)
    first = _run(
        repository,
        FakeRealtimeProvider((_quote("000001.SZ"), _quote("600519.SH"))),
        policy=_policy(),
    )
    repository.upsert_financial_records(
        (
            FinancialRecord(symbol="600519.SH", report_period=date(2025, 12, 31), announcement_date=AS_OF.date(), available_at=AS_OF - timedelta(hours=1), roe=80, roa=80, gross_margin=80, net_margin=80, revenue=180, net_profit=180, deducted_net_profit=180, source="test"),
        )
    )
    second = _run(
        repository,
        FakeRealtimeProvider((_quote("000001.SZ"), _quote("600519.SH"))),
        policy=_policy(),
    )
    assert first.slow_inputs.base_scores != second.slow_inputs.base_scores
    with pytest.raises(ValidationError):
        _normal_runtime(first, slow_inputs=second.slow_inputs)


def _normal_runtime(
    result: RealtimeSelectionRuntimeResult, **update: object
) -> RealtimeSelectionRuntimeResult:
    values = result.model_dump() | update
    for field in ("slow_inputs", "capture", "pipeline_policy", "pipeline"):
        values.setdefault(field, getattr(result, field))
    return RealtimeSelectionRuntimeResult(**values)
