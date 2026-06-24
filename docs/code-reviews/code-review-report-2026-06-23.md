# Code Review Report — 2026-06-23

审查范围：`main` 分支全部后端（12 个 Python 文件）和前端（10 个 JSX/JS/CSS 文件）代码。

审查方法：三通道并行审查（后端 + 前端 + 项目整体架构），逐文件通读 + 跨文件对照 + 对照 PRD/README 预期行为。

## 一、总体评估

项目当前是一个**结构清晰、可运行、可复现的本地 A 股日线回测 MVP**。代码组织合理：数据层 → 引擎层 → 持久化层 → API 层 → 报告层 → 任务调度层各司其职。测试覆盖率良好（20 项测试全部通过），回测引擎正确性经过金标准测试验证。

本次三通道审查共发现 **45 项问题**：Critical 2 / High 5 / Medium 11 / Low 27。

---

## 二、严重级发现

### 🔴 Critical (2)

#### C-1: `formatPercent` NaN 崩溃
- **文件**: `frontend/src/formatters.js:2`
- **类别**: Bug
- **描述**: `Number(value || 0)` 对非数字字符串（如 `"N/A"`）返回 `NaN`。`NaN.toFixed(2)` 抛出 `TypeError`，导致组件树崩溃。
- **重现**: `formatPercent("N/A")` → crash
- **修复**:
  ```js
  export const formatPercent = (value, digits = 2) =>
    `${((Number.isFinite(value) ? value : 0) * 100).toFixed(digits)}%`;
  ```

#### C-2: `RateInput` undefined 值崩溃
- **文件**: `frontend/src/components/common.jsx:43`
- **类别**: Bug
- **描述**: `value={(value * 100).toFixed(3)}` 中若 `value` 为 `undefined`，`undefined * 100` = `NaN`，`.toFixed()` 抛出 TypeError。
- **修复**: `value={((value ?? 0) * 100).toFixed(3)}`

### 🟠 High (5)

#### H-1: 前端 fetch 错误处理静默吞掉异常
- **文件**: `frontend/src/App.jsx:37-42, 227-294`
- **类别**: 代码质量 / 可靠性
- **描述**: 多处 `fetch(...).then(...).catch(() => {})` 完全忽略错误。后端不可用时用户仅看到空白页面，Sidebar 的 "本地服务运行中" 实际是硬编码。
- **修复**: 至少 `console.error` 记录，或将 source 状态联动实际连接状态。

#### H-2: 报告 HTML `str.format()` 对花括号敏感
- **文件**: `backend/reports.py:152-162, 169-218`
- **类别**: Bug
- **描述**: `html.escape()` 不转义 `{` `}`，若股票名或原因字段包含花括号，`str.format()` 抛出 `KeyError`。
- **修复**: 改用 f-string 直接拼接或 `string.Template`。

#### H-3: `_enrich_frame_with_security_master` 全量深拷贝
- **文件**: `backend/app.py:355-369`
- **类别**: 性能
- **描述**: `.copy()` 拷贝整个 DataFrame 后仅修改两列。全市场同步时可能产生数 GB 内存开销。
- **修复**: 使用 `frame.assign()` 链式操作或原地修改。

#### H-4: 缺少 `useCallback` 导致全树重渲染
- **文件**: `frontend/src/App.jsx:44-216`
- **类别**: 性能
- **描述**: 15 个事件处理器全部在每次 render 时重新创建，其中 `progress` 是高频状态（回测轮询每 180ms 更新），每次 progress 变化触发所有子组件的 props 引用变化，导致全量重渲染。
- **修复**: 用 `useCallback` 包裹事件处理器。

#### H-5: AbortSignal 竞态——listener 可能在 abort 之后才注册
- **文件**: `frontend/src/App.jsx:51-66`
- **类别**: Bug
- **描述**: `signal.addEventListener("abort", ...)` 注册前未检查 `signal.aborted`。若组件在 fetch 期间卸载，`abort` 事件可能先于 listener 触发，导致服务器上的孤儿任务无法取消。
- **修复**: 注册前先检查 `if (signal?.aborted) return;`

---

## 三、中等级发现 (11)

### 后端

#### M-1: 止损使用未复权收盘价，除权除息时可能误触发
- **文件**: `backend/engine.py:177-178`
- **类别**: 正确性
- **描述**: `holding_return = float(previous["close"]) / position.average_cost - 1` 使用未复权价格。除权时 close 跳变（如 100→50），即使投资者收到等额分红，引擎也会误判为 -50% 触发止损。
- **修复**: `signal_price_mode == "adjusted"` 时跳过 `corporate_action` 当日的止损判断。

#### M-2: `cancel()` 与 `_execute()` 之间的竞态——已完成任务可被覆盖为 cancelled
- **文件**: `backend/tasks.py:36-45, 106-108`
- **类别**: Bug / 并发
- **描述**: `cancel()` 先调用 `repository.request_cancel()`（锁外），再取 event/future（锁内）。若任务在两步之间完成，finally 已清理了 event/future，`cancel_run()` 仍会将 completed 状态覆盖为 cancelled。
- **修复**: `cancel()` 中调用 `cancel_run()` 前重读 run 状态确认仍可取消。

