# Agent Center 后续演进实施计划书

> Version: v1.0
> Status: Implementation Plan（Phase 1+2+P3-1 已落地，本计划书覆盖 Phase 3 收尾 + 跨模块对齐 + Phase 4）
> 依据: 《Agent Center 实施计划》（v1.2）、《Agent Center 设计规范 v1.0》
> 范围: langgraph/（api、agents、runtime）、frontend/src/app/pages/（AgentsPage/AgentDetailPage/WorkflowPage）、specs/agent-registry.yaml
> 核心目标（不可变更）: Agent Center 负责 Agent 注册、配置、Prompt、Skill、Tool、MCP、Memory、运行记录与监控；不侵入知识生产（Document Pipeline）与知识运营（Knowledge Operations Center）的业务逻辑。

---

# 0. 对齐结论摘要（跨模块分歧决策表）

本计划书与《Document Pipeline + Knowledge Package 实施计划书》《Knowledge Operations Center 实施计划书》《News Intelligence Center 实施计划书》共享以下决策（摘录与 Agent Center 直接相关项）：

| # | 分歧 | 决策 |
|---|---|---|
| 2 | Knowledge Extraction 归属 | Knowledge Ingestion Agent 是 Document Pipeline Stage 5 执行器（生产职责）；其注册/配置/监控仍归 Agent Center |
| 5 | News 链路 | News Intelligence Agent 保留实时专链（生产职责归 DP）；注册与运行记录归 Agent Center |
| 9 | `specs/agent-registry.yaml` 目录映射失效（指向不存在的 `langgraph/agent/*`，实际在 `graphs/` + `nodes/`） | 由本计划书 AC-B1 修正，registry 重新成为命名与路径权威源 |
| 10 | WorkflowPage 任务中心 vs Workflow 图可视化 | 任务监控保留，图可视化作为新 Tab（AC-P3-2），不重建任务系统 |
| 11 | SiYuan 归属 | 见下方依赖说明 |

---

# 1. 模块定位（Positioning）

Agent Center 是平台的 **Agent 管理与监控中枢**：

- **管理面**：Agent 注册与发现、生命周期（active/paused/deprecated）、配置（热生效+历史回滚）、Prompt（DB 化+版本）、Skill/Tool/MCP/Memory 四类能力管理。
- **观测面**：运行记录（agent_runs）、Metrics（Runs/Latency/Tokens/Cost）、Logs 与节点级 Trace、Workflow Graph 可视化。
- **边界**：不实现任何知识生产/运营业务逻辑；Pipeline Agent（Knowledge Ingestion / News Intelligence）的业务编排归 Document Pipeline，Agent Center 只负责其注册、运行埋点与监控展示。

---

# 2. 与现有项目的差距分析

## 2.1 已实现（Phase 1 + 2 + P3-1，已验证基座）

| 能力 | 现状 |
|---|---|
| 数据库 | `postgres/init/13-agent-center.sql`：agents 扩展列 + agent_prompts + agent_configs_history + agent_runs + agent_tool_stats + mcp_connections |
| Registry | `api/agents.py`（AGENT_REGISTRY + agents 表 + `config/agent_meta.yaml` 三方合并）、detail/toggle/config 端点、lifespan 内置 upsert |
| 前端 | `AgentsPage.tsx` 卡片（状态点/版本/最后活跃）、`AgentDetailPage.tsx` 7 Tab（概览/提示词/配置/技能/工具/MCP/记忆） |
| Prompt | `scripts/migrate_prompts_to_db.py`（19/19 对账）、`prompts/loader.py` 仅读 DB、`api/prompts.py` |
| 配置 | 保存/历史/回滚/校验端点 + ConfigTab |
| Skill/Tool/MCP/Memory | `skills/registry.py` enabled+reload、`api/skills.py`；`monitoring/agent_center.py` 埋点、`api/tools.py`；`monitoring/mcp_manager.py` 纳管+心跳、`api/mcp.py`；`api/memory.py` 三层记忆概览 |
| 运行记录 | chat 路径 agent_runs 埋点；scheduler `agent_center_archive` 每日归档 job |

## 2.2 待实现（差距清单）

