import { lazy, Suspense, useEffect, useMemo, useState } from "react";

import { API, initialSettings } from "./appConfig";
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

function App() {
  const [settings, setSettings] = useState(initialSettings);
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentTaskId, setCurrentTaskId] = useState(null);
  const [drawer, setDrawer] = useState("settings");
  const [securities, setSecurities] = useState([]);
  const [source, setSource] = useState(null);
  const [notice, setNotice] = useState("");
  const [datasets, setDatasets] = useState([]);
  const [importing, setImporting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [strategyRecord, setStrategyRecord] = useState(null);
  const [savingStrategy, setSavingStrategy] = useState(false);
  const [booting, setBooting] = useState(true);

  const runBacktest = async (candidateSignal) => {
    const signal = candidateSignal?.constructor?.name === "AbortSignal" ? candidateSignal : undefined;
    let taskId = null;
    const cancelSubmittedTask = () => {
      if (taskId) fetch(`${API}/backtests/${taskId}/cancel`, { method: "POST" }).catch(() => {});
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

      while (true) {
        const statusResponse = await fetch(`${API}/backtests/${task.id}`, { signal });
        if (!statusResponse.ok) throw new Error("无法读取回测任务状态");
        const status = await statusResponse.json();
        setProgress(status.progress || 0);
        if (status.status === "completed") {
          const resultResponse = await fetch(`${API}/backtests/${task.id}/result`, { signal });
          if (!resultResponse.ok) throw new Error("无法读取回测结果");
          setResult(await resultResponse.json());
          setNotice("回测已完成，结果已持久化");
          break;
        }
        if (status.status === "failed" || status.status === "cancelled") {
          throw new Error(status.error || `任务状态: ${status.status}`);
        }
        await new Promise((resolve) => setTimeout(resolve, 180));
      }
    } catch (error) {
      if (error.name !== "AbortError") setNotice(`回测未完成：${error.message}`);
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
      setNotice(`取消失败：${error.message}`);
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
      setNotice(dataset.duplicate ? "该数据集已存在并已选中" : `数据集已导入并选中：${dataset.summary.row_count} 行`);
    } catch (error) {
      setNotice(`导入失败：${error.message}`);
    } finally {
      setImporting(false);
      event.target.value = "";
    }
  };

  const syncAkshare = async () => {
    setSyncing(true);
    setNotice("");
    try {
      const response = await fetch(`${API}/datasets/akshare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: `AkShare ${settings.start_date} 至 ${settings.end_date}`,
          symbols: settings.symbols,
          start_date: settings.start_date,
          end_date: settings.end_date,
          benchmark: settings.benchmark,
        }),
      });
      if (!response.ok) throw new Error((await response.json()).detail || "AkShare 同步失败");
      const dataset = await response.json();
      setDatasets((current) => [dataset, ...current.filter((item) => item.id !== dataset.id)]);
      applyDataset(dataset, dataset.summary.symbols);
      setNotice(dataset.duplicate ? "真实行情快照已存在并已选中" : `真实行情已同步：${dataset.summary.row_count} 行`);
    } catch (error) {
      setNotice(`同步失败：${error.message}`);
    } finally {
      setSyncing(false);
    }
  };

  const selectDataset = async (dataset) => {
    if (!dataset) {
      applyDataset(null);
      return;
    }
    try {
      const response = await fetch(`${API}/datasets/${dataset.id}/preview`);
      if (!response.ok) throw new Error("无法读取数据集");
      const preview = await response.json();
      applyDataset(dataset, preview.summary.symbols);
    } catch (error) {
      setNotice(`选择失败：${error.message}`);
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
      setNotice(`保存失败：${error.message}`);
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
    fetch(`${API}/datasets`).then((response) => response.json()).then(setDatasets).catch(() => {});
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
      .catch(() => {});
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    Promise.all([
      fetch(`${API}/securities`, { signal: controller.signal }).then((response) => response.json()),
      fetch(`${API}/data/status`, { signal: controller.signal }).then((response) => response.json()),
      fetch(`${API}/backtests?limit=1`, { signal: controller.signal }).then((response) => response.json()),
    ])
      .then(async ([securityData, sourceData, history]) => {
        if (!active) return;
        setSecurities(securityData);
        setSource(sourceData);
        const latest = history[0];
        if (latest?.status === "completed") {
          setSettings((current) => ({
            ...latest.config,
            project_id: latest.config.project_id || current.project_id,
            strategy_id: latest.config.strategy_id || current.strategy_id,
            strategy_version_id: latest.config.strategy_version_id || current.strategy_version_id,
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
        if (active && error.name !== "AbortError") setSource({ message: "本地服务尚未启动" });
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
    if (label === "数据中心") setDrawer("data");
    else if (label === "策略研究") setDrawer("strategy");
    else if (label === "回测中心" || label === "结果分析") setDrawer("settings");
    else setNotice(`${label}将在后续版本开放`);
  };

  const openWorkflowStep = (index) => {
    if (index === 0) setDrawer("data");
    else if (index === 1) setDrawer("strategy");
    else setDrawer("settings");
  };

  return (
    <div className="app-shell">
      <Sidebar openNav={openNav} openSettings={() => setDrawer("settings")} />
      <main className="main-view">
        <Topbar
          settings={settings}
          setSettings={setSettings}
          onExportReport={exportReport}
          canExportReport={Boolean(result?.task_id)}
        />
        <Workflow settings={settings} openStep={openWorkflowStep} />
        <ReportTitle result={result} settings={settings} running={running} onRun={runBacktest} />
        {booting ? <LoadingBanner message="正在连接本地服务并加载最近一次回测…" /> : null}
        {running ? <LoadingBanner message={`回测运行中，进度 ${Math.round(progress * 100)}%`} /> : null}
        <MetricsStrip metrics={metrics} />
        <Suspense fallback={<ChartLoading />}>
          <DashboardCharts chartData={chartData} result={result} settings={settings} metrics={metrics} years={years} taskId={result?.task_id} />
        </Suspense>
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
          close={() => setDrawer("settings")}
        />
      ) : null}
      {drawer === "data" ? (
        <DataDrawer
          settings={settings}
          setSettings={setSettings}
          securities={securities}
          source={source}
          datasets={datasets}
          onImport={importCsv}
          importing={importing}
          onSync={syncAkshare}
          syncing={syncing}
          onSelectDataset={selectDataset}
          close={() => setDrawer("settings")}
        />
      ) : null}
      <Toast notice={notice} onClose={() => setNotice("")} />
    </div>
  );
}

export { App };
