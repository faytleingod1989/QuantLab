# Code Review Report — AkShare / 数据快照 / 引擎 v0.4.0

**审查日期**：2026-06-22
**审查范围**：PRD.md V1.1（A 股专版） vs 当前 working tree diff
**变更量**：12 文件，+410 / −93 行
**审查人**：Claude Code (deepseek-v4-pro)

---

## 审查结论

8 项声称功能均已落地，数据流设计合理（AkShare→快照→DataView→引擎→持久化）。**2 个严重问题**需在合入前修复，6 个重要问题建议下个迭代处理。

---

## 1. 已实现功能对照

| # | 声称功能 | 代码位置 | 状态 |
|---|---------|---------|------|
| 1 | AkShare 1.18.64 真实沪深日线 | `requirements.txt:7`, `data.py:213-280` | ✅ |
| 2 | 沪深300 真实基准 + 交易日历 | `data.py:194-210`, `data.py:250-270` | ✅ |
| 3 | 东方财富失败→新浪回退 | `data.py:238-243`（个股）, `data.py:257-265`（基准） | ✅ |
| 4 | SHA-256 不可变快照 + 去重 | `app.py:205-225`, `repository.py:106` | ✅ |
| 5 | CSV/AkShare → DataView（日期+标的受限） | `data.py:173-191`, `tasks.py:65-72` | ✅ |
| 6 | 前端演示/CSV/AkShare 三路切换 | `App.jsx:58-65` | ✅ |
| 7 | 回测记录：dataset_id + 指纹 + source | `repository.py:105-106`, `tasks.py:89` | ✅ |
| 8 | 引擎 v0.4.0 | `app.py:65`, `App.jsx:97` | ✅ |

---

## 2. 严重问题 (CRITICAL)

### CRIT-01 — ST 涨跌停 5% 在真实数据中完全失效

**文件**：`backend/data.py:40-48`
**PRD**：FR-109 (P0) — "维护历史涨跌停价格"

```python
def _limit_rate(symbol: str, trade_date: pd.Timestamp, name: str) -> float:
    code = symbol.split(".")[0]
    if "ST" in name.upper():      # ← 对 AkShare 数据永远不触发
        return 0.05
```

`fetch_akshare_dataset()` 在 line 248 将 `name` 设为：

```python
current["name"] = SAMPLE_NAMES.get(symbol, symbol)  # 非 5 只示例股 → "600519.SH"
```

对任何非示例股票，`name` 是裸代码（如 `"600519.SH"`），不含 `"ST"` 子串。**所有 ST 股票将错误使用 10% 涨跌停**，回测结果系统性偏乐观。

**修复**：从 `stock_zh_a_hist` 返回的 `名称` 列提取真实股票名，而非用 `SAMPLE_NAMES` 覆盖。

---

### CRIT-02 — 北交所 30% 涨跌停规则缺失

**文件**：`backend/data.py:40-48`
**PRD**：FR-109 (P0)，PRD §4.1 — "覆盖沪市、深市和北交所 A 股现货"

`_limit_rate()` 未处理北交所代码（`8xxxxx`）：

```python
if code.startswith(("688", "689")):   # 科创板 20%
    return 0.20
if code.startswith(("300", "301")):   # 创业板 20%（含日期判断）
    return 0.20
return 0.10  # ← 北交所 83xxxx/87xxxx 错误落入 10%
```

北交所涨跌停为 30%，当前代码会给出 10%。

**修复**：
```python
if code.startswith("8"):
    return 0.30
```

---

## 3. 重要问题 (MAJOR)

### MAJ-01 — CSV 导入无交易日历校验

**文件**：`backend/app.py:228-234`, `backend/data.py`
**PRD**：FR-106 (P0) — "非交易日不驱动策略"

AkShare 路径有日历校验（`data.py:272-275`），但 CSV 路径（`/api/datasets/csv`）完全不检查日期是否落在交易日历内。用户可导入包含周末/节假日的 CSV，导致在这些日期产生虚假信号。

**修复建议**：CSV 导入时可选校验；回测执行时统一过滤非交易日。

---

### MAJ-02 — AkShare 同步阻塞事件循环

**文件**：`backend/app.py:237-246`

```python
@app.post("/api/datasets/akshare", status_code=201)
def sync_akshare_dataset(payload: AkshareDatasetRequest) -> dict:  # 同步 def
```

`fetch_akshare_dataset()` 对每只股票发起网络请求（通常 10-30 秒），同步端点在此期间阻塞整个 FastAPI 事件循环，健康检查和所有其他 API 均无响应。

**修复建议**：改为 `async def` + `run_in_executor`，或复用 `BacktestTaskManager` 线程池。

---

### MAJ-03 — AkShare 真实股票名称被丢弃

**文件**：`backend/data.py:248`

```python
current["name"] = SAMPLE_NAMES.get(symbol, symbol)
```

