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
  Trash,
  X,
} from "@phosphor-icons/react";

import { controlPullbackTemplate } from "../appConfig";
import { RateInput, SettingRow } from "./common";

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
        <SettingRow label="数据来源"><span className="static-value">{settings.dataset_id ? "固定数据快照" : "演示数据"}</span></SettingRow>
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
  ["body_amplitude", "实体振幅"],
  ["price_ma_deviation", "价格偏离均线"],
  ["volume_return_spike", "放量大阳"],
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
  body_amplitude: { left: 10, right: 60, threshold: 0.1 },
  price_ma_deviation: { left: 10, right: 60, threshold: 1.02 },
  volume_return_spike: { left: 10, right: 60, threshold: 3, lower: 0.07 },
  life_line_watch: { left: 20, right: 10, threshold: 3, lower: -0.01, upper: 1.8 },
};

export function updateRuleConditionValue(condition, key, value) {
  if (key === "indicator") {
    return { ...condition, ...indicatorDefaults[value], indicator: value };
  }
  return { ...condition, [key]: key === "operator" ? value : Number(value) };
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
    body_amplitude: "最大实体阈值",
    price_ma_deviation: "均线倍率",
    volume_return_spike: "放量倍率",
    life_line_watch: "观察天数",
  }[indicator];
  const leftLabel = {
    volume_vs_ma: "均量周期",
    volume_max_vs_ma: "统计窗口",
    return_between: "收益窗口",
    kline_up_ratio: "统计窗口",
    body_amplitude: "统计窗口",
    price_ma_deviation: "均线周期",
    volume_return_spike: "均量周期",
    life_line_watch: "生命线周期",
    bollinger: "周期",
    rsi: "RSI周期",
  }[indicator] || "短周期";
  const rightLabel = indicator === "life_line_watch" ? "均量周期" : "长周期";
  const showRight = !["price_vs_ma", "rsi", "bollinger", "volume_vs_ma", "return_between", "kline_up_ratio", "body_amplitude", "price_ma_deviation", "volume_return_spike"].includes(indicator);
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

