import { describe, expect, it } from "vitest";

import { updateRuleConditionValue } from "./drawers.jsx";

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
