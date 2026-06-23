from __future__ import annotations

from typing import Any


def paginate_trades(
    result: dict[str, Any],
    limit: int = 50,
    offset: int = 0,
    side: str | None = None,
) -> dict[str, Any]:
    trades = list(result.get("trades") or [])
    if side in {"买入", "卖出"}:
        trades = [trade for trade in trades if trade.get("side") == side]
    safe_limit = max(1, min(int(limit), 500))
    safe_offset = max(0, int(offset))
    return {
        "total": len(trades),
        "limit": safe_limit,
        "offset": safe_offset,
        "side": side if side in {"买入", "卖出"} else "all",
        "items": trades[safe_offset : safe_offset + safe_limit],
    }


def render_markdown_report(record: dict[str, Any]) -> str:
    result = record.get("result") or {}
    config = record.get("config") or {}
    metrics = result.get("metrics") or {}
    period = result.get("period") or {}
    benchmark = result.get("benchmark") or {}
    data_quality = result.get("data_quality") or {}
    quality_checks = data_quality.get("quality_checks") or []
    trades = result.get("trades") or []
    assumptions = result.get("assumptions") or []

    lines = [
        f"# QuantLab 回测报告：{result.get('strategy', config.get('strategy', {}).get('name', '未命名策略'))}",
        "",
        "## 基本信息",
        "",
        f"- 任务 ID：`{record.get('id')}`",
        f"- 状态：{record.get('status')}",
        f"- 回测区间：{period.get('start', config.get('start_date'))} 至 {period.get('end', config.get('end_date'))}",
        f"- 数据来源：{result.get('data_source', 'unknown')}",
        f"- 信号价格口径：{data_quality.get('signal_price_mode', config.get('signal_price_mode', 'unadjusted'))}",
        f"- 基准：{benchmark.get('label', config.get('benchmark', '000300.SH'))}",
        "",
        "## 核心指标",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| 累计收益 | {_pct(metrics.get('total_return'))} |",
        f"| 年化收益 | {_pct(metrics.get('annual_return'))} |",
        f"| 最大回撤 | {_pct(metrics.get('max_drawdown'))} |",
        f"| 夏普比率 | {_num(metrics.get('sharpe'))} |",
        f"| 胜率 | {_pct(metrics.get('win_rate'))} |",
        f"| 交易次数 | {metrics.get('trade_count', 0)} |",
        f"| 期末权益 | {_money(metrics.get('final_equity'))} |",
        "",
        "## 数据质量检查",
        "",
    ]
    if quality_checks:
        lines.extend(["| 检查项 | 级别 | 说明 |", "|---|---|---|"])
        for check in quality_checks:
            lines.append(
                f"| {check.get('check_name')} | {check.get('severity')} | {check.get('message')} |"
            )
    else:
        lines.append("- 当前回测未关联固定数据集质量检查。")
    lines.extend(["", "## 假设与撮合口径", ""])
    lines.extend([f"- {item}" for item in assumptions])
    lines.extend(["", "## 最近交易记录", ""])
    if trades:
        lines.extend(["| 日期 | 代码 | 名称 | 方向 | 价格 | 数量 | 收益 |", "|---|---|---|---|---:|---:|---:|"])
        for trade in trades[:20]:
            lines.append(
                "| {date} | {symbol} | {name} | {side} | {price} | {quantity} | {pnl} |".format(
                    date=trade.get("date"),
                    symbol=trade.get("symbol"),
                    name=trade.get("name", ""),
                    side=trade.get("side"),
                    price=trade.get("price"),
                    quantity=trade.get("quantity"),
                    pnl="—" if trade.get("pnl") is None else trade.get("pnl"),
                )
            )
    else:
        lines.append("- 本次回测没有成交记录。")
    lines.extend(["", "> 回测结果仅用于研究，不代表未来收益。", ""])
    return "\n".join(lines)


def _pct(value) -> str:
    return f"{float(value or 0) * 100:.2f}%"


def _num(value) -> str:
    return f"{float(value or 0):.2f}"


def _money(value) -> str:
    return f"{float(value or 0):,.2f}"
