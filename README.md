# QuantLab

面向沪深 A 股的本地 Web 量化策略研究与日线回测平台。当前版本提供可视化双均线策略、A 股基础交易约束、异步回测、版本化策略管理和可复现的离线演示行情。

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

当前回归结果：后端 16 项测试通过，前端生产构建通过。

## 数据说明

尚未接入真实 AkShare 数据时，系统使用确定性的离线演示行情。策略标的与“演示沪深300”基准来自彼此独立的行情序列，但均不是真实证券历史数据，仅用于验证产品流程和回测引擎。

CSV 至少需要以下字段：

```text
trade_date,symbol,open,high,low,close,volume
```

数据集接口：`POST /api/datasets/csv`、`GET /api/datasets`、`GET /api/datasets/{id}/preview`。

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
