# Watchlist Intelligence Center 实施计划

> Version: v1.0
> Status: Ready for Execution
> 依据: 《Watchlist 智能监控 页面重构设计方案》（docs/design/ Watchlist 智能监控 页面重构设计方案.md）
> 范围: frontend/（React + Vite）、langgraph/（FastAPI + LangGraph）、postgres/init/（DDL）、mcp-news

---

# 1. 现状盘点

## 1.1 Frontend（frontend/src）

| 类别 | 现状 | 与 Watchlist Intelligence Center 的关系 |
|---|---|---|
| 路由 | `app/router.tsx` 已注册 `/watchlist` 路由，lazy 加载 WatchlistPage | 路由无需新增，但需考虑是否拆分子路由（`/watchlist/:stockCode` 详情） |
| WatchlistPage | `app/pages/WatchlistPage.tsx`：845 行单文件，5 个 Tab（自选股/监控配置/今日重点/每日报告/通知），手动管理状态（useState + useEffect），无 React Query 缓存层 | Phase 1 在此基础上升级为 Today Overview 优先布局 |
| services 层 | `services/watchlist.ts`：6 组 API（Watchlist CRUD / Config / Events / Reports / Alerts / Groups + Stock Lookup），类型定义完整（WatchlistItem / WatchlistEvent / DailyReport / WebAlert / GroupInfo / CompanyLookup） | 直接扩展，新增 Overview / History / Timeline / AI Summary 端点 |
| 导航 | `components/layout/Sidebar.tsx`：Watchlist 使用 Star 图标，label 为 "Watchlist" | Phase 1 考虑改名为 "Intelligence" 或 "Watchlist"，副标题同步更新 |
| 可复用组件 | `components/ui/`：tabs / card / badge / button / combobox / dialog / windowed-dialog / select / input / skeleton / table / tooltip / scroll-area / progress / separator | 全部直接复用 |
| 可复用组件（业务） | `components/news/`：NewsListTab / EventsTab / ImpactTab / TimelineTab / ArticleDetailDialog；`components/common/EmptyState.tsx` | News 组件可拆出共用；EmptyState 用于空态降级 |
| 可复用模式 | AgentsPage → AgentDetailPage（路由拆分 + lazy load）、KnowledgePage（多 Tab + 卡片网格 + 任务面板）是成熟的范式参考 | Watchlist 详情 Drawer / 子页面可套用此模式 |
| 外部 API 服务 | `services/news.ts`：fetchNewsArticles / fetchNewsTimeline / fetchNewsImpact / fetchNewsEvents / fetchEventImpact / triggerNewsCollect；`services/research.ts`：fetchResearch / fetchResearchDetail；`services/reports.ts` | 新闻 Timeline / Impact 聚合可直接用于 Stock Detail；Research API 用于"加入研究"集成 |

## 1.2 LangGraph 后端（langgraph/，端口 8100）

| 模块 | 现状 |
|---|---|
| Watchlist API | `api/watchlist.py`：11 个端点（CRUD / groups / lookup / run / config / reports / events / alerts），直接操作 `watchlist` schema 表，无缓存层 |
| 监控引擎 | `monitoring/watchlist_monitor.py`：主流程（加载自选股 → 复用 news 采集管线逐股采集 → 查询当日文章/事件 → 幂等写入 watchlist_events → 告警 → 日报），**无并发控制**（逐股串行采集，25 只股票约需 10-15 分钟） |
| 告警引擎 | `monitoring/watchlist_alerts.py`：Web 通知（write DB）+ 通用 Webhook（httpx POST），仅 importance≥4 触发告警 |
| 日报引擎 | `monitoring/watchlist_report.py`：从当日 watchlist_events 聚合 Markdown，按 report_date 幂等 upsert |
| 调度器 | `runtime/scheduler.py`：watchlist_daily job（按 watchlist_settings 的 schedule_time/auto_enabled 动态注册/移除），支持 `resync_watchlist_job()` 热更新 |
| News API | `api/news.py`：8 个端点（articles / article detail / events / event impact / impact analysis / timeline / collect / sources），含实体聚合、事件影响分析、时间线——均可直接被 Watchlist 复用 |
| Research API | `api/research.py`：2 个端点（list / detail），查询 `research_tasks` 表——Watchlist "加入研究"流程可复用 |
| Reports API | `api/reports.py`：大师分析报告列表/详情/触发分析——Watchlist 日报导出/分享功能可复用 |
| Knowledge Graph | `storage/knowledge/age.py`：Apache AGE 图存储（investment_knowledge_graph，Entity/Relation/Event 顶点与边）——Stock Detail 的 Knowledge Graph 面板可直接查询 AGE |
| MCP News | `mcp-news/server/`：7 个工具（端口 8201），独立新闻查询层——Watchlist 无需直接依赖，通过 langgraph API 间接消费 |

## 1.3 数据库（postgres/init/）

