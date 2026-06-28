from __future__ import annotations

import logging
import os
import hashlib
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pandas as pd
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from .data import (
    SAMPLE_NAMES,
    DataSourceError,
    adjustment_quality_checks,
    dataset_summary,
    extract_security_daily_status,
    extract_security_master,
    fetch_akshare_dataset,
    fetch_akshare_security_master,
    fetch_trading_calendar,
    filter_to_trading_calendar,
    infer_board,
    load_csv,
    load_csv_text,
    load_dataset_view,
    load_industry_history_csv_text,
    normalize_symbol,
    prepare_market_frame,
    sample_daily,
    source_status,
)
from .engine import run_backtest
from .models import (
    BacktestRequest,
    AkshareAllDatasetRequest,
    AkshareDatasetRequest,
    CsvDatasetRequest,
    IndustryHistoryCsvRequest,
    ProjectCreate,
    StrategyCreate,
    StrategyVersionCreate,
    VisualStrategy,
)
from .repository import BacktestRepository
from .reports import (
    paginate_trades,
    render_html_report,
    render_markdown_report,
    render_pdf_report,
    summarize_run_comparison,
)
from .tasks import BacktestTaskManager


logging.basicConfig(
    level=os.getenv("QUANTLAB_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("quantlab.api")

database_path = Path(
    os.getenv(
        "QUANTLAB_DB_PATH",
        str(Path(__file__).resolve().parent.parent / "data" / "quantlab.db"),
    )
)
repository = BacktestRepository(database_path)
repository.mark_interrupted_runs()
repository.ensure_default_project()
repository.upsert_securities(
    [
        {
            "symbol": symbol,
            "name": name,
            "exchange": symbol.split(".")[-1],
            "board": infer_board(symbol),
            "listed_date": "1990-12-19",
            "delisted_date": None,
            "status": "active",
            "source": "demo",
            "industry": None,
            "total_share": None,
            "float_share": None,
        }
        for symbol, name in SAMPLE_NAMES.items()
    ]
)
task_manager = BacktestTaskManager(
    repository, max_workers=int(os.getenv("QUANTLAB_BACKTEST_WORKERS", "2"))
)
MIN_ALL_MARKET_SYNC_COVERAGE = 0.8
ALL_MARKET_SYNC_BATCH_SIZE = int(os.getenv("QUANTLAB_ALL_MARKET_BATCH_SIZE", "200"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    await run_in_threadpool(_backfill_market_warehouse_from_datasets)
    yield
    task_manager.shutdown()


app = FastAPI(title="QuantLab A 股回测 API", version="0.4.0", lifespan=lifespan)
allowed_origins = [
    item.strip()
    for item in os.getenv(
        "QUANTLAB_CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    ).split(",")
    if item.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "frequency": "日线", "minute_extension": "reserved"}


@app.get("/api/data/status")
def data_status() -> dict:
    status = source_status()
    warehouse = repository.market_daily_bar_summary()
    status["warehouse"] = warehouse
    if warehouse["row_count"]:
        status["message"] = (
            f"{status['message']}；本地日线仓库已有 {warehouse['symbol_count']} 标的、"
            f"{warehouse['row_count']} 行"
        )
    return status


@app.get("/api/securities")
def securities(include_inactive: bool = False) -> list[dict]:
    records = repository.list_securities(include_inactive=include_inactive)
    if records:
        return records
    return [
        {
            "symbol": symbol, "name": name, "exchange": symbol.split(".")[-1],
            "board": infer_board(symbol), "listed_date": "1990-12-19",
            "delisted_date": None, "status": "active", "source": "demo",
            "industry": None, "total_share": None, "float_share": None,
        }
        for symbol, name in SAMPLE_NAMES.items()
    ]


@app.post("/api/securities/sync/akshare", status_code=202)
async def sync_security_master() -> dict:
    try:
        records = await run_in_threadpool(fetch_akshare_security_master)
    except DataSourceError as error:
        logger.warning("security_master_sync_failed error=%s", error)
        raise HTTPException(status_code=502, detail=str(error)) from error
    await run_in_threadpool(repository.upsert_securities, records)
    await run_in_threadpool(repository.upsert_industry_history, records)
    status_counts: dict[str, int] = {}
    exchange_counts: dict[str, int] = {}
    for record in records:
        status_counts[record["status"]] = status_counts.get(record["status"], 0) + 1
        exchange_counts[record["exchange"]] = exchange_counts.get(record["exchange"], 0) + 1
    return {
        "source": "akshare_master",
        "count": len(records),
        "status_counts": status_counts,
        "exchange_counts": exchange_counts,
    }


@app.post("/api/securities/industry-history/csv", status_code=201)
def import_industry_history_csv(payload: IndustryHistoryCsvRequest) -> dict:
    try:
        records = load_industry_history_csv_text(payload.csv_text)
    except (ValueError, UnicodeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    security_master = _missing_security_master_from_industry_history(records)
    repository.upsert_securities(security_master)
    repository.upsert_industry_history(records)
    return {
        "source": "industry_history_csv",
        "count": len(records),
        "security_count": len(security_master),
    }


def _missing_security_master_from_industry_history(records: list[dict]) -> list[dict]:
    missing_by_symbol = {}
    for record in records:
        symbol = record["symbol"]
        if symbol in missing_by_symbol or repository.get_security(symbol):
            continue
        missing_by_symbol[symbol] = {
            "symbol": symbol,
            "name": symbol,
            "exchange": symbol.split(".")[-1],
            "board": record.get("board") or infer_board(symbol),
            "listed_date": record.get("valid_from") or "1990-12-19",
            "delisted_date": None,
            "status": "active",
            "industry": record.get("industry"),
            "source": "industry_history_csv",
        }
    return list(missing_by_symbol.values())


@app.get("/api/securities/{symbol}/status")
def security_status(symbol: str, start_date: str | None = None, end_date: str | None = None) -> dict:
    try:
        normalized = normalize_symbol(symbol)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    security = repository.get_security(normalized)
    if not security:
        raise HTTPException(status_code=404, detail="证券主数据不存在")
    return {
        "security": security,
        "daily_status": repository.list_security_daily_status(normalized, start_date, end_date),
        "industry_history": repository.list_industry_history(normalized),
    }


@app.post("/api/backtests/run")
def backtest(request: BacktestRequest) -> dict:
    task_id = uuid4().hex
    unsupported = [symbol for symbol in request.symbols if symbol not in SAMPLE_NAMES]
    if unsupported:
        raise HTTPException(status_code=400, detail=f"演示数据暂不包含: {', '.join(unsupported)}")
    data = {symbol: sample_daily(symbol) for symbol in request.symbols}
    benchmark_data = sample_daily(request.benchmark)
    logger.info(
        "backtest_started task_id=%s strategy=%s symbols=%s period=%s..%s",
        task_id,
        request.strategy.name,
        ",".join(request.symbols),
        request.start_date,
        request.end_date,
    )
    try:
        result = run_backtest(data, request, benchmark_data, benchmark_is_demo=True)
        result["task_id"] = task_id
        logger.info(
            "backtest_completed task_id=%s trades=%s",
            task_id,
            result["metrics"]["trade_count"],
        )
        return result
    except (ValueError, IndexError) as error:
        logger.warning("backtest_rejected task_id=%s error=%s", task_id, error)
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("backtest_failed task_id=%s", task_id)
        raise HTTPException(status_code=500, detail=f"回测失败，任务编号: {task_id}") from error


def _validate_demo_symbols(request: BacktestRequest) -> None:
    unsupported = [symbol for symbol in request.symbols if symbol not in SAMPLE_NAMES]
    if unsupported:
        count = len(unsupported)
        sample = ", ".join(unsupported[:5])
        raise HTTPException(
            status_code=400,
            detail=f"演示数据仅支持 5 只预设股票（如 600519.SH），当前 {len(request.symbols)} 只中的 {count} 只无对应数据"
            if count > 5
            else f"演示数据暂不包含: {sample}",
        )


@app.post("/api/backtests", status_code=202)
def create_backtest(request: BacktestRequest) -> dict:
    if request.strategy_version_id:
        version = repository.get_strategy_version(request.strategy_version_id)
        if not version:
            raise HTTPException(status_code=400, detail="策略版本不存在")
        strategy = repository.get_strategy(version["strategy_id"])
        request.strategy_id = version["strategy_id"]
        request.project_id = strategy["project_id"]
        request.strategy = VisualStrategy.model_validate(version["definition"])
    if request.dataset_id:
        dataset = repository.get_dataset(request.dataset_id)
        if not dataset:
            raise HTTPException(status_code=400, detail="数据集不存在")
        request.dataset_fingerprint = dataset["fingerprint"]
        try:
            load_dataset_view(
                dataset["path"], request.symbols, request.start_date,
                request.end_date, request.benchmark,
            )
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    else:
        _validate_demo_symbols(request)
    try:
        lifecycle_symbols = [normalize_symbol(symbol) for symbol in request.symbols]
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    lifecycle_errors = repository.validate_security_window(
        lifecycle_symbols, request.start_date, request.end_date
    )
    if lifecycle_errors:
        raise HTTPException(status_code=400, detail="；".join(lifecycle_errors))
    return task_manager.submit(request)


@app.get("/api/backtests")
def list_backtests(limit: int = 50) -> list[dict]:
    return repository.list_runs(limit=max(1, min(limit, 200)))


@app.get("/api/backtests/compare")
def compare_backtests(limit: int = 6) -> list[dict]:
    records = repository.list_completed_runs_with_results(limit=max(1, min(limit, 20)))
    return summarize_run_comparison(records)


@app.get("/api/backtests/{run_id}")
def get_backtest(run_id: str) -> dict:
    record = repository.get_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="回测任务不存在")
    return record


@app.get("/api/backtests/{run_id}/result")
def get_backtest_result(run_id: str) -> dict:
    record = repository.get_run(run_id, include_result=True)
    if not record:
        raise HTTPException(status_code=404, detail="回测任务不存在")
    if record["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"任务尚未完成，当前状态: {record['status']}")
    return record["result"]


@app.get("/api/backtests/{run_id}/trades")
def get_backtest_trades(run_id: str, limit: int = 50, offset: int = 0, side: str | None = None) -> dict:
    record = repository.get_run(run_id, include_result=True)
    if not record:
        raise HTTPException(status_code=404, detail="回测任务不存在")
    if record["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"任务尚未完成，当前状态: {record['status']}")
    return paginate_trades(record["result"], limit=limit, offset=offset, side=side)


@app.get("/api/backtests/{run_id}/report.md")
def get_backtest_report(run_id: str) -> Response:
    record = repository.get_run(run_id, include_result=True)
    if not record:
        raise HTTPException(status_code=404, detail="回测任务不存在")
    if record["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"任务尚未完成，当前状态: {record['status']}")
    return Response(
        content=render_markdown_report(record),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="quantlab-{run_id}.md"',
        },
    )


@app.get("/api/backtests/{run_id}/report.html")
def get_backtest_html_report(run_id: str) -> Response:
    record = repository.get_run(run_id, include_result=True)
    if not record:
        raise HTTPException(status_code=404, detail="回测任务不存在")
    if record["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"任务尚未完成，当前状态: {record['status']}")
    return Response(
        content=render_html_report(record),
        media_type="text/html; charset=utf-8",
    )


@app.get("/api/backtests/{run_id}/report.pdf")
def get_backtest_pdf_report(run_id: str) -> Response:
    record = repository.get_run(run_id, include_result=True)
    if not record:
        raise HTTPException(status_code=404, detail="回测任务不存在")
    if record["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"任务尚未完成，当前状态: {record['status']}")
    return Response(
        content=render_pdf_report(record),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="quantlab-{run_id}.pdf"',
        },
    )


@app.post("/api/backtests/{run_id}/cancel", status_code=202)
def cancel_backtest(run_id: str) -> dict:
    record = repository.get_run(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="回测任务不存在")
    if record["status"] not in {"queued", "running"}:
        raise HTTPException(status_code=409, detail=f"任务无法取消，当前状态: {record['status']}")
    task_manager.cancel(run_id)
    return {"id": run_id, "cancel_requested": True}


@app.get("/api/datasets")
def list_datasets() -> list[dict]:
    return repository.list_datasets()


def _active_sh_sz_symbols() -> list[str]:
    records = repository.list_securities(include_inactive=True)
    if len(records) < 100:
        records = fetch_akshare_security_master()
        repository.upsert_securities(records)
        repository.upsert_industry_history(records)
    symbols = [
        record["symbol"]
        for record in records
        if record.get("exchange") in {"SH", "SZ"}
        and record.get("status", "active") != "delisted"
    ]
    return sorted(set(symbols))


def _ensure_all_market_sync_coverage(frame, requested_symbols: list[str], benchmark: str) -> int:
    requested = {normalize_symbol(symbol) for symbol in requested_symbols}
    benchmark_symbol = normalize_symbol(benchmark)
    synced = {normalize_symbol(symbol) for symbol in frame["symbol"].dropna().unique()}
    actual = len((synced - {benchmark_symbol}) & requested)
    expected = len(requested)
    if expected and actual / expected < MIN_ALL_MARKET_SYNC_COVERAGE:
        raise HTTPException(
            status_code=502,
            detail=(
                f"全A行情同步覆盖不足：请求 {expected} 只，成功获取 {actual} 只，"
                f"低于 {int(MIN_ALL_MARKET_SYNC_COVERAGE * 100)}% 保存门槛。"
                " 通常是 AkShare/网络限流或中途中断导致；本次快照未保存，请稍后重试。"
            ),
        )
    return actual


def _all_market_coverage(frame, requested_symbols: list[str], benchmark: str) -> dict:
    requested = {normalize_symbol(symbol) for symbol in requested_symbols}
    benchmark_symbol = normalize_symbol(benchmark)
    synced = {normalize_symbol(symbol) for symbol in frame["symbol"].dropna().unique()}
    covered = sorted((synced - {benchmark_symbol}) & requested)
    expected = len(requested)
    return {
        "expected": expected,
        "covered": len(covered),
        "missing": max(0, expected - len(covered)),
        "coverage": (len(covered) / expected) if expected else 0,
        "covered_symbols": covered,
    }


def _all_market_datasets_by_name(name: str) -> list[dict]:
    return [
        dataset
        for dataset in repository.list_datasets()
        if dataset.get("source") == "akshare_all" and dataset.get("name") == name
    ]


def _all_market_base_datasets(name: str, base_dataset_id: str | None) -> list[dict]:
    datasets = _all_market_datasets_by_name(name)
    if not base_dataset_id:
        return datasets
    base = repository.get_dataset(base_dataset_id)
    if not base:
        raise HTTPException(status_code=404, detail="要补齐的全A数据集不存在，请刷新后重试")
    if base.get("source") != "akshare_all":
        raise HTTPException(status_code=400, detail="只能在沪深全A快照基础上继续补齐")
    if base.get("name") != name:
        raise HTTPException(status_code=400, detail="当前全A快照的日期范围与本次同步不一致，请重新选择匹配的数据集")
    rest = [dataset for dataset in datasets if dataset["id"] != base["id"]]
    return [base, *rest]


def _delete_dataset_record_and_file(record: dict) -> None:
    deleted = repository.delete_dataset(record["id"])
    if not deleted:
        return
    try:
        dataset_path = Path(deleted["path"]).resolve()
        datasets_root = (database_path.parent / "datasets").resolve()
        if dataset_path.is_file() and datasets_root in dataset_path.parents:
            dataset_path.unlink()
    except OSError as error:
        logger.warning("dataset_file_delete_failed dataset_id=%s error=%s", deleted["id"], error)


def _merge_market_frames(existing_frame, new_frame):
    if existing_frame is None or existing_frame.empty:
        return new_frame
    if new_frame is None or new_frame.empty:
        return existing_frame
    combined = pd.concat([existing_frame, new_frame], ignore_index=True)
    combined["symbol"] = combined["symbol"].map(normalize_symbol)
    combined["trade_date"] = pd.to_datetime(combined["trade_date"])
    return (
        combined
        .sort_values(["symbol", "trade_date"])
        .drop_duplicates(["symbol", "trade_date"], keep="last")
        .reset_index(drop=True)
    )


def _enrich_frame_with_security_master(frame) -> object:
    current = frame.copy()
    current["symbol"] = current["symbol"].map(normalize_symbol)
    securities = {
        item["symbol"]: item
        for item in repository.list_securities(include_inactive=True)
    }
    listed_dates = current["symbol"].map(
        lambda symbol: securities.get(symbol, {}).get("listed_date")
    )
    if "listed_date" in current:
        current["listed_date"] = current["listed_date"].fillna(listed_dates)
    else:
        current["listed_date"] = listed_dates
    return prepare_market_frame(current)


def _warehouse_records_from_frame(frame, source: str) -> list[dict]:
    current = frame.copy()
    output = current.assign(
        trade_date=current["trade_date"].dt.strftime("%Y-%m-%d"),
        listed_date=current["listed_date"].dt.strftime("%Y-%m-%d").fillna(""),
        source=source,
    )
    records = output.to_dict(orient="records")
    for record in records:
        if not record.get("listed_date"):
            record["listed_date"] = None
    return records


def _store_market_warehouse(frame, source: str) -> None:
    repository.upsert_market_daily_bars(_warehouse_records_from_frame(frame, source))


def _load_market_warehouse(symbols: list[str], start_date: str, end_date: str, benchmark: str | None = None):
    requested = sorted({normalize_symbol(symbol) for symbol in symbols})
    if benchmark:
        requested.append(normalize_symbol(benchmark))
    records = repository.list_market_daily_bars(sorted(set(requested)), start_date, end_date)
    if not records:
        return None
    return _enrich_frame_with_security_master(pd.DataFrame(records))


def _market_warehouse_symbol_coverage(
    frame,
    requested_symbols: list[str],
    benchmark: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    if frame is None or frame.empty:
        requested = {normalize_symbol(symbol) for symbol in requested_symbols}
        return {
            "expected": len(requested),
            "covered": 0,
            "missing": len(requested),
            "coverage": 0,
            "covered_symbols": [],
        }
    requested = {normalize_symbol(symbol) for symbol in requested_symbols}
    current = frame.copy()
    current["trade_date"] = pd.to_datetime(current["trade_date"])
    start_boundary = pd.to_datetime(start_date, errors="coerce") if start_date else None
    end_boundary = pd.to_datetime(end_date, errors="coerce") if end_date else None
    synced = set()
    for symbol, group in current.groupby("symbol", sort=False):
        normalized = normalize_symbol(symbol)
        if normalized not in requested:
            continue
        first_date = group["trade_date"].min()
        last_date = group["trade_date"].max()
        listed_date = pd.to_datetime(group["listed_date"], errors="coerce").dropna().min()
        start_ok = True
        end_ok = True
        if start_boundary is not None and pd.notna(start_boundary):
            start_ok = first_date <= start_boundary + pd.Timedelta(days=7)
            if pd.notna(listed_date) and listed_date > start_boundary:
                start_ok = first_date <= listed_date + pd.Timedelta(days=7)
        if end_boundary is not None and pd.notna(end_boundary):
            end_ok = last_date >= end_boundary - pd.Timedelta(days=7)
        if start_ok and end_ok:
            synced.add(normalized)
    if benchmark:
        synced -= {normalize_symbol(benchmark)}
    covered = sorted(synced & requested)
    expected = len(requested)
    return {
        "expected": expected,
        "covered": len(covered),
        "missing": max(0, expected - len(covered)),
        "coverage": (len(covered) / expected) if expected else 0,
        "covered_symbols": covered,
    }


def _backfill_market_warehouse_from_datasets() -> dict:
    summary = repository.market_daily_bar_summary()
    if summary["row_count"]:
        return {"skipped": True, **summary}
    imported = {"datasets": 0, "rows": 0}
    for dataset in reversed(repository.list_datasets()):
        try:
            dataset_path = Path(dataset["path"])
            if not dataset_path.is_file():
                continue
            frame = load_csv(dataset_path)
            _store_market_warehouse(frame, dataset.get("source", "csv"))
            imported["datasets"] += 1
            imported["rows"] += len(frame)
        except (OSError, ValueError) as error:
            logger.warning("warehouse_backfill_dataset_failed dataset_id=%s error=%s", dataset.get("id"), error)
    if imported["rows"]:
        logger.info(
            "market_warehouse_backfilled datasets=%s rows=%s",
            imported["datasets"], imported["rows"],
        )
    return {"skipped": False, **imported}


def _persist_dataset(name: str, frame, source: str) -> dict:
    frame = _enrich_frame_with_security_master(frame)
    _store_market_warehouse(frame, source)
    normalized = frame.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8")
    fingerprint = hashlib.sha256(normalized).hexdigest()
    summary = dataset_summary(frame, prepared=True)
    existing = repository.find_dataset_by_fingerprint(fingerprint)
    if existing:
        security_master = extract_security_master(frame, source, prepared=True)
        repository.upsert_securities(security_master)
        repository.upsert_industry_history(security_master)
        repository.replace_security_daily_status(
            existing["id"], extract_security_daily_status(existing["id"], frame, source, prepared=True)
        )
        quality_checks = adjustment_quality_checks(existing["id"], frame, prepared=True)
        repository.replace_dataset_quality_checks(
            existing["id"], quality_checks
        )
        return {**existing, "duplicate": True, "summary": summary, "quality_checks": quality_checks}
    dataset_id = uuid4().hex
    dataset_directory = database_path.parent / "datasets"
    dataset_directory.mkdir(parents=True, exist_ok=True)
    dataset_path = dataset_directory / f"{dataset_id}.csv"
    dataset_path.write_bytes(normalized)
    record = repository.create_dataset(
        {
            "id": dataset_id, "name": name, "path": str(dataset_path),
            "fingerprint": fingerprint, "row_count": summary["row_count"],
            "symbol_count": summary["symbol_count"], "start_date": summary["start_date"],
            "end_date": summary["end_date"], "source": source,
        }
    )
    security_master = extract_security_master(frame, source, prepared=True)
    repository.upsert_securities(security_master)
    repository.upsert_industry_history(security_master)
    repository.replace_security_daily_status(
        dataset_id, extract_security_daily_status(dataset_id, frame, source, prepared=True)
    )
    quality_checks = adjustment_quality_checks(dataset_id, frame, prepared=True)
    repository.replace_dataset_quality_checks(
        dataset_id, quality_checks
    )
    return {**record, "duplicate": False, "summary": summary, "quality_checks": quality_checks}


def _replace_dataset_snapshot(record: dict, frame, source: str) -> dict:
    frame = _enrich_frame_with_security_master(frame)
    _store_market_warehouse(frame, source)
    normalized = frame.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8")
    fingerprint = hashlib.sha256(normalized).hexdigest()
    summary = dataset_summary(frame, prepared=True)
    dataset_path = Path(record["path"])
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_path.write_bytes(normalized)
    updated = repository.update_dataset(
        record["id"],
        {
            "name": record["name"],
            "path": str(dataset_path),
            "fingerprint": fingerprint,
            "row_count": summary["row_count"],
            "symbol_count": summary["symbol_count"],
            "start_date": summary["start_date"],
            "end_date": summary["end_date"],
            "source": source,
        },
    )
    security_master = extract_security_master(frame, source, prepared=True)
    repository.upsert_securities(security_master)
    repository.upsert_industry_history(security_master)
    repository.replace_security_daily_status(
        record["id"], extract_security_daily_status(record["id"], frame, source, prepared=True)
    )
    quality_checks = adjustment_quality_checks(record["id"], frame, prepared=True)
    repository.replace_dataset_quality_checks(record["id"], quality_checks)
    return {**updated, "duplicate": False, "summary": summary, "quality_checks": quality_checks}


@app.post("/api/datasets/csv", status_code=201)
def import_csv_dataset(payload: CsvDatasetRequest) -> dict:
    try:
        frame = load_csv_text(payload.csv_text)
        frame = filter_to_trading_calendar(frame)
    except (ValueError, UnicodeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _persist_dataset(payload.name, frame, "csv")


@app.post("/api/datasets/akshare", status_code=201)
async def sync_akshare_dataset(payload: AkshareDatasetRequest) -> dict:
    if len(payload.symbols) > 20:
        raise HTTPException(
            status_code=400,
            detail=f"单次选股同步最多支持 20 只股票，当前选择了 {len(payload.symbols)} 只。"
                   " 请先缩小股票池再试，或使用「同步沪深全A」。",
        )
    try:
        warehouse_frame = await run_in_threadpool(
            _load_market_warehouse,
            payload.symbols, payload.start_date, payload.end_date, payload.benchmark
        )
        warehouse_coverage = _market_warehouse_symbol_coverage(
            warehouse_frame, payload.symbols, payload.benchmark, payload.start_date, payload.end_date
        )
        covered = set(warehouse_coverage.get("covered_symbols", []))
        missing_symbols = [
            symbol for symbol in payload.symbols
            if normalize_symbol(symbol) not in covered
        ]
        fetched_frame = None
        if missing_symbols:
            fetched_frame = await run_in_threadpool(
                fetch_akshare_dataset,
                missing_symbols, payload.start_date, payload.end_date, payload.benchmark
            )
        frame = _merge_market_frames(warehouse_frame, fetched_frame)
        if frame is None or frame.empty:
            raise ValueError("本地仓库和免费数据源都未能提供可用行情")
    except (DataSourceError, ValueError) as error:
        logger.warning("akshare_sync_failed error=%s", error)
        raise HTTPException(status_code=502, detail=str(error)) from error
    result = await run_in_threadpool(_persist_dataset, payload.name, frame, "akshare")
    result["_warehouse"] = {
        "covered_before_fetch": warehouse_coverage["covered"],
        "fetched_symbols": len(missing_symbols),
        "reused": bool(warehouse_coverage["covered"]),
    }
    return result


@app.post("/api/datasets/akshare/all", status_code=201)
async def sync_all_akshare_dataset(payload: AkshareAllDatasetRequest) -> dict:
    try:
        symbols = await run_in_threadpool(_active_sh_sz_symbols)
        if not symbols:
            raise ValueError("没有可同步的沪深 A 股证券主数据")
        existing_records = await run_in_threadpool(
            _all_market_base_datasets, payload.name, payload.base_dataset_id
        )
        existing_record = existing_records[0] if existing_records else None
        duplicate_records = existing_records[1:]
        existing_frame = None
        existing_coverage = {"covered_symbols": []}
        for record in existing_records:
            current_frame = await run_in_threadpool(load_csv, record["path"])
            existing_frame = _merge_market_frames(existing_frame, current_frame)
        warehouse_symbols = symbols if existing_frame is None else [
            symbol
            for symbol in symbols
            if normalize_symbol(symbol) not in set(
                _all_market_coverage(existing_frame, symbols, payload.benchmark).get("covered_symbols", [])
            )
        ]
        warehouse_frame = await run_in_threadpool(
            _load_market_warehouse,
            warehouse_symbols, payload.start_date, payload.end_date, payload.benchmark
        )
        warehouse_coverage = _market_warehouse_symbol_coverage(
            warehouse_frame, warehouse_symbols, payload.benchmark, payload.start_date, payload.end_date
        )
        existing_frame = _merge_market_frames(existing_frame, warehouse_frame)
        if existing_frame is not None:
            existing_coverage = _all_market_coverage(existing_frame, symbols, payload.benchmark)
        covered = set(existing_coverage.get("covered_symbols", []))
        missing_symbols = [symbol for symbol in symbols if normalize_symbol(symbol) not in covered]
        if not missing_symbols and existing_record and existing_frame is not None:
            result = await run_in_threadpool(
                _replace_dataset_snapshot, existing_record, existing_frame, "akshare_all"
            )
            for duplicate_record in duplicate_records:
                await run_in_threadpool(_delete_dataset_record_and_file, duplicate_record)
            result["_coverage"] = {
                key: value
                for key, value in _all_market_coverage(existing_frame, symbols, payload.benchmark).items()
                if key != "covered_symbols"
            }
            if duplicate_records:
                result["_consolidated_dataset_ids"] = [record["id"] for record in duplicate_records]
            result["_sync_note"] = f"沪深全A已覆盖 {result['_coverage']['covered']} / {result['_coverage']['expected']} 只，无需补齐"
            return result
        batch_size = max(1, min(ALL_MARKET_SYNC_BATCH_SIZE, len(missing_symbols)))
        batch_symbols = missing_symbols[:batch_size]
        frame = await run_in_threadpool(
            fetch_akshare_dataset,
            batch_symbols, payload.start_date, payload.end_date, payload.benchmark
        )
        merged_frame = _merge_market_frames(existing_frame, frame)
        coverage = _all_market_coverage(merged_frame, symbols, payload.benchmark)
        previous_count = len(covered)
        if coverage["covered"] <= previous_count:
            raise ValueError(
                f"本批未新增任何A股行情，当前仍为 {previous_count} / {coverage['expected']} 只。"
                " 可能是 AkShare/网络限流，请稍后再试。"
            )
    except (DataSourceError, ValueError) as error:
        logger.warning("akshare_all_sync_failed error=%s", error)
        raise HTTPException(status_code=502, detail=str(error)) from error
    if existing_record:
        result = await run_in_threadpool(_replace_dataset_snapshot, existing_record, merged_frame, "akshare_all")
        for duplicate_record in duplicate_records:
            await run_in_threadpool(_delete_dataset_record_and_file, duplicate_record)
        if duplicate_records:
            result["_consolidated_dataset_ids"] = [record["id"] for record in duplicate_records]
    else:
        result = await run_in_threadpool(_persist_dataset, payload.name, merged_frame, "akshare_all")
    result["_coverage"] = {key: value for key, value in coverage.items() if key != "covered_symbols"}
    result["_warehouse"] = {
        "covered_before_fetch": warehouse_coverage["covered"],
        "fetched_symbols": len(batch_symbols),
        "reused": bool(warehouse_coverage["covered"]),
    }
    added_count = coverage["covered"] - previous_count
    if coverage["covered"] < len(symbols):
        result["_sync_note"] = (
            f"本批尝试 {len(batch_symbols)} 只，新增 {added_count} 只；"
            f"累计覆盖 {coverage['covered']} / {coverage['expected']} 只。"
            " 可继续点击「同步沪深全A」补齐剩余股票。"
        )
    return result


@app.delete("/api/datasets/{dataset_id}")
def delete_dataset(dataset_id: str) -> dict:
    record = repository.delete_dataset(dataset_id)
    if not record:
        raise HTTPException(status_code=404, detail="数据集不存在")
    try:
        dataset_path = Path(record["path"]).resolve()
        datasets_root = (database_path.parent / "datasets").resolve()
        if dataset_path.is_file() and datasets_root in dataset_path.parents:
            dataset_path.unlink()
    except OSError as error:
        logger.warning("dataset_file_delete_failed dataset_id=%s error=%s", dataset_id, error)
    return {"id": dataset_id, "deleted": True}


@app.get("/api/data/calendar")
def trading_calendar(start_date: str, end_date: str) -> dict:
    try:
        calendar = fetch_trading_calendar(start_date, end_date)
    except DataSourceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {
        "start_date": start_date,
        "end_date": end_date,
        "count": int(len(calendar)),
        "dates": calendar["trade_date"].dt.strftime("%Y-%m-%d").tolist(),
    }


@app.get("/api/datasets/{dataset_id}/preview")
def preview_dataset(dataset_id: str) -> dict:
    record = repository.get_dataset(dataset_id)
    if not record:
        raise HTTPException(status_code=404, detail="数据集不存在")
    try:
        frame = load_csv(record["path"])
    except (OSError, ValueError) as error:
        logger.exception("dataset_read_failed dataset_id=%s", dataset_id)
        raise HTTPException(status_code=500, detail="数据集文件不可用") from error
    return {
        "dataset": record,
        "summary": dataset_summary(frame),
        "quality_checks": repository.list_dataset_quality_checks(dataset_id),
    }


@app.get("/api/datasets/{dataset_id}/quality")
def dataset_quality(dataset_id: str) -> dict:
    record = repository.get_dataset(dataset_id)
    if not record:
        raise HTTPException(status_code=404, detail="数据集不存在")
    return {
        "dataset": record,
        "quality_checks": repository.list_dataset_quality_checks(dataset_id),
    }


@app.get("/api/projects")
def list_projects() -> list[dict]:
    return repository.list_projects()


@app.post("/api/projects", status_code=201)
def create_project(payload: ProjectCreate) -> dict:
    return repository.create_project(uuid4().hex, payload.name, payload.description)


@app.get("/api/projects/{project_id}/strategies")
def list_strategies(project_id: str) -> list[dict]:
    if not repository.get_project(project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    return repository.list_strategies(project_id)


@app.post("/api/strategies", status_code=201)
def create_strategy(payload: StrategyCreate) -> dict:
    if not repository.get_project(payload.project_id):
        raise HTTPException(status_code=400, detail="项目不存在")
    return repository.create_strategy(
        uuid4().hex,
        uuid4().hex,
        payload.project_id,
        payload.name,
        payload.definition.model_dump(mode="json"),
    )


@app.get("/api/strategies/{strategy_id}/versions")
def list_strategy_versions(strategy_id: str) -> list[dict]:
    if not repository.get_strategy(strategy_id):
        raise HTTPException(status_code=404, detail="策略不存在")
    return repository.list_strategy_versions(strategy_id)


@app.post("/api/strategies/{strategy_id}/versions", status_code=201)
def create_strategy_version(strategy_id: str, payload: StrategyVersionCreate) -> dict:
    try:
        return repository.create_strategy_version(
            uuid4().hex,
            strategy_id,
            payload.definition.model_dump(mode="json"),
            payload.note,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="策略不存在") from error