| # | 差距 | 对应规范章节 |
|---|---|---|
| 1 | Workflow Graph 可视化缺失（`api/workflows.py` 不存在） | §10 |
| 2 | Runtime Metrics 缺失（`api/metrics.py` 不存在，无 Runs/Latency/Tokens/Cost 聚合与趋势） | §12 |
| 3 | Agent Center Dashboard 布局未升级（规范 §16 三栏布局） | §16 |
| 4 | Logs 与 Trace 缺失（`api/logs.py` 不存在，无运行级日志筛选/节点级 Trace/CSV 导出） | §13 |
| 5 | `specs/agent-registry.yaml` 目录映射失效：指向 `langgraph/agent/agents|knowledge_agent|news_agent/`（不存在），实际代码在 `langgraph/agents/`、`langgraph/graphs/` + `langgraph/nodes/` | Registry 权威源 |
| 6 | Pipeline Agent 未纳入口径：Knowledge Ingestion / News Intelligence Agent 未在 agent_meta.yaml 注册，其运行未写 agent_runs | §4/§12 |
| 7 | Phase 4 高级能力全部缺失：热更新、Prompt 版本审批、A/B、Marketplace、跨 Agent Trace、权限 | §17 |

---

# 3. 阶段划分与任务清单

> 依赖链：`AC-B（对齐，可先行）→ AC-P3-2（Workflow 图，独立）→ AC-P3-3（Metrics）/ AC-P3-5（Logs）→ AC-P3-4（Dashboard）→ AC-P4-*（高级能力）`
> 优先级：P0 数据口径统一，P1 可视化主干，P2 高级能力。

## Phase B：跨模块对齐（P0，本计划书新增，优先于可视化）

**目标**：修正 Registry 权威源，Pipeline Agent 纳入统一口径——这是与 DP/KOC/NIC 三份计划书联动的前提。

| 编号 | 任务 | 涉及文件 | 验收标准 |
|---|---|---|---|
| AC-B1 | 修正 agent-registry.yaml 目录映射：Chat/Investment/KB/Research → `langgraph/agents/`；Knowledge Ingestion Agent → `graphs/knowledge_graph.py` + `nodes/knowledge/`；News Intelligence Agent → `graphs/news_analysis_graph.py` + `nodes/news/` | `specs/agent-registry.yaml` | 表中每个入口文件路径在代码库中真实存在（ls 逐一验证） |
| AC-B2 | Pipeline Agent 注册：agent_meta.yaml 补 Knowledge Ingestion / News Intelligence 两个条目（名称/描述/版本对齐 registry 规范命名），`GET /api/agents` 返回 6 个 Agent | `config/agent_meta.yaml`、`api/agents.py` | /api/agents 返回 6 项且卡片可见 |
| AC-B3 | Pipeline Agent 运行埋点：在图调用层提供统一包装器（如 `invoke_tracked(graph, input, agent_id)`，建议置于 graphs 层工具模块），覆盖全部真实调用入口——Knowledge Ingestion：知识抽取任务入口；News Intelligence 两个入口：`runtime/scheduler.py::_job_news_collect`（定时采集）与 `api/news.py::_run_collection`（手动 /api/news/collect）；写 agent_runs（task_kind=pipeline，复用 P3-1 既有模式，禁止节点层重复埋点） | `graphs/knowledge_graph.py`、`graphs/news_analysis_graph.py`、`runtime/scheduler.py`、`api/news.py`、`agents/base_agent.py` 埋点工具 | 一次知识抽取 + 一次新闻入库后 agent_runs 各有一条记录且 trace 含节点序列；**定时采集 job 与手动 collect 两条路径各产生一条记录，无遗漏** |
| AC-B4 | 口径文档化：research_tasks=研究语义记录、tasks=Pipeline 任务、agent_runs=Agent Center 指标源，三表口径写入 agent_meta.yaml 注释或 registry 说明段 | `specs/agent-registry.yaml` | 口径说明存在且与现状一致 |

**阶段验收**：Registry 路径全部有效；6 个 Agent 统一可见；Pipeline 类运行出现在 Metrics 数据源中（定时与手动两条触发路径均不遗漏）。

## Phase P3：可视化收尾（P1）

