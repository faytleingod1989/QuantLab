import { lazy, Suspense, useEffect, useMemo, useState } from "react";

import { API, initialSettings, navItems } from "./appConfig";
import {
  ChartLoading,
  DashboardFooter,
  LoadingBanner,
  MetricsStrip,
  ReportTitle,
  Sidebar,
  Toast,
  Topbar,
  Workflow,
} from "./components/dashboard";
import { DataDrawer, SettingsDrawer, StrategyModal } from "./components/drawers";

const DashboardCharts = lazy(() => import("./components/charts.jsx"));

const errorMessage = (error, fallback = "操作失败") =>
  error instanceof Error ? error.message : String(error || fallback);

const logIgnoredError = (scope, error) => {
  if (!(error instanceof DOMException && error.name === "AbortError")) {
    console.error(`[QuantLab] ${scope}`, error);
  }
};

const VIEW_META = {
  data: ["数据中心", "行情快照、全 A 同步、数据质量与股票池管理"],
  strategy: ["策略研究", "策略版本、可视化条件与研究备注"],
  backtest: ["回测中心", "参数设置、任务执行与回测进度"],
  factors: ["因子分析", "因子库与选股信号规划"],
  portfolio: ["组合管理", "组合约束、持仓与调仓计划"],
  results: ["结果分析", "收益曲线、交易记录与多次回测对比"],
  reports: ["报告管理", "HTML、PDF 与 Markdown 报告导出"],
  settings: ["系统设置", "本地服务、数据源与运行参数"],
};

const viewForNav = (label) => {
  if (label.includes("数据")) return "data";
  if (label.includes("策略")) return "strategy";
  if (label.includes("回测")) return "backtest";
  if (label.includes("因子")) return "factors";
  if (label.includes("组合")) return "portfolio";
  if (label.includes("结果")) return "results";
  if (label.includes("报告")) return "reports";
  return "backtest";
};

const navLabelForView = (view) => {
  if (view === "settings") return "系统设置";
  return navItems.find(([label]) => viewForNav(label) === view)?.[0] || "回测中心";
};

function PageCard({ title, value, note, action }) {
  return (
    <article className="page-card">
      <span>{title}</span>
      <b>{value}</b>
      {note ? <small>{note}</small> : null}
      {action}
    </article>
  );
}

const compactNumber = (value) => {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return "--";
  if (Math.abs(number) >= 100000000) return `${(number / 100000000).toFixed(2)}亿`;
  if (Math.abs(number) >= 10000) return `${(number / 10000).toFixed(1)}万`;
  return `${Math.round(number)}`;
};

const toChartNumber = (value, fallback = 0) => {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
};

const normalizedStockName = (stock) => {
  const symbol = String(stock?.symbol || "");
  const name = String(stock?.name || "").trim();
  return name && name !== symbol && !/^\d{6}(\.(SH|SZ|BJ))?$/i.test(name) ? name : "";
};

const stockDisplayName = (stock, fallbackSymbol = "") => {
  const symbol = String(stock?.symbol || fallbackSymbol || "");
  const name = normalizedStockName(stock);
  return name ? `${symbol} · ${name}` : symbol;
};

const priceChangeMeta = (bar, previousBar) => {
  if (!bar) return { change: 0, percent: 0, text: "--", className: "flat" };
  const close = toChartNumber(bar.close);
  const previousClose = toChartNumber(bar.prev_close, toChartNumber(previousBar?.close, toChartNumber(bar.open)));
  const change = close - previousClose;
  const percent = previousClose ? (change / previousClose) * 100 : 0;
  const sign = change > 0 ? "+" : "";
  return {
    change,
    percent,
    text: `${sign}${change.toFixed(2)} / ${sign}${percent.toFixed(2)}%`,
    className: change > 0 ? "up" : change < 0 ? "down" : "flat",
  };
};

const clampNumber = (value, min, max) => Math.min(max, Math.max(min, value));

const chartIndexFromPointer = (event, width, padding, count) => {
  if (!count) return null;
  const rect = event.currentTarget.getBoundingClientRect();
  const localX = (event.clientX - rect.left) * (width / Math.max(rect.width, 1));
  const plotWidth = width - padding.left - padding.right;
  const step = plotWidth / Math.max(count, 1);
  return clampNumber(Math.round((localX - padding.left - step / 2) / step), 0, count - 1);
};

function ChartEmptyState({ text }) {
  return <div className="warehouse-chart-empty">{text}</div>;
}

function KLineSvg({ bars, hoveredIndex, onHoverIndex, onLeave, onWheel }) {
  const visibleBars = bars || [];
  if (!visibleBars.length) return <ChartEmptyState text="暂无本地日 K 数据，请先补齐该股票行情。" />;
  const width = 900;
  const height = 320;
  const padding = { top: 18, right: 54, bottom: 28, left: 18 };
  const plotWidth = width - padding.left - padding.right;
  const renderStride = Math.max(1, Math.ceil(visibleBars.length / 180));
  const displayBars = visibleBars
    .map((bar, index) => ({ bar, index }))
    .filter(({ index }) => index === visibleBars.length - 1 || index % renderStride === 0);
  const prices = visibleBars.flatMap((bar) => [
    toChartNumber(bar.high),
    toChartNumber(bar.low),
    toChartNumber(bar.open),
    toChartNumber(bar.close),
  ]).filter((item) => Number.isFinite(item) && item > 0);
  if (!prices.length) return <ChartEmptyState text="本地日线存在，但没有可绘制的有效价格。" />;
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const range = maxPrice - minPrice || Math.max(maxPrice * 0.02, 1);
  const plotHeight = height - padding.top - padding.bottom;
  const step = plotWidth / Math.max(visibleBars.length, 1);
  const candleWidth = Math.max(1.8, Math.min(10, step * renderStride * 0.52));
  const y = (price) => padding.top + ((maxPrice - price) / range) * plotHeight;
  const lastBar = visibleBars[visibleBars.length - 1];
  const hoveredBar = hoveredIndex == null ? null : visibleBars[hoveredIndex];
  const hoveredPreviousBar = hoveredIndex == null ? null : visibleBars[hoveredIndex - 1];
  const hoveredChange = priceChangeMeta(hoveredBar, hoveredPreviousBar);
  const hoveredX = hoveredBar ? padding.left + hoveredIndex * step + step / 2 : null;
  const hoveredClose = hoveredBar ? toChartNumber(hoveredBar.close) : null;
  const tooltipX = hoveredX == null ? padding.left : clampNumber(hoveredX + 12, padding.left + 6, width - padding.right - 180);
  return (
    <svg
      className="warehouse-kline-svg chart-interactive"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="日 K 线"
      onMouseMove={(event) => onHoverIndex?.(chartIndexFromPointer(event, width, padding, visibleBars.length))}
      onMouseLeave={onLeave}
      onWheel={onWheel}
    >
      <g className="chart-grid">
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => (
          <line key={ratio} x1={padding.left} x2={width - padding.right} y1={padding.top + ratio * plotHeight} y2={padding.top + ratio * plotHeight} />
        ))}
      </g>
      {displayBars.map(({ bar, index }) => {
        const open = toChartNumber(bar.open);
        const close = toChartNumber(bar.close);
        const high = toChartNumber(bar.high);
        const low = toChartNumber(bar.low);
        const x = padding.left + index * step + step / 2;
        const up = close >= open;
        const bodyTop = Math.min(y(open), y(close));
        const bodyHeight = Math.max(1.4, Math.abs(y(open) - y(close)));
        return (
          <g key={`${bar.date}-${index}`} className={up ? "candle-up" : "candle-down"}>
            <line x1={x} x2={x} y1={y(high)} y2={y(low)} />
            <rect className={index === hoveredIndex ? "hovered-candle" : ""} x={x - candleWidth / 2} y={bodyTop} width={candleWidth} height={bodyHeight} rx="1.2" />
          </g>
        );
      })}
      {hoveredBar ? (
        <g className="chart-hover-layer">
          <line className="chart-crosshair" x1={hoveredX} x2={hoveredX} y1={padding.top} y2={height - padding.bottom} />
          <circle cx={hoveredX} cy={y(hoveredClose)} r="4" />
          <g className="chart-tooltip-box" transform={`translate(${tooltipX} ${padding.top + 8})`}>
            <rect width="176" height="76" rx="5" />
            <text x="10" y="18">{hoveredBar.date}</text>
            <text x="10" y="36">开 {toChartNumber(hoveredBar.open).toFixed(2)}  高 {toChartNumber(hoveredBar.high).toFixed(2)}</text>
            <text x="10" y="54">低 {toChartNumber(hoveredBar.low).toFixed(2)}  收 {toChartNumber(hoveredBar.close).toFixed(2)}</text>
            <text className={`price-change-${hoveredChange.className}`} x="10" y="72">涨跌 {hoveredChange.text}</text>
          </g>
        </g>
      ) : null}
      <text className="chart-axis-label" x={width - padding.right + 8} y={y(maxPrice) + 4}>{maxPrice.toFixed(2)}</text>
      <text className="chart-axis-label" x={width - padding.right + 8} y={y(minPrice) + 4}>{minPrice.toFixed(2)}</text>
      <text className="chart-date-label" x={padding.left} y={height - 8}>{visibleBars[0]?.date}</text>
      <text className="chart-date-label" x={width - padding.right} y={height - 8} textAnchor="end">{lastBar?.date}</text>
    </svg>
  );
}

