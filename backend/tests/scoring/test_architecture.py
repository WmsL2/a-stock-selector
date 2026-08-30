"""Architecture boundary tests for the pure scoring package."""

from pathlib import Path


def test_scoring_core_has_no_runtime_integrations() -> None:
    root = Path(__file__).parents[2] / "src" / "stock_selector" / "scoring"
    forbidden = (
        "import akshare",
        "import requests",
        "import fastapi",
        "import duckdb",
        "import pyarrow",
        "import pandas",
        "import numpy",
        "stock_selector.storage",
        "stock_selector.providers",
        "stock_selector.api",
        "datetime.now",
        "date.today",
    )
    for path in root.glob("*.py"):
        assert not any(
            token in path.read_text(encoding="utf-8") for token in forbidden
        ), path
