from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class BacktestRepository:
    """Small SQLite repository designed for a single-user local application."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS backtest_runs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    config_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_backtest_runs_created ON backtest_runs(created_at DESC)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    row_count INTEGER NOT NULL,
                    symbol_count INTEGER NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS strategies (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_versions (
                    id TEXT PRIMARY KEY,
                    strategy_id TEXT NOT NULL REFERENCES strategies(id),
                    version INTEGER NOT NULL,
                    definition_json TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(strategy_id, version)
                )
                """
            )
            self._ensure_column(connection, "backtest_runs", "project_id", "TEXT")
            self._ensure_column(connection, "backtest_runs", "strategy_id", "TEXT")
            self._ensure_column(connection, "backtest_runs", "strategy_version_id", "TEXT")
            self._ensure_column(connection, "backtest_runs", "dataset_fingerprint", "TEXT")

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table: str, column: str, kind: str) -> None:
        columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")

    def create_run(self, run_id: str, config: dict[str, Any]) -> dict[str, Any]:
        created_at = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO backtest_runs(id, status, progress, config_json, created_at)
                VALUES (?, 'queued', 0, ?, ?)
                """,
                (run_id, json.dumps(config, ensure_ascii=False), created_at),
            )
            connection.execute(
                """
                UPDATE backtest_runs
                SET project_id = ?, strategy_id = ?, strategy_version_id = ?, dataset_fingerprint = ?
                WHERE id = ?
                """,
                (
                    config.get("project_id"),
                    config.get("strategy_id"),
                    config.get("strategy_version_id"),
                    config.get("dataset_fingerprint"),
                    run_id,
                ),
            )
        return self.get_run(run_id)

    def update_run(self, run_id: str, **fields: Any) -> None:
        allowed = {
            "status",
            "progress",
            "cancel_requested",
            "result_json",
            "error",
            "started_at",
            "finished_at",
        }
        values = {key: value for key, value in fields.items() if key in allowed}
        if not values:
            return
        assignments = ", ".join(f"{key} = ?" for key in values)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE backtest_runs SET {assignments} WHERE id = ?",
                (*values.values(), run_id),
            )

    def complete_run(self, run_id: str, result: dict[str, Any]) -> None:
        self.update_run(
            run_id,
            status="completed",
            progress=1.0,
            result_json=json.dumps(result, ensure_ascii=False),
            finished_at=utc_now(),
        )

    def fail_run(self, run_id: str, error: str) -> None:
        self.update_run(run_id, status="failed", error=error, finished_at=utc_now())

    def cancel_run(self, run_id: str) -> None:
        self.update_run(
            run_id,
            status="cancelled",
            cancel_requested=1,
            error="任务已由用户取消",
            finished_at=utc_now(),
        )

    def request_cancel(self, run_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE backtest_runs SET cancel_requested = 1
                WHERE id = ? AND status IN ('queued', 'running')
                """,
                (run_id,),
            )
            return cursor.rowcount == 1

    def is_cancel_requested(self, run_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT cancel_requested FROM backtest_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return bool(row and row["cancel_requested"])

    def get_run(self, run_id: str, *, include_result: bool = False) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM backtest_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return self._decode(row, include_result=include_result) if row else None

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM backtest_runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._decode(row, include_result=False) for row in rows]

    def mark_interrupted_runs(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE backtest_runs
                SET status = 'failed', error = '应用重启导致任务中断', finished_at = ?
                WHERE status IN ('queued', 'running')
                """,
                (utc_now(),),
            )
            return cursor.rowcount

    def create_dataset(self, dataset: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO datasets(
                    id, name, path, fingerprint, row_count, symbol_count,
                    start_date, end_date, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dataset["id"],
                    dataset["name"],
                    dataset["path"],
                    dataset["fingerprint"],
                    dataset["row_count"],
                    dataset["symbol_count"],
                    dataset["start_date"],
                    dataset["end_date"],
                    dataset.get("created_at", utc_now()),
                ),
            )
        return self.get_dataset(dataset["id"])

    def get_dataset(self, dataset_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM datasets WHERE id = ?", (dataset_id,)
            ).fetchone()
        return dict(row) if row else None

    def find_dataset_by_fingerprint(self, fingerprint: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM datasets WHERE fingerprint = ?", (fingerprint,)
            ).fetchone()
        return dict(row) if row else None

    def list_datasets(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM datasets ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _decode(row: sqlite3.Row, *, include_result: bool) -> dict[str, Any]:
        result = {
            "id": row["id"],
            "status": row["status"],
            "progress": row["progress"],
            "cancel_requested": bool(row["cancel_requested"]),
            "config": json.loads(row["config_json"]),
            "error": row["error"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "project_id": row["project_id"],
            "strategy_id": row["strategy_id"],
            "strategy_version_id": row["strategy_version_id"],
            "dataset_fingerprint": row["dataset_fingerprint"],
        }
        if include_result:
            result["result"] = json.loads(row["result_json"]) if row["result_json"] else None
        return result

    def ensure_default_project(self) -> dict[str, Any]:
        existing = self.get_project("default")
        if existing:
            return existing
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO projects(id, name, description, status, created_at, updated_at)
                VALUES ('default', '默认研究项目', 'QuantLab 本地默认项目', 'active', ?, ?)
                """,
                (now, now),
            )
        return self.get_project("default")

    def create_project(self, project_id: str, name: str, description: str) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO projects VALUES (?, ?, ?, 'active', ?, ?)",
                (project_id, name, description, now, now),
            )
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return dict(row) if row else None

    def list_projects(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM projects WHERE status = 'active' ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def create_strategy(
        self,
        strategy_id: str,
        version_id: str,
        project_id: str,
        name: str,
        definition: dict[str, Any],
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO strategies VALUES (?, ?, ?, 'active', ?, ?)",
                (strategy_id, project_id, name, now, now),
            )
            connection.execute(
                "INSERT INTO strategy_versions VALUES (?, ?, 1, ?, '', ?)",
                (version_id, strategy_id, json.dumps(definition, ensure_ascii=False), now),
            )
        return self.get_strategy(strategy_id, include_latest=True)

    def create_strategy_version(
        self, version_id: str, strategy_id: str, definition: dict[str, Any], note: str
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS next_version FROM strategy_versions WHERE strategy_id = ?",
                (strategy_id,),
            ).fetchone()
            if not connection.execute(
                "SELECT 1 FROM strategies WHERE id = ? AND status = 'active'", (strategy_id,)
            ).fetchone():
                raise KeyError(strategy_id)
            connection.execute(
                "INSERT INTO strategy_versions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    version_id,
                    strategy_id,
                    row["next_version"],
                    json.dumps(definition, ensure_ascii=False),
                    note,
                    now,
                ),
            )
            connection.execute(
                "UPDATE strategies SET updated_at = ? WHERE id = ?", (now, strategy_id)
            )
        return self.get_strategy_version(version_id)

    def get_strategy(self, strategy_id: str, *, include_latest: bool = False) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM strategies WHERE id = ?", (strategy_id,)
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        if include_latest:
            versions = self.list_strategy_versions(strategy_id, limit=1)
            result["latest_version"] = versions[0] if versions else None
        return result

    def list_strategies(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM strategies
                WHERE project_id = ? AND status = 'active'
                ORDER BY updated_at DESC
                """,
                (project_id,),
            ).fetchall()
        return [self.get_strategy(row["id"], include_latest=True) for row in rows]

    def get_strategy_version(self, version_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM strategy_versions WHERE id = ?", (version_id,)
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["definition"] = json.loads(result.pop("definition_json"))
        return result

    def list_strategy_versions(self, strategy_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM strategy_versions
                WHERE strategy_id = ? ORDER BY version DESC LIMIT ?
                """,
                (strategy_id, limit),
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["definition"] = json.loads(item.pop("definition_json"))
            results.append(item)
        return results
