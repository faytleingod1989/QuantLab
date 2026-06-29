from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RuleCondition(BaseModel):
    indicator: Literal[
        "ma_cross",
        "price_vs_ma",
        "rsi",
        "macd",
        "bollinger",
        "ma_stack",
        "volume_vs_ma",
        "volume_max_vs_ma",
        "return_between",
        "kline_up_ratio",
        "body_amplitude",
        "range_amplitude",
        "price_ma_deviation",
        "volume_return_spike",
        "volume_down_spike",
        "life_line_watch",
    ] = "ma_cross"
    operator: Literal["cross_above", "cross_below", "above", "below"] = "cross_above"
    left: int = Field(default=20, ge=1, le=500)
    right: int = Field(default=60, ge=2, le=500)
    threshold: float = Field(default=50, ge=0, le=500)
    lower: float | None = Field(default=None, ge=-10, le=10)
    upper: float | None = Field(default=None, ge=-10, le=10)

    @model_validator(mode="after")
    def validate_indicator_parameters(self):
        if self.indicator in {"ma_cross", "macd"} and self.left >= self.right:
            raise ValueError("短周期必须小于长周期")
        if self.indicator == "ma_stack":
            if self.threshold == 50:
                self.threshold = 60
            if not (self.left < self.right < int(self.threshold)):
                raise ValueError("均线排列必须满足短周期 < 中周期 < 长周期")
        if self.indicator == "macd":
            if self.left == 20 and self.right == 60 and self.threshold == 50:
                self.left = 12
                self.right = 26
                self.threshold = 9
            if not 2 <= self.threshold <= 60:
                raise ValueError("MACD 信号周期必须在 2 到 60 之间")
        if self.indicator == "bollinger":
            if self.threshold == 50:
                self.threshold = 2
            if not 0 < self.threshold <= 10:
                raise ValueError("布林带标准差倍数必须大于 0 且不超过 10")
        if self.indicator == "rsi" and not 0 <= self.threshold <= 100:
            raise ValueError("RSI 阈值必须在 0 到 100 之间")
        if self.indicator == "return_between":
            if self.lower is None:
                self.lower = -0.01
            if self.upper is None:
                self.upper = 0.05
            if self.lower > self.upper:
                raise ValueError("收益率区间下限不能大于上限")
        if self.indicator == "price_ma_deviation" and self.threshold <= 0:
            raise ValueError("价格均线偏离倍率必须大于 0")
        if self.indicator in {
            "volume_vs_ma",
            "volume_max_vs_ma",
            "kline_up_ratio",
            "body_amplitude",
            "range_amplitude",
            "volume_return_spike",
            "volume_down_spike",
        }:
            if self.threshold <= 0:
                raise ValueError("倍率/阈值必须大于 0")
        if self.indicator == "volume_return_spike" and self.lower is None:
            self.lower = 0.07
        if self.indicator == "life_line_watch":
            if self.left == 20 and self.right == 60 and self.threshold == 50:
                self.right = 10
                self.threshold = 3
            if self.lower is None:
                self.lower = -0.01
            if self.upper is None:
                self.upper = 1.8
            if self.right < 2:
                raise ValueError("生命线风控均量周期必须大于 1")
            if self.threshold < 1:
                raise ValueError("生命线观察天数必须至少为 1")
            if self.upper <= 0:
                raise ValueError("生命线放量倍率必须大于 0")
        return self


class RuleGroup(BaseModel):
    name: str = Field(default="规则组", min_length=1, max_length=60)
    logic: Literal["all", "any"] = "all"
    conditions: list[RuleCondition] = Field(min_length=1, max_length=50)


class VisualStrategy(BaseModel):
    name: str = "均线多头策略"
    buy_logic: Literal["all", "any"] = "all"
    sell_logic: Literal["all", "any"] = "any"
    buy_group_logic: Literal["all", "any"] = "any"
    sell_group_logic: Literal["all", "any"] = "any"
    max_hold_num: int | None = Field(default=None, ge=1, le=200)
    candidate_sort: Literal["none", "return_asc", "return_desc"] = "none"
    sort_window: int = Field(default=20, ge=2, le=500)
    position_sizing: Literal["cash_weight", "equal_weight"] = "cash_weight"
    buy_conditions: list[RuleCondition] = Field(
        default_factory=lambda: [
            RuleCondition(indicator="ma_cross", operator="cross_above", left=20, right=60)
        ]
    )
    sell_conditions: list[RuleCondition] = Field(
        default_factory=lambda: [
            RuleCondition(indicator="ma_cross", operator="cross_below", left=20, right=60)
        ]
    )
    buy_groups: list[RuleGroup] | None = Field(default=None, max_length=20)
    sell_groups: list[RuleGroup] | None = Field(default=None, max_length=20)


