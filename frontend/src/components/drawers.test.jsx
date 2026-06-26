import { describe, expect, it } from "vitest";

import { createStrategyExportPayload, normalizeImportedStrategy, updateRuleConditionValue } from "./drawers.jsx";

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
});
