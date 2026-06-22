from __future__ import annotations

from functools import lru_cache
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd


SAMPLE_NAMES = {
    "600519.SH": "贵州茅台",
    "000333.SZ": "美的集团",
    "600036.SH": "招商银行",
    "601318.SH": "中国平安",
    "000858.SZ": "五粮液",
}


def _stable_seed(symbol: str) -> int:
    return sum((index + 1) * ord(char) for index, char in enumerate(symbol))


@lru_cache(maxsize=32)
def sample_daily(symbol: str, start: str = "2017-01-01", end: str = "2025-12-31") -> pd.DataFrame:
    """Generate deterministic offline OHLCV data for product demos and tests."""
    dates = pd.bdate_range(start, end)
    rng = np.random.default_rng(_stable_seed(symbol))
    market = rng.normal(0.00035, 0.012, len(dates))
    cycle = np.sin(np.arange(len(dates)) / 95) * 0.0015
    shocks = np.zeros(len(dates))
    for index in range(180, len(dates), 420):
        shocks[index : index + 16] -= 0.007
    returns = np.clip(market + cycle + shocks, -0.095, 0.095)
    base = 18 + (_stable_seed(symbol) % 90)
    close = base * np.cumprod(1 + returns)
    prev_close = np.r_[close[0] / (1 + returns[0]), close[:-1]]
    overnight = rng.normal(0, 0.004, len(dates))
    open_price = np.clip(prev_close * (1 + overnight), prev_close * 0.905, prev_close * 1.095)
    high = np.maximum(open_price, close) * (1 + rng.uniform(0.001, 0.018, len(dates)))
    low = np.minimum(open_price, close) * (1 - rng.uniform(0.001, 0.018, len(dates)))
    volume = rng.integers(1_500_000, 28_000_000, len(dates))
    frame = pd.DataFrame(
        {
            "trade_date": dates,
            "symbol": symbol,
            "name": SAMPLE_NAMES.get(symbol, symbol),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "prev_close": prev_close,
            "volume": volume,
            "amount": volume * close,
            "limit_up": np.round(prev_close * 1.10, 2),
            "limit_down": np.round(prev_close * 0.90, 2),
            "suspended": False,
        }
    )
    return frame.round({"open": 2, "high": 2, "low": 2, "close": 2, "prev_close": 2})


def _validate_csv_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"trade_date", "symbol", "open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"CSV 缺少字段: {', '.join(sorted(missing))}")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame = frame.sort_values(["trade_date", "symbol"]).drop_duplicates(
        ["trade_date", "symbol"], keep="last"
    )
    invalid = (
        (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
        | (frame[["open", "high", "low", "close"]] <= 0).any(axis=1)
    )
    if invalid.any():
        raise ValueError(f"CSV 包含 {int(invalid.sum())} 行非法 OHLC 数据")
    return frame


def load_csv(path: str | Path) -> pd.DataFrame:
    return _validate_csv_frame(pd.read_csv(path))


def load_csv_text(content: str) -> pd.DataFrame:
    return _validate_csv_frame(pd.read_csv(StringIO(content)))


def dataset_summary(frame: pd.DataFrame) -> dict:
    return {
        "row_count": int(len(frame)),
        "symbol_count": int(frame["symbol"].nunique()),
        "start_date": str(frame["trade_date"].min().date()),
        "end_date": str(frame["trade_date"].max().date()),
        "symbols": sorted(frame["symbol"].astype(str).unique().tolist()),
        "preview": frame.head(20).assign(
            trade_date=lambda value: value["trade_date"].dt.strftime("%Y-%m-%d")
        ).to_dict(orient="records"),
    }


def source_status() -> dict:
    try:
        import akshare  # noqa: F401

        return {"source": "AkShare + CSV", "available": True, "message": "AkShare 已就绪"}
    except ImportError:
        return {
            "source": "演示数据 + CSV",
            "available": True,
            "message": "未安装 AkShare，当前使用可复现演示行情",
        }
