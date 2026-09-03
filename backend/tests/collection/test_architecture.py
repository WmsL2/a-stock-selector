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
