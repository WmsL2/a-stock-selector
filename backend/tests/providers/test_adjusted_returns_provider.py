"""Offline provider-boundary regressions for Task32 HFQ return evidence."""

from datetime import date

import pandas as pd
import pytest

from stock_selector.models import AdjustmentType
from stock_selector.providers import (
    AdjustedDailyReturnsRequest,
    AKShareProvider,
    ProviderConnectionError,
    ProviderDataError,
    ProviderNotSupportedError,
)
from stock_selector.providers import akshare_provider as provider_module


def _request(symbol: str = "600519.SH") -> AdjustedDailyReturnsRequest:
    return AdjustedDailyReturnsRequest(symbol=symbol, start_date=date(2026, 9, 1), end_date=date(2026, 9, 3))


def _em_frame() -> pd.DataFrame:
    return pd.DataFrame({"日期": ["2026-09-01", "2026-09-02"], "收盘": [100, 102]})


def _sina_frame() -> pd.DataFrame:
    return pd.DataFrame({"date": ["2026-09-01", "2026-09-02"], "close": [100, 102]})


def test_adjusted_returns_use_eastmoney_once_without_sina(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_hist", lambda **kwargs: (calls.append(kwargs), _em_frame())[1])
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_daily", lambda **kwargs: (_ for _ in ()).throw(AssertionError("no fallback")))
    records = AKShareProvider().get_adjusted_daily_returns(_request())
    assert calls == [{"symbol": "600519", "period": "daily", "start_date": "20260901", "end_date": "20260903", "adjust": "hfq"}]
    assert len({item.observed_at for item in records}) == 1
    assert all(item.adjustment is AdjustmentType.HFQ for item in records)


def test_adjusted_returns_fallback_is_transport_only(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"em": 0, "sina": 0}
    def fail_em(**kwargs):  # type: ignore[no-untyped-def]
        calls["em"] += 1
        raise RuntimeError("transport")
    def sina(**kwargs):  # type: ignore[no-untyped-def]
        calls["sina"] += 1
        return _sina_frame()
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_hist", fail_em)
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_daily", sina)
    records = AKShareProvider().get_adjusted_daily_returns(_request())
    assert calls == {"em": 1, "sina": 1}
    assert records[0].source == "akshare:stock_zh_a_daily:hfq"


def test_adjusted_returns_bad_schema_does_not_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_hist", lambda **kwargs: pd.DataFrame({"日期": ["2026-09-01"]}))
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_daily", lambda **kwargs: (_ for _ in ()).throw(AssertionError("no fallback")))
    with pytest.raises(ProviderDataError):
        AKShareProvider().get_adjusted_daily_returns(_request())


def test_adjusted_returns_both_transport_boundaries_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_hist", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("em")))
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_daily", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("sina")))
    with pytest.raises(ProviderConnectionError):
        AKShareProvider().get_adjusted_daily_returns(_request())


def test_adjusted_returns_bse_fallback_is_not_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_module.ak, "stock_zh_a_hist", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("em")))
    with pytest.raises(ProviderNotSupportedError):
        AKShareProvider().get_adjusted_daily_returns(_request("430047.BJ"))