#### M-3: 数据集导入管线重复 normalize DataFrame 5 次
- **文件**: `backend/app.py:372-410`
- **类别**: 性能
- **描述**: `_persist_dataset` 调用链中 `prepare_market_frame` 被执行 5 次（enrich → summary → extract_master → extract_status → quality_checks），每次全量复制和处理 DataFrame。
- **修复**: 在 `_persist_dataset` 顶部调用一次 `prepare_market_frame`，复用处理后的 frame。

#### M-4: PDF 中文字体硬编码 Windows 路径
- **文件**: `backend/reports.py:337-349`
- **类别**: Bug
- **描述**: `C:/Windows/Fonts/msyh.ttc` 等仅在 Windows 有效。Linux/macOS 回退到 Helvetica，CJK 字符显示为空白方块（tofu）。
- **修复**: 搜索跨平台字体路径或内置字体。

#### M-5: `_decode` 对损坏 JSON 无防御
- **文件**: `backend/repository.py:630-648`
- **类别**: 代码质量
- **描述**: `json.loads()` 若遇损坏的 config_json 或 result_json 直接崩溃 API 端点，而非返回降级记录。
- **修复**: try/except JSONDecodeError 返回部分记录。

#### M-6: `_ensure_column` f-string 拼接 SQL
- **文件**: `backend/repository.py:201-203`
- **类别**: 安全性 / 代码卫生
- **描述**: `f"ALTER TABLE {table} ADD COLUMN {column} {kind}"` 虽然当前所有调用使用硬编码常量，但函数签名不阻止未来从外部传入恶意值。
- **修复**: 添加白名单：`assert table in ALLOWED_TABLES`

### 前端

#### M-7: Modal backdrop 使用 onMouseDown 而非 onClick
- **文件**: `frontend/src/components/drawers.jsx:127, 198`
- **类别**: Bug / 无障碍
- **描述**: 文字拖动选择时（mousedown 在内容区，drag 到 backdrop 释放）会意外关闭弹窗。键盘用户无法触发 mousedown。
- **修复**: 改为 `onClick`。

#### M-8: 回测轮询无退避策略
- **文件**: `frontend/src/App.jsx:87`
- **类别**: 性能 / 架构
- **描述**: `setTimeout(resolve, 180)` 硬编码约 5.5 次/秒的轮询，无退避、无 jitter、无最大次数限制。
- **修复**: 实现渐进退避：`delay = Math.min(delay * 1.3, 3000)`。

#### M-9: `error.message` 访问不安全
- **文件**: `frontend/src/App.jsx:90`
- **类别**: Bug
- **描述**: `error.message` 未检查 error 是否为 Error 实例。非 Error throw（如 `throw "string"`）会导致 notice 显示 "undefined"。
- **修复**: `error?.message || String(error)`

#### M-10: `lang="en"` 应用于全中文界面
- **文件**: `frontend/index.html:2`
- **类别**: 无障碍
- **描述**: 屏幕阅读器会用英文规则朗读中文文本，严重损害视障用户体验。
- **修复**: 改为 `lang="zh-CN"`。

#### M-11: Vite 构建工具列入 `dependencies` 而非 `devDependencies`
- **文件**: `frontend/package.json:11-18`
- **类别**: 代码质量
- **描述**: `@vitejs/plugin-react` 和 `vite` 在生产环境中不被使用，应归类为 devDependencies。
- **修复**: 将其移至 `devDependencies`。

---

## 四、低等级发现 (27)