| 编号 | 任务 | 涉及文件 | 验收标准 |
|---|---|---|---|
| AC-P3-2 | Workflow Graph 可视化：`GET /api/workflows`（workflows.yaml 列表，news/knowledge 已注册在案）+ `GET /api/workflows/{name}/graph`（LangGraph 原生 `get_graph().to_json()`，失败回退静态节点序列）；WorkflowPage 新增 "Workflow 图" Tab（ReactFlow 渲染，与任务 Tab 并列） | `langgraph/api/workflows.py`（新建）、`frontend/src/app/pages/WorkflowPage.tsx`、`npm i reactflow` | 6 个 workflow 全部可渲染；research 图呈 Planner→Retrieve→Rerank→Reason→Reflect→Finish 链路；**news 图呈 Cleaner→Dedup→EmbeddingDedup→Classifier→[Entity‖Event]→Impact→Publisher 链路（NIC 边界声明“生产链路可视化在 Agent Center”的对应验收）** |
| AC-P3-3 | Runtime Metrics：`GET /api/agents/{id}/metrics?range=`（Today Runs/Success/Failed/Avg Latency/Avg Tokens/Avg Cost，cost 按 providers.yaml 单价，无单价置 0）+ 趋势序列；AgentDetailPage 顶部指标卡 + recharts 图表 | `langgraph/api/metrics.py`（新建）、`AgentDetailPage.tsx`、`npm i recharts`（如未引入） | 与规范 §12 六项指标一一对应；时间范围切换数据正确；**News Intelligence / Knowledge Ingestion 两个 Pipeline Agent 可按 agent_id 筛选且存在真实运行数据（NIC 边界声明“生产链路监控在 Agent Center”的对应验收，依赖 AC-B2/B3）** |
| AC-P3-5 | Logs 与 Trace：`GET /api/logs`（agent_runs + task_logs 联合视图，支持 agent_id/status/keyword/分页）、`GET /api/logs/{run_id}/trace`（节点级轨迹+耗时）、`GET /api/logs/export`（CSV）；Logs Tab 表格 + 行展开 Trace 时间线 + 错误分类（tool_timeout/embedding_error/mcp_error） | `langgraph/api/logs.py`（新建）、`AgentDetailPage.tsx` | 可筛选失败记录；任一失败可展开看失败节点与错误分类；CSV 可下载；**两个 Pipeline Agent 的运行记录可筛选且 Trace 含完整节点序列（含 news 图 publisher 节点）** |
| AC-P3-4 | Dashboard 布局：AgentsPage 重构为规范 §16 三栏（Agent Registry | Runtime Metrics 汇总 | Recent Logs）+ `/api/agents/summary` 全局汇总端点 | `AgentsPage.tsx`、`api/agents.py` | 首屏与规范 §16 一致；卡片点击进入 Detail |

**执行顺序**：AC-P3-2 独立可先行；AC-P3-3 与 AC-P3-5 并行（均依赖 agent_runs 数据，P3-1 已就绪）；AC-P3-4 依赖 AC-P3-3。

## Phase 4：高级能力（P2，依赖 Phase 1-3 基座，可并行排期）

| 编号 | 任务 | 验收标准 |
|---|---|---|
| AC-P4-1 | Agent 热更新：yaml 监听 + `POST /api/agents/reload` 重建 AGENT_REGISTRY，不断开在途请求 | 改 yaml 后 reload，新请求路由到新配置，无服务重启 |
| AC-P4-2 | Prompt Version Control：diff 视图、草稿、发布审批（复用 approvals API） | 两版本 diff 可视化；发布需审批通过 |
| AC-P4-3 | A/B Prompt Test：agent_prompts 增 traffic_weight，运行记录按 variant 打标，Metrics 按 variant 对比 | 同一 Agent 两版 prompt 分流并对比成功率/耗时 |
| AC-P4-4 | Agent Marketplace：agent_templates 表 + 导入/导出 Agent 定义 JSON | 导出定义可在另一实例导入 |
| AC-P4-5 | 多 Agent 协同监控：基于 agent_runs.trace 关联跨 Agent 调用链（news→knowledge ingestion），Trace 页聚合展示 | 一次新闻入库可追踪两个 Agent 的衔接（依赖 AC-B3 埋点） |
| AC-P4-6 | Agent 权限管理：agents 表加权限字段 + API 级校验中间件（先开关粒度，后角色） | 停用 Agent 后其 API 返回 403 |

---

# 4. SiYuan 依赖说明（仅一段，不展开）

mcp-knowledge（含 SiYuan tools/rendering）已按 P2-3 纳管（mcp_servers.yaml 注册 + 心跳监控），本计划书仅负责其 MCP Server 的注册、心跳与健康状态展示；SiYuan 同步/渲染的业务编排（审核→渲染入队、Render Queue 监控、冲突治理）归《Knowledge Operations Center 实施计划书》Phase F，不在本计划书内实现。SiYuan 服务不可用时，本模块 MCP 状态面板体现 Disconnected 并递增 Retry Count 即为履职完毕。

---

# 5. 依赖关系

