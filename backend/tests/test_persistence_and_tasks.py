import time

import pandas as pd
import pytest

from backend.data import load_csv_text, sample_daily
from backend.engine import BacktestCancelled, run_backtest
from backend.models import BacktestRequest
from backend.repository import BacktestRepository
from backend.tasks import BacktestTaskManager


CSV_TEXT = """trade_date,symbol,open,high,low,close,volume
2024-01-02,600000.SH,10,10.5,9.8,10.2,100000
2024-01-03,600000.SH,10.2,10.8,10.1,10.7,120000
"""


def test_csv_validation_and_normalization():
    frame = load_csv_text(CSV_TEXT)
    assert len(frame) == 2
    assert str(frame.iloc[0]["trade_date"].date()) == "2024-01-02"
    with pytest.raises(ValueError, match="缺少字段"):
        load_csv_text("trade_date,symbol,close\n2024-01-02,600000.SH,10\n")


def test_repository_persists_runs_across_instances(tmp_path):
    path = tmp_path / "quantlab.db"
    first = BacktestRepository(path)
    first.create_run("run-1", {"symbols": ["600519.SH"]})
    first.complete_run("run-1", {"metrics": {"total_return": 0.1}})
    second = BacktestRepository(path)
    restored = second.get_run("run-1", include_result=True)
    assert restored["status"] == "completed"
    assert restored["result"]["metrics"]["total_return"] == 0.1


def test_repository_marks_interrupted_jobs_failed(tmp_path):
    repository = BacktestRepository(tmp_path / "quantlab.db")
    repository.create_run("run-1", {"symbols": []})
    repository.update_run("run-1", status="running")
    assert repository.mark_interrupted_runs() == 1
    assert repository.get_run("run-1")["status"] == "failed"


def test_strategy_versions_are_immutable_and_ordered(tmp_path):
    repository = BacktestRepository(tmp_path / "quantlab.db")
    repository.ensure_default_project()
    first_definition = {"name": "均线策略", "buy_conditions": [{"left": 20, "right": 60}]}
    strategy = repository.create_strategy(
        "strategy-1", "version-1", "default", "均线策略", first_definition
    )
    second = repository.create_strategy_version(
        "version-2",
        strategy["id"],
        {"name": "均线策略", "buy_conditions": [{"left": 10, "right": 30}]},
        "参数调整",
    )
    versions = repository.list_strategy_versions("strategy-1")
    assert second["version"] == 2
    assert [item["version"] for item in versions] == [2, 1]
    assert repository.get_strategy_version("version-1")["definition"] == first_definition


def test_backtest_run_records_reproducibility_references(tmp_path):
    repository = BacktestRepository(tmp_path / "quantlab.db")
    record = repository.create_run(
        "run-repro",
        {
            "project_id": "project-1",
            "strategy_id": "strategy-1",
            "strategy_version_id": "version-3",
            "dataset_fingerprint": "sha256-value",
        },
    )
    assert record["project_id"] == "project-1"
    assert record["strategy_id"] == "strategy-1"
    assert record["strategy_version_id"] == "version-3"
    assert record["dataset_fingerprint"] == "sha256-value"


def test_async_task_completes_and_persists_result(tmp_path):
    repository = BacktestRepository(tmp_path / "quantlab.db")
    manager = BacktestTaskManager(repository, max_workers=1)
    request = BacktestRequest(
        symbols=["600519.SH"], start_date="2020-01-01", end_date="2020-12-31"
    )
    record = manager.submit(request)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        current = repository.get_run(record["id"], include_result=True)
        if current["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.02)
    manager.shutdown()
    assert current["status"] == "completed"
    assert current["progress"] == 1.0
    assert current["result"]["task_id"] == record["id"]


def test_async_task_uses_selected_dataset_snapshot(tmp_path):
    repository = BacktestRepository(tmp_path / "quantlab.db")
    snapshot = pd.concat(
        [
            sample_daily("600519.SH", "2020-01-01", "2020-12-31"),
            sample_daily("000300.SH", "2020-01-01", "2020-12-31"),
        ],
        ignore_index=True,
    )
    path = tmp_path / "snapshot.csv"
    snapshot.to_csv(path, index=False)
    repository.create_dataset(
        {
            "id": "dataset-1", "name": "测试快照", "path": str(path),
            "fingerprint": "snapshot-sha", "row_count": len(snapshot),
            "symbol_count": 2, "start_date": "2020-01-01", "end_date": "2020-12-31",
            "source": "csv",
        }
    )
    manager = BacktestTaskManager(repository, max_workers=1)
    record = manager.submit(
        BacktestRequest(
            dataset_id="dataset-1", symbols=["600519.SH"],
            start_date="2020-01-01", end_date="2020-12-31",
        )
    )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        current = repository.get_run(record["id"], include_result=True)
        if current["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.02)
    manager.shutdown()
    assert current["status"] == "completed"
    assert current["result"]["data_source"] == "csv"
    assert current["result"]["benchmark"]["is_demo"] is False


def test_engine_cooperative_cancellation():
    request = BacktestRequest(
        symbols=["600519.SH"], start_date="2020-01-01", end_date="2020-12-31"
    )
    with pytest.raises(BacktestCancelled):
        run_backtest(
            {"600519.SH": sample_daily("600519.SH")},
            request,
            cancel_check=lambda: True,
        )
