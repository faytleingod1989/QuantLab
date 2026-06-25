from backend.data import sample_daily
import numpy as np
import pandas as pd
import pytest

from backend.engine import _condition, _fee, _money, _passes_stock_filters, _rsi, run_backtest
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


def test_macd_and_bollinger_conditions_generate_boolean_signals():
    dates = pd.bdate_range("2024-01-02", periods=40)
    close = pd.Series(np.r_[np.linspace(10, 9, 20), np.linspace(9, 13, 20)])
    frame = pd.DataFrame(
        {
            "trade_date": dates,
            "close": close,
            "signal_close": close,
        }
    )
    macd = _condition(frame, RuleCondition(indicator="macd", operator="cross_above", left=12, right=26, threshold=9))
    bollinger = _condition(frame, RuleCondition(indicator="bollinger", operator="above", left=20, right=20, threshold=2))
    assert macd.dtype == bool
    assert bollinger.dtype == bool


def test_advanced_strategy_conditions_generate_expected_signals():
    dates = pd.bdate_range("2024-01-02", periods=90)
    close = pd.Series(np.linspace(10, 20, 90))
    frame = pd.DataFrame(
        {
            "trade_date": dates,
            "open": close * 0.995,
            "close": close,
            "signal_close": close,
            "volume": [1000] * 80 + [500] * 10,
        }
    )
    assert _condition(frame, RuleCondition(indicator="ma_stack", operator="above", left=10, right=20, threshold=60)).iloc[-1]
    assert _condition(frame, RuleCondition(indicator="volume_vs_ma", operator="below", left=5, threshold=1.1)).iloc[-1]
    assert _condition(frame, RuleCondition(indicator="kline_up_ratio", operator="above", left=10, threshold=1.5)).iloc[-1]
    assert _condition(frame, RuleCondition(indicator="body_amplitude", operator="below", left=10, threshold=0.1)).iloc[-1]
    assert _condition(frame, RuleCondition(indicator="price_ma_deviation", operator="below", left=10, threshold=1.05)).iloc[-1]


def test_indicator_defaults_are_normalized_and_invalid_periods_rejected():
    macd = RuleCondition(indicator="macd")
    assert (macd.left, macd.right, macd.threshold) == (12, 26, 9)
    bollinger = RuleCondition(indicator="bollinger")
    assert bollinger.threshold == 2
    with pytest.raises(ValueError, match="短周期"):
        RuleCondition(indicator="macd", left=26, right=12, threshold=9)


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


def test_adjusted_signal_mode_uses_adjusted_close_but_executes_unadjusted_open():
    frame = pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2024-01-02", periods=6),
            "symbol": ["600519.SH"] * 6,
            "name": ["贵州茅台"] * 6,
            "open": [10, 10, 10, 10, 10, 10],
            "high": [10.5, 10.5, 10.5, 10.5, 10.5, 10.5],
            "low": [9.8, 9.8, 9.8, 9.8, 9.8, 9.8],
            "close": [10, 10, 10, 10, 10, 10],
            "adjusted_close": [10, 10, 10, 10, 15, 15],
            "prev_close": [10, 10, 10, 10, 10, 10],
            "volume": [1_000_000] * 6,
            "amount": [10_000_000] * 6,
            "limit_up": [11] * 6,
            "limit_down": [9] * 6,
            "suspended": [False] * 6,
        }
    )
    request = BacktestRequest(
        symbols=["600519.SH"],
        start_date="2024-01-02",
        end_date="2024-01-09",
        signal_price_mode="adjusted",
        strategy=VisualStrategy(
            buy_conditions=[
                RuleCondition(indicator="price_vs_ma", operator="cross_above", left=2)
            ],
            sell_conditions=[],
        ),
    )
    result = run_backtest({"600519.SH": frame}, request)
    assert any(trade["side"] == "买入" for trade in result["trades"])
    assert result["trades"][-1]["price"] == 10.0
    assert any("复权收盘价" in item for item in result["assumptions"])


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


def test_single_symbol_position_cap_limits_buy_value():
    request = _cross_request(["AAA.SH"], max_position=0.95)
    request.max_symbol_position = 0.20
    result = run_backtest({"AAA.SH": _cross_frame("AAA.SH")}, request)
    buy_value = sum(trade["value"] for trade in result["trades"] if trade["side"] == "买入")
    assert buy_value <= request.initial_cash * request.max_symbol_position


def _rank_frame(symbol: str, start: float, end: float) -> pd.DataFrame:
    close = np.linspace(start, end, 25)
    return pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2024-01-02", periods=25),
            "symbol": symbol,
            "name": symbol,
            "open": close,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "prev_close": np.r_[close[0], close[:-1]],
            "volume": [1_000_000] * 25,
            "amount": close * 1_000_000,
            "limit_up": close + 1.0,
            "limit_down": np.maximum(close - 1.0, 0.01),
            "suspended": [False] * 25,
        }
    )


