from pathlib import Path


def test_realtime_core_has_no_concrete_provider_or_implicit_clock() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "stock_selector"
    collector = (root / "realtime" / "collector.py").read_text(encoding="utf-8")
    status = (root / "realtime" / "status.py").read_text(encoding="utf-8")
    api = (root / "api" / "routers" / "realtime.py").read_text(encoding="utf-8")
    assert "AKShareProvider" not in collector
    assert "AKShareProvider" not in status
    assert "get_realtime_quotes" not in status
    assert "datetime.now" not in collector
    assert "datetime.now" not in status
    assert "get_realtime_quotes" not in api
