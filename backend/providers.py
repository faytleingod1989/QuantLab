from __future__ import annotations

import logging
from importlib.util import find_spec
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import pandas as pd

from .data import DataSourceError, fetch_akshare_dataset, normalize_symbol, prepare_market_frame


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderFetchStat:
    provider: str
    requested_symbols: int
    fetched_symbols: int
    failed_symbols: int
    message: str = ""
    requested_symbol_list: tuple[str, ...] = ()
    fetched_symbol_list: tuple[str, ...] = ()
    failed_symbol_list: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "requested_symbols": self.requested_symbols,
            "fetched_symbols": self.fetched_symbols,
            "failed_symbols": self.failed_symbols,
            "message": self.message,
            "requested_symbol_list": list(self.requested_symbol_list),
            "fetched_symbol_list": list(self.fetched_symbol_list),
            "failed_symbol_list": list(self.failed_symbol_list),
        }


ProviderFetcher = Callable[[list[str], str, str], pd.DataFrame]


def free_provider_status() -> dict:
    """Report optional free quote providers without importing them at module load time."""

    return {
        "efinance": _module_available("efinance"),
        "baostock": _module_available("baostock"),
        "akshare": _module_available("akshare"),
        "priority": ["local_warehouse", "efinance", "baostock", "akshare"],
    }


def fetch_free_daily_dataset(
    symbols: list[str],
    start_date: str,
    end_date: str,
    benchmark: str = "000300.SH",
    provider_order: Iterable[str] = ("efinance", "baostock", "akshare"),
) -> tuple[pd.DataFrame, list[dict]]:
    """Fetch daily A-share bars through free providers with progressive fallback.

    The caller is expected to load and merge the local warehouse first. This function
    only fills missing symbols and tries providers in order. A provider may partially
    succeed; the next provider only receives symbols that are still missing.
    """

    requested_symbols = _normalize_symbols(symbols)
    benchmark_symbol = normalize_symbol(benchmark) if benchmark else None
    remaining = list(dict.fromkeys([*requested_symbols, *([benchmark_symbol] if benchmark_symbol else [])]))
    frames: list[pd.DataFrame] = []
    stats: list[ProviderFetchStat] = []

    for provider_name in provider_order:
        if not remaining:
            break
        fetcher = _provider_fetcher(provider_name)
        requested_before = tuple(remaining)
        requested_count = len(requested_before)
        try:
            frame = fetcher(remaining, start_date, end_date)
            frame = prepare_market_frame(frame)
            fetched_symbols = set(frame["symbol"].astype(str).map(normalize_symbol).unique())
            newly_fetched = fetched_symbols.intersection(remaining)
            if newly_fetched:
                frames.append(frame)
            remaining = [symbol for symbol in remaining if symbol not in newly_fetched]
            failed_after = tuple(symbol for symbol in requested_before if symbol not in newly_fetched)
            stats.append(
                ProviderFetchStat(
                    provider=provider_name,
                    requested_symbols=requested_count,
                    fetched_symbols=len(newly_fetched),
                    failed_symbols=len(failed_after),
                    message="ok" if newly_fetched else "未返回可覆盖的新标的",
                    requested_symbol_list=requested_before,
                    fetched_symbol_list=tuple(sorted(newly_fetched)),
                    failed_symbol_list=failed_after,
                )
            )
        except Exception as error:
            logger.warning("free_provider_fetch_failed provider=%s error=%s", provider_name, error)
            stats.append(
                ProviderFetchStat(
                    provider=provider_name,
                    requested_symbols=requested_count,
                    fetched_symbols=0,
                    failed_symbols=requested_count,
                    message=str(error),
                    requested_symbol_list=requested_before,
                    failed_symbol_list=requested_before,
                )
            )

    if not frames:
        messages = "；".join(f"{item.provider}: {item.message}" for item in stats)
        raise DataSourceError(f"免费行情源未能提供可用行情：{messages or '没有可用 provider'}")

    merged = _merge_frames(frames)
    covered = set(merged["symbol"].astype(str).map(normalize_symbol).unique())
    missing_requested = sorted(set(requested_symbols) - covered)
    if missing_requested:
        logger.warning("free_provider_symbols_missing symbols=%s", ",".join(missing_requested[:20]))
    return prepare_market_frame(merged), [item.as_dict() for item in stats]