| 表 | 状态 | 复用价值 |
|---|---|---|
| `watchlist.watchlist`（11-watchlist-schema.sql） | 已存在：stock_code / stock_name / market / industry / group_name / tags / enabled | 基础 CRUD 不动 |
| `watchlist.watchlist_events`（11） | 已存在：importance / sentiment / confidence / impact_horizon / summary / source_type / article_title / article_url / source_name / event_time / news_id / event_id | Today Timeline / Events 数据源，需新增 AI 评分字段 |
| `watchlist.daily_watchlist_report`（11） | 已存在：report_date / title / content / summary，幂等 upsert | Daily Report 数据源，需扩展 summary JSON 结构 |
| `watchlist.watchlist_alerts`（11） | 已存在：level / channel / delivered / read / event_id | Alerts 面板数据源，基本够用 |
| `watchlist.watchlist_settings`（11） | 已存在：schedule_time / auto_enabled / webhook_url（单行） | 需扩展：monitoring scopes（JSONB）、AI features toggles、frequency、notification channels |
| `news.articles` / `news.events` / `news.entities` / `news.relations`（09-news-schema.sql） | 已存在，为 watchlist_events 的上游数据源 | 可直接 JOIN 查询，为 Stock Detail 提供多维度数据 |
| `company_basic` | 已存在（import_company_basic.py 导入），提供 symbol/company_name/exchange/industry | Stock Lookup 已在使用 |
| `research_tasks`（01-init.sql §4.7） | 已存在，记录研究任务历史 | "加入研究"流程写此表 |

⚠️ **注意**：Docker PostgreSQL init 脚本**仅首次初始化生效**（已验证的项目坑），存量 DB 的表结构变更必须用**幂等的独立迁移文件**（`CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`）。

## 1.4 历史遗留与复用评估

| 遗留能力 | 评估结论 |
|---|---|
| WatchlistPage 单文件 845 行 | **必须拆分**：拆为 TodayOverview / AlertsPanel / WatchlistGrid / StockDetailDrawer / ConfigPanel / ReportPanel / HistoryPanel 7 个独立组件，主页面仅做布局编排 |
| 手动状态管理（useState + useEffect） | **引入 React Query**：遵循 React Query 缓存键隔离原则，为每组数据（overview / events / alerts / report / history）建独立 queryKey，按需 invalidate |
| 监控引擎串行采集 | **优化但不阻塞前端**：Phase 2 引入 asyncio.gather 并发采集（单股超时 120s），前端只管展示 |
| 告警仅 importance≥4 触发 | **保留阈值，配置化**：将阈值写入 watchlist_settings 可配置 |
| Scheduler watchlist_daily job | **复用并扩展**：增加盘中增量采集 job（每 30 分钟对 enabled 股票执行轻量采集） |

---

# 2. 差距分析

对照设计方案第 3-13 节的目标能力逐项对比：

| # | 目标能力 | 设计方案节 | 现状评估 | 差距 |
|---|---|---|---|---|
| 1 | Today Overview（今日概览卡片） | §4 | 🔴 缺失 | 无 `/api/watchlist/overview` 端点；页面首屏是"添加自选股"表单而非概览 |
| 2 | Today's Timeline（今日时间线） | §5 | 🟡 部分具备："今日重点" Tab 按 importance 展示事件 | 无时间线样式（带时间戳的事件流）、无影响行业/竞品标签、布局被 Tab 隐藏 |
| 3 | Alerts（AI 告警面板） | §6 | 🟡 部分具备："通知" Tab 含 level/read 标记 | 缺优先级颜色标识（🔴🟠🟡）、缺"查看详情/加入日报/加入研究"操作入口、缺未读计数徽标 |
| 4 | Watchlist Cards（股票卡片） | §7 | 🟡 部分具备：简单行列表 | 缺 AI 评分、今日事件数/新闻数/公告数统计、最近更新时间、星级评分、卡片化布局 |
| 5 | Stock Detail（股票详情 Drawer） | §8 | 🟡 部分具备：WindowedDialog 展示事件详情+文章正文 | 缺 Today/News/Announce/Research/Industry/Competitor 多维度统计、AI Summary、Knowledge Graph 可视化 |
| 6 | Monitoring Configuration（监控配置） | §9 | 🟡 部分具备：schedule_time + auto_enabled | 缺监控维度勾选（新闻/公告/财报/行业/政策/社交媒体/海外/竞品）、更新频率选择（实时/每小时/每日）、AI 功能开关（摘要/日报/邮件/Webhook） |
| 7 | Daily Report（日报） | §10 | 🟡 部分具备：Markdown 全文展示 | 缺 AI Summary 摘要卡、导出 PDF / 发送邮箱 / 生成研究报告操作按钮 |
| 8 | History（历史监控） | §11 | 🔴 缺失 | 无事件趋势图、无按日/周/月聚合统计、无告警历史统计 |
| 9 | 生命周期可视化 | §12 | 🔴 缺失 | 无"添加股票 → 监控 → 采集 → 分析 → 告警 → 日报 → 研究"流程可视化 |
| 10 | Research Agent 集成 | §14 | 🔴 缺失 | 无"加入研究"触发入口 |
| 11 | Knowledge Graph 集成 | §8 | 🔴 缺失 | AGE 图已有数据，但 Watchlist 页面未展示 |

