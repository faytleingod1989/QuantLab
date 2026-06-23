from __future__ import annotations

import logging
import os
import hashlib
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
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
    normalize_symbol,
    prepare_market_frame,
    sample_daily,
    source_status,
)
from .engine import run_backtest
from .models import (
    BacktestRequest,
    AkshareDatasetRequest,
    CsvDatasetRequest,
    ProjectCreate,
    StrategyCreate,
    StrategyVersionCreate,
    VisualStrategy,
)
from .repository import BacktestRepository
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


@asynccontextmanager
async def lifespan(_: FastAPI):
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
    return source_status()


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
        raise HTTPException(status_code=400, detail=f"演示数据暂不包含: {', '.join(unsupported)}")


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


def _persist_dataset(name: str, frame, source: str) -> dict:
    frame = _enrich_frame_with_security_master(frame)
    normalized = frame.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8")
    fingerprint = hashlib.sha256(normalized).hexdigest()
    summary = dataset_summary(frame)
    existing = repository.find_dataset_by_fingerprint(fingerprint)
    if existing:
        repository.upsert_securities(extract_security_master(frame, source))
        repository.replace_security_daily_status(
            existing["id"], extract_security_daily_status(existing["id"], frame, source)
        )
        repository.replace_dataset_quality_checks(
            existing["id"], adjustment_quality_checks(existing["id"], frame)
        )
        return {**existing, "duplicate": True, "summary": summary}
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
    repository.upsert_securities(extract_security_master(frame, source))
    repository.replace_security_daily_status(
        dataset_id, extract_security_daily_status(dataset_id, frame, source)
    )
    repository.replace_dataset_quality_checks(
        dataset_id, adjustment_quality_checks(dataset_id, frame)
    )
    return {**record, "duplicate": False, "summary": summary}


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
    try:
        frame = await run_in_threadpool(
            fetch_akshare_dataset,
            payload.symbols, payload.start_date, payload.end_date, payload.benchmark
        )
    except (DataSourceError, ValueError) as error:
        logger.warning("akshare_sync_failed error=%s", error)
        raise HTTPException(status_code=502, detail=str(error)) from error
    return await run_in_threadpool(_persist_dataset, payload.name, frame, "akshare")


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