`stock_zh_a_hist` 返回含 `名称` 列（已在 line 231-235 的 rename 中被忽略）。对于除 5 只示例股外的所有股票，前端显示的是裸代码而非中文名称。

**修复建议**：保留 `名称` 列 → `name`，仅在缺失时 fallback 到 `SAMPLE_NAMES` 或 symbol。

---

### MAJ-04 — 涨跌停 epsilon 过小

**文件**：`backend/engine.py:159, 188`

```python
if float(row["open"]) <= float(row.get("limit_down", -np.inf)) + 1e-8:  # 跌停
if float(row["open"]) >= float(row.get("limit_up", np.inf)) - 1e-8:     # 涨停
```

`1e-8` 对于股价（1-1000 元）来说过小。浮点计算 `prev_close * 1.10` 可能产生 `10.988999...`，与 `open=10.99` 比较时存在误判风险。

**修复建议**：使用 `Decimal` 比较，或至少 `round(price, 2)` 对齐到分。

---

### MAJ-05 — 新浪回退缺少显式列映射

**文件**：`backend/data.py:239-243`

```python
source = client.stock_zh_a_daily(...).rename(columns={"date": "trade_date"})
```

仅重命名了 `date` → `trade_date`，其余列（`open`/`high`/`low`/`close`/`volume`）假设命名一致。若两个数据源列名不同或 AkShare 版本升级改变输出 schema，将导致静默数据错误。

**修复建议**：为两个数据源分别做完整列映射字典，在 `prepare_market_frame` 之前统一。

---

### MAJ-06 — 前端 useEffect 在无历史时自动触发回测

**文件**：`frontend/src/App.jsx:82`

```javascript
} else {
    runBacktest(controller.signal);  // 无历史记录时自动回测
}
```

Strict Mode 下 effect 执行两次，虽有 `active` 守卫但 `runBacktest` 在 cleanup 中未被取消，可能产生孤立异步任务。

**修复建议**：在 cleanup 中 abort controller 对应的回测任务。

---

## 4. 次要问题 (MINOR)

| # | 描述 | 位置 |
|---|------|------|
| MIN-01 | `_validate_demo_symbols` 与 `/api/backtests/run` 内联校验逻辑重复 | `app.py:103-105`, `app.py:133-136` |
| MIN-02 | `/api/backtests/run`（同步旧版）不接受 `dataset_id`，始终使用演示数据——是否为 deprecated 旧接口？ | `app.py:100-130` |
| MIN-03 | `stock_zh_a_hist` timeout=20 秒硬编码，某些网络条件可能不足 | `data.py:229` |
| MIN-04 | 前端数据集切换失败时 toast 信息不够明确（无重试指引） | `App.jsx:78` |
| MIN-05 | CSV 大小限制 10MB（`models.py:72`），但无文件类型魔术字节校验 | `models.py:72`, PRD §10.4 |

---

## 5. 测试覆盖

### 已有测试

| 测试 | 文件 | 状态 |
|------|------|------|
| 20 项回归测试全部通过 | `test_persistence_and_tasks.py` | ✅ |
| `prepare_market_frame` 充实复权字段 | `test_data.py` | ✅ |
| DataView 标的+日期范围过滤 | `test_data.py` | ✅ |
| AkShare adapter 同时拉取个股+指数+日历 | `test_data.py` | ✅ |

### 缺失测试

- 东方财富→新浪 **回退路径**（FakeAkshare 的 `stock_zh_a_hist` 从不抛异常）
- `fetch_trading_calendar` 失败场景
- `_limit_rate` ST/科创板/创业板/北交所 各规则分支
- SHA-256 指纹去重逻辑
- CSV 交易日历校验（功能本身也缺失）

---

## 6. PRD P0 覆盖缺口

| 需求 | 状态 |
|------|------|
| FR-108 复权因子与除权除息连续性校验 | ❌ |
| FR-109 历史涨跌停规则版本（北交所 30%、IPO 首日无限制） | ⚠️ 部分 |
| FR-409 退市/长期停牌估值 | ❌ |
| §9.1 证券上市前不得进入股票池 | ❌ |

---

## 7. 修复优先级

| 优先级 | 项目 | 工作量 |
|--------|------|--------|
| P0 | CRIT-01 ST 涨跌停检测 | ~5 行 |
| P0 | CRIT-02 北交所 30% | ~3 行 |
| P1 | MAJ-01 CSV 日历校验 | ~15 行 |
| P1 | MAJ-02 AkShare 异步化 | ~10 行 |
| P1 | MAJ-03 真实名称提取 | ~5 行 |
| P2 | MAJ-04 涨跌停 epsilon | ~5 行 |
| P2 | MAJ-05 新浪回退列映射 | ~10 行 |
| P2 | MAJ-06 useEffect 竞态 | ~8 行 |

---

*本报告基于 PRD.md V1.1 和 2026-06-22 的 working tree diff 生成。*
