# News Intelligence Center 实施计划书

> Version: v1.0
> Status: Implementation Plan（待执行）
> 依据: 《News Intelligence Center 设计方案》
> 范围: frontend/src/app/pages/NewsPage.tsx 及 components/news/、langgraph/（api/news.py、collectors/、runtime/scheduler.py）、registry/news_sources.yaml、postgres/init/（news schema）
> 核心目标（不可变更）: News Intelligence Center 定位为**实时情报工作台**，负责浏览、监控、展示、触发与源健康管理；不承担新闻结构化、实体/事件抽取、Knowledge Graph 更新、AI Pipeline 等已由 Document Pipeline 与 Knowledge Operations Center 覆盖的职责。

---

# 0. 对齐结论摘要（跨模块分歧决策表）

本计划书与《Document Pipeline + Knowledge Package 实施计划书》《Knowledge Operations Center 实施计划书》《Agent Center 后续演进实施计划书》共享以下决策（摘录与 News 直接相关项）：

| # | 分歧 | 决策 |
|---|---|---|
| 5 | News 是否走统一 Pipeline | News 保留实时专链（News Intelligence Agent：cleaner→dedup→classifier→entity→event→impact→publisher），其输出由 DP-D2 封装为 `source_type=NEWS` 的 Knowledge Package 发布到 KOC；NIC 只消费结果，不做抽取 |
| 3 | 数据契约 | NIC 的 Intelligence Queue 直接消费 `knowledge_packages` 表（source_type=NEWS）状态 |
| 4 | Schema 双轨 | 事件展示以 `core.events`（KOC 权威）为准；`news.events/entities/relations` 为生产链路中间产物，仅写侧保留 |
| 9 | Registry 命名 | News Intelligence Agent 的规范命名以 `specs/agent-registry.yaml` 为准，注册/监控归 Agent Center |
| 11 | SiYuan 归属 | 与本模块无关，不展开 |

**设计方案的"建议删除功能"落地口径**：AI Summary / Entity Extraction / Event Extraction / Knowledge Graph Update / AI Pipeline 从 **News Intelligence Center（工作台 UI）** 的职责中移除；这些能力的执行体（News Intelligence Agent 生产链路）**保留不删**，归属 Document Pipeline 的实时专链（见 DP 计划书决策 #5），由 Agent Center 注册与监控。NIC 不新建任何抽取逻辑。

---

# 1. 模块定位（Positioning）

News Intelligence Center 是平台的**实时情报工作台（Real-time Intelligence Workbench）**：

**负责**：
- 浏览：Live News Feed（最新/高影响/热点/Breaking）。
- 监控：Intelligence Queue（新闻→Knowledge Package 处理状态）、Source Health（源延迟/错误/重复率）。
- 展示：Event Monitor、Impact Monitor、Trend Discovery（全部消费 KOC 已生成的结果，不重新分析）。
- 触发：Research Trigger（一键发起 Research Workflow，只触发不生成）。
- Watchlist Monitor：展示自选股命中的相关新闻（调用 Knowledge Services）。

**不负责**（边界红线）：
- 新闻结构化 / 实体抽取 / 事件抽取 → Document Pipeline（News Intelligence Agent 实时专链）。
- Knowledge Graph 更新 / Validation / Merge / Governance → Knowledge Operations Center。
- AI Summary / AI Pipeline → Document Pipeline 生成 Knowledge Package。
- Agent 注册与运行监控 → Agent Center。

目标数据流（照设计方案）：

```text
News Sources → News Collector → News Intelligence Agent（实时专链，属生产侧）
    → Document Pipeline Publish → Knowledge Package
    → Knowledge Operations Center
        ├─ Knowledge Search ──┐
        └─ Knowledge Analytics ┴──→ News Intelligence Center（展示/监控/触发）
```

与 KOC 的职责边界（照设计方案对照表）：

| News Intelligence Center | Knowledge Operations Center |
|---|---|
| 新闻浏览 / 实时新闻流 / Breaking News | Knowledge Inbox / Validation / Merge |
| 热点监控 / Watchlist 命中 / Research Trigger | Governance / Knowledge Graph / Search |
| Source Health / Intelligence Queue | Analytics / Knowledge Services |

---

# 2. 与现有项目的差距分析

## 2.1 已实现（复用基座）

