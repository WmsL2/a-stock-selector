"""Offline contracts for chronological labels of persisted selection artifacts."""

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from stock_selector.config import AppPaths
from stock_selector.models import AdjustedDailyReturn
from stock_selector.selection import (
    DailySelectionDiagnostics,
    SelectionResearchArtifactStore,
    SelectionResearchItem,
    SelectionResearchReturnHistory,
    SelectionResearchReturnHistoryBuilder,
    SelectionResearchReturnLabeler,
    SelectionResearchSnapshot,
)

AT = datetime(2026, 9, 16, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
EVALUATED_AT = datetime(2026, 12, 31, 16, tzinfo=ZoneInfo("Asia/Shanghai"))


class ReturnRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, datetime, date | None]] = []

    def load_latest_adjusted_daily_returns_as_of(
        self, symbol: str, as_of: datetime, *, start_date: date | None = None
    ) -> tuple[AdjustedDailyReturn, ...]:
        self.calls.append((symbol, as_of, start_date))
        return ()


def _snapshot(
    as_of: datetime, *, blocked: bool = False, two_items: bool = False
) -> SelectionResearchSnapshot:
    first = SelectionResearchItem(
        rank=2, as_of=as_of, symbol="600519.SH", name="贵州茅台", board="sh_main",
        industry_code=None, industry_name=None, base_score=80, confidence_adjusted_score=60,
        data_completeness=0.75, confidence=0.8, quality_score=81, value_score=79,
        growth_score=78, momentum_score=None, low_volatility_score=None, evidence=(), risks=(),
    )
    second = first.model_copy(update={"rank": 1, "symbol": "000001.SZ", "name": "平安银行"})
    items = () if blocked else (first, second) if two_items else (first,)
    diagnostics = DailySelectionDiagnostics(
        as_of=as_of, selection_ready=bool(items), blockers=(), input_instruments=len(items),
        structural_members=len(items), risk_records=len(items), risk_complete_members=len(items),
        risk_coverage_ratio=1.0 if items else 0.0, risk_eligible_members=len(items),
        factor_input_members=len(items), scoreable_members=len(items), requested_top_n=20,
        returned_items=len(items), price_factors_operational=True,
    )
    return SelectionResearchSnapshot(
        as_of=as_of, strategy_name="official", selection_ready=bool(items), blockers=(),
        refresh_had_collection_failures=False, diagnostics=diagnostics, items=items,
    )


def _builder(tmp_path: Path) -> tuple[SelectionResearchArtifactStore, SelectionResearchReturnHistoryBuilder, ReturnRepository]:
    store = SelectionResearchArtifactStore(AppPaths.from_project_root(tmp_path))
    repository = ReturnRepository()
    return store, SelectionResearchReturnHistoryBuilder(store, SelectionResearchReturnLabeler(repository)), repository  # type: ignore[arg-type]


def test_history_uses_inclusive_ranges_and_preserves_snapshot_chronology(tmp_path: Path) -> None:
    store, builder, _ = _builder(tmp_path)
    snapshots = tuple(_snapshot(AT + timedelta(days=offset)) for offset in (2, 0, 1))
    for snapshot in snapshots:
        store.export(snapshot)

    history = builder.build(EVALUATED_AT, start_date=AT.date() + timedelta(days=1), end_date=AT.date() + timedelta(days=2))

    assert [report.snapshot_as_of.date() for report in history.reports] == [
        AT.date() + timedelta(days=1), AT.date() + timedelta(days=2)
    ]
    assert all(report.evaluated_at == EVALUATED_AT for report in history.reports)


def test_history_rejects_invalid_ranges_and_naive_evaluation_time(tmp_path: Path) -> None:
    _, builder, _ = _builder(tmp_path)

    with pytest.raises(ValueError, match="must not follow"):
        builder.build(EVALUATED_AT, start_date=AT.date() + timedelta(days=1), end_date=AT.date())
    with pytest.raises(ValueError, match="timezone-aware"):
        builder.build(EVALUATED_AT.replace(tzinfo=None))


def test_history_excludes_future_snapshots_and_does_not_synthesize_missing_dates(tmp_path: Path) -> None:
    store, builder, _ = _builder(tmp_path)
    past = _snapshot(AT)
    future = _snapshot(EVALUATED_AT + timedelta(seconds=1))
    later = _snapshot(AT + timedelta(days=2))
    for snapshot in (future, later, past):
        store.export(snapshot)

    history = builder.build(EVALUATED_AT)

    assert [report.snapshot_as_of.date() for report in history.reports] == [
        AT.date(), AT.date() + timedelta(days=2)
    ]


def test_history_retains_blocked_snapshots_as_empty_reports(tmp_path: Path) -> None:
    store, builder, repository = _builder(tmp_path)
    store.export(_snapshot(AT, blocked=True))

    history = builder.build(EVALUATED_AT)

    assert len(history.reports) == 1
    assert history.reports[0].items == ()
    assert repository.calls == []


def test_empty_history_and_deterministic_repetition(tmp_path: Path) -> None:
    _, builder, _ = _builder(tmp_path)

    first = builder.build(EVALUATED_AT)
    second = builder.build(EVALUATED_AT)

    assert first == second
    assert first.reports == ()


def test_history_delegates_item_order_and_shared_evaluated_at_to_task48(tmp_path: Path) -> None:
    store, builder, repository = _builder(tmp_path)
    store.export(_snapshot(AT, two_items=True))

    history = builder.build(EVALUATED_AT)

    report = history.reports[0]
    assert [(item.rank, item.symbol) for item in report.items] == [
        (2, "600519.SH"), (1, "000001.SZ")
    ]
    assert report.evaluated_at == history.evaluated_at == EVALUATED_AT
    assert repository.calls == [
        ("600519.SH", EVALUATED_AT, AT.date()),
        ("000001.SZ", EVALUATED_AT, AT.date()),
    ]


def test_history_model_rejects_duplicate_dates_or_mismatched_evaluated_at(tmp_path: Path) -> None:
    store, builder, _ = _builder(tmp_path)
    store.export(_snapshot(AT))
    report = builder.build(EVALUATED_AT).reports[0]

    with pytest.raises(ValueError, match="unique snapshot dates"):
        SelectionResearchReturnHistory(evaluated_at=EVALUATED_AT, reports=(report, report))
    with pytest.raises(ValueError, match="share evaluated_at"):
        SelectionResearchReturnHistory(
            evaluated_at=EVALUATED_AT,
            reports=(report.model_copy(update={"evaluated_at": EVALUATED_AT + timedelta(seconds=1)}),),
        )


def test_history_source_has_no_selection_refresh_provider_or_performance_dependencies() -> None:
    source = (
            Path(__file__).parents[2]
            / "src/stock_selector/selection/research_return_history.py"
        ).read_text(encoding="utf-8")
    for forbidden in (
        "stock_selector.providers", "stock_selector.collection", "DailySelectionService",
        "CurrentDailySelectionWorkflowService", "CurrentSelectionRefreshService",
        "FiveFactorEngine", "BaseScoreEngine", "benchmark", "hit_rate", "RankIC", "PnL",
    ):
        assert forbidden not in source