export function StrategyModal({ settings, setSettings, onSave, saving, versionInfo, close }) {
  const strategy = settings.strategy;
  const updateCondition = (kind, targetIndex, key, value) =>
    setSettings((current) => ({
      ...current,
      strategy: {
        ...current.strategy,
        [kind]: current.strategy[kind].map((condition, index) =>
          index === targetIndex
            ? updateRuleConditionValue(condition, key, value)
            : condition
        ),
      },
    }));
  const addCondition = (kind) =>
    setSettings((current) => ({
      ...current,
      strategy: {
        ...current.strategy,
        [kind]: [
          ...current.strategy[kind],
          { indicator: "price_vs_ma", operator: kind === "buy_conditions" ? "above" : "below", left: 20, right: 60, threshold: 50 },
        ],
      },
    }));
  const removeCondition = (kind, removeIndex) =>
    setSettings((current) => ({
      ...current,
      strategy: {
        ...current.strategy,
        [kind]: current.strategy[kind].filter((_, index) => index !== removeIndex),
      },
    }));
  const applyControlPullbackTemplate = () =>
    setSettings((current) => ({
      ...current,
      max_symbol_position: 1 / controlPullbackTemplate.max_hold_num,
      max_position: 1,
      stop_loss_pct: 0.08,
      take_profit_pct: 0,
      exclude_st: true,
      strategy: JSON.parse(JSON.stringify(controlPullbackTemplate)),
    }));
  const updateStrategyField = (field, value) =>
    setSettings((current) => ({
      ...current,
      strategy: { ...current.strategy, [field]: value },
    }));
  return (
    <div className="modal-backdrop" onClick={(event) => event.target === event.currentTarget && close()}>
      <div className="strategy-modal">
        <div className="modal-head">
          <div>
            <span className="eyebrow">可视化策略</span>
            <h2>配置「{strategy.name}」</h2>
            <p>使用自然语言式条件组合，无需编写代码。{versionInfo ? ` 当前 ${versionInfo}` : " 尚未保存版本"}</p>
          </div>
          <button className="icon-button" onClick={close}><X size={20} /></button>
        </div>
        <div className="strategy-template-bar">
          <button className="ghost" onClick={applyControlPullbackTemplate}>套用「主力控盘回踩策略」模板</button>
          <label>最大持股<input type="number" min="1" max="200" value={strategy.max_hold_num || ""} onChange={(event) => updateStrategyField("max_hold_num", event.target.value ? Number(event.target.value) : null)} /></label>
          <label>排序
            <select value={strategy.candidate_sort || "none"} onChange={(event) => updateStrategyField("candidate_sort", event.target.value)}>
              <option value="none">不排序</option>
              <option value="return_asc">近N日涨幅升序</option>
              <option value="return_desc">近N日涨幅降序</option>
            </select>
          </label>
          <label>排序窗口<input type="number" min="2" max="500" value={strategy.sort_window || 20} onChange={(event) => updateStrategyField("sort_window", Number(event.target.value))} /></label>
        </div>
        <div className="rule-flow">
          <div className="rule-node source"><Database size={21} /><b>股票池</b><span>沪深 A 股 · {settings.symbols.length} 只</span></div>
          <div className="connector" />
          <div className="rule-group">
            <div className="rule-group-head"><b>买入条件（{strategy.buy_logic === "all" ? "全部满足" : "任一满足"}）</b><button onClick={() => addCondition("buy_conditions")}>+ 条件</button></div>
            <div className="rule-node-grid">
              {strategy.buy_conditions.map((condition, index) => (
                <RuleNode
                  key={`buy-${index}`}
                  title={`买入 ${index + 1}`}
                  tone="green"
                  condition={condition}
                  onChange={(key, value) => updateCondition("buy_conditions", index, key, value)}
                  onRemove={strategy.buy_conditions.length > 1 ? () => removeCondition("buy_conditions", index) : null}
                />
              ))}
            </div>
          </div>
          <div className="connector" />
          <div className="rule-group">
            <div className="rule-group-head"><b>卖出条件（{strategy.sell_logic === "all" ? "全部满足" : "任一满足"}）</b><button onClick={() => addCondition("sell_conditions")}>+ 条件</button></div>
            <div className="rule-node-grid">
              {strategy.sell_conditions.map((condition, index) => (
                <RuleNode
                  key={`sell-${index}`}
                  title={`卖出 ${index + 1}`}
                  tone="red"
                  condition={condition}
                  onChange={(key, value) => updateCondition("sell_conditions", index, key, value)}
                  onRemove={strategy.sell_conditions.length > 1 ? () => removeCondition("sell_conditions", index) : null}
                />
              ))}
            </div>
          </div>
          <div className="connector" />
          <div className="rule-node risk"><SlidersHorizontal size={21} /><b>仓位管理</b><span>最大仓位 {settings.max_position * 100}% · 最多 {strategy.max_hold_num || "不限"} 只</span></div>
        </div>
        <div className="validation-row">
          <span><Check size={17} weight="bold" />规则检查通过</span>
          <span>信号在收盘后产生</span>
          <span>下一交易日开盘成交</span>
          <span>T+1 可卖</span>
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
  syncing,
  syncingAll,
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
            <button className="ghost" onClick={onSyncAll} disabled={!source?.akshare_available || syncing || syncingAll}>{syncingAll ? "全A同步中…" : "同步沪深全A"}</button>
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
        <div className="dataset-picker">
          <button className={!settings.dataset_id ? "selected" : ""} onClick={() => onSelectDataset(null)}>
            <b>可复现演示数据</b>
            <span>离线生成 · 5 只示例股票</span>
          </button>
          {datasets.map((dataset) => (
            <div key={dataset.id} className={`dataset-card ${settings.dataset_id === dataset.id ? "selected" : ""}`}>
              <button className="dataset-select" onClick={() => onSelectDataset(dataset)}>
                <b>{dataset.name}</b>
                <span>{dataset.source === "akshare" || dataset.source === "akshare_all" ? "AkShare" : "CSV"} · {dataset.symbol_count} 标的 · {dataset.row_count} 行</span>
                <small>{dataset.start_date} — {dataset.end_date}</small>
              </button>
              <button className="dataset-delete" onClick={() => onDeleteDataset(dataset)} aria-label={`删除 ${dataset.name}`} title="删除快照">
                <Trash size={14} />
              </button>
            </div>
          ))}
        </div>
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
          <span className="selection-count">{settings.dataset_id ? "已选择固定数据快照" : `已选择 ${settings.symbols.length} 只股票`}</span>
          <button className="primary" disabled={!settings.symbols.length} onClick={close}>确认数据源</button>
        </div>
      </div>
    </div>
  );
}
