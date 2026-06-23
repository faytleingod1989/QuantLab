from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event, Lock
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
