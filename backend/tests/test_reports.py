from backend.reports import paginate_trades, render_markdown_report


def test_paginate_trades_clamps_limit_and_offset():
    result = {"trades": [{"id": index} for index in range(5)]}
    page = paginate_trades(result, limit=2, offset=1)
    assert page["total"] == 5
    assert page["items"] == [{"id": 1}, {"id": 2}]
    assert paginate_trades(result, limit=999, offset=-1)["limit"] == 500


def test_render_markdown_report_contains_metrics_quality_and_trades():
    report = render_markdown_report(
        {
            "id": "run-1",
            "status": "completed",
            "config": {"signal_price_mode": "adjusted"},
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
