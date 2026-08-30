"""Keep explanation generation pure and detached from I/O boundaries."""

from pathlib import Path


def test_explanation_core_has_no_io_or_clock_dependencies() -> None:
    root = Path(__file__).parents[2] / "src" / "stock_selector" / "explanation"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    forbidden = (
        "akshare",
        "requests",
        "fastapi",
        "duckdb",
        "pyarrow",
        "pandas",
        "numpy",
        "storage",
        "providers",
        "api",
        "openai",
        "prompt",
        "datetime.now",
        "date.today",
    )
    assert not [token for token in forbidden if token in source]
