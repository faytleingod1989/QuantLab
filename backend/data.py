from __future__ import annotations

from functools import lru_cache
from io import StringIO
from pathlib import Path
import re

import numpy as np
import pandas as pd


SAMPLE_NAMES = {
    "600519.SH": "贵州茅台",
    "000333.SZ": "美的集团",
    "600036.SH": "招商银行",
    "601318.SH": "中国平安",
    "000858.SZ": "五粮液",
}
SYMBOL_PATTERN = re.compile(r"^(\d{6})\.(SH|SZ|BJ)$")
MAIN_BOARD_REGISTRATION_START = pd.Timestamp("2023-04-10")


class DataSourceError(RuntimeError):
    """Raised when an external market-data provider cannot supply valid data."""


def normalize_symbol(symbol: str) -> str:
    value = str(symbol).strip().upper()
    if value.isdigit() and len(value) == 6:
        suffix = (
            "BJ"
            if value.startswith(("8", "920", "430"))
            else "SH" if value.startswith(("5", "6", "9")) else "SZ"
        )
        value = f"{value}.{suffix}"
    if not SYMBOL_PATTERN.fullmatch(value):
        raise ValueError(f"无效的 A 股证券代码: {symbol}")
    return value


def _stable_seed(symbol: str) -> int:
    return sum((index + 1) * ord(char) for index, char in enumerate(symbol))


def _limit_rate(symbol: str, trade_date: pd.Timestamp, name: str) -> float:
    code, exchange = symbol.split(".")
    if "ST" in name.upper():
        return 0.05
    if exchange == "BJ" or code.startswith("8"):
        return 0.30
    if code.startswith(("688", "689")):
        return 0.20
    if code.startswith(("300", "301")) and trade_date >= pd.Timestamp("2020-08-24"):
        return 0.20
    return 0.10


def _is_limit_exempt(
    symbol: str,
    trade_date: pd.Timestamp,
    listed_date: pd.Timestamp | None,
    listing_session: int | None,
) -> tuple[bool, str]:
    if listed_date is None or pd.isna(listed_date) or listing_session is None:
        return False, ""
    code, exchange = symbol.split(".")
    if trade_date < listed_date:
        return False, ""
    if (trade_date - listed_date).days > 14:
        return False, ""
    if exchange == "BJ" and listing_session == 1:
        return True, "北交所新股上市首日不设价格涨跌幅限制"
    if code.startswith(("688", "689")) and listing_session <= 5:
        return True, "科创板新股上市后前5个交易日不设价格涨跌幅限制"
    if code.startswith(("300", "301")) and trade_date >= pd.Timestamp("2020-08-24") and listing_session <= 5:
        return True, "创业板注册制新股上市后前5个交易日不设价格涨跌幅限制"
    if (
        exchange in {"SH", "SZ"}
        and not code.startswith(("300", "301", "688", "689"))
        and listed_date >= MAIN_BOARD_REGISTRATION_START
        and listing_session <= 5
    ):
        return True, "沪深主板注册制新股上市后前5个交易日不设价格涨跌幅限制"
    return False, ""


def infer_board(symbol: str) -> str:
    symbol = normalize_symbol(symbol)
    code, exchange = symbol.split(".")
    if exchange == "BJ" or code.startswith("8"):
        return "北交所"
    if code.startswith(("688", "689")):
        return "科创板"
    if code.startswith(("300", "301")):
        return "创业板"
    if exchange == "SH":
        return "沪市主板"
    return "深市主板"


def _market_symbol(code, exchange: str) -> str:
    return f"{str(code).strip().zfill(6)}.{exchange}"


def _clean_date(value) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return "1990-12-19"
    return str(parsed.date())


def _clean_number(value) -> int | None:
    if pd.isna(value):
        return None
    text = str(value).replace(",", "").strip()
    if not text or text in {"-", "None", "nan"}:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def is_st_name(name: str) -> bool:
    return "ST" in str(name).upper()


