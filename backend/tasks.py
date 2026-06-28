from __future__ import annotations

import json
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock
from time import sleep
from typing import Any, Callable
from uuid import uuid4

from .data import load_dataset_view, sample_daily
from .engine import BacktestCancelled, run_backtest
from .models import BacktestRequest
from .repository import BacktestRepository, utc_now


logger = logging.getLogger("quantlab.tasks")


class BacktestTaskManager:
    def __init__(self, repository: BacktestRepository, max_workers: int = 2):
        self.repository = repository
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="quantlab")
        self._cancel_events: dict[str, Event] = {}
        self._futures: dict[str, Future] = {}
        self._lock = Lock()

    def submit(self, request: BacktestRequest) -> dict:
        run_id = uuid4().hex
        record = self.repository.create_run(run_id, request.model_dump(mode="json"))
        cancel_event = Event()
        with self._lock:
            self._cancel_events[run_id] = cancel_event
            self._futures[run_id] = self.executor.submit(
                self._execute, run_id, request, cancel_event
            )
        return record

    def cancel(self, run_id: str) -> bool:
        requested = self.repository.request_cancel(run_id)
        with self._lock:
            event = self._cancel_events.get(run_id)
            future = self._futures.get(run_id)
        if event:
            event.set()
        if future and future.cancel():
            self.repository.cancel_run(run_id)
        return requested

    def _execute(self, run_id: str, request: BacktestRequest, cancel_event: Event) -> None:
        self.repository.update_run(run_id, status="running", started_at=utc_now(), progress=0.01)
        logger.info("backtest_started task_id=%s", run_id)
        last_progress = 0.0

        def cancelled() -> bool:
            return cancel_event.is_set()

        def progress(value: float) -> None:
            nonlocal last_progress
            normalized = round(min(max(value, 0.01), 0.99), 4)
            if normalized - last_progress >= 0.025:
                self.repository.update_run(run_id, progress=normalized)
                last_progress = normalized

        try:
            if cancelled():
                raise BacktestCancelled()
            if request.dataset_id:
                dataset = self.repository.get_dataset(request.dataset_id)
                if not dataset:
                    raise ValueError("数据集不存在")
                quality_checks = self.repository.list_dataset_quality_checks(request.dataset_id)
                data, benchmark = load_dataset_view(
                    dataset["path"], request.symbols, request.start_date,
                    request.end_date, request.benchmark,
                )
                benchmark_is_demo = False
                data_source = dataset.get("source", "csv")
            else:
                data = {symbol: sample_daily(symbol) for symbol in request.symbols}
                benchmark = sample_daily(request.benchmark)
                benchmark_is_demo = True
                data_source = "demo"
                quality_checks = []
            result = run_backtest(
                data,
                request,
                benchmark,
                benchmark_is_demo=benchmark_is_demo,
                progress_callback=progress,
                cancel_check=cancelled,
            )
            result["task_id"] = run_id
            result["data_source"] = data_source
            result["data_quality"] = {
                "price_mode": "unadjusted_execution",
                "signal_price_mode": request.signal_price_mode,
                "quality_checks": quality_checks,
            }
            self.repository.complete_run(run_id, result)
            logger.info("backtest_completed task_id=%s", run_id)
        except BacktestCancelled:
            self.repository.cancel_run(run_id)
            logger.info("backtest_cancelled task_id=%s", run_id)
        except Exception as error:
            self.repository.fail_run(run_id, str(error))
            logger.exception("backtest_failed task_id=%s", run_id)
        finally:
            with self._lock:
                self._cancel_events.pop(run_id, None)
                self._futures.pop(run_id, None)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)


