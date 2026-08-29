"""Architecture guards for pure risk core behavior."""

from pathlib import Path


def test_risk_core_has_no_provider_storage_or_ui_dependencies() -> None:
    root = Path(__file__).parents[2] / "src" / "stock_selector" / "risk"
    forbidden = (
        "import akshare",
        "import requests",
        "import fastapi",
        "import duckdb",
        "import pyarrow",
        "import streamlit",
        "stock_selector.storage",
    )
    for path in root.glob("*.py"):
        if path.name == "__init__.py":
            continue
        content = path.read_text(encoding="utf-8").casefold()
        assert not any(token in content for token in forbidden), path


def test_risk_evaluator_has_no_clock_access() -> None:
    content = (Path(__file__).parents[2] / "src" / "stock_selector" / "risk" / "evaluator.py").read_text(encoding="utf-8")
    assert "datetime.now" not in content
    assert "date.today" not in content
