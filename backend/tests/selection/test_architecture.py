"""Static boundaries for local read-only daily selection orchestration."""

from pathlib import Path


def test_selection_core_has_no_provider_network_or_http_dependencies() -> None:
    root = Path(__file__).parents[2] / "src" / "stock_selector" / "selection"
    forbidden = (
        "import akshare",
        "import requests",
        "import fastapi",
        "stock_selector.providers",
        "datetime.now",
        "date.today",
    )
    for path in root.glob("*.py"):
        assert not any(token in path.read_text(encoding="utf-8") for token in forbidden), path


def test_input_readiness_has_no_scope_expansion_dependencies() -> None:
    content = (Path(__file__).parents[2] / "src" / "stock_selector" / "selection" / "input_readiness.py").read_text(encoding="utf-8")
    forbidden = (
        "AKShareProvider", "stock_selector.providers", "LocalMarketRepository",
        "stock_selector.storage", "CurrentUniverseService", "datetime.now", "date.today",
        "DailySelectionService", "FiveFactorEngine", "BaseScoreEngine", "ExplanationEngine",
        "fastapi", "requests", "asyncio", "threading", "multiprocessing",
        "from time import sleep", "time.sleep(",
    )
    assert not any(token in content for token in forbidden)
