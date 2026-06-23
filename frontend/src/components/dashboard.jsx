import { ArrowsClockwise, DownloadSimple, GearSix, Info, X } from "@phosphor-icons/react";

import { navItems, workflowSteps } from "../appConfig";
import { formatPercent } from "../formatters";
import { Metric } from "./common";

export function Sidebar({ openNav, openSettings }) {
  return (
    <aside className="sidebar">
      <div className="brand"><span>QuantLab</span><small>本地量化研究平台</small></div>
      <nav>
        {navItems.map(([label, Icon]) => (
          <button key={label} className={label === "回测中心" ? "active" : ""} onClick={() => openNav(label)}>
            <Icon size={20} /><span>{label}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <span><i />本地服务运行中</span>
        <button onClick={openSettings}><GearSix size={20} /><span>系统设置</span></button>
      </div>
    </aside>
  );
}

export function Topbar({ settings, setSettings, onExportReport, canExportReport }) {
  return (
    <header className="topbar">
      <div><h1>数据驾驶舱</h1><p>结果总览与分析</p></div>
      <div className="top-actions">
        <label>
          <input type="date" value={settings.start_date} onChange={(event) => setSettings((current) => ({ ...current, start_date: event.target.value }))} />
          <span>~</span>
          <input type="date" value={settings.end_date} onChange={(event) => setSettings((current) => ({ ...current, end_date: event.target.value }))} />
        </label>
        <button className="ghost" onClick={onExportReport} disabled={!canExportReport}>
          <DownloadSimple size={18} />导出报告
        </button>
      </div>
    </header>
  );
}

export function Workflow({ settings, openStep }) {
  return (
    <div className="workflow">
      {workflowSteps.map((step, index) => (
        <button key={step} className={index === 4 ? "current" : "done"} onClick={() => openStep(index)}>
          <span>{index + 1}</span>
          <div>
            <b>{step}</b>
            <small>{index === 0 ? `${settings.symbols.length} 只股票 · 日线` : index === 1 ? settings.strategy.name : index === 4 ? "当前步骤" : "已完成"}</small>
          </div>
          {index < 4 ? <i>›</i> : null}
        </button>
      ))}
    </div>
  );
}

export function ReportTitle({ result, settings, running, onRun }) {
  return (
    <section className="report-title">
      <div><span>回测概览</span><b>{result?.strategy || settings.strategy.name}</b></div>
      <button className="text-button" onClick={onRun}>
        <ArrowsClockwise size={17} className={running ? "spin" : ""} />刷新结果
      </button>
    </section>
  );
}

export function MetricsStrip({ metrics }) {
  return (
    <section className="metrics-strip">
      <Metric label="累计收益" value={formatPercent(metrics.total_return)} tone={metrics.total_return >= 0 ? "positive" : "negative"} />
      <Metric label="年化收益" value={formatPercent(metrics.annual_return)} tone={metrics.annual_return >= 0 ? "positive" : "negative"} />
      <Metric label="最大回撤" value={formatPercent(metrics.max_drawdown)} tone="negative" />
      <Metric label="夏普比率" value={Number(metrics.sharpe || 0).toFixed(2)} />
      <Metric label="胜率" value={formatPercent(metrics.win_rate)} />
      <Metric label="交易次数" value={metrics.trade_count || 0} />
    </section>
  );
}

export function ChartLoading() {
  return (
    <div className="chart-loading" aria-live="polite">
      <div className="skeleton skeleton-large" />
      <div className="skeleton skeleton-small" />
      <span>正在加载图表模块…</span>
    </div>
  );
}

export function LoadingBanner({ message }) {
  return <div className="loading-banner"><span className="spinner-dot" />{message}</div>;
}

export function DashboardFooter({ settings, source }) {
  return (
    <footer>
      <span><i />数据状态正常</span>
      <span>数据源：{settings.dataset_id ? "固定快照" : source?.source || "连接中"}</span>
      <span>引擎版本 v0.4.0</span>
      <span><Info size={16} />回测不代表未来收益</span>
    </footer>
  );
}

export function Toast({ notice, onClose }) {
  if (!notice) return null;
  return <button className="toast" onClick={onClose}>{notice}<X size={15} /></button>;
}
