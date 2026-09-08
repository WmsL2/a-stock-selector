"""Keep collection logic bounded, provider-abstract, and clock-free."""

from pathlib import Path


def test_collection_has_no_concrete_network_or_ui_dependencies() -> None:
    root = Path(__file__).parents[2] / "src" / "stock_selector" / "collection"
    forbidden = (
        "AKShareProvider",
        "import akshare",
        "from akshare",
        "import requests",
        "from requests",
        "import fastapi",
        "from fastapi",
        "streamlit",
        "vue",
        "CurrentUniverseService",
        "load_instruments",
    )
    for path in root.glob("*.py"):
        content = path.read_text(encoding="utf-8")
        assert not any(token in content for token in forbidden), path


def test_collector_has_no_hidden_clock() -> None:
    root = Path(__file__).parents[2] / "src" / "stock_selector" / "collection"
    for path in (
        root / "daily.py",
        root / "risk.py",
        root / "structural_fundamentals.py",
        root / "structural_valuation.py",
        root / "structural_adjusted_returns.py",
        root / "structural_slow_inputs.py",
        root / "structural_slow_input_sweep.py",
        root / "structural_factor_input_coverage.py",
        root / "structural_missing_refresh.py",
        root / "adjusted_returns.py",
    ):
        content = path.read_text(encoding="utf-8")
        assert "date.today" not in content
        assert "datetime.now" not in content


def test_structural_valuation_has_no_scope_expansion_dependencies() -> None:
    path = Path(__file__).parents[2] / "src" / "stock_selector" / "collection" / "structural_valuation.py"
    content = path.read_text(encoding="utf-8")
    forbidden = (
        "AKShareProvider",
        "akshare",
        "CurrentUniverseService",
        "datetime.now",
        "date.today",
        "FastAPI",
        "selection",
        "scoring",
        "realtime",
        "frontend",
    )
    assert not any(token in content for token in forbidden)


def test_structural_adjusted_returns_has_no_scope_expansion_dependencies() -> None:
    path = Path(__file__).parents[2] / "src" / "stock_selector" / "collection" / "structural_adjusted_returns.py"
    content = path.read_text(encoding="utf-8")
    forbidden = ("AKShareProvider", "akshare", "CurrentUniverseService", "datetime.now", "date.today", "selection", "scoring", "realtime", "FastAPI")
    assert not any(token in content for token in forbidden)


def test_structural_slow_inputs_has_no_scope_expansion_dependencies() -> None:
    path = Path(__file__).parents[2] / "src" / "stock_selector" / "collection" / "structural_slow_inputs.py"
    content = path.read_text(encoding="utf-8")
    forbidden = ("AKShareProvider", "akshare", "CurrentUniverseService", "datetime.now", "date.today", "selection", "scoring", "realtime", "FastAPI", "frontend")
    assert not any(token in content for token in forbidden)


def test_structural_slow_input_sweep_has_no_scope_expansion_dependencies() -> None:
    path = Path(__file__).parents[2] / "src" / "stock_selector" / "collection" / "structural_slow_input_sweep.py"
    content = path.read_text(encoding="utf-8")
    forbidden = (
        "AKShareProvider", "akshare", "CurrentUniverseService", "datetime.now",
        "date.today", "selection", "scoring", "realtime", "FastAPI", "frontend",
        "sleep", "asyncio", "threading", "multiprocessing",
    )
    assert not any(token in content for token in forbidden)


def test_structural_factor_input_coverage_has_no_infrastructure_dependencies() -> None:
    path = Path(__file__).parents[2] / "src" / "stock_selector" / "collection" / "structural_factor_input_coverage.py"
    content = path.read_text(encoding="utf-8")
    forbidden = (
        "AKShareProvider",
        "akshare",
        "LocalMarketRepository",
        "CurrentUniverseService",
        "datetime.now",
        "date.today",
        "from stock_selector.providers",
        "import stock_selector.providers",
        "from pathlib import Path",
        "from stock_selector.selection",
        "import stock_selector.selection",
        "from stock_selector.scoring",
        "import stock_selector.scoring",
        "from stock_selector.realtime",
        "import stock_selector.realtime",
        "from stock_selector.api",
        "import stock_selector.api",
        "FastAPI",
        "sleep(",
        "from time import sleep",
        "asyncio",
        "threading",
        "multiprocessing",
    )
    assert not any(token in content for token in forbidden)


def test_structural_missing_refresh_has_no_scope_expansion_dependencies() -> None:
    path = Path(__file__).parents[2] / "src" / "stock_selector" / "collection" / "structural_missing_refresh.py"
    content = path.read_text(encoding="utf-8")
    forbidden = (
        "AKShareProvider", "akshare", "LocalMarketRepository", "CurrentUniverseService",
        "datetime.now", "date.today", "StructuralSlowInputCollector", "StructuralSlowInputSweepCollector",
        "from stock_selector.providers", "import stock_selector.providers",
        "from stock_selector.selection", "import stock_selector.selection",
        "from stock_selector.scoring", "import stock_selector.scoring",
        "from stock_selector.realtime", "import stock_selector.realtime",
        "from stock_selector.api", "import stock_selector.api", "FastAPI", "sleep(",
        "from time import sleep", "asyncio", "threading", "multiprocessing",
    )
    assert not any(token in content for token in forbidden)