| 能力 | 现状 | 复用方式 |
|---|---|---|
| News Schema | `postgres/init/09-news-schema.sql`（news.sources/articles/entities/events/relations，sources 含 last_collected_at）、`10-news-tier.sql`（articles.tier：1=永久/2=长期/3=短期） | Live Feed 与 Source Health 数据基础 |
| 采集层 | `langgraph/collectors/`（rss_collector/web_collector/source_registry）+ `registry/news_sources.yaml`（Provider Registry：声明式源配置、enabled 启停、priority 三档调度） | Source Health 的源清单，新增源仅改 YAML |
| 生产链路（保留，非 NIC 职责） | `langgraph/graphs/news_analysis_graph.py` + `nodes/news/*`（cleaner/deduplicator/embedding_dedup/classifier/entity/event/impact/publisher）+ `runtime/scheduler.py` 三档 news_collect job + news_lifecycle job | News Intelligence Agent 实时专链，输出侧由 DP-D2 封装 Package |
| News API | `langgraph/api/news.py`（/api/news：articles、articles/{id}、events、events/{id}/impact、impact、timeline、collect、sources） | Live Feed/Event Monitor 端点基础 |
| 前端工作台雏形 | `frontend/src/app/pages/NewsPage.tsx` + `components/news/`（NewsListTab/EventsTab/ImpactTab/TimelineTab/ArticleDetailDialog） | 改造为设计方案九宫格布局的基座 |
| 新闻查询 MCP | `mcp-news/server/`（tools：article/event/analysis/source，端口 8201） | Watchlist Monitor / Research Trigger 的查询通道之一 |
| Watchlist 模块 | `langgraph/api/watchlist.py` + `postgres/init/11-watchlist-schema.sql` + `14-watchlist-v2.sql` + monitoring/（alerts/report/monitor） | Watchlist Monitor 命中数据源 |

## 2.2 待实现（差距清单）

| # | 差距 | 对应设计功能 |
|---|---|---|
| 1 | Live News Feed 无高影响/Breaking/热点分层视图（现仅普通列表） | Live News Feed |
| 2 | Intelligence Queue 完全缺失：无法查看"News→Processing→Knowledge Package→Published/Failed/Waiting"链路状态 | Intelligence Queue |
| 3 | Event Monitor 读 `news.events`（生产中间产物），未切换为展示 KOC `core.events` 已生成事件（今日新增/影响公司数） | Event Monitor |
| 4 | Impact Monitor 走 `/api/news/impact` 实时重算，设计方案明确"不是重新分析，而是展示 Knowledge Analytics 的 Top Impact Events" | Impact Monitor |
| 5 | Trend Discovery 缺失：无 24 小时热点词共现/趋势聚类（来源应为 KOC Analytics） | Trend Discovery |
| 6 | Watchlist Monitor 缺失：无"自选股今日命中 N 条相关新闻"视图 | Watchlist Monitor |
| 7 | Research Trigger 缺失：无 Create Research / Open Research / Compare / Generate Report 触发入口 | Research Trigger |
| 8 | Source Health 缺失：news.sources 仅有 last_collected_at，无 Latency/Errors/Articles/Duplicates 四项监控与面板 | Source Health |
| 9 | Recent Activities 缺失：无新闻侧运营动态流 | Recent Activities |

---

# 3. 阶段划分与任务清单

> 依赖链：`NIC-C（Source Health，独立可先行）→ NIC-A（Live Feed + Intelligence Queue）→ NIC-B（Event/Impact 切换 KOC）→ NIC-D（Trend/Watchlist/Research Trigger）→ NIC-E（布局收尾）`
> 优先级：P0 依赖上游契约，P1 主干展示，P2 增值触发。

## Phase A：Live News Feed 增强 + Intelligence Queue（P1，依赖 DP-A/DP-D2）

| 编号 | 任务 | 涉及文件 | 验收标准 |
|---|---|---|---|
| NIC-A1 | Live Feed 分层视图：Breaking（priority=HIGH 且 <1h）/高影响（classifier importance 或 tier=1）/热点（近 24h 提及数 Top）三区 | `components/news/NewsListTab.tsx`、`api/news.py`（articles 增加 filter/分层参数） | 三区各有真实数据且排序规则生效 |
| NIC-A2 | Intelligence Queue 后端：联查 `news.articles` → `knowledge_packages`（source_type=NEWS）状态，输出 Waiting/Processing/Published/Failed 四态计数与明细 | `api/news.py`（新增 /api/news/intelligence-queue 端点，依赖 DP-A2 knowledge_packages 表与 DP-D2 发布封装） | 每条已采集新闻可定位到四态之一；Package 失败可看到失败原因 |
| NIC-A3 | Intelligence Queue 前端：状态卡片 + 列表 + 失败重试入口（跳转/调用 DP 的 Re-Publish） | `components/news/IntelligenceQueueTab.tsx`（新建）、`NewsPage.tsx` | Failed 记录可触发重试并刷新状态 |

