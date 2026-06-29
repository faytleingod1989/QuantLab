import time

import pandas as pd
import pytest

from backend.data import extract_security_daily_status, extract_security_master, load_csv_text, prepare_market_frame, sample_daily
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


def test_repository_decode_tolerates_corrupted_json(tmp_path):
    repository = BacktestRepository(tmp_path / "quantlab.db")
    repository.create_run("run-1", {"symbols": ["600519.SH"]})
    with repository._connect() as connection:
        connection.execute(
            "UPDATE backtest_runs SET config_json = ?, result_json = ? WHERE id = ?",
            ("{bad", "{bad", "run-1"),
        )
    restored = repository.get_run("run-1", include_result=True)
    assert restored["config"] == {}
    assert restored["result"] == {"decode_error": True}


def test_repository_marks_interrupted_jobs_failed(tmp_path):
    repository = BacktestRepository(tmp_path / "quantlab.db")
    repository.create_run("run-1", {"symbols": []})
    repository.update_run("run-1", status="running")
    assert repository.mark_interrupted_runs() == 1
    assert repository.get_run("run-1")["status"] == "failed"


def test_cancel_run_does_not_overwrite_completed_run(tmp_path):
    repository = BacktestRepository(tmp_path / "quantlab.db")
    repository.create_run("run-1", {"symbols": ["600519.SH"]})
    repository.complete_run("run-1", {"metrics": {"total_return": 0.1}})
    repository.cancel_run("run-1")
    run = repository.get_run("run-1", include_result=True)
    assert run["status"] == "completed"
    assert run["result"]["metrics"]["total_return"] == 0.1


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


def test_repository_persists_security_master_and_daily_status(tmp_path):
    repository = BacktestRepository(tmp_path / "quantlab.db")
    frame = sample_daily("600519.SH", "2024-01-02", "2024-01-05")
    repository.upsert_securities(extract_security_master(frame, "csv"))
    repository.replace_security_daily_status(
        "dataset-1", extract_security_daily_status("dataset-1", frame, "csv")
    )
    security = repository.get_security("600519.SH")
    assert security["name"] == "贵州茅台"
    assert security["board"] == "沪市主板"
    assert security["listed_date"] == "2024-01-02"
    status = repository.list_security_daily_status("600519.SH", "2024-01-02", "2024-01-05")
    assert len(status) == len(frame)
    assert {"is_st", "suspended", "suspension_streak", "long_suspended", "limit_exempt", "limit_reason", "limit_up", "limit_down"} <= set(status[0])


def test_repository_persists_market_daily_warehouse(tmp_path):
    from backend import app as app_module

    repository = BacktestRepository(tmp_path / "quantlab.db")
    frame = prepare_market_frame(sample_daily("600519.SH", "2024-01-02", "2024-01-05"))
    repository.upsert_market_daily_bars(app_module._warehouse_records_from_frame(frame, "csv"))

    rows = repository.list_market_daily_bars(["600519.SH"], "2024-01-02", "2024-01-05")
    summary = repository.market_daily_bar_summary()

    assert len(rows) == len(frame)
    assert rows[0]["symbol"] == "600519.SH"
    assert {"limit_exempt", "suspended", "corporate_action", "adjustment_anomaly"} <= set(rows[0])
    assert summary["row_count"] == len(frame)
    assert summary["symbol_count"] == 1
    assert summary["start_date"] == "2024-01-02"


def test_repository_persists_industry_history(tmp_path):
    repository = BacktestRepository(tmp_path / "quantlab.db")
    repository.upsert_industry_history(
        [
            {
                "symbol": "300750.SZ",
                "valid_from": "2018-06-11",
                "industry": "C 制造业",
                "board": "创业板",
                "source": "akshare_master",
            }
        ]
    )
    history = repository.list_industry_history("300750.SZ")
    assert history[0]["industry"] == "C 制造业"
    assert history[0]["board"] == "创业板"


