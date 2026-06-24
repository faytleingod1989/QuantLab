import { useEffect, useMemo, useState } from "react";
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

import { API } from "../appConfig";
import { formatMoney, formatPercent } from "../formatters";
import { ChartTooltip } from "./common";

const TRADE_PAGE_SIZE = 10;

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

function TradesTable({ result, taskId }) {
  const [side, setSide] = useState("all");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState(() => ({
    total: result?.trades?.length || 0,
    items: (result?.trades || []).slice(0, TRADE_PAGE_SIZE),
  }));
  const [loading, setLoading] = useState(false);

  useEffect(() => setOffset(0), [taskId, side]);

  useEffect(() => {
    const fallback = result?.trades || [];
    if (!taskId) {
      const filtered = side === "all" ? fallback : fallback.filter((trade) => trade.side === side);
      setPage({
        total: filtered.length,
        items: filtered.slice(offset, offset + TRADE_PAGE_SIZE),
      });
      return;
    }

    const controller = new AbortController();
    setLoading(true);
    const params = new URLSearchParams({
      limit: String(TRADE_PAGE_SIZE),
      offset: String(offset),
    });
    if (side !== "all") params.set("side", side);
    fetch(`${API}/backtests/${taskId}/trades?${params.toString()}`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("无法读取交易分页");
        return response.json();
      })
      .then(setPage)
      .catch((error) => {
        if (error.name !== "AbortError") {
          const filtered = side === "all" ? fallback : fallback.filter((trade) => trade.side === side);
          setPage({
            total: filtered.length,
            items: filtered.slice(offset, offset + TRADE_PAGE_SIZE),
          });
        }
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [offset, result, side, taskId]);

  const currentPage = Math.floor(offset / TRADE_PAGE_SIZE) + 1;
  const totalPages = Math.max(1, Math.ceil((page.total || 0) / TRADE_PAGE_SIZE));

  return (
    <div className="chart-panel trades-panel">
      <div className="panel-head">
        <b>交易记录</b>
        <div className="trade-controls">
          <select value={side} onChange={(event) => setSide(event.target.value)}>
            <option value="all">全部方向</option>
            <option value="买入">仅买入</option>
            <option value="卖出">仅卖出</option>
          </select>
          <span>{loading ? "加载中…" : `${page.total || 0} 笔`}</span>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>交易日期</th><th>代码</th><th>名称</th><th>方向</th><th>原因</th><th>成交价</th><th>数量</th><th>收益</th></tr></thead>
          <tbody>
            {(page.items || []).map((trade, index) => (
              <tr key={`${trade.date}-${trade.symbol}-${index}`}>
                <td>{trade.date}</td>
                <td>{trade.symbol}</td>
                <td>{trade.name}</td>
                <td className={trade.side === "买入" ? "negative" : "positive"}>{trade.side}</td>
                <td>{trade.reason || "信号"}</td>
                <td>{trade.price}</td>
                <td>{formatMoney(trade.quantity)}</td>
                <td className={(trade.pnl || 0) >= 0 ? "positive" : "negative"}>{trade.pnl == null ? "—" : formatMoney(trade.pnl)}</td>
              </tr>
            ))}
            {!(page.items || []).length ? (
              <tr><td colSpan="8" className="empty-cell">暂无交易记录</td></tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <div className="pager">
        <button className="text-button" disabled={offset <= 0} onClick={() => setOffset(Math.max(0, offset - TRADE_PAGE_SIZE))}>上一页</button>
        <span>{currentPage} / {totalPages}</span>
        <button className="text-button" disabled={offset + TRADE_PAGE_SIZE >= (page.total || 0)} onClick={() => setOffset(offset + TRADE_PAGE_SIZE)}>下一页</button>
      </div>
    </div>
  );
}

function OrderEventsSummary({ events }) {
  const stats = useMemo(() => {
    const counts = {};
    for (const event of events || []) {
      counts[event.reason || "其他"] = (counts[event.reason || "其他"] || 0) + 1;
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [events]);

  return (
    <div className="event-summary">
      <b>订单拒绝统计</b>
      {stats.length ? stats.slice(0, 4).map(([reason, count]) => (
        <span key={reason}>{reason} <em>{count}</em></span>
      )) : <span>暂无拒单</span>}
    </div>
  );
}

function ComparisonPanel({ comparisons }) {
  return (
    <section className="chart-panel compare-panel">
      <div className="panel-head"><b>最近回测对比</b><span>{comparisons?.length || 0} 次</span></div>
      <div className="table-wrap compare-wrap">
        <table>
          <thead><tr><th>策略</th><th>区间</th><th>累计收益</th><th>年化收益</th><th>最大回撤</th><th>夏普</th><th>交易</th></tr></thead>
          <tbody>
            {(comparisons || []).map((item) => (
              <tr key={item.id}>
                <td>{item.strategy}</td>
                <td>{item.start_date} ~ {item.end_date}</td>
                <td className={item.total_return >= 0 ? "positive" : "negative"}>
                  <div className="compare-bar"><i style={{ width: `${Math.min(Math.abs(item.total_return) * 100, 100)}%` }} />{formatPercent(item.total_return)}</div>
                </td>
                <td className={item.annual_return >= 0 ? "positive" : "negative"}>{formatPercent(item.annual_return)}</td>
                <td className="negative">{formatPercent(item.max_drawdown)}</td>
                <td>{Number(item.sharpe || 0).toFixed(2)}</td>
                <td>{item.trade_count}</td>
              </tr>
            ))}
            {!(comparisons || []).length ? <tr><td colSpan="7" className="empty-cell">暂无历史回测可对比</td></tr> : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function DashboardCharts({ chartData, result, settings, metrics, years, taskId, comparisons }) {
  return (
    <>
      <EquityChart chartData={chartData} result={result} settings={settings} />
      <DrawdownChart chartData={chartData} metrics={metrics} />
      <section className="lower-grid">
        <MonthlyHeatmap years={years} />
        <div className="trade-stack">
          <OrderEventsSummary events={result?.order_events} />
          <TradesTable result={result} taskId={taskId} />
        </div>
      </section>
      <ComparisonPanel comparisons={comparisons} />
    </>
  );
}