def prepare_market_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate and enrich a normalized OHLCV snapshot for deterministic backtests."""
    current = frame.copy()
    current.columns = [str(column).strip().lower() for column in current.columns]
    required = {"trade_date", "symbol", "open", "high", "low", "close", "volume"}
    missing = required - set(current.columns)
    if missing:
        raise ValueError(f"CSV 缺少字段: {', '.join(sorted(missing))}")
    current["trade_date"] = pd.to_datetime(current["trade_date"], errors="coerce")
    if current["trade_date"].isna().any():
        raise ValueError("数据包含无法识别的交易日期")
    current["symbol"] = current["symbol"].map(normalize_symbol)
    numeric = ["open", "high", "low", "close", "volume"]
    for column in numeric:
        current[column] = pd.to_numeric(current[column], errors="coerce")
    if current[numeric].isna().any().any():
        raise ValueError("数据包含无法识别的 OHLCV 数值")
    current = current.sort_values(["symbol", "trade_date"]).drop_duplicates(
        ["trade_date", "symbol"], keep="last"
    )
    invalid = (
        (current["high"] < current[["open", "close", "low"]].max(axis=1))
        | (current["low"] > current[["open", "close", "high"]].min(axis=1))
        | (current[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (current["volume"] < 0)
    )
    if invalid.any():
        raise ValueError(f"数据包含 {int(invalid.sum())} 行非法 OHLCV 数据")
    if "name" not in current:
        current["name"] = current["symbol"].map(SAMPLE_NAMES).fillna(current["symbol"])
    else:
        current["name"] = current["name"].fillna(current["symbol"]).astype(str)
    if "listed_date" in current:
        current["listed_date"] = pd.to_datetime(current["listed_date"], errors="coerce")
    else:
        current["listed_date"] = pd.NaT
    derived_prev_close = current.groupby("symbol", sort=False)["close"].shift(1)
    if "prev_close" in current:
        current["prev_close"] = pd.to_numeric(current["prev_close"], errors="coerce")
        current["prev_close"] = current["prev_close"].fillna(derived_prev_close)
    else:
        current["prev_close"] = derived_prev_close
    current["prev_close"] = current["prev_close"].fillna(current["open"])
    if "amount" not in current:
        current["amount"] = current["volume"] * current["close"]
    else:
        current["amount"] = pd.to_numeric(current["amount"], errors="coerce").fillna(
            current["volume"] * current["close"]
        )
    rates = [
        _limit_rate(symbol, date, name)
        for symbol, date, name in zip(
            current["symbol"], current["trade_date"], current["name"], strict=True
        )
    ]
    current["limit_rate"] = pd.Series(rates, index=current.index)
    listing_sessions = pd.Series(index=current.index, dtype="float")
    for _, group in current.groupby("symbol", sort=False):
        listed_date = group["listed_date"].dropna().min()
        if pd.isna(listed_date):
            continue
        eligible_index = group[group["trade_date"] >= listed_date].index
        listing_sessions.loc[eligible_index] = range(1, len(eligible_index) + 1)
    exemptions = [
        _is_limit_exempt(
            symbol,
            trade_date,
            listed_date if pd.notna(listed_date) else None,
            int(session) if pd.notna(session) else None,
        )
        for symbol, trade_date, listed_date, session in zip(
            current["symbol"],
            current["trade_date"],
            current["listed_date"],
            listing_sessions,
            strict=True,
        )
    ]
    current["limit_exempt"] = [item[0] for item in exemptions]
    current["limit_reason"] = [item[1] for item in exemptions]
    if "limit_up" not in current:
        current["limit_up"] = current["prev_close"] * (1 + pd.Series(rates, index=current.index))
    if "limit_down" not in current:
        current["limit_down"] = current["prev_close"] * (1 - pd.Series(rates, index=current.index))
    current["limit_up"] = pd.to_numeric(current["limit_up"], errors="coerce").round(2)
    current["limit_down"] = pd.to_numeric(current["limit_down"], errors="coerce").round(2)
    if "suspended" not in current:
        current["suspended"] = current["volume"] <= 0
    else:
        current["suspended"] = current["suspended"].map(_to_bool)
    adjusted_source = next(
        (
            column
            for column in ("adjusted_close", "adj_close", "qfq_close", "hfq_close")
            if column in current.columns
        ),
        None,
    )
    if "adjust_factor" in current.columns:
        current["adjust_factor"] = pd.to_numeric(current["adjust_factor"], errors="coerce")
    elif adjusted_source:
        current["adjust_factor"] = pd.to_numeric(current[adjusted_source], errors="coerce") / current["close"]
    else:
        current["adjust_factor"] = 1.0
    if current["adjust_factor"].isna().any() or (current["adjust_factor"] <= 0).any():
        raise ValueError("数据包含非法复权因子")
    if adjusted_source:
        current["adjusted_close"] = pd.to_numeric(current[adjusted_source], errors="coerce")
    else:
        current["adjusted_close"] = current["close"] * current["adjust_factor"]
    if current["adjusted_close"].isna().any() or (current["adjusted_close"] <= 0).any():
        raise ValueError("数据包含非法复权收盘价")
    previous_factor = current.groupby("symbol", sort=False)["adjust_factor"].shift(1)
    factor_ratio = current["adjust_factor"] / previous_factor
    current["corporate_action"] = (
        previous_factor.notna() & ((factor_ratio - 1.0).abs() > 1e-6)
    )
    previous_adjusted_close = current.groupby("symbol", sort=False)["adjusted_close"].shift(1)
    adjusted_return = current["adjusted_close"] / previous_adjusted_close - 1.0
    current["adjustment_anomaly"] = (
        previous_adjusted_close.notna()
        & ~current["suspended"]
        & (
            (adjusted_return.abs() > 0.35)
            | (previous_factor.notna() & ((factor_ratio - 1.0).abs() > 0.50))
        )
    )
    ordered = [
        "trade_date", "symbol", "name", "listed_date", "open", "high", "low", "close",
        "prev_close", "volume", "amount", "limit_rate", "limit_up", "limit_down",
        "limit_exempt", "limit_reason", "suspended",
        "adjust_factor", "adjusted_close", "corporate_action", "adjustment_anomaly",
    ]
    return current[ordered].round({"adjust_factor": 8, "adjusted_close": 4}).sort_values(
        ["trade_date", "symbol"]
    ).reset_index(drop=True)


def _to_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "是", "停牌"}
    return bool(value)


@lru_cache(maxsize=32)
def sample_daily(symbol: str, start: str = "2017-01-01", end: str = "2025-12-31") -> pd.DataFrame:
    """Generate deterministic offline OHLCV data for product demos and tests."""
    symbol = normalize_symbol(symbol)
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
            "trade_date": dates, "symbol": symbol, "name": SAMPLE_NAMES.get(symbol, symbol),
            "open": open_price, "high": high, "low": low, "close": close,
            "prev_close": prev_close, "volume": volume, "amount": volume * close,
            "limit_up": np.round(prev_close * 1.10, 2),
            "limit_down": np.round(prev_close * 0.90, 2), "suspended": False,
        }
    )
    return frame.round({"open": 2, "high": 2, "low": 2, "close": 2, "prev_close": 2})


def load_csv(path: str | Path) -> pd.DataFrame:
    return prepare_market_frame(pd.read_csv(path))


def load_csv_text(content: str) -> pd.DataFrame:
    return prepare_market_frame(pd.read_csv(StringIO(content)))


def filter_to_trading_calendar(
    frame: pd.DataFrame,
    start_date: str | None = None,
    end_date: str | None = None,
    *,
    client=None,
    strict: bool = False,
) -> pd.DataFrame:
    """Remove bars that cannot drive a daily A-share strategy.

    AkShare snapshots are checked strictly. CSV imports use the same calendar when available
    and gracefully fall back to weekday-only filtering for offline/local use.
    """
    current = prepare_market_frame(frame)
    start = start_date or str(current["trade_date"].min().date())
    end = end_date or str(current["trade_date"].max().date())
    try:
        calendar = fetch_trading_calendar(start, end, client=client)
        allowed_dates = set(calendar["trade_date"].dt.normalize())
        filtered = current[current["trade_date"].dt.normalize().isin(allowed_dates)]
    except DataSourceError:
        if strict:
            raise
        filtered = current[current["trade_date"].dt.weekday < 5]
    if filtered.empty:
        raise ValueError("数据过滤交易日历后没有可用行情")
    return filtered.reset_index(drop=True)


def dataset_summary(frame: pd.DataFrame) -> dict:
    current = prepare_market_frame(frame)
    return {
        "row_count": int(len(current)),
        "symbol_count": int(current["symbol"].nunique()),
        "start_date": str(current["trade_date"].min().date()),
        "end_date": str(current["trade_date"].max().date()),
        "symbols": sorted(current["symbol"].astype(str).unique().tolist()),
        "quality": adjustment_quality_summary(current),
        "preview": current.head(20).assign(
            trade_date=lambda value: value["trade_date"].dt.strftime("%Y-%m-%d"),
            listed_date=lambda value: value["listed_date"].dt.strftime("%Y-%m-%d").fillna(""),
        ).to_dict(orient="records"),
    }


def adjustment_quality_summary(frame: pd.DataFrame) -> dict:
    current = prepare_market_frame(frame)
    factor_coverage = float(current["adjust_factor"].notna().mean()) if len(current) else 0.0
    anomaly_symbols = sorted(
        current.loc[current["adjustment_anomaly"], "symbol"].astype(str).unique().tolist()
    )
    return {
        "price_mode": "unadjusted_execution_with_adjustment_metadata",
        "factor_coverage": round(factor_coverage, 4),
        "corporate_action_count": int(current["corporate_action"].sum()),
        "adjustment_anomaly_count": int(current["adjustment_anomaly"].sum()),
        "symbols_with_adjustment_anomalies": anomaly_symbols,
    }


def adjustment_quality_checks(dataset_id: str, frame: pd.DataFrame) -> list[dict]:
    current = prepare_market_frame(frame)
    checks = [
        {
            "dataset_id": dataset_id,
            "check_name": "adjustment_factor_coverage",
            "severity": "info",
            "message": "复权因子字段已标准化；缺失来源使用 1.0 作为不复权基准。",
            "details": {
                "factor_coverage": round(float(current["adjust_factor"].notna().mean()), 4),
                "price_mode": "撮合使用未复权 OHLC，复权字段仅用于质量校验与后续信号口径扩展。",
            },
        }
    ]
    corporate_action_count = int(current["corporate_action"].sum())
    checks.append(
        {
            "dataset_id": dataset_id,
            "check_name": "corporate_action_markers",
            "severity": "info",
            "message": f"识别到 {corporate_action_count} 条复权因子变化记录。",
            "details": {"corporate_action_count": corporate_action_count},
        }
    )
    anomalies = current[current["adjustment_anomaly"]]
    if anomalies.empty:
        checks.append(
            {
                "dataset_id": dataset_id,
                "check_name": "adjustment_continuity",
                "severity": "pass",
                "message": "复权连续性检查未发现异常跳变。",
                "details": {"adjustment_anomaly_count": 0},
            }
        )
    else:
        checks.append(
            {
                "dataset_id": dataset_id,
                "check_name": "adjustment_continuity",
                "severity": "warning",
                "message": f"复权连续性检查发现 {len(anomalies)} 条异常跳变。",
                "details": {
                    "adjustment_anomaly_count": int(len(anomalies)),
                    "symbols": sorted(anomalies["symbol"].astype(str).unique().tolist()),
                    "dates": anomalies["trade_date"].dt.strftime("%Y-%m-%d").head(20).tolist(),
                },
            }
        )
    return checks


def fetch_akshare_security_master(client=None) -> list[dict]:
    """Fetch A-share security master data from AkShare's exchange-level endpoints."""
    if client is None:
        import akshare as client

    records: dict[str, dict] = {}

    def put(record: dict) -> None:
        symbol = record["symbol"]
        records[symbol] = {**records.get(symbol, {}), **record}

    try:
        sh = client.stock_info_sh_name_code()
        for _, row in sh.iterrows():
            symbol = _market_symbol(row["证券代码"], "SH")
            put(
                {
                    "symbol": symbol,
                    "name": str(row["证券简称"]).strip(),
                    "exchange": "SH",
                    "board": infer_board(symbol),
                    "listed_date": _clean_date(row.get("上市日期")),
                    "delisted_date": None,
                    "status": "active",
                    "industry": None,
                    "total_share": None,
                    "float_share": None,
                    "source": "akshare_master",
                }
            )
    except Exception as error:
        raise DataSourceError(f"AkShare 沪市证券主数据获取失败: {error}") from error

    try:
        sz = client.stock_info_sz_name_code()
        for _, row in sz.iterrows():
            symbol = _market_symbol(row["A股代码"], "SZ")
            board = "创业板" if "创业" in str(row.get("板块", "")) else infer_board(symbol)
            put(
                {
                    "symbol": symbol,
                    "name": str(row["A股简称"]).strip(),
                    "exchange": "SZ",
                    "board": board,
                    "listed_date": _clean_date(row.get("A股上市日期")),
                    "delisted_date": None,
                    "status": "active",
                    "industry": str(row.get("所属行业", "")).strip() or None,
                    "total_share": _clean_number(row.get("A股总股本")),
                    "float_share": _clean_number(row.get("A股流通股本")),
                    "source": "akshare_master",
                }
            )
    except Exception as error:
        raise DataSourceError(f"AkShare 深市证券主数据获取失败: {error}") from error

    try:
        bj = client.stock_info_bj_name_code()
        for _, row in bj.iterrows():
            symbol = _market_symbol(row["证券代码"], "BJ")
            put(
                {
                    "symbol": symbol,
                    "name": str(row["证券简称"]).strip(),
                    "exchange": "BJ",
                    "board": "北交所",
                    "listed_date": _clean_date(row.get("上市日期")),
                    "delisted_date": None,
                    "status": "active",
                    "industry": str(row.get("所属行业", "")).strip() or None,
                    "total_share": _clean_number(row.get("总股本")),
                    "float_share": _clean_number(row.get("流通股本")),
                    "source": "akshare_master",
                }
            )
    except Exception as error:
        raise DataSourceError(f"AkShare 北交所证券主数据获取失败: {error}") from error

    try:
        sh_delist = client.stock_info_sh_delist()
        for _, row in sh_delist.iterrows():
            symbol = _market_symbol(row["公司代码"], "SH")
            put(
                {
                    "symbol": symbol,
                    "name": str(row["公司简称"]).strip(),
                    "exchange": "SH",
                    "board": infer_board(symbol),
                    "listed_date": _clean_date(row.get("上市日期")),
                    "delisted_date": _clean_date(row.get("暂停上市日期")),
                    "status": "delisted",
                    "source": "akshare_master",
                }
            )
    except Exception as error:
        raise DataSourceError(f"AkShare 沪市退市证券获取失败: {error}") from error

    try:
        sz_delist = client.stock_info_sz_delist()
        for _, row in sz_delist.iterrows():
            symbol = _market_symbol(row["证券代码"], "SZ")
            put(
                {
                    "symbol": symbol,
                    "name": str(row["证券简称"]).strip(),
                    "exchange": "SZ",
                    "board": infer_board(symbol),
                    "listed_date": _clean_date(row.get("上市日期")),
                    "delisted_date": _clean_date(row.get("终止上市日期")),
                    "status": "delisted",
                    "source": "akshare_master",
                }
            )
    except Exception as error:
        raise DataSourceError(f"AkShare 深市退市证券获取失败: {error}") from error

    return sorted(records.values(), key=lambda item: (item["exchange"], item["symbol"]))