def fetch_efinance_dataset(symbols: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    try:
        import efinance as ef
    except Exception as error:  # pragma: no cover - depends on optional runtime package
        raise DataSourceError("未安装 efinance，请先运行 backend 依赖安装") from error

    compact_start = start_date.replace("-", "")
    compact_end = end_date.replace("-", "")
    frames: list[pd.DataFrame] = []
    failed: list[str] = []

    for raw_symbol in _normalize_symbols(symbols):
        try:
            source = ef.stock.get_quote_history(
                _to_efinance_code(raw_symbol),
                beg=compact_start,
                end=compact_end,
                klt=101,
                fqt=0,
            )
            frame = _normalize_efinance_frame(source, raw_symbol)
        except Exception as error:  # pragma: no cover - network/provider specific
            logger.warning("efinance_symbol_fetch_failed symbol=%s error=%s", raw_symbol, error)
            failed.append(raw_symbol)
            continue
        if frame.empty:
            failed.append(raw_symbol)
            continue
        frames.append(frame)

    if not frames:
        raise DataSourceError(f"efinance 未返回可用行情，失败标的 {len(failed)} 只")
    return prepare_market_frame(pd.concat(frames, ignore_index=True))


def fetch_baostock_dataset(symbols: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    try:
        import baostock as bs
    except Exception as error:  # pragma: no cover - depends on optional runtime package
        raise DataSourceError("未安装 BaoStock，请先运行 backend 依赖安装") from error

    login = bs.login()
    if getattr(login, "error_code", "0") != "0":
        raise DataSourceError(f"BaoStock 登录失败：{getattr(login, 'error_msg', '')}")

    fields = "date,code,open,high,low,close,preclose,volume,amount"
    frames: list[pd.DataFrame] = []
    failed: list[str] = []
    try:
        for raw_symbol in _normalize_symbols(symbols):
            try:
                result = bs.query_history_k_data_plus(
                    _to_baostock_code(raw_symbol),
                    fields,
                    start_date=start_date,
                    end_date=end_date,
                    frequency="d",
                    adjustflag="3",
                )
                if getattr(result, "error_code", "0") != "0":
                    raise DataSourceError(getattr(result, "error_msg", "BaoStock 查询失败"))
                rows: list[list[str]] = []
                while result.next():
                    rows.append(result.get_row_data())
                source = pd.DataFrame(rows, columns=result.fields)
                frame = _normalize_baostock_frame(source, raw_symbol)
            except Exception as error:  # pragma: no cover - network/provider specific
                logger.warning("baostock_symbol_fetch_failed symbol=%s error=%s", raw_symbol, error)
                failed.append(raw_symbol)
                continue
            if frame.empty:
                failed.append(raw_symbol)
                continue
            frames.append(frame)
    finally:
        try:
            bs.logout()
        except Exception:  # pragma: no cover - best effort cleanup
            logger.warning("baostock_logout_failed")

    if not frames:
        raise DataSourceError(f"BaoStock 未返回可用行情，失败标的 {len(failed)} 只")
    return prepare_market_frame(pd.concat(frames, ignore_index=True))


def fetch_akshare_free_dataset(symbols: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    normalized = _normalize_symbols(symbols)
    benchmark = "000300.SH"
    stock_symbols = [symbol for symbol in normalized if symbol != benchmark]
    return fetch_akshare_dataset(stock_symbols, start_date, end_date, benchmark)


def _provider_fetcher(provider_name: str) -> ProviderFetcher:
    providers: dict[str, ProviderFetcher] = {
        "efinance": fetch_efinance_dataset,
        "baostock": fetch_baostock_dataset,
        "akshare": fetch_akshare_free_dataset,
    }
    if provider_name not in providers:
        raise DataSourceError(f"未知行情源：{provider_name}")
    return providers[provider_name]


def _module_available(module_name: str) -> bool:
    return find_spec(module_name) is not None


def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(normalize_symbol(symbol) for symbol in symbols if str(symbol).strip()))


def _to_efinance_code(symbol: str) -> str:
    return normalize_symbol(symbol).split(".")[0]


def _to_baostock_code(symbol: str) -> str:
    normalized = normalize_symbol(symbol)
    code, suffix = normalized.split(".")
    if suffix not in {"SH", "SZ"}:
        raise DataSourceError(f"BaoStock 暂不支持该市场标的：{normalized}")
    return f"{suffix.lower()}.{code}"


def _normalize_efinance_frame(source: pd.DataFrame | None, symbol: str) -> pd.DataFrame:
    if source is None or source.empty:
        return pd.DataFrame()
    normalized = normalize_symbol(symbol)
    column_map = {
        "日期": "trade_date",
        "股票名称": "name",
        "股票代码": "raw_symbol",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
        "成交额": "amount",
    }
    frame = source.rename(columns=column_map).copy()
    required = ["trade_date", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise DataSourceError(f"efinance 返回字段不完整：{', '.join(missing)}")
    frame["symbol"] = normalized
    if "name" not in frame.columns:
        frame["name"] = normalized
    return frame[[
        column for column in ["trade_date", "symbol", "name", "open", "high", "low", "close", "volume", "amount"]
        if column in frame.columns
    ]]


def _normalize_baostock_frame(source: pd.DataFrame | None, symbol: str) -> pd.DataFrame:
    if source is None or source.empty:
        return pd.DataFrame()
    normalized = normalize_symbol(symbol)
    frame = source.rename(columns={"date": "trade_date", "preclose": "prev_close"}).copy()
    required = ["trade_date", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise DataSourceError(f"BaoStock 返回字段不完整：{', '.join(missing)}")
    frame["symbol"] = normalized
    frame["name"] = normalized
    return frame[[
        column
        for column in [
            "trade_date", "symbol", "name", "open", "high", "low", "close", "prev_close", "volume", "amount"
        ]
        if column in frame.columns
    ]]


def _merge_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames, ignore_index=True)
    merged["trade_date"] = pd.to_datetime(merged["trade_date"], errors="coerce")
    merged["symbol"] = merged["symbol"].map(normalize_symbol)
    return (
        merged.sort_values(["symbol", "trade_date"])
        .drop_duplicates(["symbol", "trade_date"], keep="last")
        .reset_index(drop=True)
    )
