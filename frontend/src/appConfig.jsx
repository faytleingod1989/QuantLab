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

const flattenGroups = (groups) => groups.flatMap((group) => group.conditions);

export const topDownTrendControlTemplate = {
  name: "自上而下趋势控盘系统",
  category: "趋势控盘型",
  no_future_note: "所有条件仅使用当前日收盘、成交量及历史滚动窗口；信号当日确认，下一交易日撮合。",
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
      name: "趋势与控盘",
      logic: "all",
      conditions: [
        { indicator: "ma_stack", operator: "above", left: 5, right: 20, threshold: 60 },
        { indicator: "kline_up_ratio", operator: "above", left: 20, right: 60, threshold: 1.1 },
      ],
    },
    {
      name: "筹码稳定",
      logic: "all",
      conditions: [
        { indicator: "volume_max_vs_ma", operator: "below", left: 5, right: 30, threshold: 1.8 },
        { indicator: "body_amplitude", operator: "below", left: 10, right: 60, threshold: 0.08 },
        { indicator: "price_ma_deviation", operator: "below", left: 20, right: 60, threshold: 1.18 },
      ],
    },
  ],
  sell_groups: [
    {
      name: "趋势破位",
      logic: "any",
      conditions: [
        { indicator: "price_vs_ma", operator: "below", left: 20, right: 60, threshold: 50 },
        { indicator: "life_line_watch", operator: "below", left: 20, right: 10, threshold: 3, lower: -0.01, upper: 1.8 },
      ],
    },
    {
      name: "出货风险",
      logic: "any",
      conditions: [
        { indicator: "volume_down_spike", operator: "above", left: 10, right: 60, threshold: 3 },
        { indicator: "range_amplitude", operator: "above", left: 1, right: 60, threshold: 0.1 },
      ],
    },
  ],
};
topDownTrendControlTemplate.buy_conditions = flattenGroups(topDownTrendControlTemplate.buy_groups);
topDownTrendControlTemplate.sell_conditions = flattenGroups(topDownTrendControlTemplate.sell_groups);

export const c104FourUpMomentumTemplate = {
  name: "C104四串阳强势确认系统",
  category: "强势确认型",
  no_future_note: "连续阳线、阳线优势和放量均按当前日及历史窗口计算，不读取后续 K 线。",
  buy_logic: "all",
  sell_logic: "any",
  buy_group_logic: "all",
  sell_group_logic: "any",
  max_hold_num: 5,
  candidate_sort: "return_desc",
  sort_window: 5,
  position_sizing: "equal_weight",
  buy_groups: [
    {
      name: "短线强势确认",
      logic: "all",
      conditions: [
        { indicator: "ma_stack", operator: "above", left: 5, right: 10, threshold: 20 },
        { indicator: "kline_up_ratio", operator: "above", left: 20, right: 60, threshold: 1.15 },
        { indicator: "consecutive_up", operator: "above", left: 4, right: 60, threshold: 1 },
      ],
    },
    {
      name: "资金活跃",
      logic: "all",
      conditions: [
        { indicator: "volume_vs_ma", operator: "above", left: 5, right: 60, threshold: 1.1 },
        { indicator: "price_ma_deviation", operator: "below", left: 10, right: 60, threshold: 1.16 },
      ],
    },
  ],
  sell_groups: [
    {
      name: "短线止盈与破位",
      logic: "any",
      conditions: [
        { indicator: "return_between", operator: "above", left: 8, right: 60, threshold: 50, lower: 0.18, upper: 10 },
        { indicator: "price_vs_ma", operator: "below", left: 10, right: 60, threshold: 50 },
        { indicator: "volume_down_spike", operator: "above", left: 10, right: 60, threshold: 2.5 },
      ],
    },
  ],
};
c104FourUpMomentumTemplate.buy_conditions = flattenGroups(c104FourUpMomentumTemplate.buy_groups);
c104FourUpMomentumTemplate.sell_conditions = flattenGroups(c104FourUpMomentumTemplate.sell_groups);

export const boxBreakoutLaunchTemplate = {
  name: "蓄势箱体放量突破系统",
  category: "蓄势突破型",
  no_future_note: "箱体、放量、突破确认均用历史区间和当前日收盘判断，不等待未来回踩验证。",
  buy_logic: "all",
  sell_logic: "any",
  buy_group_logic: "all",
  sell_group_logic: "any",
  max_hold_num: 6,
  candidate_sort: "return_desc",
  sort_window: 10,
  position_sizing: "equal_weight",
  buy_groups: [
    {
      name: "蓄势结构",
      logic: "all",
      conditions: [
        { indicator: "range_amplitude", operator: "below", left: 30, right: 60, threshold: 0.22 },
        { indicator: "kline_up_ratio", operator: "above", left: 20, right: 60, threshold: 1.05 },
        { indicator: "return_between", operator: "above", left: 30, right: 60, threshold: 50, lower: -0.08, upper: 0.22 },
      ],
    },
    {
      name: "放量启动",
      logic: "all",
      conditions: [
        { indicator: "volume_return_spike", operator: "above", left: 10, right: 60, threshold: 1.8, lower: 0.03 },
        { indicator: "price_ma_deviation", operator: "above", left: 20, right: 60, threshold: 1.01 },
      ],
    },
  ],
  sell_groups: [
    {
      name: "假突破与出货",
      logic: "any",
      conditions: [
        { indicator: "price_vs_ma", operator: "below", left: 20, right: 60, threshold: 50 },
        { indicator: "volume_down_spike", operator: "above", left: 10, right: 60, threshold: 3 },
        { indicator: "range_amplitude", operator: "above", left: 1, right: 60, threshold: 0.1 },
      ],
    },
  ],
};
boxBreakoutLaunchTemplate.buy_conditions = flattenGroups(boxBreakoutLaunchTemplate.buy_groups);
boxBreakoutLaunchTemplate.sell_conditions = flattenGroups(boxBreakoutLaunchTemplate.sell_groups);