def extract_security_master(frame: pd.DataFrame, source: str) -> list[dict]:
    current = prepare_market_frame(frame)
    records = []
    for symbol, group in current.groupby("symbol", sort=True):
        ordered = group.sort_values("trade_date")
        latest = ordered.iloc[-1]
        records.append(
            {
                "symbol": symbol,
                "name": str(latest.get("name", symbol)),
                "exchange": symbol.split(".")[-1],
                "board": infer_board(symbol),
                "listed_date": str(ordered["trade_date"].min().date()),
                "delisted_date": None,
                "status": "st" if is_st_name(latest.get("name", "")) else "active",
                "source": source,
            }
        )
    return records


def extract_security_daily_status(dataset_id: str, frame: pd.DataFrame, source: str) -> list[dict]:
    current = prepare_market_frame(frame)
    records = []
    for _, row in current.iterrows():
        records.append(
            {
                "dataset_id": dataset_id,
                "symbol": row["symbol"],
                "trade_date": str(row["trade_date"].date()),
                "name": str(row.get("name", row["symbol"])),
                "is_st": is_st_name(row.get("name", "")),
                "suspended": bool(row.get("suspended", False)),
                "limit_exempt": bool(row.get("limit_exempt", False)),
                "limit_reason": str(row.get("limit_reason", "")),
                "limit_up": float(row["limit_up"]),
                "limit_down": float(row["limit_down"]),
                "source": source,
            }
        )
    return records