**结论**：前端需要从"单文件 Tas 驱动"重构为"Today Overview 优先的多面板布局"；后端需要新增 Overview / History / AI Summary 三个聚合端点；数据库需要扩展 settings 表；5 项"部分具备"是扩展，6 项"缺失"是新建。

---

# 3. 实施计划

> 依赖链总览：
> `DB 迁移 → Overview/History API → 前端布局重构（Today Overview 优先 + 组件拆分）` →（Phase 1 收尾）→ `Stock Detail 增强（AI Summary + Knowledge Graph）→ Config 扩展` →（Phase 2）→ `Research Agent 集成 → 导出能力` →（Phase 3）→ `盘中增量采集 → 高级通知`（Phase 4）

## Phase 1：页面布局重构 + 核心 API（Overview / History / Stock Detail 基础）

### P1-1 数据库迁移（新建幂等迁移文件）

新建 `postgres/init/14-watchlist-v2.sql`：

```sql
-- 1. watchlist.watchlist 扩展：AI 评分与统计冗余
ALTER TABLE watchlist.watchlist 
  ADD COLUMN IF NOT EXISTS ai_score INT DEFAULT 0;              -- 0-100
ALTER TABLE watchlist.watchlist 
  ADD COLUMN IF NOT EXISTS last_event_at TIMESTAMPTZ;           -- 最近事件时间
ALTER TABLE watchlist.watchlist 
  ADD COLUMN IF NOT EXISTS today_event_count INT DEFAULT 0;     -- 今日事件数（定时刷新）
ALTER TABLE watchlist.watchlist 
  ADD COLUMN IF NOT EXISTS today_news_count INT DEFAULT 0;      -- 今日新闻数（定时刷新）

-- 2. watchlist.watchlist_settings 扩展：监控维度 + AI 功能开关
ALTER TABLE watchlist.watchlist_settings 
  ADD COLUMN IF NOT EXISTS monitoring_scopes JSONB DEFAULT '["news","announcement","earnings","industry","policy"]';
ALTER TABLE watchlist.watchlist_settings 
  ADD COLUMN IF NOT EXISTS ai_summary_enabled BOOLEAN DEFAULT true;
ALTER TABLE watchlist.watchlist_settings 
  ADD COLUMN IF NOT EXISTS daily_report_enabled BOOLEAN DEFAULT true;
ALTER TABLE watchlist.watchlist_settings 
  ADD COLUMN IF NOT EXISTS email_enabled BOOLEAN DEFAULT false;
ALTER TABLE watchlist.watchlist_settings 
  ADD COLUMN IF NOT EXISTS email_address TEXT;
ALTER TABLE watchlist.watchlist_settings 
  ADD COLUMN IF NOT EXISTS update_frequency TEXT DEFAULT 'daily';  -- 'realtime'/'hourly'/'daily'
ALTER TABLE watchlist.watchlist_settings 
  ADD COLUMN IF NOT EXISTS alert_threshold INT DEFAULT 4;          -- 告警重要性阈值

-- 3. 监控历史聚合表（每日一条，缓存统计）
CREATE TABLE IF NOT EXISTS watchlist.watchlist_daily_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stat_date DATE NOT NULL UNIQUE,
    total_stocks INT NOT NULL DEFAULT 0,
    total_events INT NOT NULL DEFAULT 0,
    high_priority_events INT NOT NULL DEFAULT 0,   -- importance>=4
    total_alerts INT NOT NULL DEFAULT 0,
    critical_alerts INT NOT NULL DEFAULT 0,
    ai_reports_generated INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_stats_date ON watchlist.watchlist_daily_stats(stat_date DESC);

COMMENT ON TABLE watchlist.watchlist_daily_stats IS 'Watchlist 每日监控统计快照';
```

- **验收标准**：在存量 DB 上执行不报错、可重复执行；`docker compose exec postgres psql` 验证新列/表存在。
- **注意**：与 Agent Center 实施计划 P1-1 相同的迁移先例——需对运行中容器手动执行一次 `psql -f`。

### P1-2 Overview API（后端）

修改 `langgraph/api/watchlist.py`，新增：

1. `GET /api/watchlist/overview`：返回今日概览聚合数据

```python
# 聚合维度（无需新建表，实时查询）
{
  "today": "2026-08-05",
  "monitored_stocks": 24,            # COUNT watchlist WHERE enabled=true
  "today_events": 18,               # COUNT watchlist_events WHERE created_at::date = today
  "high_risk_events": 2,            # COUNT WHERE importance >= alert_threshold
  "ai_reports": 5,                  # COUNT daily_watchlist_report WHERE report_date = today
  "unread_alerts": 8,               # COUNT watchlist_alerts WHERE read=false AND channel='web'
  "active_stocks_change": "+2",     # 较昨日变化
  "events_change": "+5"             # 较昨日变化
}
```

2. `GET /api/watchlist/history?days=30`：返回历史统计趋势

```python
{
  "stats": [
    {"date": "2026-08-05", "total_events": 18, "high_priority": 2, "alerts": 3},
    ...
  ],
  "trend_summary": "事件量较上周上升 12%"
}
```