function VolumeSvg({ bars, hoveredIndex, onHoverIndex, onLeave, onWheel }) {
  const visibleBars = bars || [];
  if (!visibleBars.length) return <ChartEmptyState text="暂无成交量数据。" />;
  const maxVolume = Math.max(...visibleBars.map((bar) => toChartNumber(bar.volume)), 1);
  const width = 900;
  const height = 180;
  const padding = { top: 18, right: 54, bottom: 24, left: 18 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const step = plotWidth / Math.max(visibleBars.length, 1);
  const barWidth = Math.max(2, Math.min(9, step * 0.62));
  const hoveredBar = hoveredIndex == null ? null : visibleBars[hoveredIndex];
  const hoveredX = hoveredBar ? padding.left + hoveredIndex * step + step / 2 : null;
  return (
    <svg
      className="warehouse-volume-svg chart-interactive"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="成交量"
      onMouseMove={(event) => onHoverIndex?.(chartIndexFromPointer(event, width, padding, visibleBars.length))}
      onMouseLeave={onLeave}
      onWheel={onWheel}
    >
      <g className="chart-grid">
        {[0, 0.5, 1].map((ratio) => (
          <line key={ratio} x1={padding.left} x2={width - padding.right} y1={padding.top + ratio * plotHeight} y2={padding.top + ratio * plotHeight} />
        ))}
      </g>
      {visibleBars.map((bar, index) => {
        const volume = toChartNumber(bar.volume);
        const barHeight = Math.max(1, (volume / maxVolume) * plotHeight);
        const x = padding.left + index * step + step / 2 - barWidth / 2;
        const y = padding.top + plotHeight - barHeight;
        const up = toChartNumber(bar.close) >= toChartNumber(bar.open);
        return <rect key={`${bar.date}-${index}`} className={`${up ? "volume-up" : "volume-down"} ${index === hoveredIndex ? "hovered-volume" : ""}`} x={x} y={y} width={barWidth} height={barHeight} rx="1.2" />;
      })}
      {hoveredBar ? (
        <g className="chart-hover-layer">
          <line className="chart-crosshair" x1={hoveredX} x2={hoveredX} y1={padding.top} y2={height - padding.bottom} />
          <g className="chart-tooltip-box volume-tooltip" transform={`translate(${clampNumber(hoveredX + 12, padding.left + 6, width - padding.right - 150)} ${padding.top + 8})`}>
            <rect width="138" height="42" rx="5" />
            <text x="10" y="18">{hoveredBar.date}</text>
            <text x="10" y="34">量 {compactNumber(hoveredBar.volume)}</text>
          </g>
        </g>
      ) : null}
      <text className="chart-axis-label" x={width - padding.right + 8} y={padding.top + 4}>{compactNumber(maxVolume)}</text>
      <text className="chart-date-label" x={padding.left} y={height - 7}>{visibleBars[0]?.date}</text>
      <text className="chart-date-label" x={width - padding.right} y={height - 7} textAnchor="end">{visibleBars[visibleBars.length - 1]?.date}</text>
    </svg>
  );
}

function DataCenterPage({
  datasets,
  securities,
  settings,
  datasetQuality,
  source,
  openData,
  onSyncAll,
  onCancelSyncAll,
  onRetryFailedAll,
  syncingAll,
  allMarketSyncTask,
  onSelectDataset,
  onDeleteDataset,
}) {
  const [stockQuery, setStockQuery] = useState("");
  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [barsState, setBarsState] = useState({ loading: false, error: "", bars: [], symbol: "" });
  const [chartVisibleCount, setChartVisibleCount] = useState(110);
  const [hoveredBarIndex, setHoveredBarIndex] = useState(null);
  const localWarehouseStocks = useMemo(() => (
    securities
      .filter((item) => {
        const exchange = String(item.exchange || "").toUpperCase();
        return ["SH", "SZ", "BJ"].includes(exchange) && item.status !== "delisted" && item.symbol !== settings.benchmark;
      })
      .sort((left, right) => String(left.symbol || "").localeCompare(String(right.symbol || "")))
  ), [securities, settings.benchmark]);
  const visibleWarehouseStocks = useMemo(() => {
    const query = stockQuery.trim().toLowerCase();
    const matched = query
      ? localWarehouseStocks.filter((item) => (
        String(item.symbol || "").toLowerCase().includes(query)
        || String(item.name || "").toLowerCase().includes(query)
        || String(item.board || "").toLowerCase().includes(query)
        || String(item.industry || "").toLowerCase().includes(query)
      ))
      : localWarehouseStocks;
    return matched.slice(0, 320);
  }, [localWarehouseStocks, stockQuery]);
  const activeStock = useMemo(
    () => localWarehouseStocks.find((item) => item.symbol === selectedSymbol) || visibleWarehouseStocks[0],
    [localWarehouseStocks, selectedSymbol, visibleWarehouseStocks]
  );
  useEffect(() => {
    if (!localWarehouseStocks.length) return;
    if (!selectedSymbol || !localWarehouseStocks.some((item) => item.symbol === selectedSymbol)) {
      setSelectedSymbol(localWarehouseStocks[0].symbol);
    }
  }, [localWarehouseStocks, selectedSymbol]);
  useEffect(() => {
    if (!selectedSymbol) return undefined;
    const controller = new AbortController();
    const params = new URLSearchParams();
    if (settings.start_date) params.set("start_date", settings.start_date);
    if (settings.end_date) params.set("end_date", settings.end_date);
    setBarsState({ loading: true, error: "", bars: [], symbol: selectedSymbol });
    fetch(`${API}/market/bars/${encodeURIComponent(selectedSymbol)}?${params.toString()}`, { signal: controller.signal })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("无法读取本地日线数据")))
      .then((payload) => setBarsState({ loading: false, error: "", bars: payload.bars || [], symbol: payload.symbol || selectedSymbol }))
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setBarsState({ loading: false, error: errorMessage(error, "无法读取本地日线数据"), bars: [], symbol: selectedSymbol });
      });
    return () => controller.abort();
  }, [selectedSymbol, settings.start_date, settings.end_date]);
  useEffect(() => {
    setChartVisibleCount(110);
    setHoveredBarIndex(null);
  }, [selectedSymbol, settings.start_date, settings.end_date]);
  const localBars = barsState.symbol === selectedSymbol ? barsState.bars : [];
  const latestBar = localBars[localBars.length - 1];
  const minimumVisibleCount = localBars.length ? Math.min(30, localBars.length) : 1;
  const normalizedVisibleCount = localBars.length
    ? clampNumber(chartVisibleCount, minimumVisibleCount, localBars.length)
    : chartVisibleCount;
  const chartBars = localBars.slice(-normalizedVisibleCount);
  const safeHoveredIndex = hoveredBarIndex == null || !chartBars.length
    ? null
    : clampNumber(hoveredBarIndex, 0, chartBars.length - 1);
  const hoveredBar = safeHoveredIndex == null ? null : chartBars[safeHoveredIndex];
  const displayBar = hoveredBar || chartBars[chartBars.length - 1] || latestBar;
  const displayPreviousBar = hoveredBar ? chartBars[safeHoveredIndex - 1] : chartBars[chartBars.length - 2];
  const displayChange = priceChangeMeta(displayBar, displayPreviousBar);
  const activeStockLabel = stockDisplayName(activeStock, selectedSymbol);
  const chartRangeLabel = chartBars.length
    ? `${chartBars[0].date} → ${chartBars[chartBars.length - 1].date} · ${chartBars.length}根`
    : "等待数据";
  const handleChartWheel = (event) => {
    event.preventDefault();
    if (!localBars.length) return;
    const direction = event.deltaY > 0 ? 1 : -1;
    setChartVisibleCount((current) => {
      const base = clampNumber(Number(current) || 110, minimumVisibleCount, localBars.length);
      const step = Math.max(5, Math.round(base * 0.16));
      return clampNumber(base + direction * step, minimumVisibleCount, localBars.length);
    });
  };
  const localTaskCovered = Number(allMarketSyncTask?.covered || allMarketSyncTask?.coverage?.covered || 0);
  const localTaskExpected = Number(allMarketSyncTask?.expected || allMarketSyncTask?.coverage?.expected || 0);
  const localTaskProgress = localTaskExpected ? Math.round((localTaskCovered / localTaskExpected) * 100) : 0;
  return (
    <section className="view-page data-center-page">
      <div className="view-hero data-center-hero">
        <div>
          <span>DATA CENTER</span>
          <h2>本地行情仓库</h2>
          <p>只保留真正有用的工作区：左侧浏览本地股票，右侧查看当前时间范围内的日 K 线和成交量。快照选择、删除和补齐仍在数据管理弹窗里处理。</p>
        </div>
        <div className="view-actions">
          <button className="ghost" onClick={syncingAll ? onCancelSyncAll : onSyncAll} disabled={!syncingAll && !source?.akshare_available}>
            {syncingAll ? "停止补齐" : "同步沪深全A"}
          </button>
          <button className="primary" onClick={openData}>打开数据管理</button>
        </div>
      </div>
      {allMarketSyncTask?.status && allMarketSyncTask.status !== "idle" ? (
        <div className="sync-progress-panel data-center-sync">
          <div>
            <b>全A补齐任务：{allMarketSyncTask.status}</b>
            <span>第 {allMarketSyncTask.batch_count || 0} 批 · 覆盖 {localTaskCovered}/{localTaskExpected || "?"} · {localTaskProgress}%</span>
          </div>
          <progress value={localTaskCovered} max={localTaskExpected || 1} />
        </div>
      ) : null}
      <div className="data-center-workbench">
        <aside className="warehouse-stock-panel">
          <div className="panel-head">
            <b>数据里的个股股票</b>
            <span>{localWarehouseStocks.length} 只</span>
          </div>
          <label className="warehouse-search">
            <span>搜索股票</span>
            <input
              value={stockQuery}
              onChange={(event) => setStockQuery(event.target.value)}
              placeholder="代码、名称、板块、行业"
            />
          </label>
          <div className="warehouse-list-meta">
            显示 {visibleWarehouseStocks.length} / {localWarehouseStocks.length} 只，时间 {settings.start_date} → {settings.end_date}
          </div>
          <div className="warehouse-stock-list">
            {visibleWarehouseStocks.length ? visibleWarehouseStocks.map((stock) => (
              <button
                key={stock.symbol}
                className={stock.symbol === selectedSymbol ? "selected" : ""}
                onClick={() => setSelectedSymbol(stock.symbol)}
              >
                <span>
                  <b>{stockDisplayName(stock)}</b>
                  <small>{stock.board || stock.exchange || "未分类"}</small>
                </span>
                <em>{stock.exchange}</em>
              </button>
            )) : <ChartEmptyState text="没有匹配的股票。" />}
          </div>
        </aside>
        <section className="warehouse-chart-area">
          <article className="warehouse-chart-card kline-card">
            <div className="panel-head">
              <b>日 K 图</b>
              <div className="chart-head-actions">
                <span>
                  {displayBar
                    ? `${activeStockLabel || "未选择"} · ${displayBar.date} · 开 ${toChartNumber(displayBar.open).toFixed(2)} 高 ${toChartNumber(displayBar.high).toFixed(2)} 低 ${toChartNumber(displayBar.low).toFixed(2)} 收 ${toChartNumber(displayBar.close).toFixed(2)} · 涨跌 ${displayChange.text}`
                    : activeStockLabel || "未选择"}
                </span>
                <button className="text-button" onClick={() => setChartVisibleCount(60)} disabled={!localBars.length}>近60</button>
                <button className="text-button" onClick={() => setChartVisibleCount(120)} disabled={!localBars.length}>近120</button>
                <button className="text-button" onClick={() => setChartVisibleCount(localBars.length || 110)} disabled={!localBars.length}>全部</button>
              </div>
            </div>
            <div className="chart-range-hint">{chartRangeLabel} · 鼠标悬停看价格/成交量，滚轮缩放时间跨度</div>
            <div className="warehouse-chart-body">
              {barsState.loading ? <ChartEmptyState text="正在读取本地日线…" /> : barsState.error ? <ChartEmptyState text={barsState.error} /> : (
                <KLineSvg
                  bars={chartBars}
                  hoveredIndex={safeHoveredIndex}
                  onHoverIndex={setHoveredBarIndex}
                  onLeave={() => setHoveredBarIndex(null)}
                  onWheel={handleChartWheel}
                />
              )}
            </div>
          </article>
          <article className="warehouse-chart-card volume-card">
            <div className="panel-head">
              <b>交易量</b>
              <span>{displayBar ? `${displayBar.date} · ${compactNumber(displayBar.volume)}` : "等待数据"}</span>
            </div>
            <div className="warehouse-chart-body volume-body">
              {barsState.loading ? <ChartEmptyState text="正在读取成交量…" /> : barsState.error ? <ChartEmptyState text={barsState.error} /> : (
                <VolumeSvg
                  bars={chartBars}
                  hoveredIndex={safeHoveredIndex}
                  onHoverIndex={setHoveredBarIndex}
                  onLeave={() => setHoveredBarIndex(null)}
                  onWheel={handleChartWheel}
                />
              )}
            </div>
          </article>
        </section>
      </div>
    </section>
  );
  const selectedDataset = datasets.find((item) => item.id === settings.dataset_id);
  const syncableAllMarketCount = securities.filter((item) => (
    isSyncableShSzSecurity(item) && item.symbol !== settings.benchmark
  )).length;
  const selectedCoverage = allMarketCoverage(selectedDataset, syncableAllMarketCount);
  const hasIncompleteAllMarketDataset = Boolean(selectedCoverage && !selectedCoverage.isComplete) || datasets.some((dataset) => {
    const coverage = allMarketCoverage(dataset, syncableAllMarketCount);
    return coverage && !coverage.isComplete;
  });
  const snapshotNote = selectedDataset
    ? selectedCoverage && !selectedCoverage.isComplete
      ? `当前快照覆盖不足：${selectedCoverage.syncedCount} / ${selectedCoverage.expectedCount} 标的`
      : `当前：${selectedDataset.name}`
    : "当前股票池 / 本地日线仓库";
  const taskCovered = Number(allMarketSyncTask?.covered || allMarketSyncTask?.coverage?.covered || 0);
  const taskExpected = Number(allMarketSyncTask?.expected || allMarketSyncTask?.coverage?.expected || 0);
  const taskProgress = taskExpected ? Math.round((taskCovered / taskExpected) * 100) : 0;
  const failedSymbols = allMarketSyncTask?.failed_symbols || allMarketSyncTask?.last_failed_symbols || [];
  const skippedSymbols = allMarketSyncTask?.skipped_symbols || [];
  return (
    <section className="view-page">
      <div className="view-hero">
        <div>
          <span>DATA CENTER</span>
          <h2>管理回测数据，而不是只弹一个选择框</h2>
          <p>这里集中展示行情快照、证券主表和质量检查；常用的选择、删除、全 A 同步可以直接在主页面完成。</p>
        </div>
        <div className="view-actions">
          <button className="ghost" onClick={syncingAll ? onCancelSyncAll : onSyncAll} disabled={!syncingAll && !source?.akshare_available}>
            {syncingAll ? "停止自动补齐" : hasIncompleteAllMarketDataset ? "自动补齐全A" : "同步沪深全A"}
          </button>
          <button className="primary" onClick={openData}>打开数据管理</button>
        </div>
      </div>
      {allMarketSyncTask?.status && allMarketSyncTask.status !== "idle" ? (
        <div className="sync-progress-panel">
          <div>
            <b>全A补齐任务：{allMarketSyncTask.status}</b>
            <span>第 {allMarketSyncTask.batch_count || 0} 批 · 覆盖 {taskCovered}/{taskExpected || "?"} · {taskProgress}%</span>
          </div>
          <progress value={taskCovered} max={taskExpected || 1} />
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
        </div>
      ) : null}
      <div className="page-card-grid">
        <PageCard title="数据快照" value={`${datasets.length} 个`} note={snapshotNote} />
        <PageCard title="沪深可同步股票" value={`${syncableAllMarketCount || securities.length} 只`} note={syncableAllMarketCount ? `主表总计 ${securities.length} 只；北交所/退市不纳入全 A 同步` : "等待证券主表加载"} />
        <PageCard title="数据源状态" value={source?.akshare_available ? "AkShare 可用" : "本地/演示"} note={source?.message || "等待数据源检测"} />
        <PageCard title="质量检查" value={`${datasetQuality?.quality_checks?.length || 0} 项`} note={settings.dataset_id ? "本地数据质量记录" : "当前选择暂无固定检查"} />
      </div>
      <div className="view-panel">
        <div className="panel-head"><b>最近数据集</b><span>可直接选择或删除旧快照；重复同步会复用相同指纹快照</span></div>
        <div className="mini-list">
          {datasets.length ? datasets.slice(0, 6).map((dataset) => {
            const coverage = allMarketCoverage(dataset, syncableAllMarketCount);
            const coverageText = coverage ? ` · 覆盖 ${coverage.syncedCount} / ${coverage.expectedCount}` : "";
            return (
              <div key={dataset.id} className={`dataset-row-mini ${settings.dataset_id === dataset.id ? "selected" : ""} ${coverage?.isLow ? "warning" : ""}`}>
                <span>
                  <b>{dataset.name}</b>
                  <small>{dataset.source === "akshare_all" ? "沪深全A" : dataset.source === "akshare" ? "AkShare" : "CSV"} · {dataset.symbol_count} 标的 · {dataset.row_count} 行 · {dataset.start_date} — {dataset.end_date}{coverageText}</small>
                  {coverage?.isLow ? <small className="dataset-warning">全A快照覆盖不足，当前只有部分行情；可继续同步补齐剩余股票。</small> : null}
                </span>
                <div>
                  <button className="ghost" onClick={() => onSelectDataset(dataset)} disabled={settings.dataset_id === dataset.id}>
                    {settings.dataset_id === dataset.id ? "使用中" : "选择"}
                  </button>
                  <button className="danger-ghost" onClick={() => onDeleteDataset(dataset)}>删除</button>
                </div>
              </div>
            );
          }) : <em>暂无固定数据快照，可打开数据管理同步沪深全 A 或导入 CSV。</em>}
        </div>
      </div>
    </section>
  );
}

