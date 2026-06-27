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

export const chipStableMaStackTemplate = {
  name: "筹码稳定均线多头选股",
  buy_logic: "all",
  sell_logic: "any",
  buy_group_logic: "all",
  sell_group_logic: "any",
  max_hold_num: 8,
  candidate_sort: "return_asc",
  sort_window: 20,
  position_sizing: "equal_weight",
  buy_groups: [
    {
      name: "趋势与控盘结构",
      logic: "all",
      conditions: [
        { indicator: "ma_stack", operator: "above", left: 5, right: 20, threshold: 60 },
        { indicator: "kline_up_ratio", operator: "above", left: 20, right: 60, threshold: 1.1 },
      ],
    },
    {
      name: "筹码稳定与低波动",
      logic: "all",
      conditions: [
        { indicator: "volume_max_vs_ma", operator: "below", left: 5, right: 30, threshold: 1.5 },
        { indicator: "body_amplitude", operator: "below", left: 10, right: 60, threshold: 0.05 },
        { indicator: "return_between", operator: "above", left: 20, right: 60, threshold: 50, lower: -0.05, upper: 0.18 },
        { indicator: "price_ma_deviation", operator: "below", left: 20, right: 60, threshold: 1.18 },
      ],
    },
  ],
  buy_conditions: [
    { indicator: "ma_stack", operator: "above", left: 5, right: 20, threshold: 60 },
    { indicator: "kline_up_ratio", operator: "above", left: 20, right: 60, threshold: 1.1 },
    { indicator: "volume_max_vs_ma", operator: "below", left: 5, right: 30, threshold: 1.5 },
    { indicator: "body_amplitude", operator: "below", left: 10, right: 60, threshold: 0.05 },
    { indicator: "return_between", operator: "above", left: 20, right: 60, threshold: 50, lower: -0.05, upper: 0.18 },
    { indicator: "price_ma_deviation", operator: "below", left: 20, right: 60, threshold: 1.18 },
  ],
  sell_conditions: [
    { indicator: "price_vs_ma", operator: "below", left: 20, right: 60, threshold: 50 },
    { indicator: "volume_return_spike", operator: "above", left: 10, right: 60, threshold: 3, lower: 0.07 },
    { indicator: "body_amplitude", operator: "above", left: 1, right: 60, threshold: 0.1 },
  ],
};

export const boxBreakoutTemplate = {
  name: "蓄势箱体放量突破选股",
  buy_logic: "all",
  sell_logic: "any",
  buy_group_logic: "all",
  sell_group_logic: "any",
  max_hold_num: 5,
  candidate_sort: "return_desc",
  sort_window: 10,
  position_sizing: "equal_weight",
  buy_groups: [
    {
      name: "蓄势箱体结构",
      logic: "all",
      conditions: [
        { indicator: "return_between", operator: "above", left: 20, right: 60, threshold: 50, lower: -0.08, upper: 0.2 },
        { indicator: "kline_up_ratio", operator: "above", left: 20, right: 60, threshold: 1.2 },
        { indicator: "body_amplitude", operator: "below", left: 20, right: 60, threshold: 0.12 },
      ],
    },
    {
      name: "放量突破确认",
      logic: "all",
      conditions: [
        { indicator: "volume_return_spike", operator: "above", left: 10, right: 60, threshold: 2, lower: 0.03 },
        { indicator: "price_ma_deviation", operator: "above", left: 20, right: 60, threshold: 1.01 },
      ],
    },
  ],
  buy_conditions: [
    { indicator: "return_between", operator: "above", left: 20, right: 60, threshold: 50, lower: -0.08, upper: 0.2 },
    { indicator: "kline_up_ratio", operator: "above", left: 20, right: 60, threshold: 1.2 },
    { indicator: "body_amplitude", operator: "below", left: 20, right: 60, threshold: 0.12 },
    { indicator: "volume_return_spike", operator: "above", left: 10, right: 60, threshold: 2, lower: 0.03 },
    { indicator: "price_ma_deviation", operator: "above", left: 20, right: 60, threshold: 1.01 },
  ],
  sell_conditions: [
    { indicator: "price_vs_ma", operator: "below", left: 20, right: 60, threshold: 50 },
    { indicator: "volume_return_spike", operator: "above", left: 10, right: 60, threshold: 3, lower: 0.07 },
    { indicator: "body_amplitude", operator: "above", left: 1, right: 60, threshold: 0.1 },
  ],
};

export const strategyTemplates = [
  {
    id: "control_pullback",
    title: "主力控盘回踩策略",
    description: "均线多头、缩量回踩、红肥绿瘦，适合波段跟踪。",
    strategy: controlPullbackTemplate,
  },
  {
    id: "chip_stable_ma_stack",
    title: "筹码稳定均线多头选股",
    description: "均线多头 + 阳线优势 + 低波动缩量，筛偏稳的控盘票。",
    strategy: chipStableMaStackTemplate,
  },
  {
    id: "box_breakout",
    title: "蓄势箱体放量突破选股",
    description: "先找箱体蓄势，再用放量大阳和站上均线确认启动。",
    strategy: boxBreakoutTemplate,
  },
];

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