| # | 文件 | 描述 | 类别 |
|---|---|---|---|
| L-1 | backend/engine.py:35-41 | _rsi 用 Python for 循环逐行计算而非 ewm 向量化 | 性能 |
| L-2 | backend/engine.py:157-159 | 小日期范围下进度回调每 tick 触发 | 性能 |
| L-3 | backend/engine.py:327-331 | sharpe 分母为 0 返回 0.0，前端应区分"0"和"不适用" | 代码质量 |
| L-4 | backend/app.py:183-185 | `/api/backtests/run` 内联重复了 `_validate_demo_symbols` 逻辑 | 重复代码 |
| L-5 | backend/app.py:378-388 | 重复数据集上传时静默覆盖已有关联数据 | 设计 |
| L-6 | backend/data.py:692-703 | 双源回退吞掉原始异常，不利调试 | 代码质量 |
| L-7 | backend/data.py:349 | `filter_to_trading_calendar` 内部重复调 `prepare_market_frame` | 性能 |
| L-8 | backend/models.py:60-66 | date 校验用字符串比较而非真实日期解析 | Bug |
| L-9 | backend/tasks.py:111 | shutdown(wait=False) 可能导致写数据库中途退出 | 并发 |
| L-10 | backend/engine.py:88-109 | `_money`(Decimal) 和 `_round`(float) 精度不一致 | 代码质量 |
| L-11 | backend/repository.py:262-269 | `cancel_run` 无条件覆盖已有 error 消息 | 代码质量 |
| L-12 | frontend/App.jsx:46 | 用 `constructor.name === "AbortSignal"` 区分调用方式 | 代码质量 |
| L-13 | frontend/App.jsx:266-283 | 首次启动自动运行回测，用户可能困惑 | UX |
| L-14 | frontend/App.jsx:282 | 自动回测无"运行默认示例"提示 | UX |
| L-15 | frontend/components/dashboard.jsx:19 | Sidebar "本地服务运行中" 为硬编码 | 代码质量 |
| L-16 | frontend/components/dashboard.jsx:50-51 | Workflow 步骤状态全部硬编码 | 代码质量 |
| L-17 | frontend/components/dashboard.jsx:13 | Nav 只有一个按钮可以 active | 代码质量 |
| L-18 | frontend/components/dashboard.jsx:32-34 | 日期范围输入无验证 | Bug |
| L-19 | frontend/components/charts.jsx:63-72 | 月度热力图静默截断 7 年以上数据 | 代码质量 |
| L-20 | frontend/components/charts.jsx:146 | TradesTable key 使用数组 index，过滤时可能冲突 | Bug |
| L-21 | frontend/components/charts.jsx:86-124 | taskId 切换时存在一帧 stale 数据 | Bug |
| L-22 | frontend/components/drawers.jsx:46 | 百分比输入清空（空字符串）静默归零 | 代码质量 |
| L-23 | frontend/appConfig.jsx:11 | VITE_API_BASE 不强制 /api 后缀 | 代码质量 |
| L-24 | frontend/main.jsx:7 | getElementById("root") 无 null 检查 | Bug |
| L-25 | frontend/styles.css:5 | utility class 使用 !important | 代码质量 |
| L-26 | frontend/vite.config.mjs:5-8 | optimizeDeps.include 可能不必要 | 代码质量 |
| L-27 | frontend/package.json | 缺少 Content-Security-Policy | 安全性 |

---

## 五、已验证的修复项（自上次审查以来）

| 自审修复 | 状态 |
|---|---|
| demo seed 不再覆盖 AkShare 上市日期 | ✅ 已通过测试验证 |
| 北交所 920/430 前缀 30% 涨跌停 | ✅ 已通过测试验证 |
| 主板注册制前 IPO 首日 44%/36% 特殊限制 | ✅ 已通过测试验证 |
| 策略风控（止损/止盈/仓位限制） | ✅ 已实现并通过测试 |
| HTML/PDF 报告导出 | ✅ 已实现并通过测试 |
| 交易分页过滤和拒单统计 | ✅ 已实现并通过测试 |
| 策略版本不可变 + 回测引用 | ✅ 已通过测试验证 |

---

## 六、架构评价

### 优点

1. **五层分离**：data → engine → repository → api → reports，每层职责单一
2. **数据不可变**：数据集先固化为 CSV 快照再读入，SHA-256 指纹保证复现
3. **A 股规则覆盖**：T+1、涨跌停、交易单位、佣金、印花税、过户费、滑点、IPO 豁免、ST 状态、长期停牌
4. **协作式取消**：引擎通过 `cancel_check` 回调而非强制 kill 线程
5. **前端延迟加载**：charts 组件 React.lazy + Suspense
6. **ErrorBoundary**：防止渲染异常导致白屏

### 待改进

1. **状态管理**：App 中 15 个 useState，后续功能增多需考虑 Context 或状态库
2. **API 请求去重**：快速操作时无去重/节流
3. **跨平台兼容**：PDF 字体、文件路径等硬编码 Windows
4. **策略隔离**：PRD 要求的用户代码隔离未实现（当前仅支持可视化策略，可控）
5. **前端性能**：缺少 useCallback/useMemo 优化，progress 高频更新触发全量渲染

---

## 七、测试覆盖分析

| 领域 | 覆盖 | 缺口 |
|---|---|---|
| 引擎确定性 | ✅ | — |
| 费用计算 | ✅ | — |
| RSI 计算 | ✅ | — |
| 基准对比 | ✅ | — |
| 涨跌停 4 项 | ✅ | 缺跌停卖出 |
| 复权信号 | ✅ | — |
| 仓位限制 | ✅ | — |
| 止损 | ✅ | 缺止盈独立测试 |
| 异步任务 | ✅ | 缺取消流程测试 |
| 数据集快照 | ✅ | — |
| IPO 豁免 | ✅ | — |
| 数据校验 5 项 | ✅ | — |
| 报告渲染 5 项 | ✅ | — |
| 证券主数据 3 项 | ✅ | — |
| **前端组件** | ❌ | **无前端测试** |

---

## 八、总结

代码整体质量**良好**，适合作为 MVP 继续迭代。20 项后端测试全部通过，前端构建成功。

**本次未发现需要立即回滚的缺陷。** 两个 Critical 问题（formatPercent NaN 和 RateInput undefined）触发条件罕见但应修复。

主要后续工作方向：
1. 修复 C-1/C-2 和 H-1~H-5（高优先）
2. 引入前端测试框架（如 Vitest + Testing Library）
3. 补上前端 useCallback/useMemo 性能优化
4. 跨平台兼容（PDF 字体、文件路径）
5. 引入真实除权数据后验证 M-1（止损误触发）
