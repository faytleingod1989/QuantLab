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
    dataset_summary,
    fetch_akshare_dataset,
    fetch_trading_calendar,
    filter_to_trading_calendar,
    load_csv,
    load_csv_text,
    load_dataset_view,
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
def securities() -> list[dict]:
    return [
        {"symbol": symbol, "name": name, "exchange": symbol.split(".")[-1]}
        for symbol, name in SAMPLE_NAMES.items()
    ]


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


def _persist_dataset(name: str, frame, source: str) -> dict:
    normalized = frame.to_csv(index=False, date_format="%Y-%m-%d").encode("utf-8")
    fingerprint = hashlib.sha256(normalized).hexdigest()
    summary = dataset_summary(frame)
    existing = repository.find_dataset_by_fingerprint(fingerprint)
    if existing:
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
    return {"dataset": record, "summary": dataset_summary(frame)}


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
