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
