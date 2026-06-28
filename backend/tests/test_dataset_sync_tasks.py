from __future__ import annotations

from time import sleep

from backend.tasks import DatasetSyncTaskManager


class SyncRequest:
    def __init__(self, base_dataset_id: str | None = None):
        self.base_dataset_id = base_dataset_id

    def model_copy(self, update: dict):
        return SyncRequest(base_dataset_id=update.get("base_dataset_id", self.base_dataset_id))


def wait_until_finished(manager: DatasetSyncTaskManager, task_id: str) -> dict:
    for _ in range(100):
        task = manager.get(task_id)
        if task and task["status"] in {"completed", "failed", "cancelled"}:
            return task
        sleep(0.01)
    raise AssertionError("dataset sync task did not finish")


def test_dataset_sync_task_runs_batches_until_coverage_complete():
    calls: list[str | None] = []

    def execute_batch(request: SyncRequest) -> dict:
        calls.append(request.base_dataset_id)
        covered = 1 if len(calls) == 1 else 2
        return {
            "id": f"dataset-{len(calls)}",
            "symbol_count": covered + 1,
            "_coverage": {"covered": covered, "expected": 2},
            "_providers": [{"provider": "test", "fetched_symbols": 1}],
            "_sync_note": f"batch {len(calls)}",
        }

    manager = DatasetSyncTaskManager(
        execute_batch,
        max_workers=1,
        batch_interval_seconds=0,
        retry_interval_seconds=0,
    )
    try:
        task = manager.submit(SyncRequest())
        finished = wait_until_finished(manager, task["id"])
    finally:
        manager.shutdown()

    assert finished["status"] == "completed"
    assert finished["covered"] == 2
    assert finished["expected"] == 2
    assert finished["batch_count"] == 2
    assert calls == [None, "dataset-1"]


def test_dataset_sync_task_fails_after_consecutive_errors():
    def execute_batch(_: SyncRequest) -> dict:
        raise RuntimeError("provider limited")

    manager = DatasetSyncTaskManager(
        execute_batch,
        max_workers=1,
        max_consecutive_failures=2,
        batch_interval_seconds=0,
        retry_interval_seconds=0,
    )
    try:
        task = manager.submit(SyncRequest())
        finished = wait_until_finished(manager, task["id"])
    finally:
        manager.shutdown()

    assert finished["status"] == "failed"
    assert "provider limited" in finished["error"]
