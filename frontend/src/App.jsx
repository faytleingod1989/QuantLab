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

function DataCenterPage({ datasets, securities, settings, datasetQuality, source, openData }) {
  const selectedDataset = datasets.find((item) => item.id === settings.dataset_id);
  return (
    <section className="view-page">
      <div className="view-hero">
        <div>
          <span>DATA CENTER</span>
          <h2>管理回测数据，而不是只弹一个选择框</h2>
          <p>这里集中展示行情快照、证券主表和质量检查；需要导入、同步或删除时再进入数据管理。</p>
        </div>
        <button className="primary" onClick={openData}>打开数据管理</button>
      </div>
      <div className="page-card-grid">
        <PageCard title="数据快照" value={`${datasets.length} 个`} note={selectedDataset ? `当前：${selectedDataset.name}` : "当前使用演示数据"} />
        <PageCard title="股票池主表" value={`${securities.length} 只`} note="支持沪深 A 股，北交所暂不纳入全 A 同步" />
        <PageCard title="数据源状态" value={source?.akshare_available ? "AkShare 可用" : "本地/演示"} note={source?.message || "等待数据源检测"} />
        <PageCard title="质量检查" value={`${datasetQuality?.quality_checks?.length || 0} 项`} note={settings.dataset_id ? "固定快照质量记录" : "演示数据暂无固定检查"} />
      </div>
      <div className="view-panel">
        <div className="panel-head"><b>最近数据集</b><span>可在数据管理中删除旧快照</span></div>
        <div className="mini-list">
          {datasets.length ? datasets.slice(0, 6).map((dataset) => (
            <span key={dataset.id}><b>{dataset.name}</b><small>{dataset.symbol_count} 标的 · {dataset.row_count} 行 · {dataset.start_date} — {dataset.end_date}</small></span>
          )) : <em>暂无固定数据快照，可打开数据管理同步沪深全 A 或导入 CSV。</em>}
        </div>
      </div>
    </section>
  );
}

function StrategyResearchPage({ settings, strategyRecord, openStrategy }) {
  const buy = settings.strategy.buy_conditions?.[0];
  const sell = settings.strategy.sell_conditions?.[0];
  return (
    <section className="view-page">
      <div className="view-hero">
        <div>
          <span>STRATEGY LAB</span>
          <h2>{settings.strategy.name}</h2>
          <p>策略研究页现在作为独立主视图承载策略概览，编辑动作仍通过可视化策略编辑器完成。</p>
        </div>
        <button className="primary" onClick={openStrategy}>编辑策略</button>
      </div>
      <div className="page-card-grid">
        <PageCard title="版本状态" value={strategyRecord?.latest_version ? `v${strategyRecord.latest_version.version}` : "未保存"} note="保存后会形成不可变策略版本" />
        <PageCard title="买入条件" value={buy ? buy.indicator : "未配置"} note={buy ? `${buy.operator} · ${buy.left}/${buy.right}` : ""} />
        <PageCard title="卖出条件" value={sell ? sell.indicator : "未配置"} note={sell ? `${sell.operator} · ${sell.left}/${sell.right}` : ""} />
        <PageCard title="信号价格" value={settings.signal_price_mode === "adjusted" ? "复权收盘" : "未复权收盘"} note="撮合仍使用未复权价格" />
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
        <PageCard title="股票数量" value={`${settings.symbols.length} 只`} note={settings.dataset_id ? "来自固定数据快照" : "来自当前股票池"} />
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
          <button className="ghost" onClick={() => onExportReport("html")} disabled={!result?.task_id}>HTML 报告</button>
          <button className="primary" onClick={() => onExportReport("pdf")} disabled={!result?.task_id}>PDF</button>
        </div>
      </div>
      <div className="page-card-grid">
        <PageCard title="最近任务" value={result?.task_id ? result.task_id.slice(0, 8) : "暂无"} note={result ? result.period ? `${result.period.start} — ${result.period.end}` : "已完成回测" : "先运行一次回测后再导出"} />
        <PageCard title="HTML" value="在线报告" note="含指标卡、权益曲线和交易记录" />
        <PageCard title="PDF" value="离线归档" note="适合投研复盘和分享" />
        <PageCard title="Markdown" value="后端可用" note="后续可在页面补下载入口" />
      </div>
    </section>
  );
}

function RoadmapPage({ kind }) {
  const copy = kind === "factors"
    ? ["因子分析", "这里将承载因子库、因子筛选、IC/分层回测和信号解释。"]
    : ["组合管理", "这里将承载组合约束、持仓、行业暴露和调仓计划。"];
  return (
    <section className="view-page">
      <div className="view-hero">
        <div>
          <span>ROADMAP</span>
          <h2>{copy[0]}</h2>
          <p>{copy[1]}</p>
        </div>
      </div>
      <div className="page-card-grid">
        <PageCard title="当前状态" value="规划中" note="菜单已成为真实页面，不再只是 toast 提示" />
        <PageCard title="下一步" value="补业务模块" note="根据你的优先级继续开发" />
        <PageCard title="数据依赖" value="复用回测数据集" note="全 A 快照可作为后续输入" />
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
  const [strategyRecord, setStrategyRecord] = useState(null);
  const [savingStrategy, setSavingStrategy] = useState(false);
  const [booting, setBooting] = useState(true);
  const [comparisons, setComparisons] = useState([]);

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

  const syncAkshare = async (scope = "selected") => {
    const allMarket = scope === "all";
    allMarket ? setSyncingAll(true) : setSyncing(true);
    setNotice("");
    try {
      const response = await fetch(`${API}/datasets/akshare${allMarket ? "/all" : ""}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          allMarket
            ? {
                name: `AkShare 沪深全A ${settings.start_date} 至 ${settings.end_date}`,
                start_date: settings.start_date,
                end_date: settings.end_date,
                benchmark: settings.benchmark,
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
      setDatasets((current) => [dataset, ...current.filter((item) => item.id !== dataset.id)]);
      applyDataset(dataset, dataset.summary.symbols);
      setDatasetQuality({ dataset, summary: dataset.summary, quality_checks: dataset.quality_checks || [] });
      setNotice(dataset.duplicate ? "真实行情快照已存在并已选中" : `真实行情已同步：${dataset.summary.symbol_count} 标的，${dataset.summary.row_count} 行`);
    } catch (error) {
      setNotice(`同步失败：${errorMessage(error)}`);
    } finally {
      allMarket ? setSyncingAll(false) : setSyncing(false);
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

  const openWorkflowStep = (index) => {
    if (index === 0) {
      setActiveView("data");
      setDrawer("data");
    } else if (index === 1) {
      setActiveView("strategy");
      setDrawer("strategy");
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
      return <DataCenterPage datasets={datasets} securities={securities} settings={settings} datasetQuality={datasetQuality} source={source} openData={() => setDrawer("data")} />;
    }
    if (activeView === "strategy") {
      return <StrategyResearchPage settings={settings} strategyRecord={strategyRecord} openStrategy={() => setDrawer("strategy")} />;
    }
    if (activeView === "results") {
      return <ResultsAnalysisPage result={result} settings={settings} running={running} metrics={metrics} chartData={chartData} years={years} comparisons={comparisons} onRun={runBacktest} />;
    }
    if (activeView === "reports") {
      return <ReportsPage result={result} onExportReport={exportReport} />;
    }
    if (activeView === "factors" || activeView === "portfolio") {
      return <RoadmapPage kind={activeView} />;
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
      <main className="main-view">
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
          syncing={syncing}
          syncingAll={syncingAll}
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
