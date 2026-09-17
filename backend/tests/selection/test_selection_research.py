"""Offline contracts for durable projections of official daily selections."""

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from stock_selector.config import AppPaths, Settings
from stock_selector.models import Board, Exchange, Instrument
from stock_selector.models.selection import SelectionResult, StockScore
from stock_selector.selection import (
    DailySelectionDiagnostics,
    DailySelectionResult,
    SelectionResearchArtifactStore,
    SelectionResearchError,
    SelectionResearchSnapshot,
    SelectionResearchSnapshotBuilder,
)

NOW = datetime(2026, 9, 16, 16, tzinfo=ZoneInfo("Asia/Shanghai"))


class Repository:
    def __init__(self) -> None:
        self.loads = 0

    def load_instruments(self):  # type: ignore[no-untyped-def]
        self.loads += 1
        return (Instrument(symbol="000001.SZ", name="平安银行", exchange=Exchange.SZSE, board=Board.SZ_MAIN, listing_date=date(2000, 1, 1)),)

    def load_industry_records(self, symbol: str, *, as_of: date):  # type: ignore[no-untyped-def]
        assert symbol == "000001.SZ" and as_of == NOW.date()
        return ()


def _result(rank: int | None = 1) -> DailySelectionResult:
    score = StockScore(symbol="000001.SZ", as_of=NOW, base_score=80, quality_score=81, value_score=79, growth_score=78, data_completeness=.75, confidence=.8, confidence_adjusted_score=60, market_rank=rank)
    diagnostics = DailySelectionDiagnostics(as_of=NOW, selection_ready=True, blockers=(), input_instruments=1, structural_members=1, risk_records=1, risk_complete_members=1, risk_coverage_ratio=1, risk_eligible_members=1, factor_input_members=1, scoreable_members=1, requested_top_n=20, returned_items=1, price_factors_operational=True)
    return DailySelectionResult(as_of=NOW, diagnostics=diagnostics, selection=SelectionResult(as_of=NOW, strategy_name="official", items=(score,)))


def test_builder_preserves_official_projection_and_missing_pit_industry() -> None:
    repository = Repository()
    snapshot = SelectionResearchSnapshotBuilder(repository, Settings()).build(_result(), refresh_had_collection_failures=True)  # type: ignore[arg-type]
    item = snapshot.items[0]
    assert repository.loads == 1
    assert (item.rank, item.symbol, item.base_score, item.name, item.board) == (1, "000001.SZ", 80, "平安银行", "sz_main")
    assert item.industry_code is None and item.industry_name is None
    assert snapshot.refresh_had_collection_failures is True


def test_builder_rejects_missing_official_market_rank() -> None:
    with pytest.raises(SelectionResearchError, match="market_rank"):
        SelectionResearchSnapshotBuilder(Repository(), Settings()).build(_result(None), refresh_had_collection_failures=False)  # type: ignore[arg-type]


def test_store_round_trip_is_deterministic_and_csv_is_header_only_when_blocked(tmp_path: Path) -> None:
    snapshot = SelectionResearchSnapshotBuilder(Repository(), Settings()).build(_result(), refresh_had_collection_failures=False)  # type: ignore[arg-type]
    store = SelectionResearchArtifactStore(AppPaths.from_project_root(tmp_path))
    assert store.canonical_json(snapshot) == store.canonical_json(snapshot)
    exported = store.export(snapshot)
    assert store.load_latest() == snapshot
    assert Path(exported.json_path).is_file() and Path(exported.csv_path).read_text(encoding="utf-8").splitlines()[0].startswith("rank,")


def test_stray_csv_is_not_a_committed_snapshot_and_corrupt_json_is_explicit(tmp_path: Path) -> None:
    root = AppPaths.from_project_root(tmp_path).snapshots_dir / "selection" / "2026-09-16"
    root.mkdir(parents=True)
    (root / "selection.csv").write_text("rank\n", encoding="utf-8")
    store = SelectionResearchArtifactStore(AppPaths.from_project_root(tmp_path))
    assert store.load_latest() is None
    (root / "selection.json").write_text("not json", encoding="utf-8")
    with pytest.raises(SelectionResearchError, match="corrupt"):
        store.load_latest()


