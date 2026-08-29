"""Keep preprocessing pure and isolated from runtime integrations."""

from pathlib import Path


def test_preprocessing_has_no_runtime_or_network_dependencies() -> None:
    root = Path(__file__).parents[2] / "src" / "stock_selector" / "preprocessing"
    forbidden = (
        "import akshare",
        "from akshare",
        "import requests",
        "from requests",
        "import fastapi",
        "from fastapi",
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
        content = path.read_text(encoding="utf-8")
        assert not any(token in content for token in forbidden), path
