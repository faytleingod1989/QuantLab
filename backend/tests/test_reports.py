from io import BytesIO

from pypdf import PdfReader

from backend.reports import (
    paginate_trades,
    render_html_report,
    render_markdown_report,
    render_pdf_report,
    summarize_run_comparison,
)


def test_paginate_trades_clamps_limit_and_offset():
    result = {"trades": [{"id": index} for index in range(5)]}
    page = paginate_trades(result, limit=2, offset=1)
    assert page["total"] == 5
    assert page["items"] == [{"id": 1}, {"id": 2}]
    assert paginate_trades(result, limit=999, offset=-1)["limit"] == 500


def test_paginate_trades_filters_by_side():
    result = {
        "trades": [
            {"id": 1, "side": "买入"},
            {"id": 2, "side": "卖出"},
            {"id": 3, "side": "买入"},
        ]
    }
    page = paginate_trades(result, limit=10, side="买入")
    assert page["side"] == "买入"
    assert page["total"] == 2
    assert [item["id"] for item in page["items"]] == [1, 3]


def test_summarize_run_comparison_extracts_core_metrics():
    rows = summarize_run_comparison([_sample_record()])
    assert rows == [
        {
            "id": "abc",
            "strategy": "均线多头",
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "finished_at": None,
            "total_return": 0.12,
            "annual_return": 0.2,
            "max_drawdown": -0.05,
            "sharpe": 1.2,
            "trade_count": 1,
        }
    ]


def test_render_markdown_report_contains_metrics_quality_and_trades():
    report = render_markdown_report(
        {
            "id": "run-1",
            "status": "completed",
            "config": {"signal_price_mode": "adjusted", "report_note": "测试备注"},
            "result": {
                "strategy": "均线策略",
                "period": {"start": "2024-01-01", "end": "2024-12-31"},
                "data_source": "csv",
                "metrics": {"total_return": 0.12, "trade_count": 1, "final_equity": 1120000},
                "benchmark": {"label": "沪深300"},
                "data_quality": {
                    "signal_price_mode": "adjusted",
                    "quality_checks": [
                        {
                            "check_name": "adjustment_continuity",
                            "severity": "pass",
                            "message": "复权连续性检查未发现异常跳变。",
                        }
                    ],
                },
                "assumptions": ["T+1"],
                "trades": [
                    {
                        "date": "2024-01-02",
                        "symbol": "600519.SH",
                        "name": "贵州茅台",
                        "side": "买入",
                        "price": 10,
                        "quantity": 100,
                        "pnl": None,
                    }
                ],
            },
        }
    )
    assert "# QuantLab 回测报告：均线策略" in report
    assert "adjustment_continuity" in report
    assert "600519.SH" in report
    assert "研究备注" in report


def test_render_html_report_contains_svg_and_order_events():
    report = render_html_report(_sample_record())
    assert "<svg" in report
    assert "涨停未成交" in report
    assert "600519.SH" in report


def test_render_pdf_report_returns_readable_pdf():
    content = render_pdf_report(_sample_record())
    assert content.startswith(b"%PDF")
    reader = PdfReader(BytesIO(content))
    assert len(reader.pages) >= 1


def _sample_record():
    return {
        "id": "abc",
        "status": "completed",
        "config": {"strategy": {"name": "均线多头"}, "start_date": "2024-01-01", "end_date": "2024-01-31", "report_note": "测试备注"},
        "result": {
            "strategy": "均线多头",
            "period": {"start": "2024-01-01", "end": "2024-01-31"},
            "benchmark": {"label": "沪深300"},
            "metrics": {
                "total_return": 0.12,
                "annual_return": 0.2,
                "max_drawdown": -0.05,
                "sharpe": 1.2,
                "win_rate": 0.5,
                "trade_count": 1,
                "final_equity": 112000,
            },
            "data_quality": {
                "signal_price_mode": "adjusted",
                "quality_checks": [{"check_name": "adjustment_continuity", "severity": "pass", "message": "ok"}],
            },
            "equity_curve": [
                {"date": "2024-01-01", "equity": 0.0, "benchmark": 0.0, "drawdown": 0.0},
                {"date": "2024-01-31", "equity": 0.12, "benchmark": 0.02, "drawdown": -0.01},
            ],
            "order_events": [{"reason": "涨停未成交"}],
            "assumptions": ["T+1"],
            "trades": [
                {"date": "2024-01-02", "symbol": "600519.SH", "name": "贵州茅台", "side": "买入", "price": 100, "quantity": 100, "pnl": None}
            ],
        },
    }