- **数据源**：优先读 `watchlist_daily_stats` 表，无则实时聚合 `watchlist_events` 回退。
- **验收标准**：curl 返回今日实时数据与昨日对比值；history 30 天各维度可查。

### P1-3 前端布局重构：Today Overview 优先

**重构 `frontend/src/app/pages/WatchlistPage.tsx`**（主页面仅做布局）:

1. **引入 React Query**：新建 `frontend/src/hooks/useWatchlistOverview.ts`、`useWatchlistEvents.ts`、`useWatchlistAlerts.ts`、`useWatchlistReport.ts`、`useWatchlistHistory.ts`，各自使用独立 queryKey。
2. **拆除手动状态管理**：移除 `useState` + `useEffect` 数据加载，替换为 `useQuery` / `useMutation`（遵循 React Query 缓存键隔离原则）。
3. **页面结构调整**：从"5 个 Tabs 平铺"改为"6 个区域纵向布局"（对齐设计方案 §3）：

```
┌─────────────────────────────────────┐
│ ① Today Overview（统计卡片栏）       │
│ 24 Stocks │ 18 Events │ 2 Risks │   │
│ 5 AI Reports │ 8 Unread              │
└─────────────────────────────────────┘

┌────────────────┬────────────────────┐
│ ② Timeline     │ ③ Alerts           │
│ （今日重点事件） │ （AI 风险告警）      │
└────────────────┴────────────────────┘

┌─────────────────────────────────────┐
│ ④ Watchlist（股票卡片网格）          │
│ 每行：名称 │ AI评分 │ 事件数 │ ...  │
│ 操作：查看详情 │ 暂停 │ 删除          │
└─────────────────────────────────────┘

┌────────────────┬────────────────────┐
│ ⑤ Config       │ ⑥ Report           │
│ （监控配置）    │ （每日报告）         │
└────────────────┴────────────────────┘

┌─────────────────────────────────────┐
│ ⑦ History（近30天趋势图 + 统计）     │
└─────────────────────────────────────┘
```

4. **组件拆分**：将 845 行单文件拆为独立文件：

| 组件文件 | 职责 | 来源 |
|---|---|---|
| `components/watchlist/TodayOverview.tsx` | 5 个统计卡片（现有 DashboardPage 卡片样式可复用） | 新建 |
| `components/watchlist/TodayTimeline.tsx` | 事件流时间线（现有 events Tab 升级） | 重构 |
| `components/watchlist/AlertsPanel.tsx` | 告警列表 + 未读标记 + 操作按钮 | 重构 |
| `components/watchlist/WatchlistGrid.tsx` | 股票卡片网格（现有列表升级为卡片） | 重构 |
| `components/watchlist/StockDetailDrawer.tsx` | 点击股票后的详情 Drawer（含 Tab） | Phase 1 基础，Phase 2 增强 |
| `components/watchlist/MonitoringConfig.tsx` | 监控维度/频率/AI 功能配置 | 重构 |
| `components/watchlist/DailyReport.tsx` | 日报预览 + 导出操作 | 重构 |
| `components/watchlist/HistoryPanel.tsx` | 历史趋势图 + 统计表 | 新建 |
| `components/watchlist/AddStockDialog.tsx` | 添加股票表单（独立弹窗，不再放首屏） | 重构 |
| `components/watchlist/WatchlistSkeleton.tsx` | 加载骨架屏 | 新建 |

5. **侧栏更新**：`Sidebar.tsx` 中 label 改为 "Intelligence"，图标可保持 Star 或改为 `BellDot` / `Eye`。
6. **路由**：`/watchlist` 保持不变；可选新增 `/watchlist/:stockCode` 深度链接（Phase 2）。

- **验收标准**：首屏不再是"添加股票"表单，而是 Today Overview 5 个统计卡片；各区域独立 queryKey 互不干扰；加载态与空态完整。

### P1-4 TodayOverview 组件（前端）

1. 调用 `/api/watchlist/overview`（queryKey: `['watchlist', 'overview']`）。
2. 5 个卡片水平排列：Monitored Stocks / Today Events / High Risk / AI Reports / Unread Alerts。
3. 每个卡片含数值 + 较昨日变化箭头（↑/↓）。
4. 加载态用 `Skeleton`，空态用 `EmptyState`。

- **验收标准**：卡片数据与后端实时一致；刷新按钮可手动 invalidate。

### P1-5 TodayTimeline 组件（前端，重构现有"今日重点"Tab）

1. 调用 `/api/watchlist/events?importance=3&limit=50`（queryKey: `['watchlist', 'events']`）。
2. 时间线样式：左侧时间轴 + 右侧事件卡片（股票名 / 重要性星级 / 影响标签 / 摘要）。
3. 高重要性事件（≥4）卡片高亮边框。
4. 点击事件 → 打开 `StockDetailDrawer` 或现有事件详情弹窗。
5. 影响行业/竞品标签 Badge。

- **验收标准**：时间线可滚动；事件按时间倒序；点击事件可查看详情。

### P1-6 AlertsPanel 组件（前端，重构现有"通知"Tab）

