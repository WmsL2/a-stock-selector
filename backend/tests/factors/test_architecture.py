from pathlib import Path


def test_factor_core_has_no_runtime_integrations() -> None:
    root = Path(__file__).parents[2] / "src" / "stock_selector" / "factors"
    forbidden = (
        "import akshare",
        "import requests",
        "import fastapi",
        "import duckdb",
        "import pandas",
        "import numpy",
        "stock_selector.storage",
        "stock_selector.providers",
        "datetime.now",
        "date.today",
    )
    for path in root.glob("*.py"):
        assert not any(
            token in path.read_text(encoding="utf-8") for token in forbidden
        ), path
