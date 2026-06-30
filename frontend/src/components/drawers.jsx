import {
  useMemo,
  useState,
} from "react";

import {
  Check,
  Database,
  Play,
  Pulse,
  SlidersHorizontal,
  X,
} from "@phosphor-icons/react";

import { strategyTemplates } from "../appConfig";
import { RateInput, SettingRow } from "./common";

const STRATEGY_JSON_SCHEMA_VERSION = 1;

export function SettingsDrawer({ settings, setSettings, onRun, onCancel, running, progress, close }) {
  const update = (field, value) => setSettings((current) => ({ ...current, [field]: value }));
  return (
    <aside className="settings-drawer">
      <div className="drawer-title">
        <div>
          <b>A 股回测设置</b>
          <span>沪深 A 股 · 日线</span>
        </div>
        <button className="icon-button" onClick={close} aria-label="关闭">
          <X size={18} />
        </button>
      </div>
      <section>
        <h3>基础规则</h3>
        <SettingRow label="市场范围"><span className="static-value">沪深 A 股</span></SettingRow>
        <SettingRow label="交易规则"><span className="static-value">T+1</span></SettingRow>
        <SettingRow label="数据频率">
          <select value={settings.frequency} disabled><option value="1d">日线（当前）</option></select>
        </SettingRow>
        <small className="hint">分钟线架构已预留，将在后续版本开放。</small>
      </section>
      <section>
        <h3>资金与仓位</h3>
        <SettingRow label="初始资金">
          <input type="number" value={settings.initial_cash} onChange={(event) => update("initial_cash", Number(event.target.value))} />
        </SettingRow>
        <SettingRow label="最大仓位">
          <div className="input-suffix">
            <input type="number" value={settings.max_position * 100} onChange={(event) => update("max_position", Number(event.target.value) / 100)} />
            <span>%</span>
          </div>
        </SettingRow>
        <SettingRow label="单股上限">
          <div className="input-suffix">
            <input type="number" value={(settings.max_symbol_position || 0.35) * 100} onChange={(event) => update("max_symbol_position", Number(event.target.value) / 100)} />
            <span>%</span>
          </div>
        </SettingRow>
        <SettingRow label="调仓周期">
          <input type="number" min="1" max="250" value={settings.rebalance_days || 1} onChange={(event) => update("rebalance_days", Number(event.target.value))} />
        </SettingRow>
        <SettingRow label="止损">
          <div className="input-suffix">
            <input type="number" value={(settings.stop_loss_pct || 0) * 100} onChange={(event) => update("stop_loss_pct", Number(event.target.value) / 100)} />
            <span>%</span>
          </div>
        </SettingRow>
        <SettingRow label="止盈">
          <div className="input-suffix">
            <input type="number" value={(settings.take_profit_pct || 0) * 100} onChange={(event) => update("take_profit_pct", Number(event.target.value) / 100)} />
            <span>%</span>
          </div>
        </SettingRow>
      </section>
      <section>
        <h3>股票池过滤</h3>
        <SettingRow label="排除 ST">
          <select value={settings.exclude_st === false ? "no" : "yes"} onChange={(event) => update("exclude_st", event.target.value === "yes")}>
            <option value="yes">是</option>
            <option value="no">否</option>
          </select>
        </SettingRow>
        <SettingRow label="上市天数">
          <input type="number" min="0" value={settings.min_listed_days || 0} onChange={(event) => update("min_listed_days", Number(event.target.value))} />
        </SettingRow>
        <SettingRow label="20日均额">
          <input type="number" min="0" value={settings.min_average_amount || 0} onChange={(event) => update("min_average_amount", Number(event.target.value))} />
        </SettingRow>
        <small className="hint">过滤条件只影响新买入候选，不会强制卖出已持仓股票。</small>
      </section>
      <section>
        <h3>交易成本（双边）</h3>
        <RateInput label="佣金费率" value={settings.commission_rate} onChange={(value) => update("commission_rate", value)} note={`最低 ${settings.min_commission} 元`} />
        <RateInput label="印花税率" value={settings.stamp_duty_rate} onChange={(value) => update("stamp_duty_rate", value)} note="仅卖出收取" />
        <RateInput label="滑点（成交价）" value={settings.slippage_rate} onChange={(value) => update("slippage_rate", value)} note="按成交价比例" />
        <RateInput label="过户费率" value={settings.transfer_fee_rate} onChange={(value) => update("transfer_fee_rate", value)} note="规则可版本化" />
      </section>
      <section>
        <h3>数据设置</h3>
        <SettingRow label="数据来源"><span className="static-value">{settings.dataset_id ? "本地数据快照" : "当前股票池 / 本地日线仓库"}</span></SettingRow>
        <SettingRow label="信号价格口径">
          <select value={settings.signal_price_mode || "unadjusted"} onChange={(event) => update("signal_price_mode", event.target.value)}>
            <option value="unadjusted">未复权收盘价</option>
            <option value="adjusted">复权收盘价</option>
          </select>
        </SettingRow>
        <SettingRow label="撮合价格口径"><span className="static-value">未复权开盘/收盘</span></SettingRow>
        <SettingRow label="报告批注">
          <textarea value={settings.report_note || ""} maxLength={1000} onChange={(event) => update("report_note", event.target.value)} placeholder="记录本次回测假设、观察或复盘结论" />
        </SettingRow>
        <small className="hint">真实行情和 CSV 会先固化为带指纹的数据集；可用复权价算信号，但撮合、现金和费用始终使用未复权价格。</small>
      </section>
      <div className="task-actions">
        {running ? <button className="ghost" onClick={onCancel}>取消</button> : null}
        <button className="primary run-button" onClick={onRun} disabled={running}>
          {running ? <Pulse className="spin" size={18} /> : <Play weight="fill" size={18} />}
          {running ? `回测中 ${Math.round(progress * 100)}%` : "运行回测"}
        </button>
      </div>
    </aside>
  );
}

