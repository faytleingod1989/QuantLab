import {
  ArrowsClockwise,
  ChartLineUp,
  Database,
  FileText,
  Strategy,
  TrendUp,
  UsersThree,
} from "@phosphor-icons/react";

export const API = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000/api";

export const initialSettings = {
  dataset_id: null,
  symbols: ["600519.SH", "000333.SZ", "600036.SH"],
  start_date: "2018-01-01",
  end_date: "2024-05-20",
  initial_cash: 1000000,
  commission_rate: 0.00025,
  min_commission: 5,
  stamp_duty_rate: 0.0005,
  transfer_fee_rate: 0.00001,
  slippage_rate: 0.0002,
  max_position: 0.95,
  max_symbol_position: 0.35,
  exclude_st: true,
  min_listed_days: 0,
  min_average_amount: 0,
  stop_loss_pct: 0,
  take_profit_pct: 0,
  rebalance_days: 1,
  lot_size: 100,
  benchmark: "000300.SH",
  frequency: "1d",
  signal_price_mode: "unadjusted",
  report_note: "",
  strategy: {
    name: "均线多头策略",
    buy_logic: "all",
    sell_logic: "any",
    buy_conditions: [
      { indicator: "ma_cross", operator: "cross_above", left: 20, right: 60, threshold: 50 },
    ],
    sell_conditions: [
      { indicator: "ma_cross", operator: "cross_below", left: 20, right: 60, threshold: 50 },
    ],
  },
};

export const controlPullbackTemplate = {
  name: "主力控盘回踩策略",
  buy_logic: "all",
  sell_logic: "any",
  max_hold_num: 5,
  candidate_sort: "return_asc",
  sort_window: 20,
  position_sizing: "equal_weight",
  buy_conditions: [
    { indicator: "ma_stack", operator: "above", left: 10, right: 20, threshold: 60 },
    { indicator: "volume_vs_ma", operator: "below", left: 20, right: 60, threshold: 1.5 },
    { indicator: "volume_max_vs_ma", operator: "below", left: 20, right: 20, threshold: 3 },
    { indicator: "return_between", operator: "above", left: 1, right: 60, threshold: 50, lower: -0.01, upper: 0.05 },
    { indicator: "kline_up_ratio", operator: "above", left: 10, right: 60, threshold: 1.5 },
    { indicator: "body_amplitude", operator: "below", left: 10, right: 60, threshold: 0.1 },
    { indicator: "price_ma_deviation", operator: "below", left: 10, right: 60, threshold: 1.02 },
    { indicator: "volume_vs_ma", operator: "below", left: 5, right: 60, threshold: 0.7 },
    { indicator: "return_between", operator: "below", left: 20, right: 60, threshold: 50, lower: -10, upper: 0.3 },
  ],
  sell_conditions: [
    { indicator: "volume_return_spike", operator: "above", left: 10, right: 60, threshold: 3, lower: 0.07 },
    { indicator: "price_ma_deviation", operator: "below", left: 10, right: 60, threshold: 0.97 },
    { indicator: "life_line_watch", operator: "below", left: 20, right: 10, threshold: 3, lower: -0.01, upper: 1.8 },
  ],
};

export const navItems = [
  ["数据中心", Database],
  ["策略研究", Strategy],
  ["回测中心", ArrowsClockwise],
  ["因子分析", ChartLineUp],
  ["组合管理", UsersThree],
  ["结果分析", TrendUp],
  ["报告管理", FileText],
];

export const workflowSteps = ["选择数据", "配置策略", "设置成本", "运行回测", "分析结果"];
