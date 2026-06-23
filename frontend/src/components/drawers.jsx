import {
  Check,
  Database,
  Play,
  Pulse,
  SlidersHorizontal,
  X,
} from "@phosphor-icons/react";

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
        <SettingRow label="复权方式"><span className="static-value">不复权成交</span></SettingRow>
        <small className="hint">真实行情和 CSV 会先固化为带指纹的数据集，再进入回测。</small>
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

function RuleNode({ title, tone, condition, onChange }) {
  return (
    <div className={`rule-node ${tone}`}>
      <b>{title}</b>
      <span>短期均线</span>
      <input type="number" value={condition.left} onChange={(event) => onChange("left", event.target.value)} />
      <span>{tone === "green" ? "上穿" : "下穿"}长期均线</span>
      <input type="number" value={condition.right} onChange={(event) => onChange("right", event.target.value)} />
    </div>
  );
}

export function StrategyModal({ settings, setSettings, onSave, saving, versionInfo, close }) {
  const strategy = settings.strategy;
  const updateCondition = (kind, key, value) =>
    setSettings((current) => ({
      ...current,
      strategy: {
        ...current.strategy,
        [kind]: current.strategy[kind].map((condition, index) =>
          index === 0 ? { ...condition, [key]: Number(value) } : condition
        ),
      },
    }));
  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && close()}>
      <div className="strategy-modal">
        <div className="modal-head">
          <div>
            <span className="eyebrow">可视化策略</span>
            <h2>配置「{strategy.name}」</h2>
            <p>使用自然语言式条件组合，无需编写代码。{versionInfo ? ` 当前 ${versionInfo}` : " 尚未保存版本"}</p>
          </div>
          <button className="icon-button" onClick={close}><X size={20} /></button>
        </div>
        <div className="rule-flow">
          <div className="rule-node source"><Database size={21} /><b>股票池</b><span>沪深 A 股 · {settings.symbols.length} 只</span></div>
          <div className="connector" />
          <RuleNode title="买入条件" tone="green" condition={strategy.buy_conditions[0]} onChange={(key, value) => updateCondition("buy_conditions", key, value)} />
          <div className="connector" />
          <RuleNode title="卖出条件" tone="red" condition={strategy.sell_conditions[0]} onChange={(key, value) => updateCondition("sell_conditions", key, value)} />
          <div className="connector" />
          <div className="rule-node risk"><SlidersHorizontal size={21} /><b>仓位管理</b><span>最大仓位 {settings.max_position * 100}%</span></div>
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
  onImport,
  importing,
  onSync,
  syncing,
  onSelectDataset,
  close,
}) {
  const toggle = (symbol) =>
    setSettings((current) => ({
      ...current,
      dataset_id: null,
      symbols: current.symbols.includes(symbol)
        ? current.symbols.filter((item) => item !== symbol)
        : [...current.symbols, symbol],
    }));
  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && close()}>
      <div className="data-modal">
        <div className="modal-head">
          <div>
            <span className="eyebrow">数据中心</span>
            <h2>选择回测数据</h2>
            <p>{source?.message || "正在检查本地数据源"}</p>
          </div>
          <div className="data-actions">
            <button className="ghost" onClick={onSync} disabled={!source?.akshare_available || syncing}>{syncing ? "同步中…" : "同步 AkShare"}</button>
            <label className="csv-upload">
              <input type="file" accept=".csv,text/csv" onChange={onImport} disabled={importing} />
              {importing ? "正在校验…" : "导入 CSV"}
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
            <button key={dataset.id} className={settings.dataset_id === dataset.id ? "selected" : ""} onClick={() => onSelectDataset(dataset)}>
              <b>{dataset.name}</b>
              <span>{dataset.source === "akshare" ? "AkShare" : "CSV"} · {dataset.symbol_count} 标的 · {dataset.row_count} 行</span>
              <small>{dataset.start_date} — {dataset.end_date}</small>
            </button>
          ))}
        </div>
        {!settings.dataset_id ? (
          <div className="security-list">
            {securities.map((item) => (
              <button key={item.symbol} className={settings.symbols.includes(item.symbol) ? "selected" : ""} onClick={() => toggle(item.symbol)}>
                <span><b>{item.name}</b><small>{item.symbol}</small></span>
                {settings.symbols.includes(item.symbol) ? <Check size={18} weight="bold" /> : null}
              </button>
            ))}
          </div>
        ) : null}
        <div className="modal-actions">
          <span className="selection-count">{settings.dataset_id ? "已选择固定数据快照" : `已选择 ${settings.symbols.length} 只股票`}</span>
          <button className="primary" disabled={!settings.symbols.length} onClick={close}>确认数据源</button>
        </div>
      </div>
    </div>
  );
}
