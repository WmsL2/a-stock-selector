"""Architecture guards for pure data-quality calculation."""

from pathlib import Path


def test_quality_evaluator_has_no_storage_provider_network_or_clock() -> None:
    path = Path(__file__).parents[2] / "src" / "stock_selector" / "quality" / "evaluator.py"
    content = path.read_text(encoding="utf-8")
    for forbidden in ("stock_selector.storage", "providers", "requests", "datetime.now", "date.today"):
        assert forbidden not in content