const STRATEGY_INDICATOR_OPTIONS = [
  ["ma_cross", "均线交叉"],
  ["ma_stack", "均线多头"],
  ["price_vs_ma", "价格/均线"],
  ["price_ma_deviation", "均线偏离"],
  ["volume_vs_ma", "成交量/均量"],
  ["volume_max_vs_ma", "天量限制"],
  ["volume_return_spike", "放量涨跌"],
  ["return_between", "区间收益"],
  ["kline_up_ratio", "阳线密度"],
  ["body_amplitude", "振幅/实体"],
  ["life_line_watch", "生命线监控"],
];

const STRATEGY_OPERATOR_OPTIONS = [
  ["above", "高于"],
  ["below", "低于"],
  ["cross_above", "上穿"],
  ["cross_below", "下穿"],
  ["between", "区间内"],
];

const indicatorLabel = (indicator) =>
  STRATEGY_INDICATOR_OPTIONS.find(([value]) => value === indicator)?.[1] || indicator || "未配置";

const operatorLabel = (operator) =>
  STRATEGY_OPERATOR_OPTIONS.find(([value]) => value === operator)?.[1] || operator || "未配置";

const createStrategyCondition = (side) =>
  side === "sell"
    ? { indicator: "price_vs_ma", operator: "below", left: 20, right: 60, threshold: 50 }
    : { indicator: "ma_stack", operator: "above", left: 5, right: 20, threshold: 60 };

const strategyGroupKey = (side) => (side === "sell" ? "sell_groups" : "buy_groups");
const strategyConditionKey = (side) => (side === "sell" ? "sell_conditions" : "buy_conditions");
const strategyDefaultGroupName = (side) => (side === "sell" ? "卖出组" : "买入组");
const strategyDefaultGroupLogic = (side) => (side === "sell" ? "any" : "all");

const cloneStrategyGroups = (strategy, side) => {
  const groupKey = strategyGroupKey(side);
  const conditionKey = strategyConditionKey(side);
  const groups = Array.isArray(strategy?.[groupKey]) && strategy[groupKey].length
    ? strategy[groupKey]
    : [{ name: `${strategyDefaultGroupName(side)} 1`, logic: strategyDefaultGroupLogic(side), conditions: strategy?.[conditionKey] || [] }];
  return groups.map((group, index) => ({
    name: group.name || `${strategyDefaultGroupName(side)} ${index + 1}`,
    logic: group.logic || strategyDefaultGroupLogic(side),
    conditions: Array.isArray(group.conditions) ? group.conditions.map((condition) => ({ ...condition })) : [],
  }));
};

const flattenStrategyGroupConditions = (groups) =>
  groups.flatMap((group, groupIndex) =>
    (group.conditions || []).map((condition, conditionIndex) => ({
      condition,
      groupIndex,
      conditionIndex,
      groupName: group.name,
      groupLogic: group.logic,
    })),
  );

const editableStrategyConfig = (settings) => ({
  strategy: settings.strategy,
  risk: {
    max_position: settings.max_position,
    max_symbol_position: settings.max_symbol_position,
    max_hold_num: settings.strategy.max_hold_num,
  },
  execution: {
    signal_price_mode: settings.signal_price_mode,
    rebalance_days: settings.rebalance_days,
    lot_size: settings.lot_size,
  },
});

const normalizedNumber = (value, fallback = 0) => {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
};

