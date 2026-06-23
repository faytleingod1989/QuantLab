from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

import numpy as np
import pandas as pd

from .models import BacktestRequest, RuleCondition


class BacktestCancelled(Exception):
    """Raised when a running backtest receives a cooperative cancellation request."""


@dataclass
class Position:
    quantity: int = 0
    available: int = 0
    unsettled: int = 0
    average_cost: float = 0.0


def _rsi(series: pd.Series, period: int) -> pd.Series:
    """Wilder RSI with an SMA seed followed by Wilder's recursive smoothing."""
    delta = series.diff()
    gain = delta.clip(lower=0).fillna(0.0)
    loss = (-delta.clip(upper=0)).fillna(0.0)
    average_gain = pd.Series(np.nan, index=series.index, dtype=float)
    average_loss = pd.Series(np.nan, index=series.index, dtype=float)
    if len(series) <= period:
        return pd.Series(50.0, index=series.index)
    average_gain.iloc[period] = gain.iloc[1 : period + 1].mean()
    average_loss.iloc[period] = loss.iloc[1 : period + 1].mean()
    for index in range(period + 1, len(series)):
        average_gain.iloc[index] = (
            average_gain.iloc[index - 1] * (period - 1) + gain.iloc[index]
        ) / period
        average_loss.iloc[index] = (
            average_loss.iloc[index - 1] * (period - 1) + loss.iloc[index]
        ) / period
    relative = average_gain / average_loss.replace(0, np.nan)
    result = 100 - 100 / (1 + relative)
    result = result.mask((average_loss == 0) & (average_gain > 0), 100.0)
    result = result.mask((average_loss == 0) & (average_gain == 0), 50.0)
    return result.fillna(50.0)


def _condition(frame: pd.DataFrame, rule: RuleCondition) -> pd.Series:
    close = frame["close"]
    if rule.indicator == "ma_cross":
        left = close.rolling(rule.left).mean()
        right = close.rolling(rule.right).mean()
        if rule.operator == "cross_above":
            return (left > right) & (left.shift(1) <= right.shift(1))
        if rule.operator == "cross_below":
            return (left < right) & (left.shift(1) >= right.shift(1))
        return left > right if rule.operator == "above" else left < right
    if rule.indicator == "price_vs_ma":
        moving = close.rolling(rule.left).mean()
        if rule.operator == "cross_above":
            return (close > moving) & (close.shift(1) <= moving.shift(1))
        if rule.operator == "cross_below":
            return (close < moving) & (close.shift(1) >= moving.shift(1))
        return close > moving if rule.operator == "above" else close < moving
    value = _rsi(close, rule.left)
    if rule.operator == "cross_above":
        return (value > rule.threshold) & (value.shift(1) <= rule.threshold)
    if rule.operator == "cross_below":
        return (value < rule.threshold) & (value.shift(1) >= rule.threshold)
    return value > rule.threshold if rule.operator == "above" else value < rule.threshold


def _combine(frame: pd.DataFrame, rules: list[RuleCondition], logic: str) -> pd.Series:
    if not rules:
        return pd.Series(False, index=frame.index)
    signals = pd.concat([_condition(frame, rule) for rule in rules], axis=1)
    return signals.all(axis=1) if logic == "all" else signals.any(axis=1)


def _fee(value: float, request: BacktestRequest, is_sell: bool) -> float:
    commission = _money(max(request.min_commission, value * request.commission_rate))
    transfer = _money(value * request.transfer_fee_rate)
    stamp = _money(value * request.stamp_duty_rate) if is_sell else 0.0
    return _money(commission + transfer + stamp)