```text
AC-B1~B4（对齐）──→ AC-P3-3 / AC-P3-5（Pipeline Agent 数据进入 Metrics/Logs 口径）
AC-P3-2 独立可先行（不依赖其他任务）
AC-P3-3 + AC-P3-5 并行 ──→ AC-P3-4（Dashboard）
AC-P4-5 依赖 AC-B3；AC-P4-2/3 依赖 Phase 1 Prompt 基座；AC-P4-6 依赖 toggle 能力（已有）
【外部】DP 计划书：Knowledge Ingestion Agent 被编排为 Stage 5 后，其运行入口不变，埋点（AC-B3）不受影响
【外部】KOC 计划书：mcp-knowledge 业务编排归 KOC Phase F，本计划书只管 MCP 连接健康
【外部】NIC 计划书：News Intelligence Agent 的生产监控在本模块展示，NIC 不重建监控。反向确认两点：
         （1）NIC 不依赖本模块 API——Intelligence Queue 四态消费 knowledge_packages（DP 契约），无需建立 NIC→Agent Center 查询接口；
         （2）NIC-C Source Health（源级 Latency/Errors/Articles/Duplicates）是设计方案定义的 News 独有域，埋点在 collectors、数据落 news.sources，Agent Center 不承接，避免职责重叠
```

# 6. 优先级总表

| 优先级 | 任务 |
|---|---|
| P0 | AC-B1~B4（Registry 修正与口径统一，阻塞跨模块一致性） |
| P1 | AC-P3-2、AC-P3-3、AC-P3-5、AC-P3-4 |
| P2 | AC-P4-1 ~ AC-P4-6 |

---

# 7. 风险与回滚建议

| # | 风险 | 影响 | 应对/回滚 |
|---|---|---|---|
| 1 | Pipeline Agent 埋点改变图调用路径，且 News 图存在定时（scheduler）与手动（api/news.py）两个调用入口 | 知识/新闻生产链路回归；单一入口埋点导致另一路径运行从 Metrics/Logs 中消失 | AC-B3 采用图调用层统一包装器（两入口共用），不进入节点内部；异常捕获保证埋点失败不阻断生产；policy 开关可停用埋点；验收强制双路径各有记录 |
| 2 | 数据双写不一致（agent_runs vs research_tasks vs tasks） | Metrics 口径混乱 | AC-B4 三表口径固化；禁止节点层重复埋点；Metrics 只读 agent_runs |
| 3 | ReactFlow 渲染失败或图结构导出异常 | Workflow Tab 空白 | 回退方案：各 graph 模块内静态节点序列（已确认决策）；Tab 懒加载 + EmptyState |
| 4 | Metrics 计价依赖 providers.yaml 单价缺失 | Cost 显示错误 | 无单价一律置 0 并标注"未配置单价"，不估算 |
| 5 | agent-registry.yaml 修正与实际代码再漂移 | 权威源再次失效 | AC-B1 完成后增加 CI/检查脚本校验路径存在性（可选 P2） |
| 6 | 前端路由/缓存冲突（AgentsPage 重构） | 页面异常 | `/agents` 与 `/agents/:id` 分开声明；MCP/Metrics 走独立 React Query 缓存键（遵守缓存键隔离原则） |
| 7 | WSL 环境：挂载盘需重启 vite；Docker 命令用 docker.exe | 验证误判 | 验证阶段遵循既有环境约定 |

**整体回滚策略**：AC-B 埋点与 registry 修正均可独立撤销（git 粒度）；P3 各 API 为纯新增端点，回滚 = 前端隐藏 Tab；Phase 4 每项独立 feature flag。

---

# 附录：涉及文件清单（速查）

**新建**
- `langgraph/api/workflows.py`、`api/metrics.py`、`api/logs.py`

**修改**
- `specs/agent-registry.yaml`（路径修正 + 口径说明）
- `langgraph/config/agent_meta.yaml`（补 2 个 Pipeline Agent）
- `langgraph/graphs/knowledge_graph.py`、`graphs/news_analysis_graph.py`（入口埋点）
- `langgraph/runtime/scheduler.py`（`_job_news_collect` 接入埋点包装器）、`langgraph/api/news.py`（`_run_collection` 接入埋点包装器）
- `frontend/src/app/pages/AgentsPage.tsx`、`AgentDetailPage.tsx`、`WorkflowPage.tsx`
- `frontend/src/services/`（workflows/metrics/logs service 新增）

**复用（不改）**
- 任务系统（tasks/task_logs）、scheduler（归档 job 已有）、`api/prompts.py`/`skills.py`/`tools.py`/`mcp.py`/`memory.py`（Phase 1/2 产物）
- `monitoring/mcp_manager.py`（MCP 心跳，SiYuan 相关 MCP 健康展示沿用）