class BacktestRequest(BaseModel):
    project_id: str | None = None
    strategy_id: str | None = None
    strategy_version_id: str | None = None
    dataset_id: str | None = None
    dataset_fingerprint: str | None = None
    symbols: list[str] = Field(
        default_factory=lambda: ["600519.SH", "000333.SZ", "600036.SH"]
    )
    start_date: str = "2018-01-01"
    end_date: str = "2024-05-20"
    initial_cash: float = Field(default=1_000_000, gt=0)
    commission_rate: float = Field(default=0.00025, ge=0, le=0.01)
    min_commission: float = Field(default=5.0, ge=0)
    stamp_duty_rate: float = Field(default=0.0005, ge=0, le=0.01)
    transfer_fee_rate: float = Field(default=0.00001, ge=0, le=0.01)
    slippage_rate: float = Field(default=0.0002, ge=0, le=0.02)
    max_position: float = Field(default=0.95, gt=0, le=1)
    max_symbol_position: float = Field(default=0.35, gt=0, le=1)
    exclude_st: bool = True
    min_listed_days: int = Field(default=0, ge=0, le=3650)
    min_average_amount: float = Field(default=0.0, ge=0)
    stop_loss_pct: float = Field(default=0.0, ge=0, le=1)
    take_profit_pct: float = Field(default=0.0, ge=0, le=10)
    rebalance_days: int = Field(default=1, ge=1, le=250)
    lot_size: int = Field(default=100, ge=1)
    benchmark: str = "000300.SH"
    frequency: Literal["1d"] = "1d"
    signal_price_mode: Literal["unadjusted", "adjusted"] = "unadjusted"
    report_note: str = Field(default="", max_length=1000)
    strategy: VisualStrategy = Field(default_factory=VisualStrategy)

    @model_validator(mode="after")
    def validate_dates(self):
        try:
            start = date.fromisoformat(self.start_date)
            end = date.fromisoformat(self.end_date)
        except ValueError as error:
            raise ValueError("日期格式必须为 YYYY-MM-DD") from error
        if start >= end:
            raise ValueError("结束日期必须晚于开始日期")
        if not self.symbols:
            raise ValueError("至少选择一只股票")
        return self


class DataSourceStatus(BaseModel):
    source: str
    available: bool
    message: str


class CsvDatasetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    csv_text: str = Field(min_length=1, max_length=10_000_000)


class IndustryHistoryCsvRequest(BaseModel):
    csv_text: str = Field(min_length=1, max_length=5_000_000)


class AkshareDatasetRequest(BaseModel):
    name: str = Field(default="AkShare 沪深日线", min_length=1, max_length=100)
    symbols: list[str] = Field(min_length=1, max_length=20)
    start_date: str
    end_date: str
    benchmark: str = "000300.SH"

    @model_validator(mode="after")
    def validate_dates(self):
        try:
            start = date.fromisoformat(self.start_date)
            end = date.fromisoformat(self.end_date)
        except ValueError as error:
            raise ValueError("日期格式必须为 YYYY-MM-DD") from error
        if start >= end:
            raise ValueError("结束日期必须晚于开始日期")
        return self


class AkshareAllDatasetRequest(BaseModel):
    name: str = Field(default="AkShare 沪深全A日线", min_length=1, max_length=100)
    start_date: str
    end_date: str
    benchmark: str = "000300.SH"
    base_dataset_id: str | None = None
    symbols: list[str] | None = None
    skip_symbols: list[str] | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        try:
            start = date.fromisoformat(self.start_date)
            end = date.fromisoformat(self.end_date)
        except ValueError as error:
            raise ValueError("日期格式必须为 YYYY-MM-DD") from error
        if start >= end:
            raise ValueError("结束日期必须晚于开始日期")
        if self.symbols is not None:
            self.symbols = [str(symbol).strip().upper() for symbol in self.symbols if str(symbol).strip()]
            if not self.symbols:
                raise ValueError("重试股票列表不能为空")
        if self.skip_symbols is not None:
            self.skip_symbols = [
                str(symbol).strip().upper()
                for symbol in self.skip_symbols
                if str(symbol).strip()
            ]
        return self


class MarketCoverageRequest(BaseModel):
    start_date: str
    end_date: str
    benchmark: str = "000300.SH"
    symbols: list[str] | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        try:
            start = date.fromisoformat(self.start_date)
            end = date.fromisoformat(self.end_date)
        except ValueError as error:
            raise ValueError("日期格式必须为 YYYY-MM-DD") from error
        if start >= end:
            raise ValueError("结束日期必须晚于开始日期")
        if self.symbols is not None:
            self.symbols = [str(symbol).strip().upper() for symbol in self.symbols if str(symbol).strip()]
        return self


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)


class StrategyCreate(BaseModel):
    project_id: str
    name: str = Field(min_length=1, max_length=100)
    definition: VisualStrategy


class StrategyVersionCreate(BaseModel):
    definition: VisualStrategy
    note: str = Field(default="", max_length=300)
