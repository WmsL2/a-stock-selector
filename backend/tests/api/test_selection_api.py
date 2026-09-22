"""HTTP contract tests for truthful on-demand daily selection readiness."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from stock_selector.api.app import create_app
from stock_selector.config import AppPaths, Settings
from stock_selector.models import (
    AdjustedDailyReturn,
    AdjustmentType,
    Board,
    Exchange,
    FinancialRecord,
    IndustryRecord,
    Instrument,
    ValuationRecord,
)
from stock_selector.models.selection import (
    Evidence,
    RiskFlag,
    RiskSeverity,
    SelectionResult,
    StockScore,
)
from stock_selector.risk import DatedRiskState
from stock_selector.selection import (
    DailySelectionDiagnostics,
    DailySelectionResult,
    SelectionBlocker,
    SelectionResearchArtifactStore,
    SelectionResearchExportResult,
    SelectionResearchSnapshot,
    SelectionResearchSnapshotBuilder,
)

_AS_OF = datetime(2026, 3, 31, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
_EVALUATED_AT = _AS_OF + timedelta(days=90)
_CLASSIFICATION = "证监会行业分类标准（2012）"


def _instrument(symbol: str) -> Instrument:
    exchange = Exchange(symbol.rsplit(".", maxsplit=1)[1])
    return Instrument(
        symbol=symbol,
        name=f"name-{symbol}",
        exchange=exchange,
        board=Board.SZ_MAIN if exchange is Exchange.SZSE else Board.SH_MAIN,
        listing_date=date(2000, 1, 1),
    )


def _seed_ready_selection(client: TestClient) -> None:
    repository = client.app.state.repository
    symbols = ("000001.SZ", "600519.SH", "601398.SH")
    repository.save_instruments(tuple(_instrument(symbol) for symbol in symbols))
    for symbol in symbols:
        repository.upsert_risk_states(
            (
                DatedRiskState(
                    symbol=symbol,
                    as_of=_AS_OF.date(),
                    is_st=False,
                    is_suspended=False,
                    is_delisting_period=False,
                    observed_at=_AS_OF,
                    source="synthetic",
                ),
            )
        )
        repository.upsert_financial_records(
            tuple(
                FinancialRecord(
                    symbol=symbol,
                    report_period=period,
                    announcement_date=(_AS_OF - timedelta(days=10)).date(),
                    available_at=_AS_OF - timedelta(days=10),
                    roe=10,
                    roa=10,
                    gross_margin=10,
                    net_margin=10,
                    revenue=110,
                    net_profit=110,
                    deducted_net_profit=110,
                    source="synthetic",
                )
                for period in (date(2024, 12, 31), date(2025, 12, 31))
            )
        )
        repository.upsert_valuation_records(
            (
                ValuationRecord(
                    symbol=symbol,
                    as_of=_AS_OF - timedelta(days=1),
                    pe=10,
                    pb=2,
                    pcf=5,
                    source="synthetic",
                ),
            )
        )
        repository.upsert_industry_records(
            (
                IndustryRecord(
                    symbol=symbol,
                    industry_code="C15",
                    industry_name="酒、饮料和精制茶制造业",
                    classification=_CLASSIFICATION,
                    effective_from=date(2020, 1, 1),
                    source="synthetic",
                ),
            )
        )


def _research_result(*, blocked: bool = False) -> DailySelectionResult:
    blockers = (
        (SelectionBlocker.ELIGIBLE_FACTOR_INPUT_COVERAGE_INCOMPLETE,)
        if blocked
        else ()
    )
    items = () if blocked else (
        StockScore(
            symbol="600519.SH", as_of=_AS_OF, base_score=72.5,
            confidence_adjusted_score=58.0, data_completeness=0.75,
            confidence=0.8, quality_score=81.0, value_score=70.0,
            growth_score=68.0, momentum_score=None, low_volatility_score=None,
            market_rank=2,
            evidence=(Evidence(code="quality", message="quality evidence"),),
            risks=(RiskFlag(code="volatility", message="volatility risk", severity=RiskSeverity.WARNING),),
        ),
        StockScore(
            symbol="000001.SZ", as_of=_AS_OF, base_score=91.0,
            confidence_adjusted_score=None, data_completeness=0.8,
            confidence=0.75, quality_score=90.0, value_score=89.0,
            growth_score=88.0, momentum_score=87.0, low_volatility_score=86.0,
            market_rank=1,
            evidence=(Evidence(code="value", message="value evidence"),), risks=(),
        ),
    )
    diagnostics = DailySelectionDiagnostics(
        as_of=_AS_OF, selection_ready=not blocked, blockers=blockers,
        input_instruments=2, structural_members=2, risk_records=2,
        risk_complete_members=2, risk_coverage_ratio=1.0,
        risk_eligible_members=2, factor_input_members=0 if blocked else 2,
        scoreable_members=0 if blocked else 2, requested_top_n=20,
        returned_items=len(items), price_factors_operational=True,
    )
    return DailySelectionResult(
        as_of=_AS_OF, diagnostics=diagnostics,
        selection=SelectionResult(as_of=_AS_OF, strategy_name="official", items=items),
    )


def _export_research_artifact(
    client: TestClient, *, blocked: bool = False, failures: bool = False
) -> tuple[SelectionResearchSnapshot, SelectionResearchExportResult]:
    repository = client.app.state.repository
    repository.save_instruments((_instrument("600519.SH"), _instrument("000001.SZ")))
    result = _research_result(blocked=blocked)
    snapshot = SelectionResearchSnapshotBuilder(
        repository, client.app.state.settings
    ).build(result, refresh_had_collection_failures=failures)
    export = SelectionResearchArtifactStore(repository.paths).export(snapshot)
    return snapshot, export


def _export_research_artifact_at(
    client: TestClient,
    as_of: datetime,
    *,
    blocked: bool = False,
    failures: bool = False,
    strategy_name: str = "official",
    item_specs: tuple[tuple[str, int], ...] | None = None,
) -> SelectionResearchSnapshot:
    repository = client.app.state.repository
    repository.save_instruments(
        (_instrument("600519.SH"), _instrument("000001.SZ"))
    )
    snapshot = SelectionResearchSnapshotBuilder(
        repository, client.app.state.settings
    ).build(
        _research_result(blocked=blocked),
        refresh_had_collection_failures=failures,
    )
    data = snapshot.model_dump(mode="python")
    data["as_of"] = as_of
    data["strategy_name"] = strategy_name
    data["diagnostics"] = snapshot.diagnostics.model_copy(update={"as_of": as_of})
    items = tuple(
        item.model_copy(update={"as_of": as_of}) for item in snapshot.items
    )
    if item_specs is not None:
        by_symbol = {item.symbol: item for item in items}
        items = tuple(
            by_symbol[symbol].model_copy(update={"rank": rank})
            for symbol, rank in item_specs
        )
        data["diagnostics"] = data["diagnostics"].model_copy(
            update={"returned_items": len(items)}
        )
    data["items"] = items
    historical = SelectionResearchSnapshot.model_validate(data)
    SelectionResearchArtifactStore(repository.paths).export(historical)
    return historical


def _research_effectiveness(
    client: TestClient,
    *,
    evaluated_at: datetime = _EVALUATED_AT,
    start_date: date | None = None,
    end_date: date | None = None,
):
    params: dict[str, str] = {"evaluated_at": evaluated_at.isoformat()}
    if start_date is not None:
        params["start_date"] = start_date.isoformat()
    if end_date is not None:
        params["end_date"] = end_date.isoformat()
    return client.get("/api/selection/research/effectiveness", params=params)


def _seed_adjusted_returns(
    client: TestClient,
    symbol: str,
    *,
    fraction: float = 0.01,
    observed_at: datetime = _AS_OF + timedelta(days=70),
) -> None:
    previous = _AS_OF.date()
    records: list[AdjustedDailyReturn] = []
    for offset in range(1, 61):
        trade_date = _AS_OF.date() + timedelta(days=offset)
        records.append(AdjustedDailyReturn(
            symbol=symbol,
            trade_date=trade_date,
            previous_trade_date=previous,
            return_fraction=fraction,
            adjustment=AdjustmentType.HFQ,
            observed_at=observed_at,
            source="synthetic",
        ))
        previous = trade_date
    client.app.state.repository.upsert_adjusted_daily_returns(tuple(records))


def _empty_effectiveness_body(evaluated_at: datetime) -> dict[str, object]:
    return {
        "evaluated_at": evaluated_at.isoformat(),
        "start_date": None,
        "end_date": None,
        "snapshot_count": 0,
        "empty_snapshot_count": 0,
        "item_observation_count": 0,
        "ranks": [],
        "cutoffs": [],
    }

def test_daily_selection_returns_truthful_empty_readiness(client: TestClient) -> None:
    response = client.get("/api/selection/daily")
    assert response.status_code == 200
    body = response.json()
    assert body["selection_ready"] is False
    assert body["items"] == []
    assert body["diagnostics"]["risk_coverage_ratio"] == 0


def test_selection_research_latest_is_truthful_when_no_artifact_exists(client: TestClient) -> None:
    response = client.get("/api/selection/research/latest")
    assert response.status_code == 200
    assert response.json() == {"available": False, "snapshot": None}
    assert client.get("/api/selection/research/latest.json").status_code == 404
    assert client.get("/api/selection/research/latest.csv").status_code == 404


def test_selection_research_effectiveness_requires_aware_explicit_time(client: TestClient) -> None:
    assert client.get("/api/selection/research/effectiveness").status_code == 422
    naive = client.get(
        "/api/selection/research/effectiveness",
        params={"evaluated_at": "2026-06-29T16:00:00"},
    )
    assert naive.status_code == 422
    assert "evaluated_at" in naive.json()["detail"]


def test_selection_research_effectiveness_returns_fixed_empty_history(client: TestClient) -> None:
    response = _research_effectiveness(client)

    assert response.status_code == 200
    body = response.json()
    assert {key: body[key] for key in _empty_effectiveness_body(_EVALUATED_AT)} == _empty_effectiveness_body(_EVALUATED_AT)
    assert [item["horizon_sessions"] for item in body["overall_horizons"]] == [5, 20, 60]
    assert all(
        item["total_labels"] == 0
        and item["availability_rate"] is None
        and item["mean_return_fraction"] is None
        and item["median_return_fraction"] is None
        for item in body["overall_horizons"]
    )


def test_selection_research_effectiveness_respects_time_and_date_range_filters(client: TestClient) -> None:
    _export_research_artifact(client)

    before = _research_effectiveness(client, evaluated_at=_AS_OF - timedelta(seconds=1))
    excluded = _research_effectiveness(
        client,
        start_date=_AS_OF.date() + timedelta(days=1),
        end_date=_AS_OF.date() + timedelta(days=2),
    )
    invalid = _research_effectiveness(
        client,
        start_date=_AS_OF.date() + timedelta(days=2),
        end_date=_AS_OF.date() + timedelta(days=1),
    )

    assert before.status_code == excluded.status_code == 200
    assert before.json()["snapshot_count"] == excluded.json()["snapshot_count"] == 0
    assert invalid.status_code == 422


def test_selection_research_effectiveness_projects_blocked_and_ready_history(client: TestClient) -> None:
    _export_research_artifact(client, blocked=True)

    blocked = _research_effectiveness(client)

    assert blocked.status_code == 200
    assert blocked.json()["snapshot_count"] == 1
    assert blocked.json()["empty_snapshot_count"] == 1
    assert blocked.json()["item_observation_count"] == 0
    assert blocked.json()["ranks"] == []
    assert blocked.json()["cutoffs"] == []


def test_selection_research_effectiveness_projects_exact_ranks_cutoffs_and_pit_returns(client: TestClient) -> None:
    snapshot, _ = _export_research_artifact(client)
    _seed_adjusted_returns(client, "600519.SH")
    _seed_adjusted_returns(client, "000001.SZ")
    revision = AdjustedDailyReturn(
        symbol="000001.SZ",
        trade_date=_AS_OF.date() + timedelta(days=1),
        previous_trade_date=_AS_OF.date(),
        return_fraction=0.10,
        adjustment=AdjustmentType.HFQ,
        observed_at=_AS_OF + timedelta(days=80),
        source="synthetic-revision",
    )
    client.app.state.repository.upsert_adjusted_daily_returns((revision,))

    before_revision = _research_effectiveness(client, evaluated_at=_AS_OF + timedelta(days=75))
    response = _research_effectiveness(client)

    assert before_revision.status_code == response.status_code == 200
    body = response.json()
    assert body["snapshot_count"] == snapshot.schema_version == 1
    assert body["item_observation_count"] == 2
    assert body["empty_snapshot_count"] == 0
    assert [item["horizon_sessions"] for item in body["overall_horizons"]] == [5, 20, 60]
    assert [item["rank"] for item in body["ranks"]] == [1, 2]
    assert [item["cutoff_rank"] for item in body["cutoffs"]] == [1, 2]
    assert [item["included_ranks"] for item in body["cutoffs"]] == [[1], [1, 2]]
    assert body["overall_horizons"][0]["mean_return_fraction"] != before_revision.json()["overall_horizons"][0]["mean_return_fraction"]
    assert "items" not in body


def test_selection_research_effectiveness_preserves_sparse_rank_http_projection(
    client: TestClient,
) -> None:
    snapshot, _ = _export_research_artifact(client)
    payload = snapshot.model_dump()
    payload["items"] = [
        item.model_dump() | {"rank": rank}
        for item, rank in zip(snapshot.items, (3, 1), strict=True)
    ]
    sparse_snapshot = SelectionResearchSnapshot.model_validate(payload)
    SelectionResearchArtifactStore(client.app.state.repository.paths).export(
        sparse_snapshot
    )

    response = _research_effectiveness(client)

    assert response.status_code == 200
    body = response.json()
    assert [item["rank"] for item in body["ranks"]] == [1, 3]
    assert [item["cutoff_rank"] for item in body["cutoffs"]] == [1, 3]
    assert body["cutoffs"][0]["included_ranks"] == [1]
    assert body["cutoffs"][1]["included_ranks"] == [1, 3]
    assert 2 not in [item["rank"] for item in body["ranks"]]
    assert 2 not in [item["cutoff_rank"] for item in body["cutoffs"]]


def test_selection_research_effectiveness_corrupt_artifact_is_generic_503(client: TestClient) -> None:
    snapshot, _ = _export_research_artifact(client)
    root = client.app.state.repository.paths.project_root
    corrupt = client.app.state.repository.paths.snapshots_dir / "selection" / snapshot.as_of.date().isoformat() / "selection.json"
    corrupt.write_text("{not valid json", encoding="utf-8")

    response = _research_effectiveness(client)

    assert response.status_code == 503
    assert response.json() == {"detail": "selection research artifact unavailable"}
    assert str(root) not in response.text
    assert "json" not in response.text.lower()


def test_selection_research_latest_projects_real_ready_artifact_exactly(client: TestClient) -> None:
    _export_research_artifact(client)

    response = client.get("/api/selection/research/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    snapshot = body["snapshot"]
    assert snapshot["as_of"] == _AS_OF.isoformat()
    assert snapshot["strategy_name"] == "official"
    assert snapshot["selection_ready"] is True
    assert snapshot["refresh_had_collection_failures"] is False
    assert snapshot["diagnostics"] == {
        "input_instruments": 2, "structural_members": 2, "risk_records": 2,
        "risk_complete_members": 2, "risk_coverage_ratio": 1.0,
        "risk_eligible_members": 2, "factor_input_members": 2,
        "scoreable_members": 2, "requested_top_n": 20, "returned_items": 2,
        "price_factors_operational": True,
    }
    assert [(item["rank"], item["symbol"], item["base_score"]) for item in snapshot["items"]] == [
        (2, "600519.SH", 72.5), (1, "000001.SZ", 91.0),
    ]


def test_selection_research_latest_projects_blockers_without_rows(client: TestClient) -> None:
    _export_research_artifact(client, blocked=True)

    response = client.get("/api/selection/research/latest")

    assert response.status_code == 200
    snapshot = response.json()["snapshot"]
    assert snapshot["selection_ready"] is False
    assert snapshot["blockers"] == ["eligible_factor_input_coverage_incomplete"]
    assert snapshot["items"] == []
    assert snapshot["diagnostics"]["returned_items"] == 0
    assert snapshot["diagnostics"]["factor_input_members"] == 0


def test_selection_research_latest_projects_refresh_failure_provenance(client: TestClient) -> None:
    _export_research_artifact(client, failures=True)

    response = client.get("/api/selection/research/latest")

    assert response.status_code == 200
    assert response.json()["snapshot"]["refresh_had_collection_failures"] is True


def test_selection_research_history_returns_an_empty_success(client: TestClient) -> None:
    response = client.get("/api/selection/research/history")

    assert response.status_code == 200
    assert response.json() == {
        "start_date": None,
        "end_date": None,
        "snapshot_count": 0,
        "snapshots": [],
    }


def test_selection_research_history_preserves_canonical_order_and_fidelity(
    client: TestClient,
) -> None:
    earlier = _export_research_artifact_at(
        client, datetime(2026, 9, 15, 16, tzinfo=ZoneInfo("Asia/Shanghai")), failures=True
    )
    later = _export_research_artifact_at(
        client, datetime(2026, 9, 16, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    )

    response = client.get("/api/selection/research/history")

    assert response.status_code == 200
    snapshots = response.json()["snapshots"]
    assert [item["as_of"] for item in snapshots] == [
        earlier.as_of.isoformat(), later.as_of.isoformat()
    ]
    first = snapshots[0]
    assert first["selection_ready"] is True
    assert first["blockers"] == []
    assert first["refresh_had_collection_failures"] is True
    assert first["diagnostics"]["returned_items"] == 2
    assert [item["rank"] for item in first["items"]] == [2, 1]
    assert first["items"][0]["evidence"][0]["code"] == "quality"
    assert first["items"][0]["risks"][0]["code"] == "volatility"


@pytest.mark.parametrize(
    ("params", "expected_dates"),
    [
        ({"start_date": "2026-09-16"}, ["2026-09-16", "2026-09-17"]),
        ({"end_date": "2026-09-16"}, ["2026-09-15", "2026-09-16"]),
        (
            {"start_date": "2026-09-16", "end_date": "2026-09-16"},
            ["2026-09-16"],
        ),
    ],
)
def test_selection_research_history_date_filters_are_inclusive(
    client: TestClient, params: dict[str, str], expected_dates: list[str]
) -> None:
    for day in (15, 16, 17):
        _export_research_artifact_at(
            client, datetime(2026, 9, day, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
        )

    response = client.get("/api/selection/research/history", params=params)

    assert response.status_code == 200
    assert [item["as_of"][:10] for item in response.json()["snapshots"]] == expected_dates


def test_selection_research_history_rejects_an_invalid_date_range(client: TestClient) -> None:
    response = client.get(
        "/api/selection/research/history",
        params={"start_date": "2026-09-17", "end_date": "2026-09-16"},
    )

    assert response.status_code == 422


def test_selection_research_history_projects_blocked_snapshots(client: TestClient) -> None:
    _export_research_artifact_at(
        client,
        datetime(2026, 9, 16, 16, tzinfo=ZoneInfo("Asia/Shanghai")),
        blocked=True,
        failures=True,
    )

    response = client.get("/api/selection/research/history")

    assert response.status_code == 200
    snapshot = response.json()["snapshots"][0]
    assert snapshot["selection_ready"] is False
    assert snapshot["blockers"] == ["eligible_factor_input_coverage_incomplete"]
    assert snapshot["refresh_had_collection_failures"] is True
    assert snapshot["diagnostics"]["returned_items"] == 0


def test_selection_research_history_corrupt_artifact_is_a_generic_503(
    client: TestClient,
) -> None:
    snapshot, _ = _export_research_artifact(client)
    corrupt = (
        client.app.state.repository.paths.snapshots_dir
        / "selection"
        / snapshot.as_of.date().isoformat()
        / "selection.json"
    )
    corrupt.write_text("{not valid json", encoding="utf-8")

    response = client.get("/api/selection/research/history")

    assert response.status_code == 503
    assert response.json() == {"detail": "selection research artifact unavailable"}


def test_selection_research_stability_returns_empty_and_single_reports(
    client: TestClient,
) -> None:
    empty = client.get("/api/selection/research/stability")
    assert empty.status_code == 200
    assert empty.json() == {
        "start_date": None,
        "end_date": None,
        "snapshot_count": 0,
        "transition_count": 0,
        "comparable_transition_count": 0,
        "transitions": [],
    }
    _export_research_artifact_at(
        client, datetime(2026, 9, 15, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    )
    single = client.get("/api/selection/research/stability")
    assert single.status_code == 200
    assert single.json()["snapshot_count"] == 1
    assert single.json()["transitions"] == []


def test_selection_research_stability_projects_ready_order_and_filters(
    client: TestClient,
) -> None:
    _export_research_artifact_at(
        client,
        datetime(2026, 9, 15, 16, tzinfo=ZoneInfo("Asia/Shanghai")),
        item_specs=(("600519.SH", 3), ("000001.SZ", 1)),
    )
    _export_research_artifact_at(
        client,
        datetime(2026, 9, 16, 16, tzinfo=ZoneInfo("Asia/Shanghai")),
        item_specs=(("000001.SZ", 2),),
    )
    _export_research_artifact_at(
        client,
        datetime(2026, 9, 17, 16, tzinfo=ZoneInfo("Asia/Shanghai")),
        item_specs=(("000001.SZ", 1), ("600519.SH", 4)),
    )

    response = client.get("/api/selection/research/stability")

    assert response.status_code == 200
    body = response.json()
    assert [(item["previous_as_of"][:10], item["current_as_of"][:10]) for item in body["transitions"]] == [
        ("2026-09-15", "2026-09-16"), ("2026-09-16", "2026-09-17")
    ]
    first = body["transitions"][0]
    assert (first["retained_count"], first["entered_count"], first["exited_count"]) == (1, 0, 1)
    assert (first["retention_rate"], first["overlap_rate"]) == (0.5, 0.5)
    assert [item["symbol"] for item in first["movements"]] == ["000001.SZ", "600519.SH"]
    assert [item["status"] for item in first["movements"]] == ["retained", "exited"]
    assert first["movements"][0]["rank_change"] == -1
    filtered = client.get("/api/selection/research/stability", params={"start_date": "2026-09-16"})
    assert filtered.status_code == 200
    assert filtered.json()["transition_count"] == 1


def test_selection_research_stability_handles_blocked_strategy_changed_and_errors(
    client: TestClient,
) -> None:
    _export_research_artifact_at(
        client, datetime(2026, 9, 15, 16, tzinfo=ZoneInfo("Asia/Shanghai")), blocked=True
    )
    _export_research_artifact_at(
        client, datetime(2026, 9, 16, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    )
    blocked = client.get("/api/selection/research/stability")
    assert blocked.status_code == 200
    transition = blocked.json()["transitions"][0]
    assert transition["comparable"] is False
    assert transition["comparison_blockers"] == ["previous_selection_blocked"]
    assert transition["previous_blockers"] == ["eligible_factor_input_coverage_incomplete"]
    assert transition["movements"] == []
    invalid = client.get(
        "/api/selection/research/stability",
        params={"start_date": "2026-09-17", "end_date": "2026-09-16"},
    )
    assert invalid.status_code == 422


def test_selection_research_stability_strategy_change_and_corrupt_artifact(
    client: TestClient,
) -> None:
    first = _export_research_artifact_at(
        client, datetime(2026, 9, 15, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    )
    _export_research_artifact_at(
        client,
        datetime(2026, 9, 16, 16, tzinfo=ZoneInfo("Asia/Shanghai")),
        strategy_name="other-official",
    )
    changed = client.get("/api/selection/research/stability")
    assert changed.json()["transitions"][0]["comparison_blockers"] == ["strategy_changed"]
    corrupt = (
        client.app.state.repository.paths.snapshots_dir / "selection"
        / first.as_of.date().isoformat() / "selection.json"
    )
    corrupt.write_text("{not valid json", encoding="utf-8")
    unavailable = client.get("/api/selection/research/stability")
    assert unavailable.status_code == 503
    assert unavailable.json() == {"detail": "selection research artifact unavailable"}


@pytest.mark.parametrize(
    ("suffix", "content_type"),
    (("json", "application/json"), ("csv", "text/csv")),
)
def test_selection_research_downloads_exact_committed_artifacts(
    client: TestClient, suffix: str, content_type: str
) -> None:
    snapshot, export = _export_research_artifact(client)
    expected_path = getattr(export, f"{suffix}_path")

    response = client.get(f"/api/selection/research/latest.{suffix}")

    assert response.status_code == 200
    assert content_type in response.headers["content-type"]
    assert response.content == Path(expected_path).read_bytes()
    assert f'filename="selection-{snapshot.as_of.date().isoformat()}.{suffix}"' in response.headers["content-disposition"]
    assert str(client.app.state.repository.paths.project_root) not in response.headers["content-disposition"]
    if suffix == "json":
        assert json.loads(response.text)["items"][0]["symbol"] == "600519.SH"
    else:
        assert response.text.splitlines()[0].startswith("rank,symbol,name,board")
        assert response.text.splitlines()[1].startswith("2,600519.SH")


def test_selection_research_corrupt_artifact_is_a_generic_503(client: TestClient) -> None:
    snapshot, _ = _export_research_artifact(client)
    root = client.app.state.repository.paths.project_root
    corrupt = client.app.state.repository.paths.snapshots_dir / "selection" / snapshot.as_of.date().isoformat() / "selection.json"
    corrupt.write_text("{not valid json", encoding="utf-8")

    for path in ("/api/selection/research/latest", "/api/selection/research/latest.json"):
        response = client.get(path)
        assert response.status_code == 503
        assert response.json() == {"detail": "selection research artifact unavailable"}
        assert str(root) not in response.text
        assert "json" not in response.text.lower()


def test_selection_research_routes_do_not_invoke_daily_selection_or_provider(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ForbiddenProvider:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(f"provider must not be used: {name}")

    application = create_app(
        AppPaths.from_project_root(tmp_path), settings=Settings(),
        realtime_provider=ForbiddenProvider(),
    )
    with TestClient(application) as client:
        _export_research_artifact(client)
        monkeypatch.setattr(
            "stock_selector.selection.daily.DailySelectionService.build",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("daily selection must not run")),
        )
        monkeypatch.setattr(
            "stock_selector.selection.research.SelectionResearchArtifactStore.export",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("artifact export must not run")),
        )
        assert client.get("/api/selection/research/latest").status_code == 200
        assert client.get("/api/selection/research/latest.json").status_code == 200
        assert client.get("/api/selection/research/latest.csv").status_code == 200
        assert client.get("/api/selection/research/history").status_code == 200
        assert client.get("/api/selection/research/stability").status_code == 200
        assert _research_effectiveness(client).status_code == 200


def test_daily_selection_rejects_naive_as_of(client: TestClient) -> None:
    response = client.get("/api/selection/daily", params={"as_of": "2026-03-31T16:00:00"})
    assert response.status_code == 422
    aware = datetime(2026, 3, 31, 16, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert client.get("/api/selection/daily", params={"as_of": aware.isoformat()}).status_code == 200


def test_daily_selection_ready_contract_returns_ranked_qvg_items(tmp_path) -> None:  # type: ignore[no-untyped-def]
    application = create_app(AppPaths.from_project_root(tmp_path), settings=Settings())
    with TestClient(application) as client:
        _seed_ready_selection(client)
        response = client.get("/api/selection/daily", params={"as_of": _AS_OF.isoformat()})

    assert response.status_code == 200
    body = response.json()
    assert body["selection_ready"] is True
    assert body["blockers"] == []
    assert [item["symbol"] for item in body["items"]] == [
        "000001.SZ",
        "600519.SH",
        "601398.SH",
    ]
    assert [item["rank"] for item in body["items"]] == [1, 2, 3]
    assert [item["base_score"] for item in body["items"]] == sorted(
        (item["base_score"] for item in body["items"]), reverse=True
    )
    item = body["items"][0]
    assert {"rank", "symbol", "name", "board", "base_score", "confidence_adjusted_score", "data_completeness", "confidence", "quality_score", "value_score", "growth_score", "momentum_score", "low_volatility_score"} <= item.keys()
    assert item["data_completeness"] == 0.75
    assert item["momentum_score"] is None
    assert item["low_volatility_score"] is None
    assert isinstance(item["evidence"], list) and item["evidence"]
    assert {"code", "message", "factor_name", "value", "percentile", "contribution"} <= item["evidence"][0].keys()
    assert isinstance(item["risks"], list) and item["risks"]
    assert {"code", "message", "severity"} <= item["risks"][0].keys()
    assert all(risk["code"] != "price_factors_unavailable" for risk in item["risks"])
    assert {risk["code"] for risk in item["risks"]} >= {
        "missing_momentum",
        "missing_low_volatility",
    }