def test_industry_history_import_builds_missing_security_master(monkeypatch):
    from backend import app as app_module

    class FakeRepository:
        def get_security(self, symbol):
            return {"symbol": symbol} if symbol == "600519.SH" else None

    monkeypatch.setattr(app_module, "repository", FakeRepository())
    records = [
        {
            "symbol": "600519.SH",
            "valid_from": "2001-08-27",
            "industry": "食品饮料",
            "board": "沪市主板",
            "source": "industry_history_csv",
        },
        {
            "symbol": "300750.SZ",
            "valid_from": "2018-06-11",
            "industry": "电力设备",
            "board": "创业板",
            "source": "industry_history_csv",
        },
    ]
    masters = app_module._missing_security_master_from_industry_history(records)
    assert masters == [
        {
            "symbol": "300750.SZ",
            "name": "300750.SZ",
            "exchange": "SZ",
            "board": "创业板",
            "listed_date": "2018-06-11",
            "delisted_date": None,
            "status": "active",
            "industry": "电力设备",
            "source": "industry_history_csv",
        }
    ]


def test_all_market_sync_symbol_pool_uses_active_sh_sz_only(monkeypatch):
    from backend import app as app_module

    records = [
        {
            "symbol": "600519.SH",
            "exchange": "SH",
            "status": "active",
            "industry": "食品饮料",
            "board": "沪市主板",
        },
        {
            "symbol": "300750.SZ",
            "exchange": "SZ",
            "status": "active",
            "industry": "电力设备",
            "board": "创业板",
        },
        {"symbol": "920000.BJ", "exchange": "BJ", "status": "active"},
        {"symbol": "000300.SH", "exchange": "SH", "status": "active"},
        {"symbol": "600001.SH", "exchange": "SH", "status": "delisted"},
    ]

    class FakeRepository:
        def list_securities(self, include_inactive=False):
            return []

        def upsert_securities(self, synced_records):
            self.synced_records = synced_records

        def upsert_industry_history(self, synced_records):
            self.industry_records = synced_records

    fake_repository = FakeRepository()
    monkeypatch.setattr(app_module, "repository", fake_repository)
    monkeypatch.setattr(app_module, "fetch_akshare_security_master", lambda: records)

    assert app_module._active_sh_sz_symbols() == ["300750.SZ", "600519.SH"]
    assert app_module._active_market_symbols("all_market") == ["300750.SZ", "600519.SH", "920000.BJ"]
    assert app_module._active_market_symbols("bj") == ["920000.BJ"]
    assert fake_repository.synced_records == records


def test_all_market_sync_rejects_low_coverage_snapshot():
    from fastapi import HTTPException
    from backend import app as app_module

    requested = [f"600{i:03d}.SH" for i in range(10)]
    partial = pd.concat(
        [
            sample_daily("600000.SH", "2024-01-01", "2024-01-10"),
            sample_daily("600001.SH", "2024-01-01", "2024-01-10"),
            sample_daily("000300.SH", "2024-01-01", "2024-01-10"),
        ],
        ignore_index=True,
    )

    with pytest.raises(HTTPException) as error:
        app_module._ensure_all_market_sync_coverage(partial, requested, "000300.SH")

    assert error.value.status_code == 502
    assert "全A行情同步覆盖不足" in error.value.detail
    assert "请求 10 只，成功获取 2 只" in error.value.detail


def test_all_market_coverage_excludes_benchmark_and_merge_deduplicates():
    from backend import app as app_module

    requested = ["600000.SH", "600001.SH", "600002.SH", "000300.SH"]
    first = pd.concat(
        [
            sample_daily("600000.SH", "2024-01-01", "2024-01-10"),
            sample_daily("000300.SH", "2024-01-01", "2024-01-10"),
        ],
        ignore_index=True,
    )
    second = pd.concat(
        [
            sample_daily("600000.SH", "2024-01-01", "2024-01-10"),
            sample_daily("600001.SH", "2024-01-01", "2024-01-10"),
            sample_daily("000300.SH", "2024-01-01", "2024-01-10"),
        ],
        ignore_index=True,
    )

    merged = app_module._merge_market_frames(first, second)
    coverage = app_module._all_market_coverage(merged, requested, "000300.SH")

    assert coverage["expected"] == 3
    assert coverage["covered"] == 2
    assert coverage["missing"] == 1
    assert coverage["covered_symbols"] == ["600000.SH", "600001.SH"]
    assert not merged.duplicated(["symbol", "trade_date"]).any()


