"""Static boundaries that keep structural universe logic pure and offline."""

from pathlib import Path


def test_universe_core_has_no_provider_ui_or_storage_engine_dependencies() -> None:
    root = Path(__file__).parents[2] / "src" / "stock_selector" / "universe"
    forbidden = (
        "import akshare",
        "from akshare",
        "import requests",
        "from requests",
        "import fastapi",
        "from fastapi",
        "import duckdb",
        "from duckdb",
        "import pyarrow",
        "from pyarrow",
        "import streamlit",
        "from streamlit",
    )
    for path in root.glob("*.py"):
        content = path.read_text(encoding="utf-8")
        assert not any(token in content for token in forbidden), path


def test_builder_is_explicitly_point_in_time_and_storage_independent() -> None:
    path = Path(__file__).parents[2] / "src" / "stock_selector" / "universe" / "builder.py"
    content = path.read_text(encoding="utf-8")
    assert "stock_selector.storage" not in content
    assert "datetime.now" not in content
    assert "date.today" not in content
    assert "instrument.status" not in content