function StrategyResearchPage({ settings, setSettings, strategyRecord, openStrategy }) {
  const buyGroups = useMemo(() => cloneStrategyGroups(settings.strategy, "buy"), [settings.strategy]);
  const sellGroups = useMemo(() => cloneStrategyGroups(settings.strategy, "sell"), [settings.strategy]);
  const buyNodes = useMemo(() => flattenStrategyGroupConditions(buyGroups), [buyGroups]);
  const sellNodes = useMemo(() => flattenStrategyGroupConditions(sellGroups), [sellGroups]);
  const buyGroupCount = settings.strategy.buy_groups?.length || 1;
  const sellGroupCount = settings.strategy.sell_groups?.length || 1;
  const candidateSortLabel = {
    none: "不排序",
    return_asc: "回撤优先",
    return_desc: "强势优先",
  }[settings.strategy.candidate_sort || "none"];
  const versionLabel = strategyRecord?.latest_version ? `v${strategyRecord.latest_version.version}` : "未保存";
  const signalPriceLabel = settings.signal_price_mode === "adjusted" ? "复权收盘" : "未复权收盘";
  const strategyConfigJson = useMemo(() => JSON.stringify(editableStrategyConfig(settings), null, 2), [settings]);
  const [strategyDraft, setStrategyDraft] = useState(strategyConfigJson);
  const [strategyDraftDirty, setStrategyDraftDirty] = useState(false);
  const [strategyDraftError, setStrategyDraftError] = useState("");

  useEffect(() => {
    if (!strategyDraftDirty) {
      setStrategyDraft(strategyConfigJson);
    }
  }, [strategyConfigJson, strategyDraftDirty]);

  const commitSettings = (updater) => {
    setStrategyDraftDirty(false);
    setStrategyDraftError("");
    setSettings(updater);
  };

  const updateStrategy = (updater) => {
    commitSettings((current) => {
      const nextStrategy = updater(current.strategy || {});
      return { ...current, strategy: nextStrategy };
    });
  };

  const updateStrategyField = (field, value) => {
    updateStrategy((strategy) => ({ ...strategy, [field]: value }));
  };

  const updateRuleGroupLogic = (side, value) => {
    updateStrategy((strategy) => ({
      ...strategy,
      [side === "sell" ? "sell_group_logic" : "buy_group_logic"]: value,
    }));
  };

  const updateConditionNode = (side, groupIndex, conditionIndex, patch) => {
    updateStrategy((strategy) => {
      const groups = cloneStrategyGroups(strategy, side);
      if (!groups[groupIndex]?.conditions?.[conditionIndex]) return strategy;
      groups[groupIndex].conditions[conditionIndex] = { ...groups[groupIndex].conditions[conditionIndex], ...patch };
      return {
        ...strategy,
        [strategyGroupKey(side)]: groups,
        [strategyConditionKey(side)]: groups.flatMap((group) => group.conditions),
      };
    });
  };

  const addConditionNode = (side) => {
    updateStrategy((strategy) => {
      const groups = cloneStrategyGroups(strategy, side);
      groups[0] = {
        ...groups[0],
        conditions: [...(groups[0].conditions || []), createStrategyCondition(side)],
      };
      return {
        ...strategy,
        [strategyGroupKey(side)]: groups,
        [strategyConditionKey(side)]: groups.flatMap((group) => group.conditions),
      };
    });
  };

  const deleteConditionNode = (side, groupIndex, conditionIndex) => {
    updateStrategy((strategy) => {
      const groups = cloneStrategyGroups(strategy, side).map((group, index) => (
        index === groupIndex
          ? { ...group, conditions: group.conditions.filter((_, conditionIndexInGroup) => conditionIndexInGroup !== conditionIndex) }
          : group
      ));
      return {
        ...strategy,
        [strategyGroupKey(side)]: groups,
        [strategyConditionKey(side)]: groups.flatMap((group) => group.conditions),
      };
    });
  };

  const addRuleGroup = (side) => {
    updateStrategy((strategy) => {
      const groups = cloneStrategyGroups(strategy, side);
      groups.push({
        name: `${strategyDefaultGroupName(side)} ${groups.length + 1}`,
        logic: strategyDefaultGroupLogic(side),
        conditions: [createStrategyCondition(side)],
      });
      return {
        ...strategy,
        [strategyGroupKey(side)]: groups,
        [strategyConditionKey(side)]: groups.flatMap((group) => group.conditions),
      };
    });
  };

  const updateRiskPercent = (field, value) => {
    const percent = Math.max(0, Math.min(100, normalizedNumber(value, 0))) / 100;
    commitSettings((current) => ({ ...current, [field]: percent }));
  };

  const updateExecutionField = (field, value) => {
    commitSettings((current) => ({ ...current, [field]: value }));
  };

  const applyStrategyDraft = () => {
    try {
      const parsed = JSON.parse(strategyDraft);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("策略代码必须是一个 JSON 对象。");
      }
      const nextStrategy = parsed.strategy || parsed;
      if (!nextStrategy || typeof nextStrategy !== "object" || Array.isArray(nextStrategy)) {
        throw new Error("strategy 必须是一个 JSON 对象。");
      }
      setSettings((current) => ({
        ...current,
        max_position: parsed.risk?.max_position != null ? normalizedNumber(parsed.risk.max_position, current.max_position) : current.max_position,
        max_symbol_position: parsed.risk?.max_symbol_position != null ? normalizedNumber(parsed.risk.max_symbol_position, current.max_symbol_position) : current.max_symbol_position,
        rebalance_days: parsed.execution?.rebalance_days != null ? normalizedNumber(parsed.execution.rebalance_days, current.rebalance_days) : current.rebalance_days,
        lot_size: parsed.execution?.lot_size != null ? normalizedNumber(parsed.execution.lot_size, current.lot_size) : current.lot_size,
        signal_price_mode: parsed.execution?.signal_price_mode || current.signal_price_mode,
        strategy: { ...current.strategy, ...nextStrategy },
      }));
      setStrategyDraftDirty(false);
      setStrategyDraftError("");
    } catch (error) {
      setStrategyDraftError(errorMessage(error, "策略代码解析失败"));
    }
  };

  const formatStrategyDraft = () => {
    try {
      setStrategyDraft(JSON.stringify(JSON.parse(strategyDraft), null, 2));
      setStrategyDraftError("");
      setStrategyDraftDirty(true);
    } catch (error) {
      setStrategyDraftError(errorMessage(error, "JSON 格式错误"));
    }
  };

  const resetStrategyDraft = () => {
    setStrategyDraft(strategyConfigJson);
    setStrategyDraftDirty(false);
    setStrategyDraftError("");
  };

  const renderConditionNode = (side, node, index) => {
    const { condition, groupIndex, conditionIndex, groupName } = node;
    return (
      <div key={`${side}-${groupIndex}-${conditionIndex}`} className={`flow-node condition-node ${side === "sell" ? "sell" : "buy"}`}>
        <div className="node-title-row">
          <small>{groupName}</small>
          <button className="danger-ghost tiny" onClick={() => deleteConditionNode(side, groupIndex, conditionIndex)}>删除</button>
        </div>
        <b>{side === "sell" ? "卖出" : "买入"} {index + 1}</b>
        <label className="node-field">
          <span>指标</span>
          <select value={condition.indicator || ""} onChange={(event) => updateConditionNode(side, groupIndex, conditionIndex, { indicator: event.target.value })}>
            {STRATEGY_INDICATOR_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="node-field">
          <span>关系</span>
          <select value={condition.operator || "above"} onChange={(event) => updateConditionNode(side, groupIndex, conditionIndex, { operator: event.target.value })}>
            {STRATEGY_OPERATOR_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <div className="node-field-grid">
          <label className="node-field">
            <span>短窗</span>
            <input type="number" value={condition.left ?? ""} onChange={(event) => updateConditionNode(side, groupIndex, conditionIndex, { left: normalizedNumber(event.target.value, 0) })} />
          </label>
          <label className="node-field">
            <span>长窗</span>
            <input type="number" value={condition.right ?? ""} onChange={(event) => updateConditionNode(side, groupIndex, conditionIndex, { right: normalizedNumber(event.target.value, 0) })} />
          </label>
          <label className="node-field">
            <span>阈值</span>
            <input type="number" step="0.01" value={condition.threshold ?? ""} onChange={(event) => updateConditionNode(side, groupIndex, conditionIndex, { threshold: normalizedNumber(event.target.value, 0) })} />
          </label>
          <label className="node-field">
            <span>下限</span>
            <input type="number" step="0.01" value={condition.lower ?? ""} onChange={(event) => updateConditionNode(side, groupIndex, conditionIndex, { lower: normalizedNumber(event.target.value, 0) })} />
          </label>
          <label className="node-field">
            <span>上限</span>
            <input type="number" step="0.01" value={condition.upper ?? ""} onChange={(event) => updateConditionNode(side, groupIndex, conditionIndex, { upper: normalizedNumber(event.target.value, 0) })} />
          </label>
        </div>
        <em>{indicatorLabel(condition.indicator)} · {operatorLabel(condition.operator)}</em>
      </div>
    );
  };

  return (
    <section className="view-page strategy-management-page">
      <div className="strategy-management-hero">
        <div className="strategy-management-title">
          <span>STRATEGY MANAGEMENT</span>
          <h2>策略管理</h2>
          <p>{settings.strategy.name}</p>
        </div>
        <div className="strategy-management-summary">
          <span>
            <b>{versionLabel}</b>
            <small>策略版本</small>
          </span>
          <span>
            <b>{settings.symbols.length}</b>
            <small>股票池</small>
          </span>
          <span>
            <b>{buyNodes.length + sellNodes.length}</b>
            <small>交易节点</small>
          </span>
          <span>
            <b>{signalPriceLabel}</b>
            <small>信号价格</small>
          </span>
        </div>
        <div className="view-actions">
          <button className="ghost" onClick={() => openStrategy("selection")}>编辑选股</button>
          <button className="primary" onClick={() => openStrategy("trading")}>编辑交易</button>
        </div>
      </div>
      <div className="strategy-management-workbench">
        <section className="strategy-code-panel">
          <div className="panel-head">
            <b>策略代码编辑器</b>
            <span>{strategyDraftDirty ? "有未应用修改" : "已同步工作台"}</span>
          </div>
          <div className="strategy-code-block strategy-code-editor-wrap">
            <span>FULL STRATEGY JSON</span>
            <h3>一套策略，一份配置</h3>
            <p>左侧代码和右侧节点共用同一份策略。代码应用后刷新图形，图形改动后自动刷新代码。</p>
            <textarea
              className="strategy-json-editor"
              value={strategyDraft}
              spellCheck={false}
              onChange={(event) => {
                setStrategyDraft(event.target.value);
                setStrategyDraftDirty(true);
              }}
            />
            {strategyDraftError ? <div className="strategy-json-error">{strategyDraftError}</div> : null}
          </div>
          <div className="strategy-code-foot">
            <button className="primary" onClick={applyStrategyDraft}>应用代码</button>
            <button className="ghost" onClick={formatStrategyDraft}>格式化</button>
            <button className="ghost" onClick={resetStrategyDraft}>重置</button>
          </div>
        </section>
        <section className="strategy-visual-panel">
          <div className="panel-head">
            <b>节点工作台</b>
            <span>添加、删除和调整节点会写回左侧代码</span>
          </div>
          <div className="strategy-flow-canvas">
            <div className="flow-column selection">
              <span>选股环节</span>
              <div className="flow-node tall">
                <small>股票池</small>
                <b>{settings.symbols.length} 只</b>
                <em>{candidateSortLabel}</em>
                <label className="node-field">
                  <span>候选排序</span>
                  <select value={settings.strategy.candidate_sort || "none"} onChange={(event) => updateStrategyField("candidate_sort", event.target.value)}>
                    <option value="none">不排序</option>
                    <option value="return_asc">回撤优先</option>
                    <option value="return_desc">强势优先</option>
                  </select>
                </label>
                <label className="node-field">
                  <span>排序窗口</span>
                  <input type="number" value={settings.strategy.sort_window || 20} onChange={(event) => updateStrategyField("sort_window", normalizedNumber(event.target.value, 20))} />
                </label>
                <label className="node-field">
                  <span>最多持股</span>
                  <input type="number" value={settings.strategy.max_hold_num || ""} onChange={(event) => updateStrategyField("max_hold_num", normalizedNumber(event.target.value, 0))} />
                </label>
                <button className="ghost" onClick={() => openStrategy("selection")}>高级选股</button>
              </div>
            </div>
            <div className="flow-arrow">→</div>
            <div className="flow-column trading">
              <span>交易环节</span>
              <div className="flow-row">
                <div className="flow-node-list">
                  <div className="node-toolbar">
                    <b>买入条件</b>
                    <button className="ghost tiny" onClick={() => addConditionNode("buy")}>+ 节点</button>
                  </div>
                  {buyNodes.length ? buyNodes.map((node, index) => renderConditionNode("buy", node, index)) : <div className="empty-node">暂无买入节点</div>}
                </div>
                <div className="flow-arrow small">→</div>
                <div className="flow-node-list">
                  <div className="node-toolbar">
                    <b>卖出条件</b>
                    <button className="ghost tiny" onClick={() => addConditionNode("sell")}>+ 节点</button>
                  </div>
                  {sellNodes.length ? sellNodes.map((node, index) => renderConditionNode("sell", node, index)) : <div className="empty-node">暂无卖出节点</div>}
                </div>
              </div>
              <div className="flow-row bottom">
                <div className="flow-node risk">
                  <small>仓位风控</small>
                  <b>总仓 {Math.round(settings.max_position * 100)}%</b>
                  <em>单票 {Math.round((settings.max_symbol_position || 0.35) * 100)}%</em>
                  <label className="node-field">
                    <span>总仓位 %</span>
                    <input type="number" value={Math.round(settings.max_position * 100)} onChange={(event) => updateRiskPercent("max_position", event.target.value)} />
                  </label>
                  <label className="node-field">
                    <span>单票上限 %</span>
                    <input type="number" value={Math.round((settings.max_symbol_position || 0.35) * 100)} onChange={(event) => updateRiskPercent("max_symbol_position", event.target.value)} />
                  </label>
                </div>
                <div className="flow-node price">
                  <small>信号价格</small>
                  <b>{signalPriceLabel}</b>
                  <em>撮合用未复权价格</em>
                  <label className="node-field">
                    <span>信号基准</span>
                    <select value={settings.signal_price_mode || "unadjusted"} onChange={(event) => updateExecutionField("signal_price_mode", event.target.value)}>
                      <option value="unadjusted">未复权收盘</option>
                      <option value="adjusted">复权收盘</option>
                    </select>
                  </label>
                  <label className="node-field">
                    <span>再平衡天数</span>
                    <input type="number" value={settings.rebalance_days || 1} onChange={(event) => updateExecutionField("rebalance_days", normalizedNumber(event.target.value, 1))} />
                  </label>
                </div>
              </div>
              <button className="primary" onClick={() => openStrategy("trading")}>编辑交易策略</button>
            </div>
            <div className="flow-column rules">
              <span>组合规则</span>
              <div className="flow-node compact">
                <small>买入组</small>
                <b>{buyGroupCount} 组</b>
                <em>{(settings.strategy.buy_group_logic || "any") === "all" ? "全部组满足" : "任一组满足"}</em>
                <label className="node-field">
                  <span>组间规则</span>
                  <select value={settings.strategy.buy_group_logic || "any"} onChange={(event) => updateRuleGroupLogic("buy", event.target.value)}>
                    <option value="any">任一组满足</option>
                    <option value="all">全部组满足</option>
                  </select>
                </label>
                <button className="ghost tiny" onClick={() => addRuleGroup("buy")}>+ 买入组</button>
              </div>
              <div className="flow-node compact">
                <small>卖出组</small>
                <b>{sellGroupCount} 组</b>
                <em>{(settings.strategy.sell_group_logic || "any") === "all" ? "全部组满足" : "任一组满足"}</em>
                <label className="node-field">
                  <span>组间规则</span>
                  <select value={settings.strategy.sell_group_logic || "any"} onChange={(event) => updateRuleGroupLogic("sell", event.target.value)}>
                    <option value="any">任一组满足</option>
                    <option value="all">全部组满足</option>
                  </select>
                </label>
                <button className="ghost tiny" onClick={() => addRuleGroup("sell")}>+ 卖出组</button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </section>
  );
}

function BacktestCenterPage({ settings, running, progress, metrics, openStep, openSettings, onRun, onCancel }) {
  return (
    <section className="view-page">
      <Workflow settings={settings} openStep={openStep} />
      <div className="view-hero">
        <div>
          <span>BACKTEST</span>
          <h2>运行回测任务</h2>
          <p>这里是回测中心主页面；参数设置和执行动作在页面内显式触发。</p>
        </div>
        <div className="view-actions">
          <button className="ghost" onClick={openSettings}>参数设置</button>
          {running ? <button className="ghost" onClick={onCancel}>取消任务</button> : null}
          <button className="primary" onClick={onRun} disabled={running}>{running ? `运行中 ${Math.round(progress * 100)}%` : "运行回测"}</button>
        </div>
      </div>
      <MetricsStrip metrics={metrics} />
      <div className="page-card-grid">
        <PageCard title="时间区间" value={`${settings.start_date} → ${settings.end_date}`} note="顶部日期控件可直接调整" />
        <PageCard title="股票数量" value={`${settings.symbols.length} 只`} note={settings.dataset_id ? "来自本地数据快照" : "来自当前股票池"} />
        <PageCard title="最大仓位" value={`${Math.round(settings.max_position * 100)}%`} note={`单股上限 ${Math.round((settings.max_symbol_position || 0.35) * 100)}%`} />
        <PageCard title="交易规则" value="T+1 / 整手" note="信号收盘生成，下一交易日开盘撮合" />
      </div>
    </section>
  );
}

function ResultsAnalysisPage({ result, settings, running, metrics, chartData, years, comparisons, onRun }) {
  return (
    <section className="view-page">
      <ReportTitle result={result} settings={settings} running={running} onRun={onRun} />
      <MetricsStrip metrics={metrics} />
      <Suspense fallback={<ChartLoading />}>
        <DashboardCharts chartData={chartData} result={result} settings={settings} metrics={metrics} years={years} taskId={result?.task_id} comparisons={comparisons} />
      </Suspense>
    </section>
  );
}

function ReportsPage({ result, onExportReport }) {
  return (
    <section className="view-page">
      <div className="view-hero">
        <div>
          <span>REPORTS</span>
          <h2>导出与管理研究报告</h2>
          <p>报告管理现在有独立页面。完成回测后可导出 HTML、PDF，Markdown 接口保留在后端。</p>
        </div>
        <div className="view-actions">
          <button className="ghost" onClick={() => onExportReport("md")} disabled={!result?.task_id}>Markdown</button>
          <button className="ghost" onClick={() => onExportReport("html")} disabled={!result?.task_id}>HTML 报告</button>
          <button className="primary" onClick={() => onExportReport("pdf")} disabled={!result?.task_id}>PDF</button>
        </div>
      </div>
      <div className="page-card-grid">
        <PageCard title="最近任务" value={result?.task_id ? result.task_id.slice(0, 8) : "暂无"} note={result ? result.period ? `${result.period.start} — ${result.period.end}` : "已完成回测" : "先运行一次回测后再导出"} />
        <PageCard title="HTML" value="在线报告" note="含指标卡、权益曲线和交易记录" />
        <PageCard title="PDF" value="离线归档" note="适合投研复盘和分享" />
        <PageCard title="Markdown" value="复盘草稿" note="适合继续编辑、复制到投研文档或版本库归档" />
      </div>
    </section>
  );
}

function isSyncableShSzSecurity(item) {
  return ["SH", "SZ"].includes(String(item.exchange || "").toUpperCase()) && item.status !== "delisted";
}

function allMarketCoverage(dataset, expectedCount) {
  if (!dataset || dataset.source !== "akshare_all" || !expectedCount) return null;
  const syncedCount = Number(dataset._coverage?.covered ?? Math.max(0, Number(dataset.symbol_count || 0) - 1));
  const expected = Number(dataset._coverage?.expected || expectedCount);
  return {
    expectedCount: expected,
    syncedCount,
    ratio: syncedCount / expected,
    isLow: syncedCount < Math.ceil(expected * 0.9),
    isComplete: syncedCount >= expected,
  };
}

const indicatorLabels = {
  ma_cross: "均线交叉",
  price_vs_ma: "价格均线",
  rsi: "RSI",
  macd: "MACD",
  bollinger: "布林带",
};

const operatorLabels = {
  cross_above: "上穿",
  cross_below: "下穿",
  above: "高于",
  below: "低于",
};

function describeCondition(condition) {
  if (!condition) return "未配置";
  const indicator = indicatorLabels[condition.indicator] || condition.indicator || "未知指标";
  const operator = operatorLabels[condition.operator] || condition.operator || "条件";
  const left = condition.left ?? "-";
  const right = condition.right ?? "-";
  const threshold = condition.threshold ?? "-";
  if (condition.indicator === "rsi") return `${indicator}(${left}) ${operator} ${threshold}`;
  if (condition.indicator === "macd") return `${indicator}(${left}, ${right}, ${threshold}) ${operator}`;
  if (condition.indicator === "bollinger") return `${indicator}(${left}, ${threshold}) ${operator}`;
  return `${indicator}(${left}, ${right}) ${operator}`;
}

function FactorAnalysisPage({ settings, result, openStrategy }) {
  const buy = settings.strategy.buy_conditions?.[0];
  const sell = settings.strategy.sell_conditions?.[0];
  const tradeCount = result?.metrics?.trade_count ?? 0;
  return (
    <section className="view-page">
      <div className="view-hero">
        <div>
          <span>FACTOR ANALYSIS</span>
          <h2>当前策略信号拆解</h2>
          <p>先把正在使用的规则因子讲清楚：买入、卖出、价格口径和后续可扩展的 IC/分层回测路线都集中在这里。</p>
        </div>
        <button className="primary" onClick={openStrategy}>编辑信号规则</button>
      </div>
      <div className="page-card-grid">
        <PageCard title="买入信号" value={indicatorLabels[buy?.indicator] || "未配置"} note={describeCondition(buy)} />
        <PageCard title="卖出信号" value={indicatorLabels[sell?.indicator] || "未配置"} note={describeCondition(sell)} />
        <PageCard title="信号价格口径" value={settings.signal_price_mode === "adjusted" ? "复权收盘" : "未复权收盘"} note="撮合、现金和费用仍使用未复权价格" />
        <PageCard title="最近交易次数" value={`${tradeCount} 笔`} note={result?.task_id ? `来自任务 ${result.task_id.slice(0, 8)}` : "完成回测后自动更新"} />
      </div>
      <div className="view-panel">
        <div className="panel-head"><b>因子路线</b><span>从规则信号逐步扩展到因子研究</span></div>
        <div className="analysis-list">
          <span><b>1. 信号解释</b><small>展示当前买卖条件、参数和价格口径，便于复盘每次回测假设。</small></span>
          <span><b>2. 样本覆盖</b><small>基于固定数据快照统计信号覆盖标的、有效交易日和缺失情况。</small></span>
          <span><b>3. IC / 分层回测</b><small>后续可增加因子收益相关性、分组收益和行业中性分析。</small></span>
        </div>
      </div>
    </section>
  );
}

function PortfolioManagementPage({ settings, result, datasets, securities, openSettings, openData }) {
  const selectedDataset = datasets.find((item) => item.id === settings.dataset_id);
  const selectedSecurityCount = settings.dataset_id ? selectedDataset?.symbol_count || settings.symbols.length : settings.symbols.length;
  const rejectionStats = result?.order_rejections || {};
  const rejectionCount = Object.values(rejectionStats).reduce((sum, value) => sum + Number(value || 0), 0);
  return (
    <section className="view-page">
      <div className="view-hero">
        <div>
          <span>PORTFOLIO</span>
          <h2>组合约束与股票池管理</h2>
          <p>把资金、仓位、股票池和过滤器集中成一张组合控制面板；需要调整时再进入参数设置或数据中心。</p>
        </div>
        <div className="view-actions">
          <button className="ghost" onClick={openData}>管理股票池</button>
          <button className="primary" onClick={openSettings}>参数设置</button>
        </div>
      </div>
      <div className="page-card-grid">
        <PageCard title="初始资金" value={`${Number(settings.initial_cash || 0).toLocaleString("zh-CN")} 元`} note="回测账户起始现金" />
        <PageCard title="组合最大仓位" value={`${Math.round((settings.max_position || 0) * 100)}%`} note={`单标的上限 ${Math.round((settings.max_symbol_position || 0) * 100)}%`} />
        <PageCard title="候选股票池" value={`${selectedSecurityCount} 只`} note={selectedDataset ? `来自 ${selectedDataset.name}` : `当前主表 ${securities.length} 只`} />
        <PageCard title="拒单统计" value={`${rejectionCount} 次`} note={result?.task_id ? "来自最近回测结果" : "完成回测后展示涨跌停/资金不足等拒单"} />
      </div>
      <div className="view-panel">
        <div className="panel-head"><b>组合控制规则</b><span>当前回测请求中已生效的约束</span></div>
        <div className="analysis-list">
          <span><b>调仓周期</b><small>每 {settings.rebalance_days || 1} 个交易日评估一次买入候选；T+1 和整手交易规则保持开启。</small></span>
          <span><b>股票池过滤</b><small>{settings.exclude_st === false ? "允许 ST" : "排除 ST"}，最少上市 {settings.min_listed_days || 0} 天，20 日均成交额不低于 {Number(settings.min_average_amount || 0).toLocaleString("zh-CN")}。</small></span>
          <span><b>止盈止损</b><small>止损 {Math.round((settings.stop_loss_pct || 0) * 100)}%，止盈 {Math.round((settings.take_profit_pct || 0) * 100)}%，触发后会在交易记录中暴露卖出原因。</small></span>
        </div>
      </div>
    </section>
  );
}

function SystemSettingsPage({ source, openSettings }) {
  return (
    <section className="view-page">
      <div className="view-hero">
        <div>
          <span>SETTINGS</span>
          <h2>系统设置</h2>
          <p>系统设置页用于查看本地服务与数据源状态；详细回测参数仍在参数设置抽屉中维护。</p>
        </div>
        <button className="primary" onClick={openSettings}>打开参数设置</button>
      </div>
      <div className="page-card-grid">
        <PageCard title="本地 API" value={source?.available === false ? "未连接" : "运行中"} note={source?.message || "FastAPI 本地服务"} />
        <PageCard title="AkShare" value={source?.akshare_available ? "可用" : "不可用"} note={source?.source || "数据源检测中"} />
        <PageCard title="频率" value="日线" note="分钟线扩展口已保留" />
      </div>
    </section>
  );
}

function App() {
  const [settings, setSettings] = useState(initialSettings);
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentTaskId, setCurrentTaskId] = useState(null);
  const [drawer, setDrawer] = useState(null);
  const [activeView, setActiveView] = useState("backtest");
  const [securities, setSecurities] = useState([]);
  const [source, setSource] = useState(null);
  const [notice, setNotice] = useState("");
  const [datasets, setDatasets] = useState([]);
  const [datasetQuality, setDatasetQuality] = useState(null);
  const [importing, setImporting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncingAll, setSyncingAll] = useState(false);
  const [allMarketSyncTask, setAllMarketSyncTask] = useState(null);
  const [marketCoverage, setMarketCoverage] = useState(null);
  const [strategyRecord, setStrategyRecord] = useState(null);
  const [savingStrategy, setSavingStrategy] = useState(false);
  const [strategyEditorMode, setStrategyEditorMode] = useState("trading");
  const [booting, setBooting] = useState(true);
  const [comparisons, setComparisons] = useState([]);
  const selectedSymbolsKey = settings.symbols.join(",");

  const refreshComparisons = () => {
    fetch(`${API}/backtests/compare?limit=6`)
      .then((response) => response.json())
      .then(setComparisons)
      .catch((error) => logIgnoredError("刷新回测对比失败", error));
  };

  const runBacktest = async (candidateSignal) => {
    const signal = candidateSignal?.constructor?.name === "AbortSignal" ? candidateSignal : undefined;
    if (signal?.aborted) return;

    let taskId = null;
    const cancelSubmittedTask = () => {
      if (taskId) fetch(`${API}/backtests/${taskId}/cancel`, { method: "POST" }).catch((error) => logIgnoredError("取消孤儿回测任务失败", error));
    };

    signal?.addEventListener("abort", cancelSubmittedTask, { once: true });
    setRunning(true);
    setProgress(0);
    setNotice("");
    try {
      const createResponse = await fetch(`${API}/backtests`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
        signal,
      });
      if (!createResponse.ok) throw new Error((await createResponse.json()).detail || "无法创建回测任务");
      const task = await createResponse.json();
      taskId = task.id;
      setCurrentTaskId(task.id);
      if (signal?.aborted) {
        cancelSubmittedTask();
        return;
      }

      let delay = 180;
      while (true) {
        const statusResponse = await fetch(`${API}/backtests/${task.id}`, { signal });
        if (!statusResponse.ok) throw new Error("无法读取回测任务状态");
        const status = await statusResponse.json();
        setProgress(status.progress || 0);
        if (status.status === "completed") {
          const resultResponse = await fetch(`${API}/backtests/${task.id}/result`, { signal });
          if (!resultResponse.ok) throw new Error("无法读取回测结果");
          setResult(await resultResponse.json());
          refreshComparisons();
          setNotice("回测已完成，结果已持久化");
          break;
        }
        if (status.status === "failed" || status.status === "cancelled") {
          throw new Error(status.error || `任务状态: ${status.status}`);
        }
        await new Promise((resolve) => setTimeout(resolve, delay));
        delay = Math.min(Math.round(delay * 1.3), 3000);
      }
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) setNotice(`回测未完成：${errorMessage(error)}`);
    } finally {
      signal?.removeEventListener("abort", cancelSubmittedTask);
      if (!signal?.aborted) {
        setRunning(false);
        setCurrentTaskId(null);
      }
    }
  };

  const cancelBacktest = async () => {
    if (!currentTaskId) return;
    try {
      await fetch(`${API}/backtests/${currentTaskId}/cancel`, { method: "POST" });
      setNotice("正在取消回测任务…");
    } catch (error) {
      setNotice(`取消失败：${errorMessage(error)}`);
    }
  };

  const applyDataset = (dataset, symbols) =>
    setSettings((current) => ({
      ...current,
      dataset_id: dataset?.id || null,
      symbols: symbols?.filter((symbol) => symbol !== current.benchmark) || current.symbols,
    }));

  const importCsv = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const response = await fetch(`${API}/datasets/csv`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: file.name.replace(/\.csv$/i, ""), csv_text: await file.text() }),
      });
      if (!response.ok) throw new Error((await response.json()).detail || "CSV 校验失败");
      const dataset = await response.json();
      setDatasets((current) => [dataset, ...current.filter((item) => item.id !== dataset.id)]);
      applyDataset(dataset, dataset.summary.symbols);
      setDatasetQuality({ dataset, summary: dataset.summary, quality_checks: dataset.quality_checks || [] });
      setNotice(dataset.duplicate ? "该数据集已存在并已选中" : `数据集已导入并选中：${dataset.summary.row_count} 行`);
    } catch (error) {
      setNotice(`导入失败：${errorMessage(error)}`);
    } finally {
      setImporting(false);
      event.target.value = "";
    }
  };

  const importIndustryHistory = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const response = await fetch(`${API}/securities/industry-history/csv`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ csv_text: await file.text() }),
      });
      if (!response.ok) throw new Error((await response.json()).detail || "行业历史导入失败");
      const result = await response.json();
      const securitiesResponse = await fetch(`${API}/securities`);
      if (securitiesResponse.ok) setSecurities(await securitiesResponse.json());
      setNotice(`行业历史已导入：${result.count} 条`);
    } catch (error) {
      setNotice(`行业历史导入失败：${errorMessage(error)}`);
    } finally {
      setImporting(false);
      event.target.value = "";
    }
  };

  const applyAllMarketSyncTask = (task, showTerminalNotice = false) => {
    if (!task || task.status === "idle") {
      setSyncingAll(false);
      return;
    }
    setAllMarketSyncTask(task);
    const isActive = task.status === "queued" || task.status === "running";
    setSyncingAll(isActive);
    if (task.dataset) {
      const dataset = task.dataset;
      setDatasets((current) => {
        const consolidatedIds = new Set(dataset._consolidated_dataset_ids || []);
        return [dataset, ...current.filter((item) => item.id !== dataset.id && !consolidatedIds.has(item.id))];
      });
      applyDataset(dataset, dataset.summary?.symbols);
      setDatasetQuality({ dataset, summary: dataset.summary, quality_checks: dataset.quality_checks || [] });
    }
    const covered = Number(task.covered || task.coverage?.covered || 0);
    const expected = Number(task.expected || task.coverage?.expected || 0);
    if (isActive) {
      setNotice(`自动补齐全A：第 ${task.batch_count || 0} 批，覆盖 ${covered}/${expected || "?"}，后台继续处理中…`);
    } else if (showTerminalNotice && task.status === "completed") {
      setNotice(`全A自动补齐完成：覆盖 ${covered}/${expected || "全部"}，共执行 ${task.batch_count || 0} 批。`);
    } else if (showTerminalNotice && task.status === "failed") {
      setNotice(`全A自动补齐失败：${task.error || "免费数据源暂不可用"}`);
    } else if (showTerminalNotice && task.status === "cancelled") {
      setNotice("已停止自动补齐全A，当前已完成的批次会保留在数据集中。");
    }
  };

  const cancelAllMarketSync = async () => {
    if (!allMarketSyncTask?.id) {
      setNotice("当前没有正在运行的全A补齐任务。");
      return;
    }
    try {
      const response = await fetch(`${API}/datasets/akshare/all/tasks/${allMarketSyncTask.id}`, { method: "DELETE" });
      if (!response.ok) throw new Error((await response.json()).detail || "停止任务失败");
      const task = await response.json();
      applyAllMarketSyncTask(task, true);
      setNotice("正在停止自动补齐全A…");
    } catch (error) {
      setNotice(`停止失败：${errorMessage(error)}`);
    }
  };

  const startAllMarketSync = async (symbols = null, label = "全A") => {
    setSyncingAll(true);
    setNotice(`正在启动${label}后台补齐任务…`);
    try {
      const allMarketName = `AkShare 沪深全A ${settings.start_date} 至 ${settings.end_date}`;
      const targetDatasetName = symbols?.length
        ? `AkShare 所选股票池 ${settings.start_date} 至 ${settings.end_date}`
        : allMarketName;
      const baseAllMarketDataset = datasets.find((item) => (
        item.id === settings.dataset_id && item.source === "akshare_all" && item.name === targetDatasetName
      )) || datasets.find((item) => item.source === "akshare_all" && item.name === targetDatasetName);
      const response = await fetch(`${API}/datasets/akshare/all/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: targetDatasetName,
          start_date: settings.start_date,
          end_date: settings.end_date,
          benchmark: settings.benchmark,
          base_dataset_id: baseAllMarketDataset?.id || null,
          symbols,
        }),
      });
      if (!response.ok) throw new Error((await response.json()).detail || "启动全A同步任务失败");
      const task = await response.json();
      applyAllMarketSyncTask(task);
      setNotice(task.duplicate ? "已有全A补齐任务正在运行，已切换到该任务进度。" : "全A后台补齐任务已启动。");
    } catch (error) {
      setSyncingAll(false);
      setNotice(`启动失败：${errorMessage(error)}`);
    }
  };

  const retryFailedAllMarketSync = async () => {
    if (!allMarketSyncTask?.id) {
      setNotice("当前没有可重试的全A补齐任务。");
      return;
    }
    const failedSymbols = allMarketSyncTask.failed_symbols || allMarketSyncTask.last_failed_symbols || [];
    if (!failedSymbols.length) {
      setNotice("当前任务没有失败股票需要重试。");
      return;
    }
    setSyncingAll(true);
    setNotice(`正在重试 ${failedSymbols.length} 只失败股票…`);
    try {
      const response = await fetch(`${API}/datasets/akshare/all/tasks/${allMarketSyncTask.id}/retry-failed`, {
        method: "POST",
      });
      if (!response.ok) throw new Error((await response.json()).detail || "重试失败项启动失败");
      const task = await response.json();
      applyAllMarketSyncTask(task);
      setNotice(task.duplicate ? "已有同步任务正在运行，已切换到当前进度。" : `失败项重试任务已启动：${failedSymbols.length} 只。`);
    } catch (error) {
      setSyncingAll(false);
      setNotice(`重试失败：${errorMessage(error)}`);
    }
  };

  const syncAkshare = async (scope = "selected") => {
    const allMarket = scope === "all";
    if (allMarket) {
      await startAllMarketSync();
      return;
    }
    // 大股票池走后台任务：后端会先查本地仓库，只补缺口。
    if (settings.symbols.length > 20) {
      await startAllMarketSync(settings.symbols, "所选股票池");
      return;
    }
    const abortController = null;
    setSyncing(true);
    setNotice("");
    try {
      const allMarketName = `AkShare 沪深全A ${settings.start_date} 至 ${settings.end_date}`;
      const baseAllMarketDataset = allMarket
        ? datasets.find((item) => item.id === settings.dataset_id && item.source === "akshare_all" && item.name === allMarketName)
          || datasets.find((item) => item.source === "akshare_all" && item.name === allMarketName)
        : null;
      let latestDataset = null;
      let batchCount = 0;
      let shouldContinue = false;
      do {
        const response = await fetch(`${API}/datasets/akshare${allMarket ? "/all" : ""}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: abortController?.signal,
          body: JSON.stringify(
            allMarket
              ? {
                  name: allMarketName,
                  start_date: settings.start_date,
                  end_date: settings.end_date,
                  benchmark: settings.benchmark,
                  base_dataset_id: latestDataset?.id || baseAllMarketDataset?.id || null,
                }
              : {
                  name: `AkShare ${settings.start_date} 至 ${settings.end_date}`,
                  symbols: settings.symbols,
                  start_date: settings.start_date,
                  end_date: settings.end_date,
                  benchmark: settings.benchmark,
                }
          ),
        });
        if (!response.ok) throw new Error((await response.json()).detail || "AkShare 同步失败");
        const dataset = await response.json();
        latestDataset = dataset;
        batchCount += 1;
        setDatasets((current) => {
          const consolidatedIds = new Set(dataset._consolidated_dataset_ids || []);
          return [dataset, ...current.filter((item) => item.id !== dataset.id && !consolidatedIds.has(item.id))];
        });
        applyDataset(dataset, dataset.summary.symbols);
        setDatasetQuality({ dataset, summary: dataset.summary, quality_checks: dataset.quality_checks || [] });

        const coverage = dataset._coverage;
        const covered = Number(coverage?.covered || 0);
        const expected = Number(coverage?.expected || 0);
        shouldContinue = allMarket && expected > 0 && covered < expected;
        if (allMarket) {
          setNotice(`自动补齐全A：第 ${batchCount} 批完成，当前覆盖 ${covered}/${expected}；${shouldContinue ? "正在继续下一批…" : "已全部完成"}`);
          if (shouldContinue) await new Promise((resolve) => setTimeout(resolve, 300));
        } else {
          const coverageText = dataset._coverage
            ? `，A股覆盖 ${dataset._coverage.covered}/${dataset._coverage.expected}`
            : "";
          setNotice(dataset.duplicate ? "真实行情快照已存在并已选中" : `真实行情已同步：${dataset.summary.symbol_count} 标的，${dataset.summary.row_count} 行${coverageText}${dataset._sync_note ? `（${dataset._sync_note}）` : ""}`);
        }
      } while (shouldContinue);

      if (allMarket && latestDataset) {
        const coverage = latestDataset._coverage;
        setNotice(`全A自动补齐完成：覆盖 ${coverage?.covered ?? latestDataset.summary.symbol_count}/${coverage?.expected ?? "全部"}，共执行 ${batchCount} 批。`);
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        setNotice("已停止自动补齐全A，当前已完成的批次会保留在数据集中。");
      } else {
        setNotice(`同步失败：${errorMessage(error)}`);
      }
    } finally {
      setSyncing(false);
    }
  };

  const deleteDataset = async (dataset) => {
    if (!dataset) return;
    if (!window.confirm(`删除数据集「${dataset.name}」？本地快照文件也会被删除。`)) return;
    try {
      const response = await fetch(`${API}/datasets/${dataset.id}`, { method: "DELETE" });
      if (!response.ok) throw new Error((await response.json()).detail || "删除失败");
      setDatasets((current) => current.filter((item) => item.id !== dataset.id));
      if (settings.dataset_id === dataset.id) {
        applyDataset(null);
        setDatasetQuality(null);
      }
      setNotice(`数据集已删除：${dataset.name}`);
    } catch (error) {
      setNotice(`删除失败：${errorMessage(error)}`);
    }
  };

  const selectDataset = async (dataset) => {
    if (!dataset) {
      applyDataset(null);
      setDatasetQuality(null);
      return;
    }
    try {
      const response = await fetch(`${API}/datasets/${dataset.id}/preview`);
      if (!response.ok) throw new Error("无法读取数据集");
      const preview = await response.json();
      applyDataset(dataset, preview.summary.symbols);
      setDatasetQuality(preview);
    } catch (error) {
      setNotice(`选择失败：${errorMessage(error)}`);
    }
  };

  const saveStrategy = async () => {
    setSavingStrategy(true);
    try {
      let response;
      if (strategyRecord) {
        response = await fetch(`${API}/strategies/${strategyRecord.id}/versions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ definition: settings.strategy, note: "从可视化编辑器保存" }),
        });
      } else {
        response = await fetch(`${API}/strategies`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ project_id: "default", name: settings.strategy.name, definition: settings.strategy }),
        });
      }
      if (!response.ok) throw new Error((await response.json()).detail || "策略保存失败");
      const saved = await response.json();
      if (strategyRecord) {
        setStrategyRecord((current) => ({ ...current, latest_version: saved }));
        setSettings((current) => ({ ...current, project_id: "default", strategy_id: strategyRecord.id, strategy_version_id: saved.id }));
        setNotice(`策略版本 v${saved.version} 已保存`);
      } else {
        setStrategyRecord(saved);
        setSettings((current) => ({ ...current, project_id: saved.project_id, strategy_id: saved.id, strategy_version_id: saved.latest_version.id }));
        setNotice("策略 v1 已保存");
      }
      setDrawer("settings");
    } catch (error) {
      setNotice(`保存失败：${errorMessage(error)}`);
    } finally {
      setSavingStrategy(false);
    }
  };

  const exportReport = (format = "html") => {
    if (!result?.task_id) {
      setNotice("请先完成一次回测，再导出报告");
      return;
    }
    window.open(`${API}/backtests/${result.task_id}/report.${format}`, "_blank", "noopener,noreferrer");
  };

  useEffect(() => {
    fetch(`${API}/datasets`).then((response) => response.json()).then(setDatasets).catch((error) => logIgnoredError("加载数据集失败", error));
  }, []);

  useEffect(() => {
    if (!securities.length || drawer !== "data") return;
    const controller = new AbortController();
    fetch(`${API}/market/coverage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        start_date: settings.start_date,
        end_date: settings.end_date,
        benchmark: settings.benchmark,
        symbols: settings.symbols,
      }),
    })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("market coverage failed")))
      .then(setMarketCoverage)
      .catch((error) => logIgnoredError("刷新本地行情覆盖失败", error));
    return () => controller.abort();
  }, [drawer, securities.length, settings.start_date, settings.end_date, settings.benchmark, selectedSymbolsKey]);

  useEffect(() => {
    let cancelled = false;
    const pollAllMarketTask = async () => {
      try {
        const response = await fetch(`${API}/datasets/akshare/all/tasks/latest`);
        if (!response.ok) return;
        const task = await response.json();
        if (cancelled) return;
        if (task.status && task.status !== "idle") {
          const terminal = syncingAll && ["completed", "failed", "cancelled"].includes(task.status);
          applyAllMarketSyncTask(task, terminal);
        } else if (!syncingAll) {
          setAllMarketSyncTask(null);
        }
      } catch (error) {
        logIgnoredError("刷新全A同步任务失败", error);
      }
    };
    pollAllMarketTask();
    if (!syncingAll) return () => { cancelled = true; };
    const timer = window.setInterval(pollAllMarketTask, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [syncingAll]);

  useEffect(() => {
    fetch(`${API}/projects/default/strategies`)
      .then((response) => response.json())
      .then((items) => {
        const saved = items[0];
        if (!saved) return;
        setStrategyRecord(saved);
        setSettings((current) =>
          current.strategy_version_id
            ? current
            : {
                ...current,
                project_id: saved.project_id,
                strategy_id: saved.id,
                strategy_version_id: saved.latest_version.id,
                strategy: saved.latest_version.definition,
              }
        );
      })
      .catch((error) => logIgnoredError("加载策略版本失败", error));
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    Promise.all([
      fetch(`${API}/securities`, { signal: controller.signal }).then((response) => response.json()),
      fetch(`${API}/data/status`, { signal: controller.signal }).then((response) => response.json()),
      fetch(`${API}/backtests?limit=1`, { signal: controller.signal }).then((response) => response.json()),
      fetch(`${API}/backtests/compare?limit=6`, { signal: controller.signal }).then((response) => response.json()),
    ])
      .then(async ([securityData, sourceData, history, comparisonData]) => {
        if (!active) return;
        setSecurities(securityData);
        setSource(sourceData);
        setComparisons(comparisonData);
        const latest = history[0];
        if (latest?.status === "completed") {
          const latestStrategy = latest.config.strategy || initialSettings.strategy;
          setSettings((current) => ({
            ...initialSettings,
            ...latest.config,
            project_id: latest.config.project_id || current.project_id,
            strategy_id: latest.config.strategy_id || current.strategy_id,
            strategy_version_id: latest.config.strategy_version_id || current.strategy_version_id,
            strategy: { ...initialSettings.strategy, ...latestStrategy },
          }));
          const response = await fetch(`${API}/backtests/${latest.id}/result`, { signal: controller.signal });
          if (response.ok && active) {
            setResult(await response.json());
            setProgress(1);
          }
        } else {
          setBooting(false);
          runBacktest(controller.signal);
        }
      })
      .catch((error) => {
        if (active && !(error instanceof DOMException && error.name === "AbortError")) {
          console.error("[QuantLab] 初始化本地服务失败", error);
          setSource({ available: false, message: "本地服务尚未启动" });
        }
      })
      .finally(() => {
        if (active) setBooting(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  const metrics = result?.metrics || {};
  const chartData = useMemo(
    () => (result?.equity_curve || []).filter((_, index, items) => index % Math.max(1, Math.floor(items.length / 240)) === 0),
    [result]
  );
  const years = useMemo(() => {
    const table = {};
    for (const item of result?.monthly_returns || []) {
      table[item.year] ||= {};
      table[item.year][item.month] = item.return;
    }
    return Object.entries(table).sort(([a], [b]) => Number(b) - Number(a));
  }, [result]);

  const openNav = (label) => {
    setActiveView(viewForNav(label));
    setDrawer(null);
  };

  const openStrategyEditor = (mode = "trading") => {
    setStrategyEditorMode(mode);
    setDrawer("strategy");
  };

  const openWorkflowStep = (index) => {
    if (index === 0) {
      setActiveView("data");
      setDrawer("data");
    } else if (index === 1) {
      setActiveView("strategy");
      openStrategyEditor("selection");
    } else if (index === 4) {
      setActiveView("results");
      setDrawer(null);
    } else {
      setActiveView("backtest");
      setDrawer("settings");
    }
  };

  const [viewTitle, viewSubtitle] = VIEW_META[activeView] || VIEW_META.backtest;
  const renderMainView = () => {
    if (activeView === "data") {
      return (
        <DataCenterPage
          datasets={datasets}
          securities={securities}
          settings={settings}
          datasetQuality={datasetQuality}
          source={source}
          openData={() => setDrawer("data")}
          onSyncAll={() => syncAkshare("all")}
          onCancelSyncAll={cancelAllMarketSync}
          onRetryFailedAll={retryFailedAllMarketSync}
          syncingAll={syncingAll}
          allMarketSyncTask={allMarketSyncTask}
          marketCoverage={marketCoverage}
          onSelectDataset={selectDataset}
          onDeleteDataset={deleteDataset}
        />
      );
    }
    if (activeView === "strategy") {
      return <StrategyResearchPage settings={settings} setSettings={setSettings} strategyRecord={strategyRecord} openStrategy={openStrategyEditor} />;
    }
    if (activeView === "results") {
      return <ResultsAnalysisPage result={result} settings={settings} running={running} metrics={metrics} chartData={chartData} years={years} comparisons={comparisons} onRun={runBacktest} />;
    }
    if (activeView === "reports") {
      return <ReportsPage result={result} onExportReport={exportReport} />;
    }
    if (activeView === "factors") {
      return <FactorAnalysisPage settings={settings} result={result} openStrategy={() => openStrategyEditor("trading")} />;
    }
    if (activeView === "portfolio") {
      return (
        <PortfolioManagementPage
          settings={settings}
          result={result}
          datasets={datasets}
          securities={securities}
          openSettings={() => setDrawer("settings")}
          openData={() => setDrawer("data")}
        />
      );
    }
    if (activeView === "settings") {
      return <SystemSettingsPage source={source} openSettings={() => setDrawer("settings")} />;
    }
    return <BacktestCenterPage settings={settings} running={running} progress={progress} metrics={metrics} openStep={openWorkflowStep} openSettings={() => setDrawer("settings")} onRun={runBacktest} onCancel={cancelBacktest} />;
  };

  return (
    <div className={`app-shell ${drawer === "settings" ? "with-drawer" : ""}`}>
      <Sidebar
        activeNav={navLabelForView(activeView)}
        openNav={openNav}
        openSettings={() => {
          setActiveView("settings");
          setDrawer(null);
        }}
        serviceOnline={source?.available !== false}
      />
      <main className={`main-view ${activeView === "data" ? "data-main-view" : ""}`}>
        <Topbar
          title={viewTitle}
          subtitle={viewSubtitle}
          settings={settings}
          setSettings={setSettings}
          onExportReport={exportReport}
          canExportReport={Boolean(result?.task_id)}
        />
        {booting ? <LoadingBanner message="正在连接本地服务并加载最近一次回测…" /> : null}
        {running ? <LoadingBanner message={`回测运行中，进度 ${Math.round(progress * 100)}%`} /> : null}
        {renderMainView()}
        <DashboardFooter settings={settings} source={source} />
      </main>
      {drawer === "settings" ? (
        <SettingsDrawer
          settings={settings}
          setSettings={setSettings}
          onRun={runBacktest}
          onCancel={cancelBacktest}
          running={running}
          progress={progress}
          close={() => setDrawer(null)}
        />
      ) : null}
      {drawer === "strategy" ? (
        <StrategyModal
          settings={settings}
          setSettings={setSettings}
          onSave={saveStrategy}
          saving={savingStrategy}
          versionInfo={strategyRecord?.latest_version ? `v${strategyRecord.latest_version.version}` : null}
          mode={strategyEditorMode}
          setMode={setStrategyEditorMode}
          close={() => setDrawer(null)}
        />
      ) : null}
      {drawer === "data" ? (
        <DataDrawer
          settings={settings}
          setSettings={setSettings}
          securities={securities}
          source={source}
          datasets={datasets}
          datasetQuality={datasetQuality}
          onImport={importCsv}
          onImportIndustryHistory={importIndustryHistory}
          importing={importing}
          onSync={() => syncAkshare("selected")}
          onSyncAll={() => syncAkshare("all")}
          onCancelSyncAll={cancelAllMarketSync}
          onRetryFailedAll={retryFailedAllMarketSync}
          syncing={syncing}
          syncingAll={syncingAll}
          allMarketSyncTask={allMarketSyncTask}
          marketCoverage={marketCoverage}
          onSelectDataset={selectDataset}
          onDeleteDataset={deleteDataset}
          close={() => setDrawer(null)}
        />
      ) : null}
      <Toast notice={notice} onClose={() => setNotice("")} />
    </div>
  );
}

export { App };
