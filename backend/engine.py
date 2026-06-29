from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

import numpy as np
import pandas as pd

from .models import BacktestRequest, RuleCondition, RuleGroup


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
    close = frame["signal_close"] if "signal_close" in frame else frame["close"]
    volume = pd.to_numeric(frame.get("volume", pd.Series(0, index=frame.index)), errors="coerce").fillna(0)
    if rule.indicator == "ma_cross":
        left = close.rolling(rule.left).mean()
        right = close.rolling(rule.right).mean()
        if rule.operator == "cross_above":
            return (left > right) & (left.shift(1) <= right.shift(1))
        if rule.operator == "cross_below":
            return (left < right) & (left.shift(1) >= right.shift(1))
        return left > right if rule.operator == "above" else left < right
    if rule.indicator == "ma_stack":
        short = close.rolling(rule.left).mean()
        middle = close.rolling(rule.right).mean()
        long = close.rolling(int(rule.threshold)).mean()
        return (close > short) & (short > middle) & (middle > long)
    if rule.indicator == "price_vs_ma":
        moving = close.rolling(rule.left).mean()
        if rule.operator == "cross_above":
            return (close > moving) & (close.shift(1) <= moving.shift(1))
        if rule.operator == "cross_below":
            return (close < moving) & (close.shift(1) >= moving.shift(1))
        return close > moving if rule.operator == "above" else close < moving
    if rule.indicator == "price_ma_deviation":
        moving = close.rolling(rule.left).mean() * float(rule.threshold)
        return close > moving if rule.operator == "above" else close < moving
    if rule.indicator == "macd":
        fast = close.ewm(span=rule.left, adjust=False).mean()
        slow = close.ewm(span=rule.right, adjust=False).mean()
        macd = fast - slow
        signal_period = max(2, min(int(rule.threshold or 9), 100))
        signal = macd.ewm(span=signal_period, adjust=False).mean()
        if rule.operator == "cross_above":
            return (macd > signal) & (macd.shift(1) <= signal.shift(1))
        if rule.operator == "cross_below":
            return (macd < signal) & (macd.shift(1) >= signal.shift(1))
        return macd > signal if rule.operator == "above" else macd < signal
    if rule.indicator == "bollinger":
        period = close.rolling(rule.left)
        middle = period.mean()
        deviation = period.std(ddof=0)
        multiplier = rule.threshold if 0 < rule.threshold <= 10 else 2.0
        upper = middle + multiplier * deviation
        lower = middle - multiplier * deviation
        if rule.operator == "cross_above":
            return (close > upper) & (close.shift(1) <= upper.shift(1))
        if rule.operator == "cross_below":
            return (close < lower) & (close.shift(1) >= lower.shift(1))
        return close > upper if rule.operator == "above" else close < lower
    if rule.indicator == "volume_vs_ma":
        baseline = volume.rolling(rule.left).mean() * float(rule.threshold)
        return volume > baseline if rule.operator == "above" else volume < baseline
    if rule.indicator == "volume_max_vs_ma":
        recent_max = volume.rolling(rule.left).max()
        baseline = volume.rolling(rule.right).mean() * float(rule.threshold)
        return recent_max > baseline if rule.operator == "above" else recent_max < baseline
    if rule.indicator == "volume_return_spike":
        volume_spike = volume > volume.rolling(rule.left).mean() * float(rule.threshold)
        daily_return = close / close.shift(1) - 1
        return volume_spike & (daily_return > float(rule.lower or 0.07))
    if rule.indicator == "life_line_watch":
        return pd.Series(False, index=frame.index)
    if rule.indicator == "return_between":
        lookback = max(1, int(rule.left))
        returns = close / close.shift(lookback) - 1
        return returns.between(float(rule.lower or 0), float(rule.upper or 0), inclusive="both")
    if rule.indicator == "kline_up_ratio":
        up_days = (frame["close"] > frame["open"]).rolling(rule.left).sum()
        down_days = (frame["close"] < frame["open"]).rolling(rule.left).sum()
        return up_days > down_days * float(rule.threshold)
    if rule.indicator == "range_amplitude":
        recent_high = frame["high"].rolling(rule.left).max()
        recent_low = frame["low"].rolling(rule.left).min().replace(0, np.nan)
        amplitude = recent_high / recent_low - 1
        return amplitude > rule.threshold if rule.operator == "above" else amplitude < rule.threshold
    if rule.indicator == "body_amplitude":
        body = (frame["close"] - frame["open"]).abs() / frame["close"].replace(0, np.nan)
        recent_max = body.rolling(rule.left).max()
        return recent_max > rule.threshold if rule.operator == "above" else recent_max < rule.threshold
    if rule.indicator == "volume_down_spike":
        volume_spike = volume > volume.rolling(rule.left).mean() * float(rule.threshold)
        down_body = frame["close"] < frame["open"]
        return volume_spike & down_body
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


