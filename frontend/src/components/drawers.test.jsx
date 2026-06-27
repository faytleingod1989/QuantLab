import { describe, expect, it } from "vitest";

import { strategyTemplates } from "../appConfig.jsx";
import {
  createStrategyExportPayload,
  normalizeImportedStrategy,
  securityBelongsToPool,
  symbolsForPool,
  updateRuleConditionValue,
} from "./drawers.jsx";

describe("updateRuleConditionValue", () => {
  it("resets MACD parameters when switching indicator", () => {
    const condition = { indicator: "ma_cross", operator: "cross_above", left: 20, right: 60, threshold: 50 };

    expect(updateRuleConditionValue(condition, "indicator", "macd")).toEqual({
      indicator: "macd",
      operator: "cross_above",
      left: 12,
      right: 26,
      threshold: 9,
    });
  });

  it("resets Bollinger parameters without changing the operator", () => {
    const condition = { indicator: "rsi", operator: "below", left: 14, right: 60, threshold: 35 };

    expect(updateRuleConditionValue(condition, "indicator", "bollinger")).toEqual({
      indicator: "bollinger",
      operator: "below",
      left: 20,
      right: 60,
      threshold: 2,
    });
  });
});

describe("strategy JSON import/export helpers", () => {
  it("normalizes wrapped strategy JSON and fills indicator defaults", () => {
    const imported = normalizeImportedStrategy(JSON.stringify({
      strategy: {
        name: "导入策略",
        buy_logic: "all",
        sell_logic: "any",
        max_hold_num: 5,
        candidate_sort: "return_asc",
        sort_window: 20,
        position_sizing: "equal_weight",
        buy_conditions: [{ indicator: "ma_stack", operator: "above", left: 10, right: 20, threshold: 60 }],
        sell_conditions: [{ indicator: "life_line_watch", operator: "below" }],
      },
    }));

    expect(imported.name).toBe("导入策略");
    expect(imported.max_hold_num).toBe(5);
    expect(imported.sell_conditions[0]).toMatchObject({
      indicator: "life_line_watch",
      left: 20,
      right: 10,
      threshold: 3,
      lower: -0.01,
      upper: 1.8,
    });
  });

  it("normalizes grouped strategy JSON and flattens conditions for compatibility", () => {
    const imported = normalizeImportedStrategy({
      name: "分组策略",
      buy_group_logic: "any",
      sell_group_logic: "all",
      buy_groups: [
        {
          name: "趋势组",
          logic: "all",
          conditions: [{ indicator: "ma_stack", operator: "above", left: 10, right: 20, threshold: 60 }],
        },
        {
          name: "回踩组",
          logic: "all",
          conditions: [{ indicator: "volume_vs_ma", operator: "below", left: 5, threshold: 0.7 }],
        },
      ],
      sell_groups: [
        {
          name: "风险组",
          logic: "any",
          conditions: [{ indicator: "life_line_watch", operator: "below" }],
        },
      ],
    });

    expect(imported.buy_group_logic).toBe("any");
    expect(imported.sell_group_logic).toBe("all");
    expect(imported.buy_groups).toHaveLength(2);
    expect(imported.buy_conditions.map((condition) => condition.indicator)).toEqual(["ma_stack", "volume_vs_ma"]);
    expect(imported.sell_groups[0].conditions[0]).toMatchObject({ indicator: "life_line_watch", threshold: 3 });
  });

  it("rejects unsupported indicators", () => {
    expect(() => normalizeImportedStrategy({
      name: "坏策略",
      buy_conditions: [{ indicator: "unknown_indicator" }],
      sell_conditions: [{ indicator: "ma_cross" }],
    })).toThrow("暂不支持的指标");
  });

  it("exports with a stable QuantLab schema envelope", () => {
    const payload = createStrategyExportPayload({
      name: "导出策略",
      buy_conditions: [{ indicator: "ma_cross" }],
      sell_conditions: [{ indicator: "ma_cross" }],
    });

    expect(payload.schema).toBe("quantlab.visual_strategy");
    expect(payload.schema_version).toBe(1);
    expect(payload.strategy.name).toBe("导出策略");
  });

  it("keeps every built-in strategy template importable", () => {
    expect(strategyTemplates.map((template) => template.id)).toEqual([
      "control_pullback",
      "chip_stable_ma_stack",
      "box_breakout",
    ]);

    for (const template of strategyTemplates) {
      const imported = normalizeImportedStrategy(template.strategy);
      expect(imported.name).toBe(template.strategy.name);
      expect(imported.buy_conditions.length).toBeGreaterThan(0);
      expect(imported.sell_conditions.length).toBeGreaterThan(0);
    }
  });
});

describe("stock pool helpers", () => {
  const securities = [
    { symbol: "600000.SH", name: "浦发银行", exchange: "SH", board: "沪主板" },
    { symbol: "688001.SH", name: "华兴源创", exchange: "SH", board: "科创板" },
    { symbol: "000001.SZ", name: "平安银行", exchange: "SZ", board: "深主板" },
    { symbol: "300750.SZ", name: "宁德时代", exchange: "SZ", board: "创业板" },
    { symbol: "301001.SZ", name: "凯淳股份", exchange: "SZ", board: "" },
    { symbol: "600001.SH", name: "退市示例", exchange: "SH", board: "沪市主板", status: "delisted" },
    { symbol: "830799.BJ", name: "艾融软件", exchange: "BJ", board: "北交所" },
  ];

  it("selects沪深全A without北交所", () => {
    expect(symbolsForPool(securities, "all_a")).toEqual([
      "600000.SH",
      "688001.SH",
      "000001.SZ",
      "300750.SZ",
      "301001.SZ",
    ]);
  });

  it("selects exchange and board pools", () => {
    expect(symbolsForPool(securities, "sh")).toEqual(["600000.SH", "688001.SH"]);
    expect(symbolsForPool(securities, "sz")).toEqual(["000001.SZ", "300750.SZ", "301001.SZ"]);
    expect(symbolsForPool(securities, "gem")).toEqual(["300750.SZ", "301001.SZ"]);
    expect(symbolsForPool(securities, "star")).toEqual(["688001.SH"]);
  });

  it("supports board inference from symbol suffix and excludes benchmark", () => {
    expect(securityBelongsToPool({ symbol: "688123.SH", board: "" }, "star")).toBe(true);
    expect(securityBelongsToPool({ symbol: "688123", exchange: "SSE", board: "" }, "star")).toBe(true);
    expect(securityBelongsToPool({ symbol: "300123", exchange: "SZSE", board: "" }, "gem")).toBe(true);
    expect(symbolsForPool(securities, "all_a", "000001.SZ")).not.toContain("000001.SZ");
  });
});