export const pullbackResonanceTemplate = {
  name: "趋势回踩技术共振系统",
  category: "回踩共振型",
  no_future_note: "回踩条件只用当前价格相对均线、历史收益和当前成交量确认，不使用回踩后的未来反弹。",
  buy_logic: "all",
  sell_logic: "any",
  buy_group_logic: "all",
  sell_group_logic: "any",
  max_hold_num: 6,
  candidate_sort: "return_asc",
  sort_window: 10,
  position_sizing: "equal_weight",
  buy_groups: [
    {
      name: "上升趋势",
      logic: "all",
      conditions: [
        { indicator: "ma_stack", operator: "above", left: 5, right: 20, threshold: 60 },
        { indicator: "price_vs_ma", operator: "above", left: 20, right: 60, threshold: 50 },
      ],
    },
    {
      name: "缩量回踩",
      logic: "all",
      conditions: [
        { indicator: "price_ma_deviation", operator: "below", left: 20, right: 60, threshold: 1.04 },
        { indicator: "return_between", operator: "above", left: 10, right: 60, threshold: 50, lower: -0.08, upper: 0.04 },
        { indicator: "volume_vs_ma", operator: "below", left: 5, right: 60, threshold: 0.95 },
      ],
    },
  ],
  sell_groups: [
    {
      name: "趋势线失守",
      logic: "any",
      conditions: [
        { indicator: "price_vs_ma", operator: "below", left: 20, right: 60, threshold: 50 },
        { indicator: "life_line_watch", operator: "below", left: 20, right: 10, threshold: 3, lower: -0.01, upper: 1.8 },
      ],
    },
  ],
};
pullbackResonanceTemplate.buy_conditions = flattenGroups(pullbackResonanceTemplate.buy_groups);
pullbackResonanceTemplate.sell_conditions = flattenGroups(pullbackResonanceTemplate.sell_groups);

export const rightSideReversalTemplate = {
  name: "低位右侧反转确认系统",
  category: "右侧反转型",
  no_future_note: "大长腿、阳包阴、均线站回均在当前 K 线形成后确认；不使用之后几天是否上涨作为条件。",
  buy_logic: "all",
  sell_logic: "any",
  buy_group_logic: "any",
  sell_group_logic: "any",
  max_hold_num: 4,
  candidate_sort: "return_desc",
  sort_window: 5,
  position_sizing: "equal_weight",
  buy_groups: [
    {
      name: "大长腿探底确认",
      logic: "all",
      conditions: [
        { indicator: "return_between", operator: "above", left: 20, right: 60, threshold: 50, lower: -0.25, upper: 0.08 },
        { indicator: "long_lower_shadow", operator: "above", left: 1, right: 60, threshold: 0.45 },
        { indicator: "volume_vs_ma", operator: "above", left: 10, right: 60, threshold: 1.1 },
      ],
    },
    {
      name: "阳包阴反包确认",
      logic: "all",
      conditions: [
        { indicator: "ma_stack", operator: "above", left: 5, right: 20, threshold: 60 },
        { indicator: "bullish_engulfing", operator: "above", left: 1, right: 60, threshold: 0 },
        { indicator: "price_vs_ma", operator: "above", left: 20, right: 60, threshold: 50 },
      ],
    },
  ],
  sell_groups: [
    {
      name: "反转失败",
      logic: "any",
      conditions: [
        { indicator: "price_vs_ma", operator: "below", left: 20, right: 60, threshold: 50 },
        { indicator: "volume_down_spike", operator: "above", left: 10, right: 60, threshold: 2.5 },
        { indicator: "range_amplitude", operator: "above", left: 1, right: 60, threshold: 0.1 },
      ],
    },
  ],
};
rightSideReversalTemplate.buy_conditions = flattenGroups(rightSideReversalTemplate.buy_groups);
rightSideReversalTemplate.sell_conditions = flattenGroups(rightSideReversalTemplate.sell_groups);

export const strategyTemplates = [
  {
    id: "top_down_trend_control",
    category: "趋势控盘型",
    title: "自上而下趋势控盘系统",
    description: "对应选股五要素中的趋势、辨识度、筹码稳定：均线多头 + 阳线优势 + 低波动。",
    strategy: topDownTrendControlTemplate,
  },
  {
    id: "c104_four_up_momentum",
    category: "强势确认型",
    title: "C104四串阳强势确认系统",
    description: "C104 阳线优势、四串阳和短期放量确认，偏右侧短线强势。",
    strategy: c104FourUpMomentumTemplate,
  },
  {
    id: "box_breakout_launch",
    category: "蓄势突破型",
    title: "蓄势箱体放量突破系统",
    description: "低/中位箱体蓄势后，当前日放量大阳并站上均线确认启动。",
    strategy: boxBreakoutLaunchTemplate,
  },
  {
    id: "pullback_resonance",
    category: "回踩共振型",
    title: "趋势回踩技术共振系统",
    description: "上升趋势里缩量回踩到均线附近，等待当日企稳确认。",
    strategy: pullbackResonanceTemplate,
  },
  {
    id: "right_side_reversal",
    category: "右侧反转型",
    title: "低位右侧反转确认系统",
    description: "大长腿、阳包阴等 K 线反转信号，强调低位和当日确认，风险更高。",
    strategy: rightSideReversalTemplate,
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