def test_all_market_base_dataset_prefers_explicit_id_and_same_name(monkeypatch):
    from fastapi import HTTPException
    from backend import app as app_module

    datasets = [
        {"id": "newer", "name": "AkShare 沪深全A 2025", "source": "akshare_all"},
        {"id": "selected", "name": "AkShare 沪深全A 2025", "source": "akshare_all"},
        {"id": "other-date", "name": "AkShare 沪深全A 2024", "source": "akshare_all"},
    ]

    class FakeRepository:
        def list_datasets(self):
            return datasets

        def get_dataset(self, dataset_id):
            return next((item for item in datasets if item["id"] == dataset_id), None)

    monkeypatch.setattr(app_module, "repository", FakeRepository())

    selected = app_module._all_market_base_datasets("AkShare 沪深全A 2025", "selected")
    assert [item["id"] for item in selected] == ["selected", "newer"]

    with pytest.raises(HTTPException) as error:
        app_module._all_market_base_datasets("AkShare 沪深全A 2025", "other-date")
    assert error.value.status_code == 400


def test_market_warehouse_coverage_requires_requested_date_span():
    from backend import app as app_module

    frame = prepare_market_frame(sample_daily("600519.SH", "2024-01-02", "2024-01-05"))

    short_span = app_module._market_warehouse_symbol_coverage(
        frame, ["600519.SH"], start_date="2024-01-01", end_date="2024-01-10"
    )
    long_span = app_module._market_warehouse_symbol_coverage(
        frame, ["600519.SH"], start_date="2024-01-01", end_date="2024-03-01"
    )

    assert short_span["covered"] == 1
    assert long_span["covered"] == 0


def test_repository_summarizes_market_daily_symbol_ranges(tmp_path):
    from backend import app as app_module

    repository = BacktestRepository(tmp_path / "quantlab.db")
    repository.upsert_securities(
        [
            {
                "symbol": "600519.SH",
                "name": "贵州茅台",
                "exchange": "SH",
                "board": "沪市主板",
                "listed_date": "2001-08-27",
                "delisted_date": None,
                "status": "active",
                "source": "akshare_master",
            }
        ]
    )
    frame = prepare_market_frame(sample_daily("600519.SH", "2024-01-02", "2024-01-10"))
    repository.upsert_market_daily_bars(app_module._warehouse_records_from_frame(frame, "test"))

    ranges = repository.market_daily_symbol_ranges(["600519.SH"], "2024-01-01", "2024-01-31")

    assert ranges == [
        {
            "symbol": "600519.SH",
            "first_date": "2024-01-02",
            "last_date": "2024-01-10",
            "listed_date": "2001-08-27",
            "row_count": len(frame),
        }
    ]


def test_real_security_master_overrides_demo_seed_listing_date(tmp_path):
    repository = BacktestRepository(tmp_path / "quantlab.db")
    repository.upsert_securities(
        [
            {
                "symbol": "600519.SH",
                "name": "贵州茅台",
                "exchange": "SH",
                "board": "沪市主板",
                "listed_date": "1990-12-19",
                "delisted_date": None,
                "status": "active",
                "source": "seed",
            }
        ]
    )
    repository.upsert_securities(
        [
            {
                "symbol": "600519.SH",
                "name": "贵州茅台",
                "exchange": "SH",
                "board": "沪市主板",
                "listed_date": "2001-08-27",
                "delisted_date": None,
                "status": "active",
                "industry": "C 制造业",
                "total_share": 1_000_000,
                "float_share": 900_000,
                "source": "akshare_master",
            }
        ]
    )
    security = repository.get_security("600519.SH")
    assert security["listed_date"] == "2001-08-27"
    assert security["industry"] == "C 制造业"
    assert security["source"] == "akshare_master"


def test_demo_seed_does_not_regress_akshare_master_listing_date(tmp_path):
    repository = BacktestRepository(tmp_path / "quantlab.db")
    repository.upsert_securities(
        [
            {
                "symbol": "600519.SH",
                "name": "贵州茅台",
                "exchange": "SH",
                "board": "沪市主板",
                "listed_date": "2001-08-27",
                "delisted_date": None,
                "status": "active",
                "industry": "C 制造业",
                "total_share": 1_000_000,
                "float_share": 900_000,
                "source": "akshare_master",
            }
        ]
    )
    repository.upsert_securities(
        [
            {
                "symbol": "600519.SH",
                "name": "贵州茅台",
                "exchange": "SH",
                "board": "沪市主板",
                "listed_date": "1990-12-19",
                "delisted_date": None,
                "status": "active",
                "source": "demo",
            }
        ]
    )
    security = repository.get_security("600519.SH")
    assert security["listed_date"] == "2001-08-27"
    assert security["source"] == "akshare_master"