def _combine_groups(frame: pd.DataFrame, groups: list[RuleGroup], group_logic: str) -> pd.Series:
    usable_groups = [group for group in groups if group.conditions]
    if not usable_groups:
        return pd.Series(False, index=frame.index)
    group_signals = pd.concat(
        [_combine(frame, group.conditions, group.logic) for group in usable_groups],
        axis=1,
    )
    return group_signals.all(axis=1) if group_logic == "all" else group_signals.any(axis=1)


def _combine_strategy_side(
    frame: pd.DataFrame,
    rules: list[RuleCondition],
    logic: str,
    groups: list[RuleGroup] | None,
    group_logic: str,
) -> pd.Series:
    if groups:
        return _combine_groups(frame, groups, group_logic)
    return _combine(frame, rules, logic)


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


def _passes_stock_filters(row: pd.Series, request: BacktestRequest, signal_date) -> tuple[bool, str]:
    if request.exclude_st and "ST" in str(row.get("name", "")).upper():
        return False, "ST过滤"
    listing_session_checked = False
    if request.min_listed_days and pd.notna(row.get("listing_session", pd.NA)):
        listing_session_checked = True
        completed_trading_days = max(0, int(row["listing_session"]) - 1)
        if completed_trading_days < request.min_listed_days:
            return False, "上市天数不足"
    if request.min_listed_days and not listing_session_checked and pd.notna(row.get("listed_date", pd.NaT)):
        listed_date = pd.Timestamp(row["listed_date"])
        if (pd.Timestamp(signal_date) - listed_date).days < request.min_listed_days:
            return False, "上市天数不足"
    if request.min_average_amount and float(row.get("average_amount_20", 0) or 0) < request.min_average_amount:
        return False, "成交额不足"
    return True, ""


def _candidate_score(frame: pd.DataFrame, signal_date, request: BacktestRequest) -> float:
    if request.strategy.candidate_sort == "none":
        return 0.0
    window = max(1, int(request.strategy.sort_window))
    dates = frame.index[frame.index <= signal_date]
    if len(dates) <= window:
        return 0.0
    current = float(frame.loc[dates[-1], "signal_close"])
    previous = float(frame.loc[dates[-1 - window], "signal_close"])
    if previous <= 0:
        return 0.0
    return current / previous - 1


def _stateful_sell_rules(request: BacktestRequest) -> list[RuleCondition]:
    rules = [
        rule
        for rule in request.strategy.sell_conditions
        if rule.indicator == "life_line_watch"
    ]
    for group in request.strategy.sell_groups or []:
        rules.extend(rule for rule in group.conditions if rule.indicator == "life_line_watch")
    return rules


def _stateless_sell_rules(request: BacktestRequest) -> list[RuleCondition]:
    return [
        rule
        for rule in request.strategy.sell_conditions
        if rule.indicator != "life_line_watch"
    ]


def _stateless_sell_groups(request: BacktestRequest) -> list[RuleGroup] | None:
    if not request.strategy.sell_groups:
        return None
    groups = []
    for group in request.strategy.sell_groups:
        conditions = [rule for rule in group.conditions if rule.indicator != "life_line_watch"]
        if conditions:
            groups.append(RuleGroup(name=group.name, logic=group.logic, conditions=conditions))
    return groups or None