def load_dataset_view(
    path: str | Path, symbols: list[str], start_date: str, end_date: str, benchmark: str
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame | None]:
    """Create a date- and symbol-scoped view over one immutable dataset snapshot."""
    frame = load_csv(path)
    requested = [normalize_symbol(symbol) for symbol in symbols]
    start, end = pd.Timestamp(start_date), pd.Timestamp(end_date)
    scoped = frame[(frame["trade_date"] >= start) & (frame["trade_date"] <= end)]
    available = set(scoped["symbol"])
    missing = sorted(set(requested) - available)
    if missing:
        raise ValueError(f"数据集在所选日期内缺少标的: {', '.join(missing)}")
    data = {
        symbol: scoped[scoped["symbol"] == symbol].copy().reset_index(drop=True)
        for symbol in requested
    }
    benchmark_symbol = normalize_symbol(benchmark)
    benchmark_frame = scoped[scoped["symbol"] == benchmark_symbol].copy().reset_index(drop=True)
    return data, benchmark_frame if not benchmark_frame.empty else None


def fetch_trading_calendar(start_date: str, end_date: str, client=None) -> pd.DataFrame:
    try:
        if client is None:
            import akshare as client
        calendar = client.tool_trade_date_hist_sina().copy()
        calendar["trade_date"] = pd.to_datetime(calendar["trade_date"])
        scoped = calendar[
            (calendar["trade_date"] >= pd.Timestamp(start_date))
            & (calendar["trade_date"] <= pd.Timestamp(end_date))
        ].sort_values("trade_date")
        if scoped.empty:
            raise DataSourceError("交易日历在所选区间内没有记录")
        return scoped.reset_index(drop=True)
    except DataSourceError:
        raise
    except Exception as error:
        raise DataSourceError(f"AkShare 交易日历获取失败: {error}") from error