const indicatorOptions = [
  ["ma_cross", "均线交叉"],
  ["price_vs_ma", "价格均线"],
  ["rsi", "RSI"],
  ["macd", "MACD"],
  ["bollinger", "布林带"],
  ["ma_stack", "均线多头排列"],
  ["volume_vs_ma", "成交量/均量"],
  ["volume_max_vs_ma", "区间最大量/均量"],
  ["return_between", "区间收益率"],
  ["kline_up_ratio", "阳线优势"],
  ["range_amplitude", "区间振幅"],
  ["body_amplitude", "实体振幅"],
  ["price_ma_deviation", "价格偏离均线"],
  ["volume_return_spike", "放量大阳"],
  ["volume_down_spike", "天量阴线"],
  ["life_line_watch", "生命线观察"],
];

const operatorOptions = [
  ["cross_above", "上穿"],
  ["cross_below", "下穿"],
  ["above", "高于"],
  ["below", "低于"],
];

export const indicatorDefaults = {
  ma_cross: { left: 20, right: 60, threshold: 50 },
  price_vs_ma: { left: 20, right: 60, threshold: 50 },
  rsi: { left: 14, right: 60, threshold: 50 },
  macd: { left: 12, right: 26, threshold: 9 },
  bollinger: { left: 20, right: 60, threshold: 2 },
  ma_stack: { left: 10, right: 20, threshold: 60 },
  volume_vs_ma: { left: 20, right: 60, threshold: 1.5 },
  volume_max_vs_ma: { left: 20, right: 20, threshold: 3 },
  return_between: { left: 1, right: 60, threshold: 50, lower: -0.01, upper: 0.05 },
  kline_up_ratio: { left: 10, right: 60, threshold: 1.5 },
  range_amplitude: { left: 20, right: 60, threshold: 0.2 },
  body_amplitude: { left: 10, right: 60, threshold: 0.1 },
  price_ma_deviation: { left: 10, right: 60, threshold: 1.02 },
  volume_return_spike: { left: 10, right: 60, threshold: 3, lower: 0.07 },
  volume_down_spike: { left: 10, right: 60, threshold: 3 },
  life_line_watch: { left: 20, right: 10, threshold: 3, lower: -0.01, upper: 1.8 },
};

export function updateRuleConditionValue(condition, key, value) {
  if (key === "indicator") {
    return { ...condition, ...indicatorDefaults[value], indicator: value };
  }
  return { ...condition, [key]: key === "operator" ? value : Number(value) };
}

function ensureRuleList(value, field) {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error(`${field} 至少需要 1 条规则`);
  }
  return value.map((condition) => {
    if (!condition || typeof condition !== "object" || Array.isArray(condition)) {
      throw new Error(`${field} 包含无效规则`);
    }
    const indicator = condition.indicator || "ma_cross";
    if (!indicatorDefaults[indicator]) {
      throw new Error(`暂不支持的指标：${indicator}`);
    }
    return {
      ...indicatorDefaults[indicator],
      ...condition,
      indicator,
      operator: condition.operator || "above",
    };
  });
}

function flattenGroups(groups) {
  return groups.flatMap((group) => group.conditions);
}

function ensureRuleGroupList(value, field) {
  if (!Array.isArray(value) || value.length === 0) {
    return null;
  }
  return value.map((group, index) => {
    if (!group || typeof group !== "object" || Array.isArray(group)) {
      throw new Error(`${field} 包含无效规则组`);
    }
    return {
      name: String(group.name || `${field}${index + 1}`).slice(0, 60),
      logic: group.logic === "any" ? "any" : "all",
      conditions: ensureRuleList(group.conditions, `${field}${index + 1}`),
    };
  });
}

export function normalizeImportedStrategy(rawValue) {
  const parsed = typeof rawValue === "string" ? JSON.parse(rawValue) : rawValue;
  const candidate = parsed?.strategy && typeof parsed.strategy === "object" ? parsed.strategy : parsed;
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) {
    throw new Error("JSON 必须是策略对象");
  }
  const name = String(candidate.name || "").trim();
  if (!name) {
    throw new Error("策略名称不能为空");
  }
  const buyGroups = ensureRuleGroupList(candidate.buy_groups, "买入组");
  const sellGroups = ensureRuleGroupList(candidate.sell_groups, "卖出组");
  return {
    name,
    buy_logic: candidate.buy_logic === "any" ? "any" : "all",
    sell_logic: candidate.sell_logic === "all" ? "all" : "any",
    buy_group_logic: candidate.buy_group_logic === "all" ? "all" : "any",
    sell_group_logic: candidate.sell_group_logic === "all" ? "all" : "any",
    max_hold_num: candidate.max_hold_num ? Number(candidate.max_hold_num) : null,
    candidate_sort: ["none", "return_asc", "return_desc"].includes(candidate.candidate_sort) ? candidate.candidate_sort : "none",
    sort_window: Number(candidate.sort_window || 20),
    position_sizing: candidate.position_sizing === "equal_weight" ? "equal_weight" : "cash_weight",
    buy_conditions: buyGroups ? flattenGroups(buyGroups) : ensureRuleList(candidate.buy_conditions, "买入条件"),
    sell_conditions: sellGroups ? flattenGroups(sellGroups) : ensureRuleList(candidate.sell_conditions, "卖出条件"),
    buy_groups: buyGroups,
    sell_groups: sellGroups,
  };
}

export function createStrategyExportPayload(strategy) {
  return {
    schema: "quantlab.visual_strategy",
    schema_version: STRATEGY_JSON_SCHEMA_VERSION,
    exported_at: new Date().toISOString(),
    strategy,
  };
}

