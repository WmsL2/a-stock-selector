"""Offline contracts for forward-return labels of persisted selection research."""

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from stock_selector.models import AdjustedDailyReturn, AdjustmentType
from stock_selector.selection import (
    DailySelectionDiagnostics,
    SelectionResearchItem,
    SelectionResearchReturnAvailability,
    SelectionResearchReturnLabeler,
    SelectionResearchSnapshot,
)

SNAPSHOT_AT = datetime(2026, 9, 16, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
EVALUATED_AT = datetime(2026, 12, 31, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
ANCHOR = SNAPSHOT_AT.date()


class Repository:
    def __init__(self, records: tuple[AdjustedDailyReturn, ...]) -> None:
        self.records = records
        self.calls: list[tuple[str, datetime, date | None]] = []

    def load_latest_adjusted_daily_returns_as_of(
        self, symbol: str, as_of: datetime, *, start_date: date | None = None
    ) -> tuple[AdjustedDailyReturn, ...]:
        self.calls.append((symbol, as_of, start_date))
        latest: dict[date, AdjustedDailyReturn] = {}
        for record in sorted(self.records, key=lambda item: (item.trade_date, item.observed_at)):
            if (
                record.symbol == symbol
                and record.observed_at <= as_of
                and (start_date is None or record.trade_date >= start_date)
            ):
                latest[record.trade_date] = record
        return tuple(latest[item] for item in sorted(latest))


def _snapshot(*, items: tuple[SelectionResearchItem, ...] | None = None) -> SelectionResearchSnapshot:
    selected = items if items is not None else (
        SelectionResearchItem(
            rank=2, as_of=SNAPSHOT_AT, symbol="600519.SH", name="贵州茅台",
            board="sh_main", industry_code=None, industry_name=None, base_score=80,
            confidence_adjusted_score=60, data_completeness=0.75, confidence=0.8,
            quality_score=81, value_score=79, growth_score=78, momentum_score=None,
            low_volatility_score=None, evidence=(), risks=(),
        ),
        SelectionResearchItem(
            rank=1, as_of=SNAPSHOT_AT, symbol="000001.SZ", name="平安银行",
            board="sz_main", industry_code=None, industry_name=None, base_score=90,
            confidence_adjusted_score=72, data_completeness=0.8, confidence=0.8,
            quality_score=91, value_score=89, growth_score=88, momentum_score=None,
            low_volatility_score=None, evidence=(), risks=(),
        ),
    )
    diagnostics = DailySelectionDiagnostics(
        as_of=SNAPSHOT_AT, selection_ready=bool(selected), blockers=(),
        input_instruments=len(selected), structural_members=len(selected),
        risk_records=len(selected), risk_complete_members=len(selected),
        risk_coverage_ratio=1.0 if selected else 0.0,
        risk_eligible_members=len(selected), factor_input_members=len(selected),
        scoreable_members=len(selected), requested_top_n=20,
        returned_items=len(selected), price_factors_operational=True,
    )
    return SelectionResearchSnapshot(
        as_of=SNAPSHOT_AT, strategy_name="official", selection_ready=bool(selected),
        blockers=(), refresh_had_collection_failures=False,
        diagnostics=diagnostics, items=selected,
    )


def _returns(
    symbol: str, fractions: tuple[float, ...], *, observed_at: datetime = SNAPSHOT_AT
) -> tuple[AdjustedDailyReturn, ...]:
    return tuple(
        AdjustedDailyReturn(
            symbol=symbol, trade_date=ANCHOR + timedelta(days=index),
            previous_trade_date=ANCHOR + timedelta(days=index - 1),
            return_fraction=fraction, adjustment=AdjustmentType.HFQ,
            observed_at=observed_at, source="synthetic",
        )
        for index, fraction in enumerate(fractions, start=1)
    )


def _labels(report, index: int = 0):  # type: ignore[no-untyped-def]
    return {label.horizon_sessions: label for label in report.items[index].labels}


def test_exact_five_session_compounding_uses_the_anchor_linked_chain() -> None:
    fractions = (0.10, -0.05, 0.02, 0.03, -0.01)
    repository = Repository(_returns("600519.SH", fractions))

    report = SelectionResearchReturnLabeler(repository).label(_snapshot(), EVALUATED_AT)

    label = _labels(report)[5]
    assert label.availability is SelectionResearchReturnAvailability.AVAILABLE
    assert label.return_fraction == pytest.approx((1.10 * 0.95 * 1.02 * 1.03 * 0.99) - 1)
    assert label.endpoint_trade_date == ANCHOR + timedelta(days=5)
    assert repository.calls == [
        ("600519.SH", EVALUATED_AT, ANCHOR),
        ("000001.SZ", EVALUATED_AT, ANCHOR),
    ]


def test_fixed_horizons_are_independent_and_preserve_official_order() -> None:
    records = _returns("600519.SH", (0.01,) * 60) + _returns("000001.SZ", (0.02,) * 60)

    report = SelectionResearchReturnLabeler(Repository(records)).label(_snapshot(), EVALUATED_AT)

    assert [(item.rank, item.symbol) for item in report.items] == [
        (2, "600519.SH"), (1, "000001.SZ")
    ]
    labels = _labels(report)
    assert [labels[horizon].endpoint_trade_date for horizon in (5, 20, 60)] == [
        ANCHOR + timedelta(days=5), ANCHOR + timedelta(days=20), ANCHOR + timedelta(days=60)
    ]
    assert [labels[horizon].return_fraction for horizon in (5, 20, 60)] == [
        pytest.approx((1.01**5) - 1), pytest.approx((1.01**20) - 1),
        pytest.approx((1.01**60) - 1),
    ]


def test_shorter_available_horizon_does_not_fabricate_longer_labels() -> None:
    report = SelectionResearchReturnLabeler(Repository(_returns("600519.SH", (0.01,) * 5))).label(
        _snapshot(), EVALUATED_AT
    )

    labels = _labels(report)
    assert labels[5].availability is SelectionResearchReturnAvailability.AVAILABLE
    for horizon in (20, 60):
        assert labels[horizon].availability is SelectionResearchReturnAvailability.INSUFFICIENT_FUTURE_RETURNS
        assert labels[horizon].return_fraction is None
        assert labels[horizon].endpoint_trade_date is None
        assert labels[horizon].endpoint_observed_at is None


def test_missing_anchor_is_distinct_from_later_evidence() -> None:
    record = AdjustedDailyReturn(
        symbol="600519.SH", trade_date=ANCHOR + timedelta(days=2),
        previous_trade_date=ANCHOR + timedelta(days=1), return_fraction=0.01,
        adjustment=AdjustmentType.HFQ, observed_at=SNAPSHOT_AT, source="synthetic",
    )

    report = SelectionResearchReturnLabeler(Repository((record,))).label(_snapshot(), EVALUATED_AT)

    assert {label.availability for label in _labels(report).values()} == {
        SelectionResearchReturnAvailability.ANCHOR_UNAVAILABLE
    }


def test_ambiguous_anchor_successor_has_no_fabricated_label() -> None:
    records = (
        AdjustedDailyReturn(
            symbol="600519.SH", trade_date=ANCHOR + timedelta(days=1),
            previous_trade_date=ANCHOR, return_fraction=0.01,
            adjustment=AdjustmentType.HFQ, observed_at=SNAPSHOT_AT, source="synthetic",
        ),
        AdjustedDailyReturn(
            symbol="600519.SH", trade_date=ANCHOR + timedelta(days=2),
            previous_trade_date=ANCHOR, return_fraction=0.02,
            adjustment=AdjustmentType.HFQ, observed_at=SNAPSHOT_AT, source="synthetic",
        ),
    )

    report = SelectionResearchReturnLabeler(Repository(records)).label(_snapshot(), EVALUATED_AT)

    for label in _labels(report).values():
        assert label.availability is SelectionResearchReturnAvailability.NON_CONTIGUOUS_RETURN_EVIDENCE
        assert label.return_fraction is None
        assert label.endpoint_trade_date is None
        assert label.endpoint_observed_at is None


def test_broken_continuity_is_not_bridged() -> None:
    records = _returns("600519.SH", (0.01,)) + (
        AdjustedDailyReturn(
            symbol="600519.SH", trade_date=ANCHOR + timedelta(days=3),
            previous_trade_date=ANCHOR + timedelta(days=2), return_fraction=0.01,
            adjustment=AdjustmentType.HFQ, observed_at=SNAPSHOT_AT, source="synthetic",
        ),
    )

    report = SelectionResearchReturnLabeler(Repository(records)).label(_snapshot(), EVALUATED_AT)

    assert {label.availability for label in _labels(report).values()} == {
        SelectionResearchReturnAvailability.NON_CONTIGUOUS_RETURN_EVIDENCE
    }


def test_ambiguity_after_five_sessions_preserves_the_five_session_label() -> None:
    records = _returns("600519.SH", (0.01,) * 5) + (
        AdjustedDailyReturn(
            symbol="600519.SH", trade_date=ANCHOR + timedelta(days=6),
            previous_trade_date=ANCHOR + timedelta(days=5), return_fraction=0.01,
            adjustment=AdjustmentType.HFQ, observed_at=SNAPSHOT_AT, source="synthetic",
        ),
        AdjustedDailyReturn(
            symbol="600519.SH", trade_date=ANCHOR + timedelta(days=7),
            previous_trade_date=ANCHOR + timedelta(days=5), return_fraction=0.02,
            adjustment=AdjustmentType.HFQ, observed_at=SNAPSHOT_AT, source="synthetic",
        ),
    )

    report = SelectionResearchReturnLabeler(Repository(records)).label(_snapshot(), EVALUATED_AT)

    labels = _labels(report)
    assert labels[5].availability is SelectionResearchReturnAvailability.AVAILABLE
    assert labels[5].return_fraction == pytest.approx((1.01**5) - 1)
    assert labels[5].endpoint_trade_date == ANCHOR + timedelta(days=5)
    assert labels[20].availability is SelectionResearchReturnAvailability.NON_CONTIGUOUS_RETURN_EVIDENCE
    assert labels[60].availability is SelectionResearchReturnAvailability.NON_CONTIGUOUS_RETURN_EVIDENCE


def test_insufficient_contiguous_observations_are_not_a_gap() -> None:
    report = SelectionResearchReturnLabeler(Repository(_returns("600519.SH", (0.01,) * 4))).label(
        _snapshot(), EVALUATED_AT
    )

    assert {label.availability for label in _labels(report).values()} == {
        SelectionResearchReturnAvailability.INSUFFICIENT_FUTURE_RETURNS
    }


def test_latest_revision_visible_at_evaluated_at_is_used() -> None:
    early = EVALUATED_AT - timedelta(days=2)
    late = EVALUATED_AT + timedelta(days=1)
    records = list(_returns("600519.SH", (0.01,) * 5, observed_at=early))
    records[0] = records[0].model_copy(update={"return_fraction": 0.10})
    records.append(records[0].model_copy(update={"return_fraction": 0.20, "observed_at": late}))

    report = SelectionResearchReturnLabeler(Repository(tuple(records))).label(_snapshot(), EVALUATED_AT)

    assert _labels(report)[5].return_fraction == pytest.approx((1.10 * 1.01**4) - 1)


def test_revisions_observed_after_evaluated_at_are_excluded() -> None:
    late_records = _returns("600519.SH", (0.01,) * 5, observed_at=EVALUATED_AT + timedelta(seconds=1))

    report = SelectionResearchReturnLabeler(Repository(late_records)).label(_snapshot(), EVALUATED_AT)

    assert _labels(report)[5].availability is SelectionResearchReturnAvailability.ANCHOR_UNAVAILABLE


def test_blocked_snapshot_is_a_valid_empty_report_without_repository_reads() -> None:
    empty = _snapshot(items=())
    repository = Repository(())

    report = SelectionResearchReturnLabeler(repository).label(empty, EVALUATED_AT)

    assert report.items == ()
    assert report.anchor_date == ANCHOR
    assert repository.calls == []


def test_labeling_is_deterministic_and_rejects_invalid_evaluation_time() -> None:
    repository = Repository(_returns("600519.SH", (0.01,) * 60))
    labeler = SelectionResearchReturnLabeler(repository)

    assert labeler.label(_snapshot(), EVALUATED_AT) == labeler.label(_snapshot(), EVALUATED_AT)
    with pytest.raises(ValueError, match="must not precede"):
        labeler.label(_snapshot(), SNAPSHOT_AT - timedelta(seconds=1))
    with pytest.raises(ValueError, match="timezone-aware"):
        labeler.label(_snapshot(), EVALUATED_AT.replace(tzinfo=None))


def test_source_has_no_provider_collector_selection_or_scoring_dependency() -> None:
    source = (
        Path(__file__).parents[2]
        / "src/stock_selector/selection/research_returns.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "stock_selector.providers",
        "stock_selector.collection",
        "DailySelectionService",
        "FiveFactorEngine",
        "BaseScoreEngine",
        "ExplanationEngine",
    ):
        assert forbidden not in source