def _evaluate_life_line_watch(
    frame: pd.DataFrame,
    signal_date,
    rule: RuleCondition,
    watched_days: int,
) -> tuple[bool, int, str]:
    dates = frame.index[frame.index <= signal_date]
    min_bars = max(int(rule.left), int(rule.right), 2) + 1
    if len(dates) < min_bars:
        return False, watched_days, ""
    current = frame.loc[dates].copy()
    close = current["signal_close"] if "signal_close" in current else current["close"]
    volume = pd.to_numeric(current["volume"], errors="coerce").fillna(0)
    life_line = close.rolling(int(rule.left)).mean().iloc[-1]
    volume_ma = volume.rolling(int(rule.right)).mean().iloc[-1]
    current_close = float(close.iloc[-1])
    previous_close = float(close.iloc[-2])
    current_volume = float(volume.iloc[-1])
    if life_line <= 0 or previous_close <= 0 or volume_ma <= 0:
        return False, watched_days, ""

    line_name = f"MA{int(rule.left)}"
    break_line = current_close < float(life_line)
    today_return = current_close / previous_close - 1
    heavy_break = break_line and current_volume > volume_ma * float(rule.upper or 1.8)
    light_small_break = (
        break_line
        and current_volume < volume_ma
        and today_return > float(rule.lower if rule.lower is not None else -0.01)
    )

    if heavy_break:
        return True, 0, f"生命线风控：放量跌破{line_name}，强制离场"
    if not break_line:
        return False, 0, ""
    if not light_small_break:
        return True, 0, f"生命线风控：跌破{line_name}，直接离场"

    next_watched_days = watched_days + 1
    observe_days = max(1, int(rule.threshold))
    if next_watched_days >= observe_days:
        return True, 0, f"生命线风控：观察{observe_days}天仍未站回{line_name}，离场"
    return False, next_watched_days, f"生命线风控：缩量小阴跌破{line_name}，观察第{next_watched_days}天"


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
    total_symbols = max(1, len(data))
    for symbol_index, (symbol, frame) in enumerate(data.items()):
        if cancel_check and cancel_check():
            raise BacktestCancelled()
        if progress_callback and (
            symbol_index == 0 or symbol_index % max(1, total_symbols // 50) == 0
        ):
            progress_callback(0.02 + 0.18 * (symbol_index / total_symbols))
        current = frame.copy().sort_values("trade_date")
        current = current[
            (current["trade_date"] >= pd.Timestamp(request.start_date))
            & (current["trade_date"] <= pd.Timestamp(request.end_date))
        ].reset_index(drop=True)
        if request.signal_price_mode == "adjusted":
            if "adjusted_close" not in current:
                raise ValueError("数据缺少 adjusted_close，无法使用复权价计算信号")
            current["signal_close"] = pd.to_numeric(current["adjusted_close"], errors="coerce")
            if current["signal_close"].isna().any():
                raise ValueError("数据包含无法识别的复权收盘价")
        else:
            current["signal_close"] = current["close"]
        current["buy_signal"] = _combine_strategy_side(
            current,
            request.strategy.buy_conditions,
            request.strategy.buy_logic,
            request.strategy.buy_groups,
            request.strategy.buy_group_logic,
        )
        current["sell_signal"] = _combine_strategy_side(
            current,
            _stateless_sell_rules(request),
            request.strategy.sell_logic,
            _stateless_sell_groups(request),
            request.strategy.sell_group_logic,
        )
        amount = current["amount"] if "amount" in current else current["volume"] * current["close"]
        current["average_amount_20"] = pd.to_numeric(amount, errors="coerce").fillna(0).rolling(20, min_periods=1).mean()
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
    life_line_watch_days = {symbol: 0 for symbol in prepared}
    life_line_rules = _stateful_sell_rules(request)

    for date_index, date in enumerate(all_dates):
        if cancel_check and cancel_check():
            raise BacktestCancelled()
        if progress_callback and (
            date_index == 0 or date_index % max(1, len(all_dates) // 100) == 0
        ):
            progress_callback(0.20 + 0.80 * (date_index / len(all_dates)))
        for position in positions.values():
            position.available += position.unsettled
            position.unsettled = 0

        previous_date = all_dates[date_index - 1] if date_index else None
        sell_candidates: list[str] = []
        buy_candidates: list[str] = []
        sell_reasons: dict[str, str] = {}
        if previous_date is not None:
            can_rebalance = request.rebalance_days <= 1 or date_index % request.rebalance_days == 0
            for symbol, frame in prepared.items():
                if date not in frame.index or previous_date not in frame.index:
                    continue
                previous = frame.loc[previous_date]
                position = positions[symbol]
                if position.quantity:
                    skip_risk_exit = (
                        request.signal_price_mode == "adjusted"
                        and bool(previous.get("corporate_action", False))
                    )
                    holding_return = float(previous["close"]) / position.average_cost - 1 if position.average_cost else 0.0
                    if not skip_risk_exit and request.stop_loss_pct and holding_return <= -request.stop_loss_pct:
                        sell_candidates.append(symbol)
                        sell_reasons[symbol] = "止损"
                    elif not skip_risk_exit and request.take_profit_pct and holding_return >= request.take_profit_pct:
                        sell_candidates.append(symbol)
                        sell_reasons[symbol] = "止盈"
                    elif can_rebalance and bool(previous["sell_signal"]):
                        sell_candidates.append(symbol)
                        sell_reasons[symbol] = "卖出信号"
                    elif can_rebalance and life_line_rules:
                        for rule in life_line_rules:
                            should_sell, next_watch_days, reason = _evaluate_life_line_watch(
                                frame,
                                previous_date,
                                rule,
                                life_line_watch_days.get(symbol, 0),
                            )
                            life_line_watch_days[symbol] = next_watch_days
                            if should_sell:
                                sell_candidates.append(symbol)
                                sell_reasons[symbol] = reason
                                break
                elif can_rebalance and bool(previous["buy_signal"]):
                    passed, reason = _passes_stock_filters(previous, request, previous_date)
                    if passed:
                        buy_candidates.append(symbol)
                    else:
                        order_events.append({"date": str(date.date()), "symbol": symbol, "reason": reason})
            if request.strategy.candidate_sort != "none":
                buy_candidates = sorted(
                    buy_candidates,
                    key=lambda symbol: _candidate_score(prepared[symbol], previous_date, request),
                    reverse=request.strategy.candidate_sort == "return_desc",
                )

        for symbol in sell_candidates:
            row = prepared[symbol].loc[date]
            position = positions[symbol]
            if position.available <= 0 or bool(row.get("suspended", False)):
                continue
            if not bool(row.get("limit_exempt", False)) and _at_or_below(row["open"], row.get("limit_down")):
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
                    "reason": sell_reasons.get(symbol, "卖出信号"),
                }
            )
            positions[symbol] = Position()
            life_line_watch_days[symbol] = 0

        max_new_positions = len(buy_candidates)
        if request.strategy.max_hold_num:
            current_hold_count = sum(1 for position in positions.values() if position.quantity)
            max_new_positions = max(0, request.strategy.max_hold_num - current_hold_count)
        active_buys = []
        for symbol in buy_candidates:
            if len(active_buys) >= max_new_positions:
                break
            row = prepared[symbol].loc[date]
            if bool(row.get("suspended", False)):
                continue
            if not bool(row.get("limit_exempt", False)) and _at_or_above(row["open"], row.get("limit_up")):
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
            symbol_budget = min(allocation, equity_before_buys * request.max_symbol_position)
            quantity = int(symbol_budget / price / request.lot_size) * request.lot_size
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
            life_line_watch_days[symbol] = 0
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
                    "reason": "买入信号",
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
            (
                "策略信号使用复权收盘价，撮合、估值、现金和费用仍使用未复权价格"
                if request.signal_price_mode == "adjusted"
                else "策略信号、撮合、估值、现金和费用均使用未复权价格"
            ),
            f"调仓周期 {request.rebalance_days} 个交易日；单标的仓位上限 {request.max_symbol_position:.0%}",
            (
                f"最多持有 {request.strategy.max_hold_num} 只；候选排序 {request.strategy.candidate_sort}({request.strategy.sort_window}日)"
                if request.strategy.max_hold_num
                else "未限制最大持股数量"
            ),
            (
                f"启用条件分组：买入组间 {request.strategy.buy_group_logic}；卖出组间 {request.strategy.sell_group_logic}"
                if request.strategy.buy_groups or request.strategy.sell_groups
                else "未启用条件分组表达式"
            ),
            (
                f"股票池过滤：排除 ST={request.exclude_st}，最少上市天数 {request.min_listed_days}，20日均成交额下限 {request.min_average_amount:,.0f}"
            ),
            (
                f"启用止损 {request.stop_loss_pct:.0%}"
                if request.stop_loss_pct
                else "未启用止损"
            ),
            (
                f"启用止盈 {request.take_profit_pct:.0%}"
                if request.take_profit_pct
                else "未启用止盈"
            ),
        ],
    }
