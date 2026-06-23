import { ArrowsClockwise, DownloadSimple, GearSix, Info, X } from "@phosphor-icons/react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { navItems, workflowSteps } from "../appConfig";
import { formatMoney, formatPercent } from "../formatters";
import { ChartTooltip, Metric } from "./common";

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

export function Topbar({ settings, setSettings }) {
  return (
    <header className="topbar">
      <div><h1>数据驾驶舱</h1><p>结果总览与分析</p></div>
      <div className="top-actions">
        <label>
          <input type="date" value={settings.start_date} onChange={(event) => setSettings((current) => ({ ...current, start_date: event.target.value }))} />
          <span>~</span>
          <input type="date" value={settings.end_date} onChange={(event) => setSettings((current) => ({ ...current, end_date: event.target.value }))} />
        </label>
        <button className="ghost"><DownloadSimple size={18} />导出报告</button>
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

export function EquityChart({ chartData, result, settings }) {
  return (
    <section className="chart-panel equity-panel">
      <div className="panel-head">
        <div><b>累计净值走势</b><div className="legend"><span className="strategy-line">策略</span><span className="benchmark-line">{result?.benchmark?.label || "沪深300"}</span></div></div>
        <span className="period-badge">{settings.start_date} — {settings.end_date}</span>
      </div>
      <ResponsiveContainer width="100%" height={250}>
        <LineChart data={chartData} margin={{ top: 12, right: 24, left: 4, bottom: 0 }}>
          <CartesianGrid stroke="#243139" vertical={false} />
          <XAxis dataKey="date" tick={{ fill: "#7f8b91", fontSize: 11 }} tickLine={false} axisLine={false} minTickGap={54} />
          <YAxis tickFormatter={(value) => `${Math.round(value * 100)}%`} tick={{ fill: "#7f8b91", fontSize: 11 }} tickLine={false} axisLine={false} width={48} />
          <Tooltip content={<ChartTooltip />} />
          <Line type="monotone" dataKey="equity" name="策略" stroke="#35c4bd" strokeWidth={2.2} dot={false} isAnimationActive={false} />
          <Line type="monotone" dataKey="benchmark" name={result?.benchmark?.label || "沪深300"} stroke="#899399" strokeWidth={1.4} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </section>
  );
}

export function DrawdownChart({ chartData, metrics }) {
  return (
    <section className="chart-panel drawdown-panel">
      <div className="panel-head"><b>最大回撤（回撤区间）</b><span className="negative">{formatPercent(metrics.max_drawdown)}</span></div>
      <ResponsiveContainer width="100%" height={105}>
        <AreaChart data={chartData} margin={{ top: 6, right: 24, left: 4, bottom: 0 }}>
          <CartesianGrid stroke="#243139" vertical={false} />
          <XAxis dataKey="date" hide />
          <YAxis tickFormatter={(value) => `${Math.round(value * 100)}%`} tick={{ fill: "#7f8b91", fontSize: 10 }} tickLine={false} axisLine={false} width={48} />
          <Tooltip content={<ChartTooltip />} />
          <Area type="monotone" dataKey="drawdown" name="回撤" stroke="#ef525c" fill="#7d2630" fillOpacity={0.58} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </section>
  );
}

export function MonthlyHeatmap({ years }) {
  return (
    <div className="chart-panel heatmap-panel">
      <div className="panel-head"><b>月度收益热力图（%）</b></div>
      <div className="heatmap">
        <div className="heat-row heat-head"><span />{Array.from({ length: 12 }, (_, index) => <span key={index}>{index + 1}月</span>)}</div>
        {years.slice(0, 7).map(([year, values]) => (
          <div className="heat-row" key={year}>
            <b>{year}</b>
            {Array.from({ length: 12 }, (_, index) => {
              const value = values[index + 1];
              return <span key={index} className={value == null ? "empty" : value >= 0 ? "gain" : "loss"}>{value == null ? "—" : (value * 100).toFixed(1)}</span>;
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

export function TradesTable({ result }) {
  return (
    <div className="chart-panel trades-panel">
      <div className="panel-head"><b>交易记录（最近 10 笔）</b><button className="text-button">查看全部 ›</button></div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>交易日期</th><th>代码</th><th>名称</th><th>方向</th><th>成交价</th><th>数量</th><th>收益</th></tr></thead>
          <tbody>
            {(result?.trades || []).slice(0, 10).map((trade, index) => (
              <tr key={`${trade.date}-${trade.symbol}-${index}`}>
                <td>{trade.date}</td>
                <td>{trade.symbol}</td>
                <td>{trade.name}</td>
                <td className={trade.side === "买入" ? "negative" : "positive"}>{trade.side}</td>
                <td>{trade.price}</td>
                <td>{formatMoney(trade.quantity)}</td>
                <td className={(trade.pnl || 0) >= 0 ? "positive" : "negative"}>{trade.pnl == null ? "—" : formatMoney(trade.pnl)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
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
