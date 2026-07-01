from __future__ import annotations

import argparse
import json
import logging
import math
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.data import DataSourceError, normalize_symbol, prepare_market_frame  # noqa: E402
from backend.providers import fetch_baostock_dataset, fetch_efinance_batch_dataset  # noqa: E402
from backend.repository import BacktestRepository  # noqa: E402


DEFAULT_START_DATE = "2018-01-01"
DEFAULT_END_DATE = "2026-07-02"
DEFAULT_BENCHMARKS = ("000300.SH",)
LOG_PATH = ROOT / "tmp" / "preset_backfill.log"
PROGRESS_PATH = ROOT / "tmp" / "preset_backfill_progress.json"

logger = logging.getLogger("preset_backfill")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill local preset daily bars for A-share backtests."
    )
    parser.add_argument("--db", default=str(ROOT / "data" / "quantlab.db"))
    parser.add_argument("--start", default=DEFAULT_START_DATE)
    parser.add_argument("--end", default=DEFAULT_END_DATE)
    parser.add_argument("--batch-size", type=int, default=60)
    parser.add_argument(
        "--exclude-bj",
        action="store_true",
        help="Exclude Beijing Stock Exchange symbols from the preset warehouse.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.2,
        help="Seconds to sleep between provider batches.",
    )
    parser.add_argument(
        "--provider",
        choices=["auto", "baostock"],
        default="auto",
        help="auto uses efinance first and BaoStock as fallback; baostock fills suspended zero-volume days.",
    )
    parser.add_argument(
        "--gap-window",
        choices=["full", "precise"],
        default="full",
        help="full fetches the whole target window for any incomplete symbol; precise fetches only missing edges.",
    )
    parser.add_argument(
        "--limit-symbols",
        type=int,
        default=0,
        help="Debug only: limit number of symbols to process.",
    )
    return parser.parse_args()


def setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
        ],
    )


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def format_date(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def next_day(value: str) -> str:
    return format_date(parse_date(value) + timedelta(days=1))


def prev_day(value: str) -> str:
    return format_date(parse_date(value) - timedelta(days=1))


def month_end(value: str) -> str:
    current = parse_date(value)
    if current.month == 12:
        return format_date(date(current.year, 12, 31))
    return format_date(date(current.year, current.month + 1, 1) - timedelta(days=1))


def load_securities(repo: BacktestRepository, include_bj: bool) -> dict[str, dict[str, Any]]:
    allowed_exchanges = {"SH", "SZ"} | ({"BJ"} if include_bj else set())
    securities = {
        item["symbol"]: item
        for item in repo.list_securities()
        if item.get("exchange") in allowed_exchanges and item.get("status") != "delisted"
    }
    for benchmark in DEFAULT_BENCHMARKS:
        securities.setdefault(
            benchmark,
            {
                "symbol": benchmark,
                "name": "沪深300",
                "exchange": "SH",
                "board": "benchmark",
                "listed_date": "2005-04-08",
                "status": "active",
            },
        )
    return dict(sorted(securities.items()))


def load_existing_ranges(db_path: Path, symbols: list[str]) -> dict[str, dict[str, Any]]:
    if not symbols:
        return {}
    ranges: dict[str, dict[str, Any]] = {}
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        for chunk_start in range(0, len(symbols), 800):
            chunk = symbols[chunk_start : chunk_start + 800]
            placeholders = ",".join("?" for _ in chunk)
            rows = connection.execute(
                f"""
                SELECT symbol, MIN(trade_date) AS first_date, MAX(trade_date) AS last_date, COUNT(*) AS row_count
                FROM market_daily_bars
                WHERE symbol IN ({placeholders})
                GROUP BY symbol
                """,
                chunk,
            ).fetchall()
            for row in rows:
                ranges[row["symbol"]] = {
                    "first_date": row["first_date"],
                    "last_date": row["last_date"],
                    "row_count": int(row["row_count"] or 0),
                }
    return ranges


def build_missing_ranges(
    securities: dict[str, dict[str, Any]],
    existing_ranges: dict[str, dict[str, Any]],
    target_start: str,
    target_end: str,
    *,
    full_window: bool = True,
) -> dict[tuple[str, str], list[str]]:
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    target_start_date = parse_date(target_start)
    target_end_date = parse_date(target_end)
    for symbol, security in securities.items():
        listed_raw = security.get("listed_date") or target_start
        try:
            listed_date = parse_date(str(listed_raw)[:10])
        except ValueError:
            listed_date = target_start_date
        if listed_date > target_end_date:
            continue
        effective_start = max(target_start_date, listed_date)
        fetch_start = target_start
        current = existing_ranges.get(symbol)
        if not current:
            grouped[(fetch_start, target_end)].append(symbol)
            continue
        first_date = current.get("first_date")
        last_date = current.get("last_date")
        first_ok = first_date and parse_date(first_date) <= effective_start + timedelta(days=10)
        last_ok = last_date and parse_date(last_date) >= target_end_date - timedelta(days=3)
        if full_window and (not first_ok or not last_ok):
            grouped[(fetch_start, target_end)].append(symbol)
            continue
        if not full_window and not first_ok and first_date:
            grouped[(fetch_start, month_end(prev_day(first_date)))].append(symbol)
        if not full_window and not last_ok and last_date:
            grouped[(next_day(last_date), target_end)].append(symbol)
    return {
        key: symbols
        for key, symbols in grouped.items()
        if parse_date(key[0]) <= parse_date(key[1]) and symbols
    }


def enrich_frame(frame: pd.DataFrame, securities: dict[str, dict[str, Any]]) -> pd.DataFrame:
    if frame.empty:
        return frame
    current = frame.copy()
    current["symbol"] = current["symbol"].map(normalize_symbol)
    current["name"] = current["symbol"].map(
        lambda symbol: securities.get(symbol, {}).get("name") or symbol
    )
    current["listed_date"] = current["symbol"].map(
        lambda symbol: securities.get(symbol, {}).get("listed_date")
    )
    return prepare_market_frame(current)


def warehouse_records_from_frame(frame: pd.DataFrame, source: str) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    current = prepare_market_frame(frame)
    records: list[dict[str, Any]] = []
    for _, row in current.iterrows():
        listed_date = row["listed_date"]
        records.append(
            {
                "symbol": row["symbol"],
                "trade_date": row["trade_date"].strftime("%Y-%m-%d"),
                "name": row["name"],
                "listed_date": (
                    listed_date.strftime("%Y-%m-%d") if pd.notna(listed_date) else None
                ),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "prev_close": float(row["prev_close"]),
                "volume": float(row["volume"]),
                "amount": float(row["amount"]),
                "limit_rate": float(row["limit_rate"]),
                "limit_up": float(row["limit_up"]),
                "limit_down": float(row["limit_down"]),
                "limit_exempt": bool(row["limit_exempt"]),
                "limit_reason": row.get("limit_reason", ""),
                "suspended": bool(row["suspended"]),
                "adjust_factor": float(row["adjust_factor"]),
                "adjusted_close": float(row["adjusted_close"]),
                "corporate_action": bool(row["corporate_action"]),
                "adjustment_anomaly": bool(row["adjustment_anomaly"]),
                "source": source,
            }
        )
    return records


def fetch_batch_with_fallback(
    batch: list[str],
    range_start: str,
    range_end: str,
    securities: dict[str, dict[str, Any]],
    provider: str,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    frames: list[pd.DataFrame] = []
    failures: list[dict[str, Any]] = []
    remaining = list(batch)
    if provider == "auto":
        try:
            efinance_frame = fetch_efinance_batch_dataset(remaining, range_start, range_end)
            efinance_frame = enrich_frame(efinance_frame, securities)
            if not efinance_frame.empty:
                frames.append(efinance_frame.assign(_provider_source="efinance_preset"))
            fetched = set(efinance_frame["symbol"].astype(str).map(normalize_symbol).unique())
            remaining = [symbol for symbol in remaining if symbol not in fetched]
        except Exception as error:
            logger.warning(
                "efinance_batch_failed range=%s..%s symbols=%s error=%s",
                range_start,
                range_end,
                len(batch),
                error,
            )

    baostock_symbols = [symbol for symbol in remaining if not symbol.endswith(".BJ")]
    if baostock_symbols:
        try:
            baostock_frame = fetch_baostock_dataset(baostock_symbols, range_start, range_end)
            baostock_frame = enrich_frame(baostock_frame, securities)
            if not baostock_frame.empty:
                frames.append(baostock_frame.assign(_provider_source="baostock_preset"))
            fetched = set(baostock_frame["symbol"].astype(str).map(normalize_symbol).unique())
            remaining = [symbol for symbol in remaining if symbol not in fetched]
        except Exception as error:
            logger.warning(
                "baostock_batch_failed range=%s..%s symbols=%s error=%s",
                range_start,
                range_end,
                len(baostock_symbols),
                error,
            )

    for symbol in remaining:
        failures.append(
            {
                "symbol": symbol,
                "range_start": range_start,
                "range_end": range_end,
                "reason": "free_providers_returned_no_rows",
            }
        )
    if not frames:
        return pd.DataFrame(), failures
    merged = (
        pd.concat(frames, ignore_index=True)
        .sort_values(["symbol", "trade_date"])
        .drop_duplicates(["symbol", "trade_date"], keep="first")
        .reset_index(drop=True)
    )
    return prepare_market_frame(merged), failures


def discover_latest_available_end(requested_end: str) -> str:
    probe_end = parse_date(requested_end)
    probe_start = format_date(probe_end - timedelta(days=14))
    for fetcher in (fetch_efinance_batch_dataset, fetch_baostock_dataset):
        try:
            frame = fetcher(["000001.SZ"], probe_start, requested_end)
        except Exception as error:
            logger.warning("latest_end_probe_failed provider=%s error=%s", fetcher.__name__, error)
            continue
        if not frame.empty:
            latest = frame["trade_date"].max()
            if pd.notna(latest):
                return latest.strftime("%Y-%m-%d")
    return requested_end


def write_progress(payload: dict[str, Any]) -> None:
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def verify_coverage(
    db_path: Path,
    securities: dict[str, dict[str, Any]],
    target_start: str,
    target_end: str,
) -> dict[str, Any]:
    symbols = list(securities)
    ranges = load_existing_ranges(db_path, symbols)
    missing: list[dict[str, Any]] = []
    target_start_date = parse_date(target_start)
    target_end_date = parse_date(target_end)
    for symbol in symbols:
        security = securities[symbol]
        listed_raw = security.get("listed_date") or target_start
        try:
            listed_date = parse_date(str(listed_raw)[:10])
        except ValueError:
            listed_date = target_start_date
        effective_start = max(target_start_date, listed_date)
        if effective_start > target_end_date:
            continue
        row = ranges.get(symbol)
        if not row:
            missing.append({"symbol": symbol, "reason": "no_rows"})
            continue
        first_ok = parse_date(row["first_date"]) <= effective_start + timedelta(days=10)
        last_ok = parse_date(row["last_date"]) >= target_end_date - timedelta(days=10)
        if not first_ok or not last_ok:
            missing.append(
                {
                    "symbol": symbol,
                    "first_date": row["first_date"],
                    "last_date": row["last_date"],
                    "listed_date": security.get("listed_date"),
                }
            )
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        summary = dict(
            connection.execute(
                """
                SELECT COUNT(*) AS row_count, COUNT(DISTINCT symbol) AS symbol_count,
                       MIN(trade_date) AS start_date, MAX(trade_date) AS end_date
                FROM market_daily_bars
                """
            ).fetchone()
        )
    return {
        "summary": {
            "row_count": int(summary["row_count"] or 0),
            "symbol_count": int(summary["symbol_count"] or 0),
            "start_date": summary["start_date"],
            "end_date": summary["end_date"],
        },
        "target_symbol_count": len(symbols),
        "covered_symbol_count": len(symbols) - len(missing),
        "missing_symbol_count": len(missing),
        "missing_preview": missing[:50],
    }


def repair_placeholder_listed_dates(db_path: Path) -> int:
    """Replace known placeholder listing dates with the first local trading date.

    Some free security-master endpoints return 1990-12-19 for STAR Market securities
    instead of the real listing date. The local warehouse already contains the true
    first tradable date, so use it to keep coverage checks and UI classification sane.
    """

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT s.symbol, MIN(m.trade_date) AS first_date
            FROM securities s
            JOIN market_daily_bars m ON m.symbol = s.symbol
            WHERE s.status != 'delisted'
              AND s.exchange = 'SH'
              AND s.symbol LIKE '68%'
              AND s.listed_date IN ('1990-12-19', '1990-12-01', '')
            GROUP BY s.symbol
            """
        ).fetchall()
        updates = [(row[1], row[0]) for row in rows if row[1]]
        if updates:
            connection.executemany(
                """
                UPDATE securities
                SET listed_date = ?, source = source || '+listed_date_repaired', updated_at = ?
                WHERE symbol = ?
                """,
                [(first_date, datetime.now().isoformat(timespec="seconds"), symbol) for first_date, symbol in updates],
            )
    return len(updates)


def run_backfill(args: argparse.Namespace) -> dict[str, Any]:
    db_path = Path(args.db).resolve()
    repo = BacktestRepository(db_path)
    securities = load_securities(repo, include_bj=not args.exclude_bj)
    if args.limit_symbols:
        securities = dict(list(securities.items())[: args.limit_symbols])
    symbols = list(securities)
    existing_ranges = load_existing_ranges(db_path, symbols)
    effective_end = discover_latest_available_end(args.end)
    if effective_end != args.end:
        logger.info(
            "requested_end_not_available requested=%s effective_latest_trading_day=%s",
            args.end,
            effective_end,
        )
    missing_groups = build_missing_ranges(
        securities,
        existing_ranges,
        args.start,
        effective_end,
        full_window=args.gap_window == "full",
    )
    total_symbols = sum(len(items) for items in missing_groups.values())
    total_batches = sum(math.ceil(len(items) / args.batch_size) for items in missing_groups.values())
    logger.info(
        "backfill_plan db=%s target=%s..%s securities=%s range_groups=%s symbol_ranges=%s batches=%s",
        db_path,
        args.start,
        effective_end,
        len(securities),
        len(missing_groups),
        total_symbols,
        total_batches,
    )
    completed_batches = 0
    inserted_rows = 0
    failed: list[dict[str, Any]] = []
    started_at = datetime.now().isoformat(timespec="seconds")

    for (range_start, range_end), range_symbols in sorted(missing_groups.items()):
        for offset in range(0, len(range_symbols), args.batch_size):
            batch = range_symbols[offset : offset + args.batch_size]
            completed_batches += 1
            logger.info(
                "fetch_batch %s/%s range=%s..%s symbols=%s first=%s",
                completed_batches,
                total_batches,
                range_start,
                range_end,
                len(batch),
                batch[0] if batch else "",
            )
            try:
                frame, batch_failures = fetch_batch_with_fallback(
                    batch,
                    range_start,
                    range_end,
                    securities,
                    args.provider,
                )
                records = warehouse_records_from_frame(frame, "free_preset")
                repo.upsert_market_daily_bars(records)
                inserted_rows += len(records)
                fetched_symbols = (
                    set(frame["symbol"].astype(str).map(normalize_symbol).unique())
                    if "symbol" in frame.columns
                    else set()
                )
                failed.extend(batch_failures)
                logger.info(
                    "stored_batch rows=%s fetched_symbols=%s missing_symbols=%s total_inserted_rows=%s",
                    len(records),
                    len(fetched_symbols),
                    len(batch_failures),
                    inserted_rows,
                )
            except Exception as error:
                logger.warning(
                    "batch_failed range=%s..%s symbols=%s error=%s",
                    range_start,
                    range_end,
                    ",".join(batch[:10]),
                    error,
                )
                for symbol in batch:
                    failed.append(
                        {
                            "symbol": symbol,
                            "range_start": range_start,
                            "range_end": range_end,
                            "reason": str(error),
                        }
                    )
            write_progress(
                {
                    "status": "running",
                    "started_at": started_at,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "target_start": args.start,
                    "target_end": effective_end,
                    "requested_end": args.end,
                    "completed_batches": completed_batches,
                    "total_batches": total_batches,
                    "inserted_rows": inserted_rows,
                    "failed_count": len(failed),
                    "failed_preview": failed[:50],
                }
            )
            if args.sleep > 0:
                time.sleep(args.sleep)

    repaired_listed_dates = repair_placeholder_listed_dates(db_path)
    if repaired_listed_dates:
        logger.info("repaired_placeholder_listed_dates count=%s", repaired_listed_dates)
        securities = load_securities(repo, include_bj=not args.exclude_bj)
    verification = verify_coverage(db_path, securities, args.start, effective_end)
    result = {
        "status": "completed",
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "target_start": args.start,
        "target_end": effective_end,
        "requested_end": args.end,
        "inserted_rows": inserted_rows,
        "failed_count": len(failed),
        "failed_preview": failed[:100],
        "repaired_listed_dates": repaired_listed_dates,
        "verification": verification,
        "log_path": str(LOG_PATH),
        "db_path": str(db_path),
    }
    write_progress(result)
    return result


def main() -> int:
    setup_logging()
    args = parse_args()
    try:
        result = run_backfill(args)
    except (DataSourceError, sqlite3.DatabaseError, OSError, ValueError) as error:
        logger.exception("preset_backfill_failed error=%s", error)
        write_progress(
            {
                "status": "failed",
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "target_start": args.start,
                "target_end": args.end,
                "error": str(error),
                "log_path": str(LOG_PATH),
            }
        )
        return 1
    logger.info("preset_backfill_completed %s", json.dumps(result, ensure_ascii=False))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
