from __future__ import annotations

import pandas as pd

from backend.providers import (
    _normalize_baostock_frame,
    _normalize_efinance_frame,
    _to_baostock_code,
    _to_efinance_code,
    fetch_free_daily_dataset,
)


def test_provider_symbol_code_conversions():
    assert _to_efinance_code("600519.SH") == "600519"
    assert _to_efinance_code("000001.SZ") == "000001"
    assert _to_baostock_code("600519.SH") == "sh.600519"
    assert _to_baostock_code("000001.SZ") == "sz.000001"


def test_normalize_efinance_frame_to_market_schema():
    source = pd.DataFrame(
        {
            "日期": ["2024-01-02"],
            "股票名称": ["贵州茅台"],
            "股票代码": ["600519"],
            "开盘": [1700.0],
            "最高": [1710.0],
            "最低": [1690.0],
            "收盘": [1705.0],
            "成交量": [1000],
            "成交额": [1705000],
        }
    )

    frame = _normalize_efinance_frame(source, "600519.SH")

    assert frame.loc[0, "symbol"] == "600519.SH"
    assert frame.loc[0, "trade_date"] == "2024-01-02"
    assert frame.loc[0, "close"] == 1705.0
    assert frame.loc[0, "amount"] == 1705000


def test_normalize_baostock_frame_to_market_schema():
    source = pd.DataFrame(
        {
            "date": ["2024-01-02"],
            "code": ["sh.600519"],
            "open": ["1700.0"],
            "high": ["1710.0"],
            "low": ["1690.0"],
            "close": ["1705.0"],
            "preclose": ["1698.0"],
            "volume": ["100000"],
            "amount": ["1705000"],
        }
    )

    frame = _normalize_baostock_frame(source, "600519.SH")

    assert frame.loc[0, "symbol"] == "600519.SH"
    assert frame.loc[0, "trade_date"] == "2024-01-02"
    assert frame.loc[0, "prev_close"] == "1698.0"
    assert frame.loc[0, "volume"] == "100000"


def test_free_provider_chain_uses_next_provider_for_remaining_symbols(monkeypatch):
    def first_provider(symbols: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "trade_date": ["2024-01-02"],
                "symbol": ["600519.SH"],
                "open": [10],
                "high": [11],
                "low": [9],
                "close": [10.5],
                "volume": [1000],
            }
        )

    def second_provider(symbols: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        assert "000001.SZ" in symbols
        return pd.DataFrame(
            {
                "trade_date": ["2024-01-02", "2024-01-02"],
                "symbol": ["000001.SZ", "000300.SH"],
                "open": [20, 30],
                "high": [21, 31],
                "low": [19, 29],
                "close": [20.5, 30.5],
                "volume": [2000, 3000],
            }
        )

    providers = {
        "efinance": first_provider,
        "baostock": second_provider,
    }
    monkeypatch.setattr("backend.providers._provider_fetcher", lambda name: providers[name])

    frame, stats = fetch_free_daily_dataset(
        ["600519.SH", "000001.SZ"], "2024-01-02", "2024-01-02", provider_order=["efinance", "baostock"]
    )

    assert set(frame["symbol"]) == {"600519.SH", "000001.SZ", "000300.SH"}
    assert stats[0]["provider"] == "efinance"
    assert stats[0]["fetched_symbols"] == 1
    assert stats[1]["provider"] == "baostock"
    assert stats[1]["fetched_symbols"] == 2