def fetch_akshare_dataset(
    symbols: list[str], start_date: str, end_date: str, benchmark: str = "000300.SH", client=None
) -> pd.DataFrame:
    """Fetch unadjusted A-share/index bars and return one normalized immutable snapshot."""
    try:
        if client is None:
            import akshare as client
        compact_start = start_date.replace("-", "")
        compact_end = end_date.replace("-", "")
        frames: list[pd.DataFrame] = []
        for raw_symbol in symbols:
            symbol = normalize_symbol(raw_symbol)
            code = symbol.split(".")[0]
            fallback_name = SAMPLE_NAMES.get(symbol, symbol)
            try:
                source = client.stock_zh_a_hist(
                    symbol=code, period="daily", start_date=compact_start,
                    end_date=compact_end, adjust="", timeout=20,
                )
                source = source.rename(
                    columns={"日期": "trade_date", "股票代码": "raw_symbol", "名称": "name",
                             "股票简称": "name", "开盘": "open",
                             "收盘": "close", "最高": "high", "最低": "low", "成交量": "volume",
                             "成交额": "amount"}
                )
                if "volume" in source.columns:
                    source["volume"] = source["volume"] * 100
            except Exception:
                market_prefix = "sh" if symbol.endswith(".SH") else "sz"
                source = client.stock_zh_a_daily(
                    symbol=f"{market_prefix}{code}", start_date=compact_start,
                    end_date=compact_end, adjust="",
                ).rename(
                    columns={
                        "date": "trade_date", "open": "open", "high": "high", "low": "low",
                        "close": "close", "volume": "volume", "amount": "amount",
                        "name": "name", "名称": "name",
                    }
                )
            if source is None or source.empty:
                raise DataSourceError(f"AkShare 未返回 {symbol} 的行情")
            current = source.copy()
            current["symbol"] = symbol
            if "name" in current.columns:
                current["name"] = current["name"].replace("", np.nan).fillna(fallback_name)
            else:
                current["name"] = fallback_name
            frames.append(current)
        benchmark_symbol = normalize_symbol(benchmark)
        market_prefix = "sh" if benchmark_symbol.endswith(".SH") else "sz"
        try:
            index_source = client.stock_zh_index_daily_em(
                symbol=f"{market_prefix}{benchmark_symbol.split('.')[0]}",
                start_date=compact_start, end_date=compact_end,
            )
        except Exception:
            index_source = client.stock_zh_index_daily(
                symbol=f"{market_prefix}{benchmark_symbol.split('.')[0]}"
            )
            index_source["date"] = pd.to_datetime(index_source["date"])
            index_source = index_source[
                (index_source["date"] >= pd.Timestamp(start_date))
                & (index_source["date"] <= pd.Timestamp(end_date))
            ]
        if index_source is not None and not index_source.empty:
            current = index_source.rename(columns={"date": "trade_date"}).copy()
            current["symbol"] = benchmark_symbol
            current["name"] = "沪深300" if benchmark_symbol == "000300.SH" else benchmark_symbol
            frames.append(current)
        combined = prepare_market_frame(pd.concat(frames, ignore_index=True))
        calendar = fetch_trading_calendar(start_date, end_date, client=client)
        unexpected = set(combined["trade_date"].dt.normalize()) - set(calendar["trade_date"].dt.normalize())
        if unexpected:
            raise DataSourceError("行情包含交易日历之外的日期")
        return combined
    except (DataSourceError, ValueError):
        raise
    except Exception as error:
        raise DataSourceError(f"AkShare 行情获取失败: {error}") from error


def source_status() -> dict:
    try:
        import akshare
        return {
            "source": "AkShare + CSV + 演示数据", "available": True,
            "akshare_available": True, "akshare_version": akshare.__version__,
            "message": f"AkShare {akshare.__version__} 已安装，可同步真实沪深日线",
        }
    except ImportError:
        return {
            "source": "CSV + 演示数据", "available": True, "akshare_available": False,
            "akshare_version": None,
            "message": "未安装 AkShare，可使用 CSV 或可复现演示行情",
        }
