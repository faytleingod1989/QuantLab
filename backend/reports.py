from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path
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


def summarize_run_comparison(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        result = record.get("result") or {}
        config = record.get("config") or {}
        metrics = result.get("metrics") or {}
        period = result.get("period") or {}
        rows.append(
            {
                "id": record.get("id"),
                "strategy": _strategy_name(result, config),
                "start_date": period.get("start", config.get("start_date")),
                "end_date": period.get("end", config.get("end_date")),
                "finished_at": record.get("finished_at") or record.get("created_at"),
                "total_return": float(metrics.get("total_return") or 0),
                "annual_return": float(metrics.get("annual_return") or 0),
                "max_drawdown": float(metrics.get("max_drawdown") or 0),
                "sharpe": float(metrics.get("sharpe") or 0),
                "trade_count": int(metrics.get("trade_count") or 0),
            }
        )
    return rows


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
        f"# QuantLab 回测报告：{_strategy_name(result, config)}",
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
        lines.extend(["| 日期 | 代码 | 名称 | 方向 | 原因 | 价格 | 数量 | 收益 |", "|---|---|---|---|---|---:|---:|---:|"])
        for trade in trades[:20]:
            lines.append(
                "| {date} | {symbol} | {name} | {side} | {reason} | {price} | {quantity} | {pnl} |".format(
                    date=trade.get("date"),
                    symbol=trade.get("symbol"),
                    name=trade.get("name", ""),
                    side=trade.get("side"),
                    reason=trade.get("reason", "信号"),
                    price=trade.get("price"),
                    quantity=trade.get("quantity"),
                    pnl="—" if trade.get("pnl") is None else trade.get("pnl"),
                )
            )
    else:
        lines.append("- 本次回测没有成交记录。")
    lines.extend(["", "> 回测结果仅用于研究，不代表未来收益。", ""])
    return "\n".join(lines)


def render_html_report(record: dict[str, Any]) -> str:
    result = record.get("result") or {}
    config = record.get("config") or {}
    metrics = result.get("metrics") or {}
    period = result.get("period") or {}
    benchmark = result.get("benchmark") or {}
    data_quality = result.get("data_quality") or {}
    quality_checks = data_quality.get("quality_checks") or []
    assumptions = result.get("assumptions") or []
    trades = result.get("trades") or []
    events = result.get("order_events") or []
    title = _strategy_name(result, config)

    metric_cards = "".join(
        f"<article><span>{escape(label)}</span><b>{escape(value)}</b></article>"
        for label, value in [
            ("累计收益", _pct(metrics.get("total_return"))),
            ("年化收益", _pct(metrics.get("annual_return"))),
            ("最大回撤", _pct(metrics.get("max_drawdown"))),
            ("夏普比率", _num(metrics.get("sharpe"))),
            ("胜率", _pct(metrics.get("win_rate"))),
            ("交易次数", str(metrics.get("trade_count", 0))),
        ]
    )
    quality_rows = "".join(
        f"<tr><td>{escape(str(check.get('check_name', '')))}</td><td>{escape(str(check.get('severity', '')))}</td><td>{escape(str(check.get('message', '')))}</td></tr>"
        for check in quality_checks
    ) or '<tr><td colspan="3">当前回测未关联固定数据集质量检查。</td></tr>'
    trade_rows = "".join(
        "<tr><td>{date}</td><td>{symbol}</td><td>{name}</td><td>{side}</td><td>{reason}</td><td>{price}</td><td>{quantity}</td><td>{pnl}</td></tr>".format(
            date=escape(str(trade.get("date", ""))),
            symbol=escape(str(trade.get("symbol", ""))),
            name=escape(str(trade.get("name", ""))),
            side=escape(str(trade.get("side", ""))),
            reason=escape(str(trade.get("reason", "信号"))),
            price=escape(str(trade.get("price", ""))),
            quantity=escape(str(trade.get("quantity", ""))),
            pnl="-" if trade.get("pnl") is None else escape(str(trade.get("pnl"))),
        )
        for trade in trades[:30]
    ) or '<tr><td colspan="8">本次回测没有成交记录。</td></tr>'
    event_chips = "".join(
        f"<span>{escape(reason)} <b>{count}</b></span>" for reason, count in _event_counts(events)
    ) or "<span>暂无拒单</span>"
    assumptions_html = "".join(f"<li>{escape(str(item))}</li>" for item in assumptions)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>QuantLab 回测报告 - {escape(title)}</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, "Microsoft YaHei", sans-serif; background:#071014; color:#d9e1e3; }}
    body {{ margin:0; padding:32px; background:#071014; }}
    main {{ max-width:1080px; margin:auto; }}
    header {{ border:1px solid #223036; border-radius:12px; padding:28px; background:linear-gradient(135deg,#0b1519,#10252a); }}
    h1 {{ margin:0 0 8px; font-size:28px; }}
    p, li {{ color:#91a0a5; line-height:1.7; }}
    .meta, .events {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; }}
    .meta span, .events span {{ border:1px solid #223036; border-radius:999px; padding:7px 12px; color:#aab7bb; background:#0b1519; }}
    .metrics {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin:18px 0; }}
    article, section {{ border:1px solid #223036; border-radius:10px; background:#0b1519; }}
    article {{ padding:18px; }}
    article span {{ display:block; color:#77868c; font-size:12px; }}
    article b {{ display:block; margin-top:8px; font-size:24px; }}
    section {{ padding:22px; margin-top:16px; }}
    h2 {{ margin:0 0 14px; font-size:18px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th, td {{ border-bottom:1px solid #19262c; padding:9px 8px; text-align:left; }}
    th {{ color:#7f8e93; font-weight:600; }}
    .chart {{ width:100%; height:220px; border:1px solid #19262c; border-radius:8px; background:#091318; }}
    footer {{ margin-top:18px; color:#65757b; font-size:12px; }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>{escape(title)}</h1>
    <p>QuantLab A 股日线回测报告。回测结果仅用于研究，不代表未来收益。</p>
    <div class="meta">
      <span>任务 {escape(str(record.get('id', '')))}</span>
      <span>{escape(str(period.get('start', config.get('start_date', ''))))} 至 {escape(str(period.get('end', config.get('end_date', ''))))}</span>
      <span>基准 {escape(str(benchmark.get('label', config.get('benchmark', '000300.SH'))))}</span>
      <span>信号口径 {escape(str(data_quality.get('signal_price_mode', config.get('signal_price_mode', 'unadjusted'))))}</span>
    </div>
  </header>
  <div class="metrics">{metric_cards}</div>
  <section><h2>净值/回撤走势</h2>{_equity_svg(result.get('equity_curve') or [])}</section>
  <section><h2>订单拒绝统计</h2><div class="events">{event_chips}</div></section>
  <section><h2>数据质量检查</h2><table><thead><tr><th>检查项</th><th>级别</th><th>说明</th></tr></thead><tbody>{quality_rows}</tbody></table></section>
  <section><h2>假设与撮合口径</h2><ul>{assumptions_html}</ul></section>
  <section><h2>最近交易记录</h2><table><thead><tr><th>日期</th><th>代码</th><th>名称</th><th>方向</th><th>原因</th><th>价格</th><th>数量</th><th>收益</th></tr></thead><tbody>{trade_rows}</tbody></table></section>
  <footer>Generated by QuantLab</footer>
</main>
</body>
</html>"""


def render_pdf_report(record: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle, Paragraph

    font_name = _register_pdf_font(pdfmetrics, TTFont)
    result = record.get("result") or {}
    config = record.get("config") or {}
    metrics = result.get("metrics") or {}
    data_quality = result.get("data_quality") or {}
    quality_checks = data_quality.get("quality_checks") or []
    trades = result.get("trades") or []
    events = result.get("order_events") or []
    title = _strategy_name(result, config)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CJKTitle", parent=styles["Title"], fontName=font_name, fontSize=20, leading=26))
    styles.add(ParagraphStyle(name="CJKHeading", parent=styles["Heading2"], fontName=font_name, fontSize=13, leading=18, spaceBefore=12))
    styles.add(ParagraphStyle(name="CJKBody", parent=styles["BodyText"], fontName=font_name, fontSize=9, leading=14))
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    quality_rows = [["检查项", "级别", "说明"]]
    if quality_checks:
        quality_rows += [
            [str(check.get("check_name", "")), str(check.get("severity", "")), str(check.get("message", ""))]
            for check in quality_checks[:8]
        ]
    else:
        quality_rows.append(["-", "-", "当前回测未关联固定数据集质量检查。"])
    trade_rows = [["日期", "代码", "方向", "原因", "价格", "数量", "收益"]]
    if trades:
        trade_rows += [
            [
                str(trade.get("date", "")),
                str(trade.get("symbol", "")),
                str(trade.get("side", "")),
                str(trade.get("reason", "信号")),
                str(trade.get("price", "")),
                str(trade.get("quantity", "")),
                "-" if trade.get("pnl") is None else str(trade.get("pnl")),
            ]
            for trade in trades[:18]
        ]
    else:
        trade_rows.append(["-", "-", "-", "-", "-", "-", "本次回测没有成交记录"])

    story = [
        Paragraph(f"QuantLab 回测报告：{title}", styles["CJKTitle"]),
        Paragraph("回测结果仅用于研究，不代表未来收益。", styles["CJKBody"]),
        Spacer(1, 8),
        Paragraph("核心指标", styles["CJKHeading"]),
        _pdf_table(
            [["指标", "数值"],
             ["累计收益", _pct(metrics.get("total_return"))],
             ["年化收益", _pct(metrics.get("annual_return"))],
             ["最大回撤", _pct(metrics.get("max_drawdown"))],
             ["夏普比率", _num(metrics.get("sharpe"))],
             ["胜率", _pct(metrics.get("win_rate"))],
             ["交易次数", str(metrics.get("trade_count", 0))],
             ["期末权益", _money(metrics.get("final_equity"))]],
            font_name,
        ),
        Paragraph("订单拒绝统计", styles["CJKHeading"]),
        Paragraph("；".join(f"{reason}: {count}" for reason, count in _event_counts(events)) or "暂无拒单", styles["CJKBody"]),
        Paragraph("数据质量检查", styles["CJKHeading"]),
        _pdf_table(quality_rows, font_name),
        Paragraph("最近交易记录", styles["CJKHeading"]),
        _pdf_table(trade_rows, font_name),
    ]
    doc.build(story)
    return buffer.getvalue()


def _strategy_name(result: dict[str, Any], config: dict[str, Any]) -> str:
    strategy = config.get("strategy") if isinstance(config.get("strategy"), dict) else {}
    return str(result.get("strategy") or strategy.get("name") or "未命名策略")


def _event_counts(events: list[dict[str, Any]]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for event in events:
        reason = str(event.get("reason") or "其他")
        counts[reason] = counts.get(reason, 0) + 1
    return sorted(counts.items(), key=lambda item: item[1], reverse=True)


def _equity_svg(curve: list[dict[str, Any]]) -> str:
    if len(curve) < 2:
        return '<div class="chart"></div>'
    width, height, padding = 900, 220, 20
    series = [float(point.get("equity") or 0) for point in curve]
    benchmark = [float(point.get("benchmark") or 0) for point in curve]
    values = series + benchmark
    low, high = min(values), max(values)
    if low == high:
        low, high = low - 0.01, high + 0.01

    def points(items: list[float]) -> str:
        output = []
        for index, value in enumerate(items):
            x = padding + index * ((width - padding * 2) / max(1, len(items) - 1))
            y = height - padding - ((value - low) / (high - low)) * (height - padding * 2)
            output.append(f"{x:.1f},{y:.1f}")
        return " ".join(output)

    return f'''<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="净值走势">
  <polyline points="{points(series)}" fill="none" stroke="#35c4bd" stroke-width="3" />
  <polyline points="{points(benchmark)}" fill="none" stroke="#899399" stroke-width="2" />
</svg>'''


def _register_pdf_font(pdfmetrics, TTFont) -> str:
    candidates = [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    ]
    for path in candidates:
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont("QuantLabCJK", str(path)))
                return "QuantLabCJK"
            except Exception:
                continue
    return "Helvetica"


def _pdf_table(rows: list[list[str]], font_name: str):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    table = Table(rows, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#10252a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d7dee2")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f8f9")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _pct(value) -> str:
    return f"{float(value or 0) * 100:.2f}%"


def _num(value) -> str:
    return f"{float(value or 0):.2f}"


def _money(value) -> str:
    return f"{float(value or 0):,.2f}"