**阶段验收**：一条 RSS 新闻从采集到 Published 的全状态可在 Intelligence Queue 追踪。

## Phase B：Event Monitor / Impact Monitor 切换 KOC（P1，依赖 KOC-A/KOC-D/KOC-E）

| 编号 | 任务 | 涉及文件 | 验收标准 |
|---|---|---|---|
| NIC-B1 | Event Monitor 改读 `core.events`：展示今日新增事件数、每事件影响公司数（KOC 提供聚合端点） | `components/news/EventsTab.tsx`、`api/knowledge.py`（events 聚合端点，KOC 侧提供） | 事件列表与 core.events 一致，含今日新增统计 |
| NIC-B2 | Impact Monitor 改为展示 Knowledge Analytics 的 Top Impact Events（星级=影响评分），移除前端对 `/api/news/impact` 实时重算的依赖（端点保留供过渡） | `components/news/ImpactTab.tsx`、`api/news.py`（impact 端点标记 deprecated） | Top 影响事件来自 KOC 分析结果，不再触发 LLM 重算 |
| NIC-B3 | 事件双轨收口说明：`news.events` 仅作为生产链路写侧中间产物保留；NIC 展示与 Timeline 统一读 core.events（Timeline Tab 数据源同步切换） | `components/news/TimelineTab.tsx`、`api/news.py`（timeline 端点） | Timeline 与 Event Monitor 数据同源 core.events |

**阶段验收**：Event/Impact/Timeline 三 Tab 全部消费 KOC 已生成知识，NIC 侧无任何抽取/分析调用。

## Phase C：Source Health（P1，News 独有，可独立先行）

| 编号 | 任务 | 涉及文件 | 验收标准 |
|---|---|---|---|
| NIC-C1 | 采集指标埋点：collectors 每次采集记录 latency/articles/errors/duplicates 到 news.sources（扩列：last_latency_ms、last_error、error_count、duplicate_rate）或独立 news.collect_runs 表 | `postgres/init/16-news-health.sql`（新建，幂等）、`collectors/rss_collector.py`、`collectors/web_collector.py` | 一次采集后四项指标均有记录 |
| NIC-C2 | Source Health 面板：按源展示 Latency/Errors/Articles/Duplicates + 覆盖率（enabled 源中成功采集比例），异常源（连续失败）红色标记；数据源为 news_sources.yaml + 采集指标 | `components/news/SourceHealthTab.tsx`（新建）、`api/news.py`（/sources/health 端点） | 停用一个源后其状态显示异常；恢复后转绿 |
| NIC-C3 | 源启停联动：面板可直接切换 news_sources.yaml 源的 enabled（复用现有 source_registry 动态加载） | `collectors/source_registry.py`、SourceHealthTab | UI 停用源后下一采集周期不再采集该源 |

**阶段验收**：Source Health 面板四指标 + 覆盖率 + 启停操作全部可用。

## Phase D：Trend Discovery + Watchlist Monitor + Research Trigger（P2，依赖 KOC-D/Watchlist/Research）

| 编号 | 任务 | 涉及文件 | 验收标准 |
|---|---|---|---|
| NIC-D1 | Trend Discovery：展示过去 24h 热点词共现增长（如 AI+GPU+Cloud 共同增长），数据来自 KOC Insights（KOC-D2） | `components/news/TrendTab.tsx`（新建）、`api/knowledge.py`（insights 端点） | 趋势卡有真实来源并可下钻到相关新闻 |
| NIC-D2 | Watchlist Monitor：自选股今日命中新闻数列表，调用 Knowledge Services（mcp-news /api/news + watchlist 表） | `components/news/WatchlistMonitorTab.tsx`（新建）、`api/news.py` 或 `api/watchlist.py`（命中统计端点） | 自选股标的命中数与实际新闻匹配 |
| NIC-D3 | Research Trigger：事件/新闻卡片增加 Create Research / Open Research / Compare / Generate Report 动作，触发 Research Workflow（复用 /api/research 与 tasks 系统），NIC 只负责触发与跳转 | `components/news/*`（动作按钮）、`services/research.ts`（前端已有则复用） | 一键触发后 research_tasks 出现新任务并可跳转 Research 页跟踪 |

## Phase E：布局收尾（P2）