class DatasetSyncTaskManager:
    """Run long dataset sync jobs outside the request/response lifecycle."""

    def __init__(
        self,
        execute_batch: Callable[[Any], dict],
        max_workers: int = 1,
        max_consecutive_failures: int = 3,
        batch_interval_seconds: float = 0.3,
        retry_interval_seconds: float = 2.0,
        state_path: str | Path | None = None,
    ):
        self.execute_batch = execute_batch
        self.max_consecutive_failures = max(1, max_consecutive_failures)
        self.batch_interval_seconds = max(0.0, batch_interval_seconds)
        self.retry_interval_seconds = max(0.0, retry_interval_seconds)
        self.state_path = Path(state_path) if state_path else None
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="quantlab-data")
        self._cancel_events: dict[str, Event] = {}
        self._futures: dict[str, Future] = {}
        self._tasks: dict[str, dict] = {}
        self._latest_task_id: str | None = None
        self._lock = Lock()
        self._load_state()

    def submit(self, request: Any) -> dict:
        with self._lock:
            active = self._active_locked()
            if active:
                return {**active, "duplicate": True}
            task_id = uuid4().hex
            now = utc_now()
            record = {
                "id": task_id,
                "type": "all_market_dataset_sync",
                "status": "queued",
                "progress": 0.0,
                "batch_count": 0,
                "covered": 0,
                "expected": 0,
                "added_symbols": 0,
                "dataset": None,
                "coverage": None,
                "providers": [],
                "failed_symbols": [],
                "last_failed_symbols": [],
                "failure_history": [],
                "sync_note": "",
                "error": None,
                "cancel_requested": False,
                "request": self._request_payload(request),
                "duplicate": False,
                "created_at": now,
                "started_at": None,
                "finished_at": None,
            }
            cancel_event = Event()
            self._tasks[task_id] = record
            self._latest_task_id = task_id
            self._cancel_events[task_id] = cancel_event
            self._futures[task_id] = self.executor.submit(self._execute, task_id, request, cancel_event)
            self._persist_state_locked()
            return record.copy()

    def latest(self) -> dict | None:
        with self._lock:
            if not self._latest_task_id:
                return None
            return self._tasks.get(self._latest_task_id, {}).copy()

    def get(self, task_id: str) -> dict | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return task.copy() if task else None

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            event = self._cancel_events.get(task_id)
            future = self._futures.get(task_id)
            task_exists = task_id in self._tasks
            if task_exists:
                self._tasks[task_id]["cancel_requested"] = True
                self._persist_state_locked()
        if event:
            event.set()
        if future and future.cancel():
            self._update(task_id, status="cancelled", progress=self._tasks[task_id]["progress"], finished_at=utc_now())
        return task_exists

    def _execute(self, task_id: str, request: Any, cancel_event: Event) -> None:
        logger.info("dataset_sync_started task_id=%s", task_id)
        self._update(task_id, status="running", started_at=utc_now())
        consecutive_failures = 0
        base_dataset_id = getattr(request, "base_dataset_id", None)

        try:
            while not cancel_event.is_set():
                current_request = (
                    request.model_copy(update={"base_dataset_id": base_dataset_id})
                    if hasattr(request, "model_copy")
                    else request
                )
                try:
                    previous = self.get(task_id) or {}
                    previous_covered = int(previous.get("covered") or 0)
                    result = self.execute_batch(current_request)
                    consecutive_failures = 0
                except Exception as error:
                    consecutive_failures += 1
                    previous = self.get(task_id) or {}
                    history = list(previous.get("failure_history") or [])
                    retry_symbols = list((self._request_payload(current_request) or {}).get("symbols") or [])
                    history.append(
                        {
                            "at": utc_now(),
                            "batch": int(previous.get("batch_count") or 0) + 1,
                            "error": str(error),
                            "symbols": retry_symbols[:200],
                        }
                    )
                    self._update(
                        task_id,
                        status="running",
                        error=str(error),
                        last_failed_symbols=retry_symbols[:200],
                        failure_history=history[-50:],
                        sync_note=f"同步失败 {consecutive_failures}/{self.max_consecutive_failures}：{error}",
                    )
                    if consecutive_failures >= self.max_consecutive_failures:
                        self._update(task_id, status="failed", finished_at=utc_now())
                        logger.exception("dataset_sync_failed task_id=%s", task_id)
                        return
                    if cancel_event.wait(self.retry_interval_seconds):
                        break
                    continue

                coverage = result.get("_coverage") or {}
                covered = int(coverage.get("covered") or max(0, int(result.get("symbol_count") or 0) - 1))
                expected = int(coverage.get("expected") or covered)
                progress = 1.0 if not expected else min(covered / expected, 1.0)
                batch_count = int((self.get(task_id) or {}).get("batch_count") or 0) + 1
                added_symbols = max(0, covered - previous_covered)
                base_dataset_id = result.get("id") or base_dataset_id
                previous_task = self.get(task_id) or {}
                prior_failed = set(previous_task.get("failed_symbols") or [])
                batch_failed = set(result.get("_failed_symbols") or [])
                batch_covered = set(result.get("_batch_covered_symbols") or [])
                failed_symbols = sorted((prior_failed | batch_failed) - batch_covered)
                history = list(previous_task.get("failure_history") or [])
                if batch_failed:
                    history.append(
                        {
                            "at": utc_now(),
                            "batch": batch_count,
                            "error": result.get("_sync_note") or "partial symbol fetch failure",
                            "symbols": sorted(batch_failed)[:200],
                            "providers": result.get("_providers") or [],
                        }
                    )

                self._update(
                    task_id,
                    progress=progress,
                    batch_count=batch_count,
                    covered=covered,
                    expected=expected,
                    added_symbols=added_symbols,
                    dataset=result,
                    coverage=coverage,
                    providers=result.get("_providers") or [],
                    failed_symbols=failed_symbols,
                    last_failed_symbols=sorted(batch_failed),
                    failure_history=history[-50:],
                    sync_note=result.get("_sync_note") or "",
                    error=None,
                )

                if expected and covered >= expected:
                    self._update(task_id, status="completed", progress=1.0, finished_at=utc_now())
                    logger.info("dataset_sync_completed task_id=%s", task_id)
                    return
                if cancel_event.wait(self.batch_interval_seconds):
                    break

            self._update(task_id, status="cancelled", finished_at=utc_now())
            logger.info("dataset_sync_cancelled task_id=%s", task_id)
        finally:
            with self._lock:
                self._cancel_events.pop(task_id, None)
                self._futures.pop(task_id, None)

    def _active_locked(self) -> dict | None:
        for task in self._tasks.values():
            if task["status"] in {"queued", "running"}:
                return task.copy()
        return None

    def _update(self, task_id: str, **updates: Any) -> None:
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].update(updates)
                self._persist_state_locked()

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)

    def _request_payload(self, request: Any) -> dict:
        if hasattr(request, "model_dump"):
            return request.model_dump(mode="json")
        if hasattr(request, "__dict__"):
            return dict(request.__dict__)
        return {}

    def _load_state(self) -> None:
        if not self.state_path or not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            tasks = payload.get("tasks") or {}
            now = utc_now()
            for task in tasks.values():
                if task.get("status") in {"queued", "running"}:
                    task["status"] = "interrupted"
                    task["finished_at"] = task.get("finished_at") or now
                    task["sync_note"] = "服务重启后任务已中断，可重新启动自动补齐。"
            self._tasks = {str(task_id): task for task_id, task in tasks.items()}
            self._latest_task_id = payload.get("latest_task_id")
        except Exception as error:
            logger.warning("dataset_sync_state_load_failed path=%s error=%s", self.state_path, error)

    def _persist_state_locked(self) -> None:
        if not self.state_path:
            return
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"latest_task_id": self._latest_task_id, "tasks": self._tasks}
            self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as error:
            logger.warning("dataset_sync_state_save_failed path=%s error=%s", self.state_path, error)
