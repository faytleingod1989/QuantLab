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

import { formatMoney, formatPercent } from "../formatters";
import { ChartTooltip } from "./common";

function EquityChart({ chartData, result, settings }) {
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

function DrawdownChart({ chartData, metrics }) {
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

function MonthlyHeatmap({ years }) {
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

function TradesTable({ result }) {
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

export default function DashboardCharts({ chartData, result, settings, metrics, years }) {
  return (
    <>
      <EquityChart chartData={chartData} result={result} settings={settings} />
      <DrawdownChart chartData={chartData} metrics={metrics} />
      <section className="lower-grid">
        <MonthlyHeatmap years={years} />
        <TradesTable result={result} />
      </section>
    </>
  );
}
