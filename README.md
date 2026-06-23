# QuantLab

面向沪深 A 股的本地 Web 量化策略研究与日线回测平台。当前版本提供可视化双均线策略、A 股基础交易约束、异步回测、版本化策略管理、AkShare 真实日线、CSV 和可复现演示行情。

## 已实现

- 可视化配置股票池、买入条件、卖出条件与仓位。
- 项目、策略和不可变策略版本持久化；回测记录关联项目、策略、策略版本及数据指纹。
- 收盘产生信号，下一交易日开盘成交。
- T+1、100 股交易单位、佣金、最低佣金、印花税、过户费和滑点。
- 涨停不买、跌停不卖的保守成交假设。
- 累计收益、年化收益、最大回撤、夏普比率、胜率和交易次数。
- 净值曲线、回撤曲线、月度收益热力图和完整交易记录。
- SQLite 持久化异步任务、进度、取消状态及历史结果。
- CSV 导入、OHLC 校验、SHA-256 数据指纹、重复检测和预览 API。
- AkShare 真实沪深日线、沪深300基准、交易日历和东方财富/新浪双源回退。
- 数据集先固化为不可变快照，再通过日期与标的受限的 DataView 进入回测引擎。
- 日线数据接口，并通过 `frequency` 抽象预留分钟线扩展。

## 启动

环境要求：Python 3.12+、Node.js 20+。

```powershell
python -m pip install -r backend\requirements.txt
Set-Location frontend
npm install
Set-Location ..
.\run.ps1
```

- Web：http://127.0.0.1:5173
- API 文档：http://127.0.0.1:8000/docs
- 默认数据库：`data/quantlab.db`
- 导入数据：`data/datasets/`

## 测试

```powershell
python -m pytest backend\tests -q
Set-Location frontend
npm run build
```

当前回归结果：后端 20 项测试通过，前端生产构建通过。

## 数据说明

数据中心可将 AkShare 真实行情同步为本地固定快照，也可导入 CSV。回测任务只读取快照，不在计算过程中联网，以保证结果可复现。AkShare 不可用时仍可使用 CSV 或确定性的离线演示行情；演示行情仅用于验证流程和引擎。

CSV 至少需要以下字段：

```text
trade_date,symbol,open,high,low,close,volume
```

数据集接口：`POST /api/datasets/akshare`、`POST /api/datasets/csv`、`GET /api/datasets`、`GET /api/datasets/{id}/preview`。交易日历：`GET /api/data/calendar`。

策略接口：`GET/POST /api/projects`、`GET /api/projects/{id}/strategies`、`POST /api/strategies`、`GET/POST /api/strategies/{id}/versions`。

可选环境变量：

```powershell
$env:VITE_API_BASE="http://127.0.0.1:8000/api"
$env:QUANTLAB_CORS_ORIGINS="http://127.0.0.1:5173,http://localhost:5173"
$env:QUANTLAB_LOG_LEVEL="INFO"
$env:QUANTLAB_DB_PATH="E:\AI Project\QM\data\quantlab.db"
$env:QUANTLAB_BACKTEST_WORKERS="2"
```

## 风险提示

历史回测不代表未来收益。本项目当前是研究工具，不连接券商、不执行实盘交易。