1. 调用 `/api/watchlist/alerts?unread_only=false&limit=50`（queryKey: `['watchlist', 'alerts']`）。
2. 级别颜色：🔴 critical / 🟠 important / 🟡 info。
3. 未读标记 + 批量已读 / 全部已读。
4. 每条告警增加操作入口：
   - **查看详情** → 打开关联事件/文章详情弹窗
   - **加入日报** → `POST /api/watchlist/alerts/{id}/add-to-report`（Phase 1 暂为客户端标记，Phase 2 落库）
   - **加入研究** → 调 Research API 创建研究任务（Phase 2）

- **验收标准**：未读告警有视觉区分；一键全部已读生效。

### P1-7 WatchlistGrid 组件（前端，重构现有"自选股"Tab）

1. 从简单行列表 → 卡片网格（2-3 列，对应现有 `Card` + `CardContent`）。
2. 每张卡片展示：
   - 股票名称 + 代码 + 市场
   - AI 评分（ai_score，圆形进度或数字，Phase 1 显示占位值 0）
   - 今日事件数 / 新闻数 / 公告数（today_event_count / today_news_count）
   - 最近更新（last_event_at 相对时间）
   - 监控状态（Running / Paused）
3. 操作按钮：查看详情 / 暂停监控 / 删除。
4. 筛选栏保留：分组下拉 + 监控状态下拉 + 搜索。
5. 添加股票按钮独立为右上角操作，弹出 `AddStockDialog`。

- **验收标准**：卡片布局清晰；筛选/搜索功能不变；添加股票流程不受影响。

### P1-8 HistoryPanel 组件（前端 + 后端）

**后端**：`GET /api/watchlist/history?days=30`（P1-2 已实现）。

**前端**：
1. 调用 history 端点（queryKey: `['watchlist', 'history', days]`）。
2. 上方：3 个汇总卡（昨日事件数 / 近7天 / 近30天）。
3. 下方：趋势折线图（总事件量 / 高优先事件 / 告警量），使用前端现有图表方案（若未配置则 `npm i recharts`）。
4. 时间范围切换：7天 / 30天 / 90天。

- **验收标准**：图表可渲染；切换时间范围数据重新加载。

### P1-9 监控引擎采集优化（后端）

修改 `langgraph/monitoring/watchlist_monitor.py`：

1. `_collect_and_analyze_stock` 改为 `asyncio.gather(*[collect_one(s) for s in watchlist])` 并发采集（单股超时 120s）。
2. 每采集完一只股票即写入 watchlist_events（流式写入，不等全部完成）。
3. 采集完成后更新 `watchlist.watchlist` 的 `last_event_at`、`today_event_count`、`today_news_count`。
4. 生成 `watchlist_daily_stats` 快照行。

- **验收标准**：25 只股票并发采集完成时间 ≤ 3 分钟（较现有串行 10-15 分钟大幅缩短）；单股失败不影响其他。

---

## Phase 2：Stock Detail 增强 + Config 扩展 + Research 集成

### P2-1 StockDetailDrawer 增强（前端 + 后端）

**后端**：新增 `GET /api/watchlist/stocks/{stock_code}/detail`

```python
{
  "stock_code": "00700",
  "stock_name": "腾讯控股",
  "market": "hk",
  "today_stats": {
    "news_count": 12,          # 当日相关新闻（news.articles JOIN by entity）
    "announcement_count": 1,   # 公告（source_type='announcement'）
    "research_count": 3,       # 研报
    "industry_news_count": 8,  # 行业新闻（非直接关联但同一行业）
    "competitor_news_count": 5 # 竞品新闻
  },
  "ai_summary": "今日主要影响：• AI新品发布 ...",  # Phase 2 由 LLM 生成
  "knowledge_graph": {        # Phase 2 从 AGE 查询
    "nodes": [...],
    "edges": [...]
  },
  "recent_events": [...]      # 近7天事件
}
```

**前端** `StockDetailDrawer.tsx`（WindowedDialog 或右侧 Drawer，可拖拽/缩放）：

1. 顶部：股票名称 + 代码 + 市场 + AI 评分。
2. Tab 1「Today」：今日各维度计数卡片（新闻 / 公告 / 研报 / 行业 / 竞品）。
3. Tab 2「AI Summary」：AI 生成的实时摘要（调用 LLM 对当日事件做一句话总结）。
4. Tab 3「Knowledge Graph」：渲染 AGE 图数据（使用 ReactFlow 或简化力导向图）。
5. Tab 4「Research」：列出该股票的研究历史 + "发起新研究"按钮（P2-4）。

- **验收标准**：点击股票卡片 → 右侧弹出 Drawer；Tab 切换流畅；Knowledge Graph 可交互。

### P2-2 AI Summary 生成（后端）

**后端**：在 `monitoring/` 下新建 `watchlist_ai_summary.py`。

1. 输入：股票代码 + 当日 watchlist_events 列表（summary 字段）。
2. 调用 LLM（复用 `tools/llm.py`）生成 3-5 条要点摘要。
3. 缓存到 `watchlist.watchlist` 新增列 `ai_summary TEXT`（每次监控运行后更新，避免每次打开详情都调 LLM）。
4. API：`POST /api/watchlist/stocks/{stock_code}/summary`（手动触发）、`GET /api/watchlist/stocks/{stock_code}/summary`（读缓存）。

