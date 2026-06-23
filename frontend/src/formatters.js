export const formatPercent = (value, digits = 2) =>
  `${(Number(value || 0) * 100).toFixed(digits)}%`;

export const formatMoney = (value) =>
  Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 0 });