function strategyExportFilename(strategy) {
  const safeName = String(strategy?.name || "strategy")
    .trim()
    .replace(/[\\/:*?"<>|]/g, "-")
    .replace(/\s+/g, "-")
    .slice(0, 60) || "strategy";
  return `${safeName}.quantlab-strategy.json`;
}

const strategySides = {
  buy: {
    label: "买入",
    tone: "green",
    conditionsKey: "buy_conditions",
    groupsKey: "buy_groups",
    logicKey: "buy_logic",
    groupLogicKey: "buy_group_logic",
    defaultOperator: "above",
  },
  sell: {
    label: "卖出",
    tone: "red",
    conditionsKey: "sell_conditions",
    groupsKey: "sell_groups",
    logicKey: "sell_logic",
    groupLogicKey: "sell_group_logic",
    defaultOperator: "below",
  },
};

function defaultConditionForSide(side) {
  return {
    indicator: "price_vs_ma",
    operator: strategySides[side].defaultOperator,
    left: 20,
    right: 60,
    threshold: 50,
  };
}

function groupsForSide(strategy, side) {
  const meta = strategySides[side];
  const groups = strategy[meta.groupsKey];
  if (Array.isArray(groups) && groups.length) {
    return groups;
  }
  return [
    {
      name: `${meta.label}组 1`,
      logic: strategy[meta.logicKey] || (side === "buy" ? "all" : "any"),
      conditions: strategy[meta.conditionsKey] || [defaultConditionForSide(side)],
    },
  ];
}

function updateStrategySide(currentStrategy, side, nextGroups) {
  const meta = strategySides[side];
  const normalizedGroups = nextGroups.map((group, index) => ({
    ...group,
    name: group.name || `${meta.label}组 ${index + 1}`,
    conditions: group.conditions.length ? group.conditions : [defaultConditionForSide(side)],
  }));
  return {
    ...currentStrategy,
    [meta.groupsKey]: normalizedGroups,
    [meta.conditionsKey]: flattenGroups(normalizedGroups),
    [meta.logicKey]: normalizedGroups[0]?.logic || currentStrategy[meta.logicKey],
  };
}

function RuleNode({ title, tone, condition, onChange, onRemove }) {
  const indicator = condition.indicator || "ma_cross";
  const thresholdLabel = {
    rsi: "阈值",
    macd: "信号周期",
    bollinger: "标准差倍数",
    ma_stack: "长周期",
    volume_vs_ma: "均量倍率",
    volume_max_vs_ma: "最大量倍率",
    kline_up_ratio: "阳/阴倍率",
    range_amplitude: "振幅阈值",
    body_amplitude: "最大实体阈值",
    price_ma_deviation: "均线倍率",
    volume_return_spike: "放量倍率",
    volume_down_spike: "放量倍率",
    life_line_watch: "观察天数",
  }[indicator];
  const leftLabel = {
    volume_vs_ma: "均量周期",
    volume_max_vs_ma: "统计窗口",
    return_between: "收益窗口",
    kline_up_ratio: "统计窗口",
    range_amplitude: "统计窗口",
    body_amplitude: "统计窗口",
    price_ma_deviation: "均线周期",
    volume_return_spike: "均量周期",
    volume_down_spike: "均量周期",
    life_line_watch: "生命线周期",
    bollinger: "周期",
    rsi: "RSI周期",
  }[indicator] || "短周期";
  const rightLabel = indicator === "life_line_watch" ? "均量周期" : "长周期";
  const showRight = !["price_vs_ma", "rsi", "bollinger", "volume_vs_ma", "return_between", "kline_up_ratio", "range_amplitude", "body_amplitude", "price_ma_deviation", "volume_return_spike", "volume_down_spike"].includes(indicator);
  const showRange = ["return_between", "life_line_watch"].includes(indicator);
  const showLower = indicator === "volume_return_spike";
  const rangeLabels = {
    life_line_watch: ["小阴跌幅下限", "放量倍率"],
  }[indicator] || ["下限", "上限"];
  const rangeDefaults = {
    life_line_watch: [-0.01, 1.8],
  }[indicator] || [-0.01, 0.05];
  return (
    <div className={`rule-node ${tone}`}>
      <div className="rule-node-title">
        <b>{title}</b>
        {onRemove ? <button type="button" onClick={onRemove}>删除</button> : null}
      </div>
      <span>指标</span>
      <select value={indicator} onChange={(event) => onChange("indicator", event.target.value)}>
        {indicatorOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <span>条件</span>
      <select value={condition.operator || "cross_above"} onChange={(event) => onChange("operator", event.target.value)}>
        {operatorOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <span>{leftLabel}</span>
      <input type="number" value={condition.left} onChange={(event) => onChange("left", event.target.value)} />
      {showRight ? (
        <>
          <span>{rightLabel}</span>
          <input type="number" value={condition.right} onChange={(event) => onChange("right", event.target.value)} />
        </>
      ) : null}
      {thresholdLabel ? (
        <>
          <span>{thresholdLabel}</span>
          <input type="number" value={condition.threshold} onChange={(event) => onChange("threshold", event.target.value)} />
        </>
      ) : null}
      {showRange ? (
        <>
          <span>{rangeLabels[0]}</span>
          <input type="number" step="0.01" value={condition.lower ?? rangeDefaults[0]} onChange={(event) => onChange("lower", event.target.value)} />
          <span>{rangeLabels[1]}</span>
          <input type="number" step="0.01" value={condition.upper ?? rangeDefaults[1]} onChange={(event) => onChange("upper", event.target.value)} />
        </>
      ) : null}
      {showLower ? (
        <>
          <span>涨幅下限</span>
          <input type="number" step="0.01" value={condition.lower ?? 0.07} onChange={(event) => onChange("lower", event.target.value)} />
        </>
      ) : null}
    </div>
  );
}

export function StrategyModal({ settings, setSettings, onSave, saving, versionInfo, mode = "trading", setMode, close }) {
  const strategy = settings.strategy;
  const [strategyJsonText, setStrategyJsonText] = useState("");
  const [strategyTransferStatus, setStrategyTransferStatus] = useState("");
  const [showJsonPanel, setShowJsonPanel] = useState(false);
  const [selectedTemplateId, setSelectedTemplateId] = useState(strategyTemplates[0]?.id || "");
  const activeMode = mode === "selection" ? "selection" : "trading";
  const modeTitle = activeMode === "selection" ? "选股策略" : "交易策略";
  const selectedTemplate = strategyTemplates.find((template) => template.id === selectedTemplateId) || strategyTemplates[0];
  const buyGroups = groupsForSide(strategy, "buy");
  const sellGroups = groupsForSide(strategy, "sell");
  const updateSideGroups = (side, updater) =>
    setSettings((current) => ({
      ...current,
      strategy: updateStrategySide(
        current.strategy,
        side,
        updater(groupsForSide(current.strategy, side))
      ),
    }));
  const updateGroupField = (side, groupIndex, key, value) =>
    updateSideGroups(side, (groups) =>
      groups.map((group, index) => (index === groupIndex ? { ...group, [key]: value } : group))
    );
  const updateCondition = (side, groupIndex, targetIndex, key, value) =>
    updateSideGroups(side, (groups) =>
      groups.map((group, index) =>
        index === groupIndex
          ? {
              ...group,
              conditions: group.conditions.map((condition, conditionIndex) =>
                conditionIndex === targetIndex
                  ? updateRuleConditionValue(condition, key, value)
                  : condition
              ),
            }
          : group
      )
    );
  const addCondition = (side, groupIndex) =>
    updateSideGroups(side, (groups) =>
      groups.map((group, index) =>
        index === groupIndex
          ? { ...group, conditions: [...group.conditions, defaultConditionForSide(side)] }
          : group
      )
    );
  const removeCondition = (side, groupIndex, removeIndex) =>
    updateSideGroups(side, (groups) =>
      groups.map((group, index) =>
        index === groupIndex
          ? {
              ...group,
              conditions: group.conditions.filter((_, conditionIndex) => conditionIndex !== removeIndex),
            }
          : group
      )
    );
  const addGroup = (side) =>
    updateSideGroups(side, (groups) => [
      ...groups,
      {
        name: `${strategySides[side].label}组 ${groups.length + 1}`,
        logic: side === "buy" ? "all" : "any",
        conditions: [defaultConditionForSide(side)],
      },
    ]);
  const removeGroup = (side, removeIndex) =>
    updateSideGroups(side, (groups) => groups.filter((_, index) => index !== removeIndex));
  const applySelectedTemplate = () => {
    const templateStrategy = selectedTemplate?.strategy;
    if (!templateStrategy) return;
    setSettings((current) => ({
      ...current,
      max_symbol_position: templateStrategy.max_hold_num ? 1 / templateStrategy.max_hold_num : current.max_symbol_position,
      max_position: 1,
      stop_loss_pct: 0.08,
      take_profit_pct: 0,
      exclude_st: true,
      strategy: JSON.parse(JSON.stringify(templateStrategy)),
    }));
    setStrategyTransferStatus(`已套用模板「${selectedTemplate.title}」，保存后会形成新版本`);
  };
  const updateStrategyField = (field, value) =>
    setSettings((current) => ({
      ...current,
      strategy: { ...current.strategy, [field]: value },
    }));
  const importStrategy = (rawText) => {
    try {
      const importedStrategy = normalizeImportedStrategy(rawText);
      setSettings((current) => ({
        ...current,
        strategy: importedStrategy,
        strategy_version_id: null,
      }));
      setStrategyTransferStatus(`已导入策略「${importedStrategy.name}」，保存后会形成新版本`);
    } catch (error) {
      setStrategyTransferStatus(`导入失败：${error.message}`);
    }
  };
  const exportStrategy = () => {
    const payload = createStrategyExportPayload(strategy);
    const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = strategyExportFilename(strategy);
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setStrategyTransferStatus(`已导出策略「${strategy.name}」`);
  };
  const importStrategyFile = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    importStrategy(await file.text());
    event.target.value = "";
  };
  return (
    <div className="modal-backdrop" onClick={(event) => event.target === event.currentTarget && close()}>
      <div className="strategy-modal">
        <div className="modal-head">
          <div>
            <span className="eyebrow">可视化策略</span>
            <h2>配置「{strategy.name}」· {modeTitle}</h2>
            <p>{activeMode === "selection" ? "先确定候选股票与排序，再交给交易策略执行。" : "编辑买入、卖出、仓位和风控规则。"}{versionInfo ? ` 当前 ${versionInfo}` : " 尚未保存版本"}</p>
          </div>
          <button className="icon-button" onClick={close}><X size={20} /></button>
        </div>
        <div className="strategy-template-bar">
          <div className="strategy-mode-tabs" role="tablist" aria-label="策略编辑模块">
            <button className={activeMode === "selection" ? "active" : ""} onClick={() => setMode?.("selection")} role="tab" aria-selected={activeMode === "selection"}>选股策略</button>
            <button className={activeMode === "trading" ? "active" : ""} onClick={() => setMode?.("trading")} role="tab" aria-selected={activeMode === "trading"}>交易策略</button>
          </div>
          <select className="strategy-template-select" value={selectedTemplateId} onChange={(event) => setSelectedTemplateId(event.target.value)} title={selectedTemplate?.description}>
            {strategyTemplates.map((template) => (
              <option key={template.id} value={template.id}>{template.title}</option>
            ))}
          </select>
          <button className="ghost" onClick={applySelectedTemplate}>套用模板</button>
          <button className="ghost" onClick={() => setShowJsonPanel((current) => !current)}>{showJsonPanel ? "收起 JSON" : "粘贴导入"}</button>
          <button className="ghost" onClick={exportStrategy}>导出 JSON</button>
          <label className="strategy-json-upload">
            <input type="file" accept="application/json,.json" onChange={importStrategyFile} />
            导入 JSON
          </label>
        </div>
        <div className="strategy-module-config single">
          {activeMode === "selection" ? (
            <section>
              <div>
                <span>选股策略</span>
                <b>股票池、过滤与候选排序</b>
                <small>决定候选股票如何进入交易模块。</small>
              </div>
              <label>当前股票池<input value={`沪深 A 股 · ${settings.symbols.length} 只`} readOnly /></label>
              <label>最多持股<input type="number" min="1" max="200" value={strategy.max_hold_num || ""} onChange={(event) => updateStrategyField("max_hold_num", event.target.value ? Number(event.target.value) : null)} /></label>
              <label>候选排序
                <select value={strategy.candidate_sort || "none"} onChange={(event) => updateStrategyField("candidate_sort", event.target.value)}>
                  <option value="none">不排序</option>
                  <option value="return_asc">近N日涨幅升序（回撤优先）</option>
                  <option value="return_desc">近N日涨幅降序（强势优先）</option>
                </select>
              </label>
              <label>排序窗口<input type="number" min="2" max="500" value={strategy.sort_window || 20} onChange={(event) => updateStrategyField("sort_window", Number(event.target.value))} /></label>
            </section>
          ) : (
            <section>
              <div>
                <span>交易策略</span>
                <b>买入、卖出、仓位与风控</b>
                <small>决定信号如何执行，以及如何管理风险。</small>
              </div>
              <label>买入组间
                <select value={strategy.buy_group_logic || "any"} onChange={(event) => updateStrategyField("buy_group_logic", event.target.value)}>
                  <option value="any">任一组满足</option>
                  <option value="all">全部组满足</option>
                </select>
              </label>
              <label>卖出组间
                <select value={strategy.sell_group_logic || "any"} onChange={(event) => updateStrategyField("sell_group_logic", event.target.value)}>
                  <option value="any">任一组满足</option>
                  <option value="all">全部组满足</option>
                </select>
              </label>
              <label>仓位摘要<input value={`总仓 ${Math.round(settings.max_position * 100)}% · 单票 ${Math.round((settings.max_symbol_position || 0.35) * 100)}%`} readOnly /></label>
              <label>最多持股<input value={`${strategy.max_hold_num || "不限"} 只`} readOnly /></label>
            </section>
          )}
        </div>
        {showJsonPanel ? (
          <div className="strategy-json-panel">
            <textarea
              value={strategyJsonText}
              onChange={(event) => setStrategyJsonText(event.target.value)}
              placeholder="也可以把策略 JSON 粘贴到这里，再点击导入。支持纯 strategy 对象，或 { strategy: ... } 包装格式。"
            />
            <button className="ghost" disabled={!strategyJsonText.trim()} onClick={() => importStrategy(strategyJsonText)}>从粘贴内容导入</button>
            <span>{strategyTransferStatus || "导入会替换当前可视化策略；如需持久化，请再点击保存新版本。"}</span>
          </div>
        ) : null}
        {activeMode === "selection" ? (
          <div className="selection-editor-panel">
            <div className="rule-node source"><Database size={21} /><b>股票池</b><span>沪深 A 股 · {settings.symbols.length} 只</span></div>
            <div className="selection-flow-copy">
              <b>选股策略只负责“谁有资格进入交易”</b>
              <span>这里设置候选池规模、排序方式和持股上限；买入、卖出和仓位执行请切到「交易策略」。</span>
            </div>
            <div className="rule-node risk"><SlidersHorizontal size={21} /><b>候选输出</b><span>最多 {strategy.max_hold_num || "不限"} 只 · {strategy.sort_window || 20} 日排序窗口</span></div>
          </div>
        ) : (
          <div className="rule-flow">
          <div className="rule-node source"><Database size={21} /><b>股票池</b><span>沪深 A 股 · {settings.symbols.length} 只</span></div>
          <div className="connector" />
          <div className="rule-side">
            <div className="rule-side-head">
              <b>买入条件组（{(strategy.buy_group_logic || "any") === "all" ? "全部组满足" : "任一组满足"}）</b>
              <button onClick={() => addGroup("buy")}>+ 买入组</button>
            </div>
            {buyGroups.map((group, groupIndex) => (
              <div className="rule-group" key={`buy-group-${groupIndex}`}>
                <div className="rule-group-head">
                  <input value={group.name} onChange={(event) => updateGroupField("buy", groupIndex, "name", event.target.value)} />
                  <select value={group.logic || "all"} onChange={(event) => updateGroupField("buy", groupIndex, "logic", event.target.value)}>
                    <option value="all">组内全部满足</option>
                    <option value="any">组内任一满足</option>
                  </select>
                  <button onClick={() => addCondition("buy", groupIndex)}>+ 条件</button>
                  {buyGroups.length > 1 ? <button className="danger-mini" onClick={() => removeGroup("buy", groupIndex)}>删组</button> : null}
                </div>
                <div className="rule-node-grid">
                  {group.conditions.map((condition, index) => (
                    <RuleNode
                      key={`buy-${groupIndex}-${index}`}
                      title={`买入 ${groupIndex + 1}.${index + 1}`}
                      tone="green"
                      condition={condition}
                      onChange={(key, value) => updateCondition("buy", groupIndex, index, key, value)}
                      onRemove={group.conditions.length > 1 ? () => removeCondition("buy", groupIndex, index) : null}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="connector" />
          <div className="rule-side">
            <div className="rule-side-head">
              <b>卖出条件组（{(strategy.sell_group_logic || "any") === "all" ? "全部组满足" : "任一组满足"}）</b>
              <button onClick={() => addGroup("sell")}>+ 卖出组</button>
            </div>
            {sellGroups.map((group, groupIndex) => (
              <div className="rule-group" key={`sell-group-${groupIndex}`}>
                <div className="rule-group-head">
                  <input value={group.name} onChange={(event) => updateGroupField("sell", groupIndex, "name", event.target.value)} />
                  <select value={group.logic || "any"} onChange={(event) => updateGroupField("sell", groupIndex, "logic", event.target.value)}>
                    <option value="all">组内全部满足</option>
                    <option value="any">组内任一满足</option>
                  </select>
                  <button onClick={() => addCondition("sell", groupIndex)}>+ 条件</button>
                  {sellGroups.length > 1 ? <button className="danger-mini" onClick={() => removeGroup("sell", groupIndex)}>删组</button> : null}
                </div>
                <div className="rule-node-grid">
                  {group.conditions.map((condition, index) => (
                    <RuleNode
                      key={`sell-${groupIndex}-${index}`}
                      title={`卖出 ${groupIndex + 1}.${index + 1}`}
                      tone="red"
                      condition={condition}
                      onChange={(key, value) => updateCondition("sell", groupIndex, index, key, value)}
                      onRemove={group.conditions.length > 1 ? () => removeCondition("sell", groupIndex, index) : null}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="connector" />
          <div className="rule-node risk"><SlidersHorizontal size={21} /><b>仓位管理</b><span>最大仓位 {settings.max_position * 100}% · 最多 {strategy.max_hold_num || "不限"} 只</span></div>
        </div>
        )}
        <div className="validation-row">
          <span><Check size={17} weight="bold" />规则检查通过</span>
          {activeMode === "selection" ? (
            <>
              <span>候选池先过滤再排序</span>
              <span>输出给交易策略执行</span>
              <span>股票池来自数据中心</span>
            </>
          ) : (
            <>
              <span>信号在收盘后产生</span>
              <span>下一交易日开盘成交</span>
              <span>T+1 可卖</span>
            </>
          )}
        </div>
        <div className="modal-actions">
          <button className="ghost" onClick={close}>取消</button>
          <button className="primary" onClick={onSave} disabled={saving}>
            <Check size={18} />{saving ? "保存中…" : "保存新版本"}
          </button>
        </div>
      </div>
    </div>
  );
}

const stockPoolOptions = [
  { id: "all_a", title: "沪深全A", helper: "上证主板 + 深证主板 + 创业板 + 科创板" },
  { id: "sh_main", title: "上证主板", helper: "600/601/603/605 开头" },
  { id: "sz_main", title: "深证主板", helper: "000/001/002/003 开头" },
  { id: "gem", title: "创业板", helper: "300/301/302 开头" },
  { id: "star", title: "科创板", helper: "688/689 开头" },
  { id: "bj", title: "北交所", helper: "BJ / 8 / 4 / 920 开头" },
];

function getSecurityParts(item) {
  const symbol = String(item?.symbol || "").toUpperCase();
  const code = symbol.split(".")[0] || "";
  const explicitExchange = String(item?.exchange || "").toUpperCase();
  const suffixExchange = String(symbol.split(".")[1] || "").toUpperCase();
  const inferredExchange = code.startsWith("6")
    ? "SH"
    : code.startsWith("0") || code.startsWith("2") || code.startsWith("3")
      ? "SZ"
      : code.startsWith("920") || code.startsWith("8") || code.startsWith("4")
        ? "BJ"
        : "";
  const exchange = ["SH", "SZ", "BJ"].includes(explicitExchange)
    ? explicitExchange
    : suffixExchange || inferredExchange;
  const board = String(item?.board || "");
  return { symbol, code, exchange, board };
}

export function securityBelongsToPool(item, poolId) {
  const { code, exchange, board } = getSecurityParts(item);
  if (item?.status === "delisted") {
    return false;
  }
  if (poolId === "all_a") {
    return ["SH", "SZ"].includes(exchange) && ["0", "3", "6"].some((prefix) => code.startsWith(prefix));
  }
  if (poolId === "all_market") {
    return exchange === "SH" || exchange === "SZ" || exchange === "BJ";
  }
  if (poolId === "sh") {
    return exchange === "SH";
  }
  if (poolId === "sz") {
    return exchange === "SZ";
  }
  if (poolId === "sh_main") {
    return exchange === "SH" && ["600", "601", "603", "605"].some((prefix) => code.startsWith(prefix));
  }
  if (poolId === "sz_main") {
    return exchange === "SZ" && ["000", "001", "002", "003"].some((prefix) => code.startsWith(prefix));
  }
  if (poolId === "gem") {
    return exchange === "SZ" && (board.includes("创业") || code.startsWith("300") || code.startsWith("301") || code.startsWith("302"));
  }
  if (poolId === "star") {
    return exchange === "SH" && (board.includes("科创") || code.startsWith("688") || code.startsWith("689"));
  }
  if (poolId === "bj") {
    return exchange === "BJ";
  }
  return false;
}

export function symbolsFromSecurities(securities, benchmark = null) {
  const seen = new Set();
  return securities
    .map((item) => item.symbol)
    .filter((symbol) => {
      if (!symbol || symbol === benchmark || seen.has(symbol)) {
        return false;
      }
      seen.add(symbol);
      return true;
    });
}

export function symbolsForPool(securities, poolId, benchmark = null) {
  return symbolsFromSecurities(
    securities.filter((item) => securityBelongsToPool(item, poolId)),
    benchmark
  );
}

export function poolSelectionState(selectedSymbols, poolSymbols) {
  if (!poolSymbols.length) return "empty";
  const selected = new Set(selectedSymbols);
  const selectedCount = poolSymbols.filter((symbol) => selected.has(symbol)).length;
  if (selectedCount === 0) return "none";
  return selectedCount === poolSymbols.length ? "selected" : "partial";
}

export function DataDrawer({
  settings,
  setSettings,
  securities,
  source,
  datasets,
  datasetQuality,
  onImport,
  onImportIndustryHistory,
  importing,
  onSync,
  onSyncAll,
  onCancelSyncAll,
  onRetryFailedAll,
  syncing,
  syncingAll,
  allMarketSyncTask,
  marketCoverage,
  onSelectDataset,
  onDeleteDataset,
  close,
}) {
  const [query, setQuery] = useState("");
  const filteredSecurities = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return keyword
      ? securities.filter((item) =>
          `${item.symbol} ${item.name} ${item.board || ""} ${item.industry || ""}`
            .toLowerCase()
            .includes(keyword)
        )
      : securities;
  }, [query, securities]);
  const visibleSecurities = filteredSecurities.slice(0, 200);
  const hiddenCount = Math.max(0, filteredSecurities.length - visibleSecurities.length);
  const filteredSymbols = useMemo(
    () => symbolsFromSecurities(filteredSecurities, settings.benchmark),
    [filteredSecurities, settings.benchmark]
  );
  const stockPools = useMemo(
    () =>
      stockPoolOptions.map((pool) => ({
        ...pool,
        symbols: symbolsForPool(securities, pool.id, settings.benchmark),
      })),
    [securities, settings.benchmark]
  );
  const coverageByPool = useMemo(
    () => Object.fromEntries((marketCoverage?.pools || []).map((pool) => [pool.id, pool.coverage])),
    [marketCoverage]
  );
  const selectedCoverage = marketCoverage?.selected?.coverage;
  const allMarketCoverage = coverageByPool.all_a;
  const allMarketPoolCount = stockPools.find((pool) => pool.id === "all_a")?.symbols.length || 0;
  const marketTotalCount = marketCoverage?.total_symbol_count || source?.symbol_count || securities.length;
  const taskExpected = Number(allMarketSyncTask?.expected || allMarketSyncTask?.coverage?.expected || allMarketCoverage?.expected || allMarketPoolCount || 0);
  const taskCovered = Number(allMarketSyncTask?.covered || allMarketSyncTask?.coverage?.covered || allMarketCoverage?.covered || 0);
  const taskProgress = taskExpected ? Math.round((taskCovered / taskExpected) * 100) : 0;
  const hasIncompleteAllMarketDataset = datasets.some((dataset) => (
    dataset.source === "akshare_all" &&
    allMarketPoolCount &&
    Math.max(0, Number(dataset.symbol_count || 0) - 1) < allMarketPoolCount
  ));
  const poolStates = useMemo(
    () =>
      Object.fromEntries(
        stockPools.map((pool) => [
          pool.id,
          poolSelectionState(settings.symbols, pool.symbols),
        ])
      ),
    [settings.symbols, stockPools]
  );
  const applySymbols = (symbols) =>
    setSettings((current) => ({
      ...current,
      dataset_id: null,
      symbols,
    }));
  const togglePool = (pool) =>
    setSettings((current) => {
      const currentSymbols = new Set(current.symbols);
      const poolFullySelected = pool.symbols.length > 0 && pool.symbols.every((symbol) => currentSymbols.has(symbol));
      if (poolFullySelected) {
        for (const symbol of pool.symbols) currentSymbols.delete(symbol);
      } else {
        for (const symbol of pool.symbols) currentSymbols.add(symbol);
      }
      return {
        ...current,
        dataset_id: null,
        symbols: securities
          .map((item) => item.symbol)
          .filter((symbol) => currentSymbols.has(symbol) && symbol !== current.benchmark),
      };
    });
  const selectFiltered = () =>
    setSettings((current) => {
      const currentSymbols = new Set(current.symbols);
      for (const symbol of filteredSymbols) currentSymbols.add(symbol);
      return {
        ...current,
        dataset_id: null,
        symbols: securities
          .map((item) => item.symbol)
          .filter((symbol) => currentSymbols.has(symbol) && symbol !== current.benchmark),
      };
    });
  const updateDate = (field, value) =>
    setSettings((current) => ({
      ...current,
      [field]: value,
    }));
  const clearSelection = () => applySymbols([]);
  const failedSymbols = allMarketSyncTask?.failed_symbols || allMarketSyncTask?.last_failed_symbols || [];
  const skippedSymbols = allMarketSyncTask?.skipped_symbols || [];
  const toggle = (symbol) =>
    setSettings((current) => ({
      ...current,
      dataset_id: null,
      symbols: current.symbols.includes(symbol)
        ? current.symbols.filter((item) => item !== symbol)
        : [...current.symbols, symbol],
    }));
  return (
    <div className="modal-backdrop" onClick={(event) => event.target === event.currentTarget && close()}>
      <div className="data-modal">
        <div className="modal-head">
          <div>
            <span className="eyebrow">数据中心</span>
            <h2>选择回测数据</h2>
            <p>{source?.message || "正在检查本地数据源"}</p>
          </div>
          <div className="data-actions">
            <button className="ghost" onClick={onSync} disabled={!source?.akshare_available || syncing || syncingAll}>{syncing ? "同步中…" : "同步所选"}</button>
            <button className="ghost" onClick={syncingAll ? onCancelSyncAll : onSyncAll} disabled={syncing || (!syncingAll && !source?.akshare_available)}>{syncingAll ? "停止自动补齐" : hasIncompleteAllMarketDataset ? "自动补齐全A" : "同步沪深全A"}</button>
            <label className="csv-upload">
              <input type="file" accept=".csv,text/csv" onChange={onImport} disabled={importing} />
              {importing ? "正在校验…" : "导入 CSV"}
            </label>
            <label className="csv-upload">
              <input type="file" accept=".csv,text/csv" onChange={onImportIndustryHistory} disabled={importing} />
              行业历史
            </label>
          </div>
          <button className="icon-button" onClick={close} aria-label="关闭"><X size={20} /></button>
        </div>
        <section className="data-sync-overview">
          <div className="data-sync-title">
            <b>全A补齐任务：{allMarketSyncTask?.status && allMarketSyncTask.status !== "idle" ? allMarketSyncTask.status : "local"}</b>
            <strong>A股总数据 {marketTotalCount} 只</strong>
            <span>第 {allMarketSyncTask?.batch_count || 0} 批 · 覆盖 {taskCovered}/{taskExpected || "?"}</span>
          </div>
          <progress value={taskCovered} max={taskExpected || 1} />
          <small>
            本地日线仓库会优先复用已有行情；补齐只拉取当前时间范围和股票池缺失的部分。
            {taskExpected ? ` 当前覆盖率 ${taskProgress}%` : ""}
          </small>
          {failedSymbols.length ? (
            <div className="sync-failed-row">
              <span>失败 {failedSymbols.length} 只：{failedSymbols.slice(0, 8).join("、")}{failedSymbols.length > 8 ? "…" : ""}</span>
              {!syncingAll ? <button className="ghost" onClick={onRetryFailedAll}>重试失败项</button> : null}
            </div>
          ) : null}
          {skippedSymbols.length ? (
            <div className="sync-failed-row muted">
              <span>已跳过 {skippedSymbols.length} 只长期失败标的：{skippedSymbols.slice(0, 8).join("、")}{skippedSymbols.length > 8 ? "…" : ""}</span>
            </div>
          ) : null}
        </section>
        <section className="data-pick-dashboard">
          <div className="data-market-grid">
            {stockPools.map((pool) => {
              const coverage = coverageByPool[pool.id];
              const selectedInPool = settings.symbols.filter((symbol) => pool.symbols.includes(symbol)).length;
              return (
                <button
                  key={pool.id}
                  data-testid={`stock-pool-${pool.id}`}
                  className={`market-tile ${poolStates[pool.id] === "selected" ? "selected" : poolStates[pool.id] === "partial" ? "partial" : ""}`}
                  onClick={() => togglePool(pool)}
                  disabled={!pool.symbols.length}
                >
                  <b>{pool.title}</b>
                  <span>{selectedInPool}/{pool.symbols.length} 只 · {pool.helper}</span>
                  <small>{coverage ? `本地覆盖 ${coverage.covered}/${coverage.expected}，缺 ${coverage.missing}` : "正在读取本地覆盖"}</small>
                </button>
              );
            })}
          </div>
          <div className="data-date-card">
            <b>时间维度</b>
            <label>
              <span>起始时间</span>
              <input type="date" value={settings.start_date} onChange={(event) => updateDate("start_date", event.target.value)} />
            </label>
            <label>
              <span>结束时间</span>
              <input type="date" value={settings.end_date} onChange={(event) => updateDate("end_date", event.target.value)} />
            </label>
            <small>
              {selectedCoverage
                ? `当前选择本地覆盖 ${selectedCoverage.covered}/${selectedCoverage.expected}，缺 ${selectedCoverage.missing}`
                : "选择板块后会按这个时间段检查本地仓库"}
            </small>
            <div className="data-pick-actions">
              <button className="ghost" onClick={selectFiltered} disabled={!filteredSymbols.length}>加入搜索结果</button>
              <button className="danger-ghost" onClick={clearSelection} disabled={!settings.symbols.length}>清空选择</button>
            </div>
          </div>
        </section>
        {!settings.dataset_id ? (
          <>
            <div className="security-search">
              <input
                type="search"
                placeholder="搜索代码、名称、板块或行业"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
              <small>
                显示 {visibleSecurities.length} / {filteredSecurities.length} 只
                {hiddenCount ? `，还有 ${hiddenCount} 只可继续搜索` : ""}
              </small>
            </div>
            <div className="security-list">
              {visibleSecurities.map((item) => (
              <button key={item.symbol} className={settings.symbols.includes(item.symbol) ? "selected" : ""} onClick={() => toggle(item.symbol)}>
                <span><b>{item.name}</b><small>{item.symbol} · {item.board || item.exchange}</small></span>
                {settings.symbols.includes(item.symbol) ? <Check size={18} weight="bold" /> : null}
              </button>
            ))}
            </div>
          </>
        ) : (
          <div className="quality-panel">
            <b>数据质量检查</b>
            {(datasetQuality?.quality_checks || []).length ? (
              datasetQuality.quality_checks.map((check) => (
                <span key={check.check_name} className={check.severity}>{check.check_name} · {check.severity}<small>{check.message}</small></span>
              ))
            ) : (
              <span>暂无质量检查记录</span>
            )}
          </div>
        )}
        <div className="modal-actions">
          <span className="selection-count">{settings.dataset_id ? "已选择本地数据快照" : `已选择 ${settings.symbols.length} 只股票`}</span>
          <button className="primary" disabled={!settings.symbols.length} onClick={close}>确认数据源</button>
        </div>
      </div>
    </div>
  );
}
