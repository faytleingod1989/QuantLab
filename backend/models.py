from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RuleCondition(BaseModel):
    indicator: Literal["ma_cross", "price_vs_ma", "rsi"] = "ma_cross"
    operator: Literal["cross_above", "cross_below", "above", "below"] = "cross_above"
    left: int = Field(default=20, ge=2, le=500)
    right: int = Field(default=60, ge=2, le=500)
    threshold: float = Field(default=50, ge=0, le=100)


class VisualStrategy(BaseModel):
    name: str = "均线多头策略"
    buy_logic: Literal["all", "any"] = "all"
    sell_logic: Literal["all", "any"] = "any"
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
    stop_loss_pct: float = Field(default=0.0, ge=0, le=1)
    take_profit_pct: float = Field(default=0.0, ge=0, le=10)
    rebalance_days: int = Field(default=1, ge=1, le=250)
    lot_size: int = Field(default=100, ge=1)
    benchmark: str = "000300.SH"
    frequency: Literal["1d"] = "1d"
    signal_price_mode: Literal["unadjusted", "adjusted"] = "unadjusted"
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