def _money(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _price(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _at_or_below(open_price, limit_price) -> bool:
    if pd.isna(limit_price):
        return False
    return _price(open_price) <= _price(limit_price)


def _at_or_above(open_price, limit_price) -> bool:
    if pd.isna(limit_price):
        return False
    return _price(open_price) >= _price(limit_price)


def _round(value: float) -> float:
    return round(float(value), 4)


def run_backtest(
    data: dict[str, pd.DataFrame],
    request: BacktestRequest,
    benchmark_data: pd.DataFrame | None = None,
    *,
    benchmark_is_demo: bool = False,
    progress_callback=None,
    cancel_check=None,
) -> dict:
    prepared: dict[str, pd.DataFrame] = {}
    for symbol, frame in data.items():
        current = frame.copy().sort_values("trade_date")
        current = current[
            (current["trade_date"] >= pd.Timestamp(request.start_date))
            & (current["trade_date"] <= pd.Timestamp(request.end_date))
        ].reset_index(drop=True)
        current["buy_signal"] = _combine(
            current, request.strategy.buy_conditions, request.strategy.buy_logic
        )
        current["sell_signal"] = _combine(
            current, request.strategy.sell_conditions, request.strategy.sell_logic
        )
        current = current.set_index("trade_date")
        prepared[symbol] = current

    all_dates = sorted(set().union(*(set(frame.index) for frame in prepared.values())))
    if not all_dates:
        raise ValueError("所选日期范围内没有可用于回测的行情数据")
    positions = {symbol: Position() for symbol in prepared}
    cash = float(request.initial_cash)
    equity_curve: list[dict] = []
    trades: list[dict] = []
    order_events: list[dict] = []

    for date_index, date in enumerate(all_dates):
        if cancel_check and cancel_check():
            raise BacktestCancelled()
        if progress_callback and (
            date_index == 0 or date_index % max(1, len(all_dates) // 100) == 0
        ):
            progress_callback(date_index / len(all_dates))
        for position in positions.values():
            position.available += position.unsettled
            position.unsettled = 0

        previous_date = all_dates[date_index - 1] if date_index else None
        sell_candidates: list[str] = []
        buy_candidates: list[str] = []
        if previous_date is not None:
            for symbol, frame in prepared.items():
                if date not in frame.index or previous_date not in frame.index:
                    continue
                previous = frame.loc[previous_date]
                if positions[symbol].quantity and bool(previous["sell_signal"]):
                    sell_candidates.append(symbol)
                elif positions[symbol].quantity == 0 and bool(previous["buy_signal"]):
                    buy_candidates.append(symbol)

        for symbol in sell_candidates:
            row = prepared[symbol].loc[date]
            position = positions[symbol]
            if position.available <= 0 or bool(row.get("suspended", False)):
                continue
            if _at_or_below(row["open"], row.get("limit_down")):
                order_events.append({"date": str(date.date()), "symbol": symbol, "reason": "跌停未成交"})
                continue
            price = _money(float(row["open"]) * (1 - request.slippage_rate))
            quantity = position.available
            value = _money(price * quantity)
            fees = _fee(value, request, True)
            pnl = _money(value - fees - position.average_cost * quantity)
            cash = _money(cash + value - fees)
            trades.append(
                {
                    "date": str(date.date()),
                    "symbol": symbol,
                    "name": str(row.get("name", symbol)),
                    "side": "卖出",
                    "price": price,
                    "quantity": quantity,
                    "value": value,
                    "fees": fees,
                    "pnl": pnl,
                }
            )
            positions[symbol] = Position()

        active_buys = []
        for symbol in buy_candidates:
            row = prepared[symbol].loc[date]
            if bool(row.get("suspended", False)):
                continue
            if _at_or_above(row["open"], row.get("limit_up")):
                order_events.append({"date": str(date.date()), "symbol": symbol, "reason": "涨停未成交"})
                continue
            active_buys.append(symbol)

        existing_market_value = 0.0
        for symbol, position in positions.items():
            if not position.quantity:
                continue
            frame = prepared[symbol]
            if date in frame.index:
                mark_price = float(frame.loc[date, "open"])
            else:
                available_dates = frame.index[frame.index <= date]
                mark_price = float(frame.loc[available_dates[-1], "close"]) if len(available_dates) else 0.0
            existing_market_value += position.quantity * mark_price
        equity_before_buys = cash + existing_market_value
        position_capacity = max(
            0.0, equity_before_buys * request.max_position - existing_market_value
        )
        available_budget = min(cash, position_capacity)
        allocation = available_budget / max(len(active_buys), 1)
        for symbol in active_buys:
            row = prepared[symbol].loc[date]
            price = _money(float(row["open"]) * (1 + request.slippage_rate))
            quantity = int(allocation / price / request.lot_size) * request.lot_size
            while quantity > 0:
                value = _money(price * quantity)
                fees = _fee(value, request, False)
                if value + fees <= cash:
                    break
                quantity -= request.lot_size
            if quantity <= 0:
                order_events.append({"date": str(date.date()), "symbol": symbol, "reason": "资金不足"})
                continue
            value = _money(price * quantity)
            fees = _fee(value, request, False)
            cash = _money(cash - value - fees)
            positions[symbol] = Position(
                quantity=quantity,
                available=0,
                unsettled=quantity,
                average_cost=(value + fees) / quantity,
            )
            trades.append(
                {
                    "date": str(date.date()),
                    "symbol": symbol,
                    "name": str(row.get("name", symbol)),
                    "side": "买入",
                    "price": price,
                    "quantity": quantity,
                    "value": value,
                    "fees": fees,
                    "pnl": None,
                }
            )

        market_value = 0.0
        for symbol, position in positions.items():
            if not position.quantity:
                continue
            frame = prepared[symbol]
            available_dates = frame.index[frame.index <= date]
            if len(available_dates):
                market_value += position.quantity * float(frame.loc[available_dates[-1], "close"])
        equity_curve.append(
            {"date": str(date.date()), "equity": _round(cash + market_value), "cash": _round(cash)}
        )

    if progress_callback:
        progress_callback(1.0)
    return _summarize(
        equity_curve,
        trades,
        order_events,
        request,
        benchmark_data,
        benchmark_is_demo=benchmark_is_demo,
    )


def _summarize(
    curve: list[dict],
    trades: list[dict],
    events: list[dict],
    request: BacktestRequest,
    benchmark_data: pd.DataFrame | None,
    *,
    benchmark_is_demo: bool,
) -> dict:
    equity = pd.DataFrame(curve)
    equity["date"] = pd.to_datetime(equity["date"])
    equity["return"] = equity["equity"].pct_change().fillna(0)
    equity["peak"] = equity["equity"].cummax()
    equity["drawdown"] = equity["equity"] / equity["peak"] - 1
    total_return = equity["equity"].iloc[-1] / request.initial_cash - 1
    years = max((equity["date"].iloc[-1] - equity["date"].iloc[0]).days / 365.25, 1 / 252)
    annual_return = (1 + total_return) ** (1 / years) - 1
    volatility = equity["return"].std(ddof=0) * np.sqrt(252)
    sharpe = (
        equity["return"].mean() / equity["return"].std(ddof=0) * np.sqrt(252)
        if volatility
        else 0.0
    )
    max_drawdown = float(equity["drawdown"].min())
    sell_trades = [trade for trade in trades if trade["side"] == "卖出"]
    wins = [trade for trade in sell_trades if (trade.get("pnl") or 0) > 0]
    win_rate = len(wins) / len(sell_trades) if sell_trades else 0.0

    equity["month"] = equity["date"].dt.to_period("M")
    monthly = equity.groupby("month")["equity"].last().to_frame("last")
    monthly["return"] = monthly["last"].pct_change()
    monthly.iloc[0, monthly.columns.get_loc("return")] = (
        monthly.iloc[0]["last"] / request.initial_cash - 1
    )
    monthly_returns = [
        {"year": int(period.year), "month": int(period.month), "return": _round(row["return"])}
        for period, row in monthly.iterrows()
    ]

    benchmark_growth = pd.Series(np.nan, index=equity.index, dtype=float)
    if benchmark_data is not None and not benchmark_data.empty:
        benchmark = benchmark_data.copy()
        benchmark["trade_date"] = pd.to_datetime(benchmark["trade_date"])
        benchmark = benchmark.set_index("trade_date")["close"].sort_index()
        aligned = benchmark.reindex(equity["date"], method="ffill")
        if aligned.notna().any():
            first_value = float(aligned.dropna().iloc[0])
            benchmark_growth = (aligned.reset_index(drop=True) / first_value) - 1
    curve_output = []
    for index, row in equity.iterrows():
        curve_output.append(
            {
                "date": str(row["date"].date()),
                "equity": _round(row["equity"] / request.initial_cash - 1),
                "benchmark": (
                    _round(benchmark_growth.iloc[index])
                    if pd.notna(benchmark_growth.iloc[index])
                    else None
                ),
                "drawdown": _round(row["drawdown"]),
            }
        )
    return {
        "strategy": request.strategy.name,
        "period": {"start": request.start_date, "end": request.end_date},
        "metrics": {
            "total_return": _round(total_return),
            "annual_return": _round(annual_return),
            "max_drawdown": _round(max_drawdown),
            "sharpe": _round(sharpe),
            "win_rate": _round(win_rate),
            "trade_count": len(trades),
            "volatility": _round(volatility),
            "final_equity": _round(equity["equity"].iloc[-1]),
        },
        "equity_curve": curve_output,
        "monthly_returns": monthly_returns,
        "benchmark": {
            "symbol": request.benchmark,
            "label": (
                "演示沪深300"
                if benchmark_is_demo
                else "沪深300" if benchmark_data is not None and not benchmark_data.empty
                else "沪深300（数据集未提供）"
            ),
            "is_demo": benchmark_is_demo,
            "available": benchmark_data is not None and not benchmark_data.empty,
        },
        "trades": list(reversed(trades)),
        "order_events": events,
        "assumptions": [
            "收盘产生信号，下一交易日开盘成交",
            "当日买入股票下一交易日可卖",
            "涨停不买、跌停不卖，价格使用未复权口径",
        ],
    }