- **验收标准**：首次打开详情调用 LLM 生成摘要（≤10s），再次打开读缓存。

### P2-3 Knowledge Graph 集成（后端 + 前端）

**后端**：新增 `GET /api/watchlist/stocks/{stock_code}/graph`

1. 查询 AGE 图（`investment_knowledge_graph`），以 `stock_code` 对应的实体为起点，1-2 跳邻居。
2. 返回节点/边 JSON（复用 `storage/knowledge/age.py` 现有查询能力）。

**前端**：StockDetailDrawer 的「Knowledge Graph」Tab。

1. 使用 ReactFlow（`npm i reactflow`）渲染力导向图。
2. 节点类型：Stock / Industry / Event / Policy / Competitor（不同颜色）。
3. 点击节点可展开/收缩。

- **验收标准**：图可视化可交互；AGE 不可用时优雅降级（空态提示"图谱数据暂不可用"）。

### P2-4 MonitoringConfig 扩展（后端 + 前端）

**后端**：`PUT /api/watchlist/config` 扩展字段。

1. `monitoring_scopes`：JSONB 数组（news / announcement / earnings / industry / policy / social_media / overseas / competitor）。
2. `ai_summary_enabled` / `daily_report_enabled` / `email_enabled` / `email_address`。
3. `update_frequency`：realtime / hourly / daily。
4. `alert_threshold`：1-5 整数。

**前端**：`MonitoringConfig.tsx` 重构。

1. 监控维度 → 勾选框组（Switch/Checkbox）。
2. AI 功能 → 开关组。
3. 更新频率 → 单选组（RadioGroup）。
4. 告警阈值 → 滑块/数字输入。
5. 保存按钮 → `useMutation` + invalidate `['watchlist', 'config']`。

- **验收标准**：修改频率为 hourly 后，scheduler 在下次 resync 时新增 hourly job；修改维度后，下次监控仅采集勾选的维度。

### P2-5 Research Agent 集成（后端 + 前端）

**后端**：
1. 在 Alerts / Events / Stock Detail 中增加"加入研究"操作。
2. `POST /api/watchlist/stocks/{stock_code}/research`：创建一条 `research_tasks` 记录（`agent_type='investment'`），触发后台 Research Agent 执行。

**前端**：
1. AlertsPanel 每行增加"加入研究"按钮。
2. StockDetailDrawer「Research」Tab：列出该股票的历史研究任务（`GET /api/research?symbol=00700`）+ "发起新研究"按钮。
3. "发起新研究"弹窗：输入研究问题（默认填充"分析 {stock_name} 近期投资价值"），选择 Research Agent 类型。

- **验收标准**：点击"加入研究" → research_tasks 新增一条 running 记录 → ResearchPage 可见；Research Detail Tab 可查看历史。

### P2-6 日报增强（后端 + 前端）

**后端**：
1. 扩展日报内容：在现有 Markdown 基础上增加 AI 摘要段（调用 `watchlist_ai_summary` 的聚合版）。
2. `POST /api/watchlist/reports/{id}/export`：导出 Markdown / PDF（Phase 2 先做 Markdown 下载）。
3. `POST /api/watchlist/reports/{id}/email`：发送邮件（需先配置 SMTP）。

**前端**：
1. DailyReport 组件增加 AI Summary 摘要卡（顶部，优先展示）。
2. 操作按钮组：生成研究报告（跳转 Reports API）、导出 Markdown（触发下载）、发送邮箱。

- **验收标准**：日报摘要可读；Markdown 导出文件含完整内容。

---

## Phase 3：盘中增量采集 + 高级通知 + 生命周期可视化

### P3-1 盘中增量监控（后端 Scheduler）

1. 新增 `watchlist_hourly` scheduler job（当 `update_frequency='hourly'` 时注册）。
2. 增量采集：与全量不同，仅对 enabled 股票做轻量查询（不重新触发完整 News Pipeline，直接查 `news.articles` 当日增量 → 关联→ 写入 watchlist_events）。
3. `resync_watchlist_job()` 扩展：支持根据 `update_frequency` 动态注册/调整 job。

- **验收标准**：hourly job 注册后，整点自动执行，只采集最近 1 小时增量。

### P3-2 高级通知（后端 + 前端）

1. 扩展 `watchlist_settings` 的 `notification_channels` JSONB（web / email / wechat / telegram / slack / webhook）。
2. `monitoring/watchlist_alerts.py` 扩展：支持多通道投递（Phase 3 先做 email + webhook）。
3. 前端 Config 面板增加通知通道配置。

- **验收标准**：配置 email 后，告警触发时可收到测试邮件。

### P3-3 生命周期可视化（前端）

1. 在 WatchlistGrid 的某张卡片或独立小面板展示监控生命周期流程（设计方案 §12 的线性流程图）。
2. 每个阶段用 Step 状态标记（已执行 / 执行中 / 待执行 / 失败），当日监控运行后动态展示。

