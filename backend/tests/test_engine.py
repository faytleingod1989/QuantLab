from backend.data import sample_daily
import numpy as np
import pandas as pd
import pytest

from backend.engine import _fee, _money, _rsi, run_backtest
from backend.models import BacktestRequest, RuleCondition, VisualStrategy


def test_backtest_is_deterministic_and_balanced():
    request = BacktestRequest(
        symbols=["600519.SH", "000333.SZ"],
        start_date="2020-01-01",
        end_date="2022-12-31",
    )
    data = {symbol: sample_daily(symbol) for symbol in request.symbols}
    benchmark = sample_daily(request.benchmark)
    first = run_backtest(data, request, benchmark, benchmark_is_demo=True)
    second = run_backtest(data, request, benchmark, benchmark_is_demo=True)
    assert first["metrics"] == second["metrics"]
    assert first["metrics"]["final_equity"] > 0
    assert first["metrics"]["trade_count"] > 0
    assert all(trade["quantity"] % request.lot_size == 0 for trade in first["trades"])
    assert len(first["trades"]) == first["metrics"]["trade_count"]
    assert first["benchmark"]["is_demo"] is True


def test_t_plus_one_assumption_is_disclosed():
    request = BacktestRequest(symbols=["600036.SH"], start_date="2021-01-01", end_date="2021-12-31")
    result = run_backtest({"600036.SH": sample_daily("600036.SH")}, request)
    assert any("下一交易日可卖" in item for item in result["assumptions"])


def test_money_and_fee_round_half_up_to_cents():
    assert _money(1.005) == 1.01
    request = BacktestRequest(
        commission_rate=0.00025,
        min_commission=5,
        stamp_duty_rate=0.0005,
        transfer_fee_rate=0.00001,
    )
    assert _fee(10_000, request, False) == 5.10
    assert _fee(10_000, request, True) == 10.10


def test_wilder_rsi_matches_independent_recursive_reference():
    values = pd.Series(
        [44, 44.15, 43.9, 44.35, 44.8, 45.1, 44.7, 45.25, 45.6, 45.2,
         45.9, 46.1, 45.75, 46.4, 46.8, 47.1, 46.6, 47.4, 47.8, 47.2],
        dtype=float,
    )
    period = 14
    delta = values.diff()
    gains = delta.clip(lower=0).fillna(0.0)
    losses = (-delta.clip(upper=0)).fillna(0.0)
    average_gain = gains.iloc[1 : period + 1].mean()
    average_loss = losses.iloc[1 : period + 1].mean()
    expected = 100 - 100 / (1 + average_gain / average_loss)
    assert _rsi(values, period).iloc[period] == pytest.approx(expected, abs=1e-10)


def test_benchmark_uses_independent_price_series_not_strategy_return():
    request = BacktestRequest(
        symbols=["600519.SH"], start_date="2020-01-01", end_date="2020-12-31"
    )
    benchmark = sample_daily("000300.SH")
    result = run_backtest(
        {"600519.SH": sample_daily("600519.SH")},
        request,
        benchmark,
        benchmark_is_demo=True,
    )
    dates = pd.to_datetime([point["date"] for point in result["equity_curve"]])
    aligned = benchmark.set_index("trade_date")["close"].reindex(dates, method="ffill")
    expected = aligned.iloc[-1] / aligned.iloc[0] - 1
    assert result["equity_curve"][-1]["benchmark"] == pytest.approx(expected, abs=5e-5)
    assert result["equity_curve"][-1]["benchmark"] != pytest.approx(
        max(result["metrics"]["total_return"] * 0.32, 0.08), abs=1e-4
    )


def _cross_frame(symbol: str, *, blocked: str | None = None) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=6)
    close = [3.0, 2.0, 1.0, 1.0, 3.0, 3.0]
    frame = pd.DataFrame(
        {
            "trade_date": dates,
            "symbol": symbol,
            "name": symbol,
            "open": close,
            "high": np.array(close) + 0.1,
            "low": np.array(close) - 0.1,
            "close": close,
            "prev_close": [3.0, *close[:-1]],
            "volume": 1_000_000,
            "amount": np.array(close) * 1_000_000,
            "limit_up": np.array(close) + 1.0,
            "limit_down": np.maximum(np.array(close) - 1.0, 0.01),
            "suspended": False,
        }
    )
    if blocked == "limit_up":
        frame.loc[5, "limit_up"] = frame.loc[5, "open"]
    if blocked == "limit_up_exempt":
        frame.loc[5, "limit_up"] = frame.loc[5, "open"]
        frame.loc[5, "limit_exempt"] = True
    if blocked == "limit_up_cent_rounding":
        frame.loc[5, "limit_up"] = frame.loc[5, "open"] + 0.004
    if blocked == "suspended":
        frame.loc[5, "suspended"] = True
    return frame


def _cross_request(symbols: list[str], max_position: float = 0.95) -> BacktestRequest:
    return BacktestRequest(
        symbols=symbols,
        start_date="2024-01-02",
        end_date="2024-01-09",
        max_position=max_position,
        strategy=VisualStrategy(
            buy_conditions=[
                RuleCondition(
                    indicator="ma_cross", operator="cross_above", left=2, right=3
                )
            ],
            sell_conditions=[],
        ),
    )


def test_limit_up_blocks_buy_and_records_event():
    request = _cross_request(["AAA.SH"])
    result = run_backtest({"AAA.SH": _cross_frame("AAA.SH", blocked="limit_up")}, request)
    assert result["trades"] == []
    assert any(event["reason"] == "涨停未成交" for event in result["order_events"])


def test_limit_up_comparison_rounds_prices_to_cents():
    request = _cross_request(["AAA.SH"])
    result = run_backtest(
        {"AAA.SH": _cross_frame("AAA.SH", blocked="limit_up_cent_rounding")}, request
    )
    assert result["trades"] == []
    assert any(event["reason"] == "涨停未成交" for event in result["order_events"])


def test_limit_exemption_allows_ipo_day_buy_even_at_limit_price():
    request = _cross_request(["AAA.SH"])
    result = run_backtest({"AAA.SH": _cross_frame("AAA.SH", blocked="limit_up_exempt")}, request)
    assert any(trade["side"] == "买入" for trade in result["trades"])
    assert not any(event["reason"] == "涨停未成交" for event in result["order_events"])


def test_suspension_blocks_buy():
    request = _cross_request(["AAA.SH"])
    result = run_backtest({"AAA.SH": _cross_frame("AAA.SH", blocked="suspended")}, request)
    assert result["trades"] == []


def test_multi_symbol_budget_respects_portfolio_max_position():
    symbols = ["AAA.SH", "BBB.SZ"]
    request = _cross_request(symbols, max_position=0.50)
    result = run_backtest({symbol: _cross_frame(symbol) for symbol in symbols}, request)
    buy_value = sum(trade["value"] for trade in result["trades"] if trade["side"] == "买入")
    assert buy_value <= request.initial_cash * request.max_position


def test_empty_date_range_is_rejected_cleanly():
    request = BacktestRequest(
        symbols=["600519.SH"], start_date="2030-01-01", end_date="2030-12-31"
    )
    with pytest.raises(ValueError, match="没有可用于回测"):
        run_backtest({"600519.SH": sample_daily("600519.SH")}, request)
