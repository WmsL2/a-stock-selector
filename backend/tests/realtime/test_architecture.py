from pathlib import Path


def test_realtime_core_has_no_concrete_provider_or_implicit_clock() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "stock_selector"
    collector = (root / "realtime" / "collector.py").read_text(encoding="utf-8")
    status = (root / "realtime" / "status.py").read_text(encoding="utf-8")
    api = (root / "api" / "routers" / "realtime.py").read_text(encoding="utf-8")
    assert "AKShareProvider" not in collector
    assert "AKShareProvider" not in status
    assert "get_realtime_quotes" not in status
    assert "datetime.now" not in collector
    assert "datetime.now" not in status
    assert "get_realtime_quotes" not in api


def test_candidate_engine_has_no_operational_or_storage_dependencies() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "stock_selector"
    candidates = (root / "realtime" / "candidates.py").read_text(encoding="utf-8")
    for forbidden in (
        "stock_selector.providers",
        "LocalMarketRepository",
        "stock_selector.storage",
        "datetime.now",
        "FastAPI",
    ):
        assert forbidden not in candidates


def test_candidate_snapshot_engine_has_no_operational_dependencies() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "stock_selector"
    snapshot = (root / "realtime" / "candidate_snapshot.py").read_text(
        encoding="utf-8"
    )
    for forbidden in (
        "stock_selector.providers",
        "RealtimeSnapshotCollector",
        "LocalMarketRepository",
        "stock_selector.storage",
        "datetime.now",
        "FastAPI",
        "time.sleep",
    ):
        assert forbidden not in snapshot


def test_light_scanner_has_no_operational_dependencies() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "stock_selector"
    scanner = (root / "realtime" / "light_scanner.py").read_text(encoding="utf-8")
    for forbidden in (
        "stock_selector.providers",
        "RealtimeSnapshotCollector",
        "LocalMarketRepository",
        "stock_selector.storage",
        "FastAPI",
        "DataQualityEvaluator",
        "datetime.now",
        "time.sleep",
    ):
        assert forbidden not in scanner


def test_signal_normalizer_has_no_operational_dependencies_and_reuses_task10() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "stock_selector"
    normalizer = (root / "realtime" / "signal_normalizer.py").read_text(encoding="utf-8")
    assert "FactorPreprocessingEngine" in normalizer
    for forbidden in (
        "stock_selector.providers",
        "RealtimeSnapshotCollector",
        "LocalMarketRepository",
        "stock_selector.storage",
        "FastAPI",
        "DataQualityEvaluator",
        "datetime.now",
        "time.sleep",
    ):
        assert forbidden not in normalizer


def test_intraday_factors_have_no_operational_or_preprocessing_dependencies() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "stock_selector"
    factors = (root / "realtime" / "intraday_factors.py").read_text(encoding="utf-8")
    for forbidden in (
        "stock_selector.providers",
        "RealtimeSnapshotCollector",
        "LocalMarketRepository",
        "stock_selector.storage",
        "FastAPI",
        "DataQualityEvaluator",
        "FactorPreprocessingEngine",
        "datetime.now",
        "time.sleep",
    ):
        assert forbidden not in factors


def test_intraday_score_has_no_operational_or_scoring_dependencies() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "stock_selector"
    score = (root / "realtime" / "intraday_score.py").read_text(encoding="utf-8")
    for forbidden in (
        "stock_selector.providers", "RealtimeSnapshotCollector", "LocalMarketRepository",
        "stock_selector.storage", "FastAPI", "DataQualityEvaluator", "FactorPreprocessingEngine",
        "BaseScoreEngine", "stock_selector.scoring", "RealtimeIntradayFactorEngine", "datetime.now", "time.sleep",
        "Settings", "stock_selector.config", "yaml",
    ):
        assert forbidden not in score