- **验收标准**：手动触发"开始监控"后，流程图各 Step 实时切换状态。

### P3-4 今日日报的 AI 聚合摘要改进

1. 从单股票 AI Summary 升级为跨股票聚合摘要。
2. 调用 LLM：输入当日全部 watchlist_events（按 importance 排序），生成 3-5 句"今日关注要点"。
3. 落库到 `daily_watchlist_report.summary`（JSON 格式：`{"key_points": ["...", "..."], "focus_stocks": ["00700", "600519"]}`）。

- **验收标准**：日报顶部摘要可读，且标识了需要重点关注的股票。

---

## Phase 4：导出与分享 + 扩展监控对象

### P4-1 PDF 导出

1. 后端：Markdown → HTML → PDF（使用 WeasyPrint 或 Playwright headless）。
2. 前端：日报卡片新增"下载 PDF"按钮。
3. 支持自定义页眉/页脚（平台 Logo + 日期）。

### P4-2 监控对象扩展

1. 扩展 `watchlist.watchlist` 的 `item_type` 列（stock / etf / index / industry / company / person / fund / macro_theme）。
2. 对应调整监控引擎的采集逻辑（ETF/指数走不同数据源）。
3. 前端 WatchlistGrid 卡片按类型区分图标。

### P4-3 高级 AI 能力

1. **Sentiment 趋势**：按日/周聚合 sentiment 占比变化，绘制堆叠图。
2. **异常波动解释**：接入行情数据，当日涨跌幅 > 3% 时自动查询原因（关联当日事件）。
3. **行业影响分析**：同一行业多只股票同时出现事件时，标记"行业级信号"。

---

# 4. 落地顺序与依赖总表

```
P1-1 (DB迁移) ──→ P1-2 (Overview/History API) ──→ P1-3 (前端布局重构)
                                                       │
                    P1-4~P1-8 (各面板组件) ←───────────┤
                    P1-9 (采集优化)                     │
                                                       │
P2-1 (StockDetail增强) ←───────────────────────────────┤
P2-2 (AI Summary)      ←───────────────────────────────┤
P2-3 (Knowledge Graph) ←───────────────────────────────┤
P2-4 (Config 扩展)     ←───────────────────────────────┘
P2-5 (Research 集成) 可与 P2-1~P2-4 并行
P2-6 (日报增强)      依赖 P2-2

P3-1 (盘中增量采集) 依赖 P2-4 (frequency 配置)
P3-2 (高级通知)     依赖 P2-4 (通知通道配置)
P3-3 (生命周期可视化) 独立
P3-4 (聚合摘要)     依赖 P2-2

Phase 4 各项依赖 Phase 1-3 对应基座
```

---

# 5. 风险与建议

| # | 风险 | 影响 | 应对建议 |
|---|---|---|---|
| 1 | **存量 DB 迁移不生效**：postgres init 脚本仅首次初始化执行 | Phase 1 全部新列/新表缺失，API 500 | P1-1 迁移文件保持 `ADD COLUMN IF NOT EXISTS`；上线时对运行中容器手动 `psql -f` 一次；在部署文档中固化该步骤 |
| 2 | **前端重构破坏现有功能**：845 行单文件拆分为 10+ 组件，改动面大 | 现有"添加股票 / 删除 / 启停监控"流程不可用 | **先建后拆**：新组件并行开发，WatchlistPage 作为容器逐步替换；每替换一个区域即验证原流程；保留原 WatchlistPage 的 git 历史 |
| 3 | **React Query 缓存键冲突**：多个组件共享 queryKey 导致被动刷新 | 数据不一致、不必要的网络请求 | 严格遵循 React Query 缓存键隔离原则：`['watchlist', 'overview']` / `['watchlist', 'events', {importance}]` / `['watchlist', 'alerts']` 各自独立；Mutations 仅 invalidate 相关键 |
| 4 | **并发采集导致 News Pipeline 过载**：P1-9 中 25 只股票同时触发采集 | News Pipeline 入口 `_run_collection` 的资源竞争（RSS 频率限制 / LLM 并发） | 引入 `asyncio.Semaphore(5)` 限制并发度；采集阶段与 LLM 分析阶段解耦（先并发采集，再批量分析） |
| 5 | **AI Summary LLM 调用成本**：每次打开 Stock Detail 调 LLM | 频繁打开详情时 LLM 费用高 | P2-2 设计为"监控运行后预生成 + 缓存"模式；手动刷新时调 LLM；前端展示时优先读缓存 |
| 6 | **AGE 图查询性能**：Knowledge Graph 递归 2 跳可能返回大量节点 | Stock Detail Drawer 渲染慢 | 限制 2 跳内最多 50 个节点；图渲染懒加载；AGE 不可用时优雅降级（空态） |
| 7 | **WSL 开发环境**：前端在 WSL 挂载盘需重启 vite 才生效；Docker 命令需 `docker.exe` | 验证环节误判 | 验证阶段遵循既有环境约定；重启 dev server 后再做浏览器验证 |
| 8 | **侧栏"Intelligence"更名影响用户习惯** | 用户找不到入口 | Phase 1 暂保留 "Watchlist" 标签，仅改页面标题为 "Watchlist Intelligence Center"；Phase 2 根据用户反馈决定是否更名 |
| 9 | **API 缺失导致前端组件不能完整联调** | Phase 1-2 多个端点新建，前端可能先于后端完成 | 前端先用固定 mock 数据开发组件骨架；每个组件必须有 Loading / Empty / Error 三态；后端按 P1→P2 顺序交付 |
| 10 | **History 统计数据可能为空**（历史数据未积累） | 趋势图空白 | 提供"数据积累中"友好提示；实时聚合 `watchlist_events` 回退查询；不依赖 `watchlist_daily_stats` 为唯一数据源 |