def test_repository_persists_dataset_quality_checks(tmp_path):
    repository = BacktestRepository(tmp_path / "quantlab.db")
    repository.replace_dataset_quality_checks(
        "dataset-1",
        [
            {
                "dataset_id": "dataset-1",
                "check_name": "adjustment_continuity",
                "severity": "warning",
                "message": "复权连续性检查发现异常跳变。",
                "details": {"symbols": ["600519.SH"]},
            }
        ],
    )
    checks = repository.list_dataset_quality_checks("dataset-1")
    assert checks[0]["severity"] == "warning"
    assert checks[0]["details"]["symbols"] == ["600519.SH"]


def test_repository_deletes_dataset_and_related_rows(tmp_path):
    repository = BacktestRepository(tmp_path / "quantlab.db")
    frame = sample_daily("600519.SH", "2024-01-02", "2024-01-05")
    repository.create_dataset(
        {
            "id": "dataset-1",
            "name": "snapshot",
            "path": str(tmp_path / "snapshot.csv"),
            "fingerprint": "sha",
            "row_count": len(frame),
            "symbol_count": 1,
            "start_date": "2024-01-02",
            "end_date": "2024-01-05",
            "source": "csv",
        }
    )
    repository.replace_dataset_quality_checks(
        "dataset-1",
        [{"dataset_id": "dataset-1", "check_name": "x", "severity": "pass", "message": "ok"}],
    )
    repository.replace_security_daily_status(
        "dataset-1", extract_security_daily_status("dataset-1", frame, "csv")
    )

    deleted = repository.delete_dataset("dataset-1")

    assert deleted["id"] == "dataset-1"
    assert repository.get_dataset("dataset-1") is None
    assert repository.list_dataset_quality_checks("dataset-1") == []
    assert repository.list_security_daily_status("600519.SH") == []


def test_repository_updates_dataset_in_place(tmp_path):
    repository = BacktestRepository(tmp_path / "quantlab.db")
    repository.create_dataset(
        {
            "id": "dataset-1",
            "name": "snapshot",
            "path": str(tmp_path / "snapshot.csv"),
            "fingerprint": "sha-old",
            "row_count": 10,
            "symbol_count": 1,
            "start_date": "2024-01-02",
            "end_date": "2024-01-05",
            "source": "akshare_all",
        }
    )

    updated = repository.update_dataset(
        "dataset-1",
        {
            "name": "snapshot",
            "path": str(tmp_path / "snapshot.csv"),
            "fingerprint": "sha-new",
            "row_count": 25,
            "symbol_count": 3,
            "start_date": "2024-01-02",
            "end_date": "2024-01-10",
            "source": "akshare_all",
        },
    )

    assert updated["id"] == "dataset-1"
    assert updated["fingerprint"] == "sha-new"
    assert updated["row_count"] == 25
    assert updated["symbol_count"] == 3
    assert len(repository.list_datasets()) == 1


def test_security_lifecycle_validation_allows_partial_listing_overlap(tmp_path):
    repository = BacktestRepository(tmp_path / "quantlab.db")
    repository.upsert_securities(
        [
            {
                "symbol": "600000.SH",
                "name": "浦发银行",
                "exchange": "SH",
                "board": "沪市主板",
                "listed_date": "2024-01-10",
                "delisted_date": "2024-06-30",
                "status": "active",
                "source": "test",
            }
        ]
    )
    starts_before_listing = repository.validate_security_window(["600000.SH"], "2024-01-02", "2024-01-31")
    ends_after_delist = repository.validate_security_window(["600000.SH"], "2024-06-01", "2024-07-31")
    listed_after_window = repository.validate_security_window(["600000.SH"], "2024-01-02", "2024-01-09")
    delisted_before_window = repository.validate_security_window(["600000.SH"], "2024-07-01", "2024-07-31")
    assert starts_before_listing == []
    assert ends_after_delist == []
    assert "尚未上市" in listed_after_window[0]
    assert "已退市" in delisted_before_window[0]


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
    assert current["result"]["data_quality"]["price_mode"] == "unadjusted_execution"
    assert current["result"]["data_quality"]["signal_price_mode"] == "unadjusted"
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


def test_backtest_request_validates_real_dates():
    with pytest.raises(ValueError, match="日期格式"):
        BacktestRequest(start_date="2024-13-01", end_date="2024-02-01")
    with pytest.raises(ValueError, match="结束日期必须晚于开始日期"):
        BacktestRequest(start_date="2024-02-01", end_date="2024-01-31")