def test_same_date_json_commit_failure_restores_old_csv_and_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = SelectionResearchArtifactStore(AppPaths.from_project_root(tmp_path))
    old = SelectionResearchSnapshotBuilder(Repository(), Settings()).build(_result(), refresh_had_collection_failures=False)  # type: ignore[arg-type]
    old_export = store.export(old)
    old_json = Path(old_export.json_path).read_text(encoding="utf-8")
    old_csv = Path(old_export.csv_path).read_text(encoding="utf-8")
    new_item = old.items[0].model_copy(update={"base_score": 81.0})
    new = old.model_copy(update={"items": (new_item,)})
    original_replace = Path.replace

    def fail_json_commit(source: Path, target: Path) -> Path:
        if source.name == ".selection.json.tmp" and target.name == "selection.json":
            raise OSError("json boom")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_json_commit)
    with pytest.raises(SelectionResearchError, match="could not export"):
        store.export(new)
    directory = Path(old_export.json_path).parent
    assert Path(old_export.json_path).read_text(encoding="utf-8") == old_json
    assert Path(old_export.csv_path).read_text(encoding="utf-8") == old_csv
    assert store.load_latest() == old
    assert not tuple(directory.glob(".selection.*.tmp"))
    assert not tuple(directory.glob(".selection.*.bak"))


def test_same_date_csv_promotion_failure_restores_old_csv_and_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SelectionResearchArtifactStore(AppPaths.from_project_root(tmp_path))
    old = SelectionResearchSnapshotBuilder(Repository(), Settings()).build(
        _result(), refresh_had_collection_failures=False
    )  # type: ignore[arg-type]
    old_export = store.export(old)
    old_json = Path(old_export.json_path).read_bytes()
    old_csv = Path(old_export.csv_path).read_bytes()
    new_item = old.items[0].model_copy(update={"base_score": 81.0})
    new = old.model_copy(update={"items": (new_item,)})
    original_replace = Path.replace

    def fail_csv_promotion(source: Path, target: Path) -> Path:
        if source.name == ".selection.csv.tmp" and target.name == "selection.csv":
            raise OSError("csv boom")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_csv_promotion)
    with pytest.raises(SelectionResearchError, match="could not export"):
        store.export(new)
    directory = Path(old_export.json_path).parent
    assert Path(old_export.json_path).read_bytes() == old_json
    assert Path(old_export.csv_path).read_bytes() == old_csv
    assert store.load_latest() == old
    assert not tuple(directory.glob(".selection.*.tmp"))
    assert not tuple(directory.glob(".selection.*.bak"))


def test_first_export_json_commit_failure_leaves_no_committed_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = SelectionResearchArtifactStore(AppPaths.from_project_root(tmp_path))
    snapshot = SelectionResearchSnapshotBuilder(Repository(), Settings()).build(_result(), refresh_had_collection_failures=False)  # type: ignore[arg-type]
    original_replace = Path.replace

    def fail_json_commit(source: Path, target: Path) -> Path:
        if source.name == ".selection.json.tmp" and target.name == "selection.json":
            raise OSError("json boom")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_json_commit)
    with pytest.raises(SelectionResearchError):
        store.export(snapshot)
    directory = tmp_path / "runtime/snapshots/selection/2026-09-16"
    assert not (directory / "selection.json").exists()
    assert not (directory / "selection.csv").exists()
    assert store.load_latest() is None
    assert not tuple(directory.glob(".selection.*"))


@pytest.mark.parametrize("mutation", ("schema", "naive", "diagnostics", "ready", "blockers", "returned", "symbols", "ranks", "item_as_of", "rank"))
def test_snapshot_rejects_contradictory_contracts(mutation: str) -> None:
    snapshot = SelectionResearchSnapshotBuilder(Repository(), Settings()).build(_result(), refresh_had_collection_failures=False)  # type: ignore[arg-type]
    payload = snapshot.model_dump()
    if mutation == "schema": payload["schema_version"] = 2
    if mutation == "naive": payload["as_of"] = NOW.replace(tzinfo=None)
    if mutation == "diagnostics": payload["diagnostics"]["as_of"] = NOW.replace(day=15)
    if mutation == "ready": payload["selection_ready"] = False
    if mutation == "blockers": payload["blockers"] = ["no_scoreable_instruments"]
    if mutation == "returned": payload["diagnostics"]["returned_items"] = 0
    if mutation == "symbols": payload["items"] *= 2; payload["diagnostics"]["returned_items"] = 2
    if mutation == "ranks": payload["items"] *= 2; payload["items"][1]["symbol"] = "600519.SH"; payload["diagnostics"]["returned_items"] = 2
    if mutation == "item_as_of": payload["items"][0]["as_of"] = NOW.replace(day=15)
    if mutation == "rank": payload["items"][0]["rank"] = 0
    with pytest.raises(ValueError):
        SelectionResearchSnapshot.model_validate(payload)


def test_source_has_no_ranking_or_provider_dependencies() -> None:
    source = (Path(__file__).parents[2] / "src/stock_selector/selection/research.py").read_text(encoding="utf-8")
    for forbidden in ("AKShareProvider", "stock_selector.providers", "stock_selector.collection", "FiveFactorEngine", "BaseScoreEngine", "ExplanationEngine", "RiskEligibilityEvaluator", "CurrentSelectionCoverageAuditor", "FastAPI", "stock_selector.api", "stock_selector.realtime", "broker"):
        assert forbidden not in source