| 编号 | 任务 | 涉及文件 | 验收标准 |
|---|---|---|---|
| NIC-E1 | NewsPage 重构为设计方案九宫格：Live Feed / Intelligence Queue / Event Monitor / Impact Monitor / Trend Discovery / Watchlist Monitor / Research Trigger / Source Health / Recent Activities | `NewsPage.tsx`（Tab/区块重组，懒加载） | 九项能力均有入口且无职责外功能（无抽取/AI Pipeline 入口） |
| NIC-E2 | Recent Activities：新闻侧动态流（新源接入、采集异常、Breaking、Package 发布里程碑） | `components/news/RecentActivities.tsx`（新建） | 动态流按时间倒序展示真实事件 |

---

# 4. 依赖关系

```text
【外部】DP 计划书 DP-A（knowledge_packages 契约）+ DP-D2（NEWS Package 封装）──→ NIC-A2/A3（Intelligence Queue）
【外部】KOC 计划书 KOC-A（core.events 消费入库）──→ NIC-B1/B3；KOC-D/E（Analytics/Impact）──→ NIC-B2、NIC-D1
【外部】AC 计划书：News Intelligence Agent 纳入 Registry 与 agent_runs 口径（生产链路监控在 Agent Center 展示，不在 NIC）
NIC-C（Source Health）无外部依赖，可独立先行
NIC-D2 依赖 Watchlist 模块（14-watchlist-v2.sql 已落地）；NIC-D3 依赖 Research 任务系统（已有）
```

# 5. 优先级总表

| 优先级 | 任务 |
|---|---|
| P1（主干） | NIC-C1~C3、NIC-A1~A3、NIC-B1~B3 |
| P2（增值） | NIC-D1~D3、NIC-E1~E2 |

（无 P0：NIC 自身不阻塞其他模块；其 A/B 阶段被上游 DP/KOC 阻塞。）

---

# 6. 风险与回滚建议

| # | 风险 | 影响 | 应对/回滚 |
|---|---|---|---|
| 1 | 事件双轨（news.events vs core.events）切换期数据不一致 | Event Monitor 数量口径混乱 | NIC-B3 切换前对比两表计数；切换保留旧端点一周，前端以 feature flag 回退 |
| 2 | Intelligence Queue 依赖 DP-D2（NEWS Package 封装）未完成 | 四态视图无数据 | NIC-A2 端点先按 news.articles 单态降级展示（Waiting=已采集未发布），DP-D2 就绪后自动升级 |
| 3 | Impact Monitor 移除实时重算后体验降级（KOC 分析结果延迟） | 用户看不到最新影响 | `/api/news/impact` 端点保留为过渡通道，KOC 结果新鲜度达标（<1h）后再正式下线 |
| 4 | Source Health 埋点增加采集链路开销 | 采集变慢 | 埋点仅异步落表（fire-and-forget），失败不影响采集主流程 |
| 5 | Research Trigger 误触发大量 Research 任务 | 任务队列拥塞 | 触发入口加确认弹窗 + 频率限制（同事件 10 分钟内去重） |
| 6 | 九宫格重构导致现有 4 Tab 用户习惯中断 | 可用性回退 | NIC-E1 保留旧 Tab 结构为过渡布局，九宫格以新 Tab 组灰度上线 |
| 7 | 存量 DB 迁移不生效（init 仅首次执行，项目已验证坑） | 16-news-health 表缺失 | 幂等迁移 + 手动 `psql -f` 一次（沿用 12/13 先例） |

**整体回滚策略**：NIC 全部为展示/触发层改造，无生产链路侵入；各 Tab 独立组件 + feature flag，可逐 Tab 回退到现有 NewsPage 四 Tab 形态。

---

# 附录：涉及文件清单（速查）

**新建**
- `postgres/init/16-news-health.sql`
- `frontend/src/components/news/IntelligenceQueueTab.tsx`、`SourceHealthTab.tsx`、`TrendTab.tsx`、`WatchlistMonitorTab.tsx`、`RecentActivities.tsx`

**修改**
- `frontend/src/app/pages/NewsPage.tsx`、`components/news/NewsListTab.tsx`、`EventsTab.tsx`、`ImpactTab.tsx`、`TimelineTab.tsx`
- `langgraph/api/news.py`（intelligence-queue/sources/health 端点、impact/timeline 数据源切换）
- `langgraph/collectors/rss_collector.py`、`web_collector.py`、`source_registry.py`（健康埋点与启停）

**复用（不改）**
- `registry/news_sources.yaml`、`graphs/news_analysis_graph.py`、`nodes/news/*`（生产链路，归 DP/AC 管辖）
- `runtime/scheduler.py`（news_collect/news_lifecycle job）
- `mcp-news/server/*`、`api/watchlist.py`、Research 任务系统

**明确不动**
- 任何实体/事件抽取逻辑（nodes/news/entity.py、event.py、impact.py 属生产侧，NIC 不修改不新建同类能力）