def test_candidate_sort_and_max_hold_limit_select_lowest_recent_return():
    symbols = ["AAA.SH", "BBB.SH", "CCC.SH"]
    request = BacktestRequest(
        symbols=symbols,
        start_date="2024-01-02",
        end_date="2024-02-05",
        max_symbol_position=0.2,
        strategy=VisualStrategy(
            max_hold_num=2,
            candidate_sort="return_asc",
            sort_window=20,
            buy_conditions=[
                RuleCondition(indicator="return_between", left=20, lower=-1, upper=1)
            ],
            sell_conditions=[],
        ),
    )
    result = run_backtest(
        {
            "AAA.SH": _rank_frame("AAA.SH", 10, 12),
            "BBB.SH": _rank_frame("BBB.SH", 10, 11),
            "CCC.SH": _rank_frame("CCC.SH", 10, 14),
        },
        request,
    )
    bought = {trade["symbol"] for trade in result["trades"] if trade["side"] == "买入"}
    assert bought == {"AAA.SH", "BBB.SH"}
    assert any("最多持有 2 只" in item for item in result["assumptions"])


def test_stock_pool_filter_excludes_st_buy_candidates():
    frame = _cross_frame("AAA.SH")
    frame["name"] = "ST测试"
    request = _cross_request(["AAA.SH"])
    request.exclude_st = True
    result = run_backtest({"AAA.SH": frame}, request)
    assert result["trades"] == []
    assert any(event["reason"] == "ST过滤" for event in result["order_events"])


def test_stock_pool_filter_uses_listing_trading_sessions_before_calendar_days():
    request = _cross_request(["AAA.SH"])
    request.min_listed_days = 2
    row = pd.Series(
        {
            "name": "AAA.SH",
            "listed_date": pd.Timestamp("2024-01-05"),
            "listing_session": 2,
            "average_amount_20": 100_000_000,
        }
    )
    passed, reason = _passes_stock_filters(row, request, pd.Timestamp("2024-01-08"))
    assert passed is False
    assert reason == "上市天数不足"


def test_stop_loss_exits_position_before_signal_sell():
    frame = _cross_frame("AAA.SH")
    extras = pd.DataFrame(
        {
            "trade_date": [pd.Timestamp("2024-01-10"), pd.Timestamp("2024-01-11")],
            "symbol": ["AAA.SH", "AAA.SH"],
            "name": ["AAA.SH", "AAA.SH"],
            "open": [2.0, 2.0],
            "high": [2.1, 2.1],
            "low": [1.9, 1.9],
            "close": [2.0, 2.0],
            "prev_close": [3.0, 2.0],
            "volume": [1_000_000, 1_000_000],
            "amount": [2_000_000, 2_000_000],
            "limit_up": [3.3, 2.2],
            "limit_down": [2.7, 1.8],
            "suspended": [False, False],
        }
    )
    frame = pd.concat([frame, extras], ignore_index=True)
    request = _cross_request(["AAA.SH"])
    request.stop_loss_pct = 0.20
    request.end_date = "2024-01-11"
    result = run_backtest({"AAA.SH": frame}, request)
    assert any(trade["side"] == "卖出" and trade["reason"] == "止损" for trade in result["trades"])


def test_adjusted_signal_mode_skips_stop_loss_on_corporate_action_day():
    frame = _cross_frame("AAA.SH")
    extras = pd.DataFrame(
        {
            "trade_date": [pd.Timestamp("2024-01-10"), pd.Timestamp("2024-01-11")],
            "symbol": ["AAA.SH", "AAA.SH"],
            "name": ["AAA.SH", "AAA.SH"],
            "open": [1.5, 1.5],
            "high": [1.6, 1.6],
            "low": [1.4, 1.4],
            "close": [1.5, 1.5],
            "adjusted_close": [3.0, 3.0],
            "corporate_action": [True, False],
            "prev_close": [3.0, 1.5],
            "volume": [1_000_000, 1_000_000],
            "amount": [1_500_000, 1_500_000],
            "limit_up": [3.3, 1.65],
            "limit_down": [2.7, 1.35],
            "suspended": [False, False],
        }
    )
    frame = pd.concat([frame, extras], ignore_index=True)
    frame["adjusted_close"] = frame["adjusted_close"].where(frame["adjusted_close"].notna(), frame["close"])
    frame["corporate_action"] = frame["corporate_action"].where(frame["corporate_action"].notna(), False).astype(bool)
    request = _cross_request(["AAA.SH"])
    request.signal_price_mode = "adjusted"
    request.stop_loss_pct = 0.20
    request.end_date = "2024-01-11"
    result = run_backtest({"AAA.SH": frame}, request)
    assert not any(trade["side"] == "卖出" and trade["reason"] == "止损" for trade in result["trades"])


def test_empty_date_range_is_rejected_cleanly():
    request = BacktestRequest(
        symbols=["600519.SH"], start_date="2030-01-01", end_date="2030-12-31"
    )
    with pytest.raises(ValueError, match="没有可用于回测"):
        run_backtest({"600519.SH": sample_daily("600519.SH")}, request)