---

# 附录：涉及文件清单（速查）

## 新建

| 文件 | 说明 |
|---|---|
| `postgres/init/14-watchlist-v2.sql` | 幂等迁移：watchlist 扩展列 + settings 扩展 + daily_stats 表 |
| `langgraph/monitoring/watchlist_ai_summary.py` | AI 摘要生成（LLM 调用 + 缓存） |
| `frontend/src/components/watchlist/TodayOverview.tsx` | 今日概览统计卡片 |
| `frontend/src/components/watchlist/TodayTimeline.tsx` | 今日事件时间线 |
| `frontend/src/components/watchlist/AlertsPanel.tsx` | AI 告警面板 |
| `frontend/src/components/watchlist/WatchlistGrid.tsx` | 股票卡片网格 |
| `frontend/src/components/watchlist/StockDetailDrawer.tsx` | 股票详情 Drawer（含多 Tab） |
| `frontend/src/components/watchlist/MonitoringConfig.tsx` | 监控配置面板 |
| `frontend/src/components/watchlist/DailyReport.tsx` | 日报面板 |
| `frontend/src/components/watchlist/HistoryPanel.tsx` | 历史趋势面板 |
| `frontend/src/components/watchlist/AddStockDialog.tsx` | 添加股票弹窗（从首屏移出） |
| `frontend/src/components/watchlist/WatchlistSkeleton.tsx` | 加载骨架屏 |
| `frontend/src/hooks/useWatchlistOverview.ts` | React Query hook：概览数据 |
| `frontend/src/hooks/useWatchlistEvents.ts` | React Query hook：事件数据 |
| `frontend/src/hooks/useWatchlistAlerts.ts` | React Query hook：告警数据 |
| `frontend/src/hooks/useWatchlistReport.ts` | React Query hook：报告数据 |
| `frontend/src/hooks/useWatchlistHistory.ts` | React Query hook：历史数据 |
| `frontend/src/hooks/useStockDetail.ts` | React Query hook：股票详情 |

## 修改

| 文件 | 说明 |
|---|---|
| `langgraph/api/watchlist.py` | 新增 overview / history / stock detail / AI summary / graph 端点 |
| `langgraph/monitoring/watchlist_monitor.py` | 并发采集优化 + 采集后更新统计列 |
| `langgraph/runtime/scheduler.py` | 新增 watchlist_hourly job + resync 扩展 |
| `langgraph/api/server.py` | 无需修改（watchlist_router 已注册） |
| `frontend/src/app/pages/WatchlistPage.tsx` | 彻底重构：改为布局容器，引入 React Query + 拆分子组件 |
| `frontend/src/services/watchlist.ts` | 扩展类型 + 新增 API 函数（overview / history / stockDetail / stockSummary / stockGraph / stockResearch / exportReport） |
| `frontend/src/components/layout/Sidebar.tsx` | 可选：Watchlist label 改为 "Intelligence"，图标备选 BellDot |
| `frontend/package.json` | 新增依赖：`@tanstack/react-query`（如未引入）、`recharts`、`reactflow` |
| `postgres/init/11-watchlist-schema.sql` | 可单独更新：补充新列的初始默认值 |

## 复用（不改或仅加引用）

| 文件/模块 | 说明 |
|---|---|
| `frontend/src/services/news.ts` | Timeline / Impact / Events API 被 Stock Detail 直接调用 |
| `frontend/src/services/research.ts` | "加入研究"流程复用 fetchResearch / fetchResearchDetail |
| `frontend/src/services/reports.ts` | 日报触发生成研究报告复用 |
| `frontend/src/components/news/` | ArticleDetailDialog / TimelineTab 样式参考 |
| `frontend/src/components/ui/` | 全部 shadcn/ui 组件直接复用 |
| `frontend/src/components/common/EmptyState.tsx` | 空态降级 |
| `langgraph/monitoring/watchlist_alerts.py` | 告警引擎阈值改为可配置（读 settings） |
| `langgraph/monitoring/watchlist_report.py` | 日报引擎扩展 AI 摘要段 |
| `langgraph/storage/knowledge/age.py` | Knowledge Graph 查询复用 |
| `langgraph/tools/llm.py` | AI Summary 调用 |
| `langgraph/api/health.py` | 健康检测（监控引擎状态汇报） |
| `langgraph/runtime/scheduler.py` | 现有 job 框架不变，仅新增 |
