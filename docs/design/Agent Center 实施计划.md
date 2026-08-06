# Agent Center（Agent 控制中心）实施计划

> Version: v1.2（Phase 1 + 2 + P3-1 已执行并验证）
> Status: Phase 1+2+P3-1 ✅ 已落地 · Phase 3/4 待执行
> 依据: 《Agent Center 设计规范 v1.0》（docs/design/gent Center 设计规范.md）
> 范围: frontend/（React + Vite）、langgraph/（FastAPI + LangGraph）、postgres/init/（DDL）、mcp-knowledge / mcp-news

## 执行状态（2026-08-05）

| 阶段 | 状态 | 说明 |
|---|---|---|
| P1-1 数据库迁移 | ✅ | `postgres/init/13-agent-center.sql` 已应用且幂等（agent_prompts / agent_configs_history / agent_runs / agent_tool_stats / mcp_connections） |
| P1-2 Registry API | ✅ | `api/agents.py` 元数据合并 + detail/toggle/配置端点；`config/agent_meta.yaml` + `config/agent_meta.py`；lifespan 内置 upsert |
| P1-3 卡片升级 | ✅ | AgentsPage 状态点/版本/最后活跃/可点击进详情 |
| P1-4 详情页 | ✅ | `AgentDetailPage.tsx` 路由 + 7 Tab（概览/提示词/配置/技能/工具/MCP/记忆） |
| P1-5 Prompt 迁 DB | ✅ | `scripts/migrate_prompts_to_db.py`（19/19 对账）；`loader.py` 仅读 DB；`api/prompts.py`；PromptTab |
| P1-6 配置管理 | ✅ | 配置保存/历史/回滚/校验端点 + ConfigTab |
| P2-1 Skill | ✅ | `skills/registry.py` enabled+reload；`api/skills.py`；SkillsTab |
| P2-2 Tool | ✅ | `monitoring/agent_center.py` 埋点（agent_runs + agent_tool_stats）；`api/tools.py`；ToolsTab |
| P2-3 MCP | ✅ | `monitoring/mcp_manager.py` 纳管+心跳；`api/mcp.py`；McpTab |
| P2-4 Memory | ✅ | `api/memory.py` 三层记忆概览+情景/运行列表；MemoryTab |
| P3-1 埋点+归档 | ✅ | chat 路径 agent_runs 埋点；scheduler `agent_center_archive` 每日归档 job |

> 备注：前端补充缺失的 `components/ui/label.tsx`；修复多处 asyncpg 参数类型推断（trace JSONB、MCP 状态 CASE、interval 拼接）。

## 已确认决策（2026-08-05 用户确认）

| 决策点 | 结论 | 影响 |
|---|---|---|
| 实施范围 | **本批执行 Phase 1 + 2**（Phase 3/4 下批） | agent_runs 表与埋点（P3-1）提前至本批，作为 P2-2 Tool 统计与后续 Metrics 的统一数据基础 |
| Prompt 存储 | **全量迁移 DB**：文件型 Prompt Hub 一次性导入 DB 后删除，loader 仅读 DB | P1-5 增加迁移脚本与全调用点切换；风险等级上调（见第 4 节风险 #3） |
| 运行记录 | **新建 agent_runs 表**（与 research_tasks、tasks 口径分离） | 建表提前至 P1-1 迁移文件 |
| Workflow 可视化 | **LangGraph 原生导出（get_graph().to_json()）+ ReactFlow** | P3-2 实现方式锁定，回退方案为静态节点序列 |

---

# 1. 现状盘点

## 1.1 Frontend（frontend/src）

| 类别 | 现状 | 与 Agent Center 的关系 |
|---|---|---|
| 路由 | `app/router.tsx` 已注册 14 条路由：`/`、`/chat`、`/agents`、`/knowledge`、`/knowledge/review`、`/documents`、`/workflow`、`/research`、`/news`、`/watchlist`、`/models`、`/vector-db`、`/monitor`、`/settings` | `/agents` 路由已存在，可直接扩展为 Agent Center 入口 |
| AgentsPage | `app/pages/AgentsPage.tsx`：只读卡片列表（名称/描述/来源/模型/工具/激活状态），无详情页、无编辑能力，页脚注明"创建与编辑功能将在后续版本开放" | Phase 1 直接在此基础上升级 |
| WorkflowPage | `app/pages/WorkflowPage.tsx`：实质是**任务处理中心**（tasks 表），含总览/流水线/日志/统计 4 个 Tab，支持任务的创建（doc_pipeline / batch_embed / knowledge_extraction）、重试、取消、克隆、暂停/恢复 | 与 Agent Center 的"Workflow 图可视化"是**两回事**，但任务监控、日志、统计 Tab 可直接复用为 Runtime Metrics / Logs 的数据源 |
| MonitorPage | `app/pages/MonitorPage.tsx`：消费全局 `['health']` 缓存键展示各服务健康状态（数据源 `/health`） | MCP 连接状态、Agent Runtime Status 可复用同一健康检测机制 |
| DashboardPage / KnowledgePage | Dashboard 为平台总览；知识中台组件 `components/knowledge/`（KnowledgeDashboard、CollectionGrid、KnowledgeTasksPanel、EntityBrowser、GraphWorkspace、SemanticSearchPanel）是成熟的"多 Tab + 卡片网格 + 任务面板"范式 | 其组件模式可直接套用于 Agent Detail 的 Tabs 布局 |
| services 层 | `services/agents.ts` 仅有 `fetchAgents()`；`services/tasks.ts` 已有完整任务 CRUD（fetchTasks/fetchTaskLogs/fetchTaskStats/retryTask/cancelTask/triggerPipeline 等） | agents.ts 需扩展；tasks.ts 直接复用 |
| 导航 | `components/layout/Sidebar.tsx`、`CommandPalette.tsx` 已含 Agents / Workflow / Monitor 入口 | 无需新增导航项，仅需改名/调整定位 |

## 1.2 LangGraph 后端（langgraph/，端口 8100）

| 模块 | 现状 |
|---|---|
| API 层 | `api/server.py` 注册 15 个 router：chat、models、health、providers、tasks、approvals、**agents（仅 GET 列表）**、documents、research、reports、knowledge、vector、news、watchlist |
| Agent 层 | `agents/`：BaseAgent + ChatAgent / ResearchAgent / KBAgent / InvestmentAgent；`services/router.py` 依据 `config/agents.yaml` 声明式构建 `AGENT_REGISTRY`，`dispatch_agent()` 按 policies.yaml 规则路由 |
| Graph 编排 | `graphs/`：research_graph（含 chat/kb 简化图）、news_analysis_graph、knowledge_graph、document_graph；`config/workflows.yaml` 声明式注册 6 个 workflow，`graphs/__init__.py` 按需编译缓存 |
| 节点 | `nodes/research/`（planner、query_rewrite、retrieve、rerank、reason、reflect、writer、finish）、`nodes/knowledge/`（parser、entity、relation、fact、merger）、`nodes/news/`（cleaner、dedup、classifier、entity、event、impact、publisher） |
| Prompt Hub | `prompts/loader.py`：文件系统 .md 模板 + `{var}` 变量替换 + lru_cache；已有 planner/reason/reflect/writer 及 chat/research/investment/kb/news 子目录。**无版本、无 DB 持久化、无在线编辑** |
| Skills | `skills/registry.py` + base_skill + rag_search / master_analysis / web_article_summary / investment_research，在 `server.py` lifespan 中注册 |
| Tools | `tools/`：postgres、qdrant、minio、llm、embedding、reranker、docling、chunker、search_tools、market_tools、knowledge_tools、document_tools。**无调用统计埋点** |
| Memory | `memory/`：三层架构 —— 工作记忆（LangGraph Checkpoint → PG）、情景记忆（`research_tasks` 表，BaseAgent 已自动记录 start/complete/fail episode）、知识记忆（Qdrant + Vault） |
| Runtime | `runtime/`：scheduler（APScheduler：daily_pipeline、task_retry、weekly_consistency、monthly_cleanup、news_collect、watchlist_daily）、worker、queue、executor |
| 健康检测 | `api/health.py`：`/health`（HTTP + MCP 探测）、`/metrics`、`/status` |
| MCP 配置 | `config/mcp_servers.yaml`：仅 filesystem / github 两个**禁用**的占位项；真实的 Knowledge MCP / News MCP 未纳入管理 |
| Monitoring | `monitoring/` 仅 watchlist 相关（alerts / report / monitor），无 Agent 级运行指标 |

## 1.3 MCP 服务

| 服务 | 现状 |
|---|---|
| mcp-knowledge | `server/main.py`，知识访问层（15 Tools × 5 模块：adapters/storage/rendering/cache/llm） |
| mcp-news | `server/main.py`，新闻查询层（7 Tools × 4 模块，端口 8201） |

## 1.4 Skills（仓库根 skills/）

`skills/architecture`、`database`、`docker`、`documentation`、`glossary`（仅 glossary/skill.md 有内容）、`langgraph`、`mcp`、`review` —— 这些是**开发期 Agent 技能**（面向 IDE/CLI Agent），与运行时 `langgraph/skills/` 是两套体系。设计规范第 7 节的 Skill Management 针对的是**运行时 skills**（langgraph/skills/registry.py）。

## 1.5 数据库（postgres/init/）

| 表 | 状态 | 复用价值 |
|---|---|---|
| `agents`（01-init.sql §4.4） | 已存在：name / description / prompt_template / model / temperature / tools JSONB / config JSONB / is_active | Agent 配置管理直接落此表 |
| `tasks` + `task_logs`（01、12） | 已存在，WorkflowPage 消费 | 任务级日志/统计直接复用 |
| `research_tasks`（01-init.sql §4.7） | 已存在，情景记忆（question/agent_type/plan/status/耗时） | Agent 运行记录的数据基础 |

⚠️ 注意：Docker PostgreSQL init 脚本**仅首次初始化生效**（已验证的项目坑），存量 DB 的表结构变更必须用**幂等的独立迁移文件**（`CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`）。

## 1.6 历史遗留与复用评估

| 遗留能力 | 评估结论 |
|---|---|
| WorkflowPage 任务监控 | **保留并复用**：它是 Pipeline 任务的执行中心，Agent Center 的 Logs/Metrics 通过 tasks + task_logs + research_tasks 聚合数据，不重建任务系统 |
| Scheduler / Worker | **复用**：Agent 运行记录的归档、统计聚合 job 挂到现有 scheduler |
| MonitorPage / health | **复用**：MCP 心跳与 Agent Runtime 状态复用 `/health` 探测框架 |
| specs/agent-registry.yaml | **复用为命名权威源**：规范名称（Chat/Research/KB/Investment/Knowledge Ingestion/News Intelligence Agent）作为 Registry 的元数据来源 |

---

# 2. 差距分析

对照设计规范第 2/3 节目标能力逐项对比：

| # | 目标能力 | 规范章节 | 现状评估 | 差距 |
|---|---|---|---|---|
| 1 | Agent 注册与发现 | §4 | 🟡 部分具备：GET /api/agents 合并 AGENT_REGISTRY + agents 表 | 卡片缺 version / 在线状态 / 最后运行时间 / 当前模型；无统一 Registry 元数据源 |
| 2 | Agent Detail | §5 | 🔴 缺失 | 无详情页、无 /api/agents/{id}、无 Dependencies 视图 |
| 3 | Agent 生命周期管理 | §18 | 🟡 部分具备：agents.is_active 字段存在 | 无 enable/disable API、无生命周期状态机（registered→active→paused→deprecated） |
| 4 | 配置管理 | §14 | 🟡 部分具备：agents 表有 model/temperature/config | 无编辑 API、无回滚、无热更新 |
| 5 | Prompt 管理 | §6 | 🟡 部分具备：文件型 Prompt Hub（loader.py） | 无 DB 持久化、无版本/历史、无在线编辑、无变量预览 |
| 6 | Skill 管理 | §7 | 🟡 部分具备：运行时 skills/registry.py | 无查询 API、无 enable/disable/reload、无 UI |
| 7 | Tool 管理 | §8 | 🟡 部分具备：tools/ 12 个工具模块 | 无注册清单 API、无状态/平均耗时/调用次数/错误率统计 |
| 8 | MCP 管理 | §9 | 🔴 缺失 | mcp_servers.yaml 只有 2 个禁用占位；knowledge/news MCP 未纳管；无心跳/延迟/重试统计 |
| 9 | Workflow 管理 | §10 | 🟡 部分具备：workflows.yaml + graphs 编译缓存 | WorkflowPage 是任务监控而非图可视化；无 Workflow Graph / Source / Version 展示 |
| 10 | Memory 管理 | §11 | 🟡 部分具备：三层记忆架构已落地 | 无 Memory 查看 API/UI（context tokens、history、compression 开关展示） |
| 11 | 运行监控 | §12 | 🔴 缺失 | research_tasks 只记录研究类任务；无统一 agent_runs 记录、无 Runs/Latency/Tokens/Cost 聚合 |
| 12 | 日志分析 | §13 | 🟡 部分具备：task_logs（任务级）、BaseAgent 日志写 stdout | 无 Agent 运行级结构化日志、无搜索/筛选/下载/Trace |
| 13 | 性能统计 | §12 | 🟡 部分具备：tasks/stats、research_tasks 含耗时 | 无按 Agent 维度的趋势图表 |
| 14 | 热更新 / 版本控制 / A/B / Marketplace / 权限 | §17 Phase 4 | 🔴 缺失 | 全部待建 |

**结论**：注册与发现、配置、Prompt、Skill、Memory 是"扩展"；Detail、MCP 管理、运行监控、Trace 是"新建"；任务系统、健康检测、Scheduler 是"复用"。

---

# 3. 实施计划

> 依赖链总览：
> `DB 迁移 → Agent Registry API 增强 → 前端 Registry/Detail 页` →（Phase 1 收尾）→ `能力管理 API（Skill/Tool/MCP/Memory）` →（Phase 2）→ `运行埋点 agent_runs → Metrics/Logs/Workflow 可视化` →（Phase 3）→ `高级能力`（Phase 4）

## Phase 1：核心功能（Registry / Detail / Prompt / Configuration）

### P1-1 数据库迁移（新建幂等迁移文件）

新建 `postgres/init/13-agent-center.sql`：

```sql
-- 1. agents 表扩展（幂等）
ALTER TABLE agents ADD COLUMN IF NOT EXISTS version VARCHAR(20) DEFAULT 'v1.0';
ALTER TABLE agents ADD COLUMN IF NOT EXISTS display_name VARCHAR(100);
ALTER TABLE agents ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active';  -- active/paused/deprecated
ALTER TABLE agents ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMPTZ;

-- 2. agent_prompts 表：Prompt 持久化 + 版本
CREATE TABLE IF NOT EXISTS agent_prompts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(100) NOT NULL,          -- 对应 AGENT_REGISTRY key（chat/research/kb/investment）
    name VARCHAR(100) NOT NULL,              -- 如 "system" / "planner"
    content TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(agent_id, name, version)
);

-- 3. agent_configs_history 表：配置回滚
CREATE TABLE IF NOT EXISTS agent_configs_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(100) NOT NULL,
    config JSONB NOT NULL,
    changed_by VARCHAR(100) DEFAULT 'ui',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. agent_runs 表：Agent 运行记录（Metrics/Logs 统一数据源，已确认新建）
CREATE TABLE IF NOT EXISTS agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(100) NOT NULL,
    task_kind VARCHAR(50) NOT NULL,          -- chat / research / pipeline
    status VARCHAR(20) DEFAULT 'running',    -- running / success / failed
    question TEXT,
    duration_ms BIGINT,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    error TEXT,
    error_category VARCHAR(50),              -- tool_timeout / embedding_error / mcp_error / other
    trace JSONB DEFAULT '[]',                -- 节点级轨迹
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent ON agent_runs(agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status, created_at);
```

- **验收标准**：在已运行的存量 DB 上执行不报错、可重复执行；`docker compose exec postgres psql` 验证表/列存在。
- **注意**：init 目录脚本对已初始化容器不生效，需将迁移同时通过 `psql -f` 手动应用一次（沿用 12-task-logs.sql 的先例模式）。

### P1-2 Agent Registry 增强（后端）

修改 `langgraph/api/agents.py`：

1. `GET /api/agents` 扩展返回字段：`version`、`status`、`last_active_at`、`current_model`（运行时从 agents.yaml + policies.yaml 合并）、`workflows`（关联 workflows.yaml 中以该 agent 为入口的图）。
2. 内置 Agent 元数据来源：新建 `langgraph/config/agent_meta.yaml`（名称/描述/版本/作者，对齐 specs/agent-registry.yaml 的规范命名），`list_agents()` 合并三方数据：AGENT_REGISTRY（运行时）+ agents 表（配置）+ agent_meta.yaml（元数据）。
3. 新增 `GET /api/agents/{agent_id}`：基本信息、Runtime（model/temperature/context/timeout，读 agents 表 config）、Dependencies（skills/tools/mcp/workflow/memory 静态映射表，Phase 2 前可先声明式配置）。
4. 新增 `POST /api/agents/{agent_id}/toggle`：更新 agents.is_active / status（生命周期最小闭环）。

- **验收标准**：curl `/api/agents` 返回 4 个内置 Agent 且含 version/status/last_active_at；toggle 后再查状态翻转。

### P1-3 Agent Registry 卡片升级（前端）

修改 `frontend/src/app/pages/AgentsPage.tsx` + `services/agents.ts`：

1. 卡片补齐规范 §4 要素：状态点（Running/Paused）、Version、Last Active（相对时间）、当前模型。
2. 卡片可点击 → 跳转 `/agents/:id`。
3. `services/agents.ts` 扩展 `AgentDetail` 类型与 `fetchAgentDetail()`。

- **验收标准**：页面卡片与规范 §4 展示内容一一对应；点击卡片进入详情页（路由存在）。

### P1-4 Agent Detail 页（前端，新建）

新建 `frontend/src/app/pages/AgentDetailPage.tsx`，路由 `/agents/:id`（router.tsx 注册，lazy 加载）：

- 布局参考规范 §16 与 KnowledgePage 的多 Tab 模式：基本信息卡、Runtime 卡、Dependencies 卡。
- Tabs：`概览 | Prompt | 配置`（Phase 2 追加 Skills/Tools/MCP/Memory Tab）。
- **验收标准**：任一 Agent 详情页可展示规范 §5 全部字段；刷新不丢失；返回 Registry 正常。

### P1-5 Prompt 管理 —— 全量迁移 DB（已确认）

后端：

1. **迁移脚本**：新建 `langgraph/scripts/migrate_prompts_to_db.py` —— 扫描 `prompts/` 下全部 .md 文件，按目录层级生成 `agent_id`（chat/research/kb/investment/news/knowledge + 通用节点 planner/reason/reflect/writer/query_rewrite 归入 `common`）与 `name`，以 version=1 写入 `agent_prompts` 表。可重复执行（幂等：已存在则跳过）。
2. **loader 改造**：`langgraph/prompts/loader.py` 改为**仅读 DB**（is_active 最高 version），`load_prompt(name)` 签名保持兼容；移除 lru_cache 文件路径，改用进程内 dict 缓存 + `invalidate_prompt_cache(agent_id, name)`。
3. **调用点切换**：全局检索 `load_prompt(` 调用点（nodes/、agents/、skills/），确认参数与新命名映射一致，逐一回归。
4. **文件清理**：迁移验证通过后删除 `prompts/*.md`（保留 loader.py），DB 成为唯一事实源。
5. API：`GET /api/prompts?agent_id=`、`GET /api/prompts/{agent_id}/{name}`（当前版本+历史）、`PUT /api/prompts/{agent_id}/{name}`（保存新版本）、`POST /api/prompts/preview`（变量替换预览）、`POST /api/prompts/cache/invalidate`。

前端，AgentDetailPage 的 Prompt Tab：

1. 版本选择下拉 + 编辑器（textarea/Monaco）+ 变量高亮（`{var}`）。
2. Preview：输入变量值 → 调 preview 接口渲染结果。
3. **验收标准**：迁移脚本执行后 DB 中 prompt 条数 = 原文件数；服务重启后全部 prompt 加载自 DB；在线修改保存后下一次请求生效；历史版本可切回；删除 md 文件后功能不受影响。

### P1-6 Configuration 配置管理（后端 + 前端）

后端（`api/agents.py`）：

1. `PUT /api/agents/{agent_id}/config`：校验后更新 agents 表（model/temperature/top_p/max_tokens/timeout/retry），写 agent_configs_history。
2. `GET /api/agents/{agent_id}/config/history` + `POST /api/agents/{agent_id}/config/rollback`。
3. 热生效：配置读取方改为运行时查询（policies.yaml 默认值 → agents 表覆盖），保证"保存即生效"（无需重启）。

前端：AgentDetailPage 配置 Tab —— 表单（Model 下拉复用 /api/models、Temperature、Top P、Max Tokens、Timeout、Retry）+ 保存 + 历史回滚。

- **验收标准**：修改 temperature 保存 → 新请求生效；回滚到上一版本成功；非法值（如 temperature>2）被拒绝。

## Phase 2：能力管理（Skill / Tool / MCP / Memory）

### P2-1 Skill 管理

1. 后端：扩展 `langgraph/skills/registry.py` —— 增加 `enabled` 标志、`reload()`、注册元数据（version/updated_at）；新建 `api/skills.py`：`GET /api/skills`、`POST /api/skills/{name}/toggle`、`POST /api/skills/{name}/reload`，在 server.py 注册。
2. 前端：AgentDetailPage Skills Tab —— 卡片列表（名称/Version/更新时间/启用开关）。
3. **验收标准**：禁用 rag_search 后 chat agent 降级为无检索模式并可在 UI 看到状态变化；reload 不重启服务。

### P2-2 Tool 管理与调用统计

1. 新建 `langgraph/services/tool_metrics.py`：装饰器/中间件统一包装 tools/ 下工具调用，记录到 PG 新表 `agent_tool_stats`（tool_name/agent_id/duration_ms/success/error_type/created_at，建在 13-agent-center.sql 或新增 14 迁移）。
2. 新建 `api/tools.py`：`GET /api/tools`（清单 + 状态探测：postgres/qdrant/minio/docling/embedding/reranker 复用 health 探测）、`GET /api/tools/stats`（平均耗时/调用次数/错误率，SQL 聚合）。
3. 前端：AgentDetailPage Tools Tab —— 表格（状态/平均耗时/调用次数/错误率）。
4. **验收标准**：触发一次研究任务后，tool stats 中 retrieve/embedding 等出现调用记录与耗时。

### P2-3 MCP 管理

1. 更新 `langgraph/config/mcp_servers.yaml`：纳入 knowledge（mcp-knowledge 服务地址）、news（:8201）、data（postgres-mcp 预留）、search（预留），含 url/enabled 字段。
2. 扩展 `api/health.py` 的 `_check_mcp`：记录 last_heartbeat / latency / retry_count 到内存 + 定期落 PG（`mcp_connections` 表，13/14 迁移）。
3. 新建 `api/mcp.py`：`GET /api/mcp`（Connection Status / Last Heartbeat / Latency / Retry Count）。
4. 前端：AgentDetailPage MCP Tab + MonitorPage 增加 MCP 区块（复用 `['health']` 缓存键模式，遵守 MonitorPage 健康检测行为规范）。
5. **验收标准**：停掉 mcp-news 容器后，UI 在下一个探测周期内显示 Disconnected 且 Retry Count 递增。

### P2-4 Memory 管理

1. 扩展 `langgraph/memory/memory_store.py`：新增 `get_memory_summary(agent_type)` —— 聚合 Conversation（checkpoint 条数/估算 tokens）、Episodic（research_tasks 计数/最近记录）、Vector（Qdrant collection 统计）、Graph（AGE 节点/边计数，可选失败降级）。
2. 新建 `api/memory.py`：`GET /api/memory?agent_id=`。
3. 前端：AgentDetailPage Memory Tab —— 四类记忆卡片（Current Context Tokens / History 开关 / Compression 开关，开关先展示配置不强制生效）。
4. **验收标准**：Memory Tab 四类数据均有真实来源；AGE/Qdrant 不可用时优雅降级为空态。

## Phase 3：可视化（下批，Workflow Graph / Metrics / Dashboard / Logs / Trace）

### P3-1 运行记录埋点（✅ 提前至本批：agent_runs 建表已在 P1-1，埋点随 P2-2 一并落地）

1. ✅ 建表：已并入 P1-1（13-agent-center.sql §4）。
2. 修改 `agents/base_agent.py`：run/stream_run 统一写 agent_runs（复用现有 start_episode/complete_episode 时机，不双写丢失一致性）；pipeline 类 Agent（news/knowledge/document）在 graph 调用入口同样埋点。**本批完成**。
3. Scheduler 每日归档 job（90 天前 agent_runs 清理）挂到 `runtime/scheduler.py`。**本批完成**。
4. **验收标准**：一次 chat + 一次 research + 一次 news pipeline 后 agent_runs 各有一条记录，trace 字段含节点序列。

### P3-2 Workflow Graph 可视化（已确认：LangGraph 原生导出 + ReactFlow）

1. 后端 `api/workflows.py`（新建）：`GET /api/workflows` 从 workflows.yaml 生成列表；`GET /api/workflows/{name}/graph` 输出节点/边 JSON —— 优先用 LangGraph 原生 `graph.get_graph().to_json()`（已确认），失败时回退到各 graph 模块内手工声明的静态节点序列（规范 §10 的线性图即可先满足）。
2. 前端 WorkflowPage 新增 "Workflow 图" Tab（与现有任务 Tab 并列，规范 §10 明确"在 workflow 页建立"）：用 ReactFlow（`npm i reactflow`，已确认）渲染；支持选择 workflow、查看节点描述、预览 Source（builder 所在模块）。
3. **验收标准**：6 个 workflow 全部可渲染；research 图呈现 Planner → Retrieve → Rerank → Reason → Reflect → Finish 链路。

### P3-3 Runtime Metrics

1. 后端 `api/metrics.py`（扩展现有 /metrics 或新建 agent 维度端点）：`GET /api/agents/{id}/metrics?range=7d` —— Today Runs / Success / Failed / Avg Latency / Avg Tokens / Avg Cost（cost 按 providers.yaml 单价计算，无单价时置 0）+ 趋势序列（Runs/Latency/Tokens/Error Rate）。
2. 前端：AgentDetailPage 顶部指标卡 + 图表（复用项目现有图表方案，如 recharts，若未引入则 `npm i recharts`）。
3. **验收标准**：与规范 §12 六项指标一一对应；时间范围切换数据正确。

### P3-4 Agent Center Dashboard 布局

1. 重构 AgentsPage 为规范 §16 布局：上方三栏（Agent Registry | Runtime Metrics 汇总 | Recent Logs），入口保留 `/agents`。
2. 全局汇总数据来自 `/api/agents` + 新 `/api/agents/summary`（全部 Agent 的今日运行/失败数）。
3. **验收标准**：首屏与规范 §16 布局一致；卡片点击进入 Detail。

### P3-5 Logs 与 Trace

1. 后端 `api/logs.py`（新建）：`GET /api/logs?agent_id=&status=&keyword=&page=`（agent_runs + task_logs 联合视图）、`GET /api/logs/{run_id}/trace`（节点级轨迹 + 各节点耗时）、`GET /api/logs/export`（CSV 下载）。
2. 前端：AgentDetailPage Logs Tab —— 表格（时间/Agent/状态/耗时）+ 行展开显示 Trace 时间线（Started → Retrieve → Tool → Finished，失败显示 Tool Timeout / Embedding Error / MCP Error 分类）+ 搜索/筛选/下载按钮。
3. **验收标准**：可按状态筛选失败记录；任一失败记录可展开看到失败节点与错误分类；CSV 可下载。

## Phase 4：高级能力（规范 §17，可并行排期）

| 任务 | 内容 | 验收标准 |
|---|---|---|
| P4-1 Agent 热更新 | agents.yaml/policies.yaml 文件监听 + `POST /api/agents/reload` 重建 AGENT_REGISTRY（importlib.reload 级别），不断开在途请求 | 改 yaml 后 reload，新请求路由到新配置，无服务重启 |
| P4-2 Prompt Version Control | agent_prompts 已具备版本基础；补 diff 视图、分支/草稿、发布审批（可复用 approvals API） | 两版本 diff 可视化；发布需审批通过 |
| P4-3 A/B Prompt Test | agent_prompts 增加 traffic_weight；运行记录按 variant 打标；Metrics 按 variant 对比 | 同一 Agent 两版 prompt 分流并对比成功率/耗时 |
| P4-4 Agent Marketplace | agent_templates 表 + 导入/导出 Agent 定义 JSON | 导出 Agent 定义可在另一实例导入 |
| P4-5 多 Agent 协同监控 | 基于 agent_runs.trace 关联跨 Agent 调用链（news → knowledge ingestion），Trace 页聚合展示 | 一次新闻入库可追踪到两个 Agent 的衔接 |
| P4-6 Agent 权限管理 | agents 表加权限字段 + API 级校验中间件（先做开关粒度，后做角色） | 停用 Agent 后其 API 返回 403 |

## 落地顺序与依赖总表（本批 = Phase 1 + 2 + P3-1 埋点）

```
【本批】
P1-1 (DB迁移，含agent_runs) ──→ P1-2 (Registry API) ──→ P1-3 (卡片) ──→ P1-4 (Detail页)
                                                                            │
              P1-5 (Prompt全量迁移DB，含迁移脚本) ←─────────────────────────┤
              P1-6 (Config) ←───────────────────────────────────────────────┘
P2-1~P2-4 可并行（均依赖 P1-4 的 Tabs 容器）
P3-1 (agent_runs埋点+归档job) 与 P2-2 同步落地（本批）

【下批】
P3-2 (Workflow图, ReactFlow) 独立可先行
P3-1 数据就绪后 ──→ P3-3 (Metrics) / P3-5 (Logs)
P3-4 (Dashboard) 依赖 P3-3
Phase 4 各项依赖 Phase 1-3 对应基座
```

---

# 4. 风险与建议

| # | 风险 | 影响 | 应对建议 |
|---|---|---|---|
| 1 | **存量 DB 迁移不生效**：postgres init 脚本仅首次初始化执行 | Phase 1 全部表结构缺失，API 500 | 迁移文件保持幂等；上线时对运行中容器手动 `psql -f` 一次；在 CI/部署文档中固化该步骤（沿用 12-task-logs.sql 先例） |
| 2 | **数据双写不一致**：agent_runs 与 research_tasks、tasks 三套运行记录并存 | Metrics/Logs 口径混乱 | P3-1 埋点复用 BaseAgent 现有 episode 钩子；明确口径：research_tasks=研究语义记录、tasks=Pipeline 任务、agent_runs=Agent Center 指标源；禁止在节点层重复埋点 |
| 3 | **Prompt 全量迁移 DB 的切换风险**（已确认选全量迁移）：迁移脚本遗漏文件、调用点参数映射错误、删除 md 后无法回退 | 全部 Agent 提示词加载失败，线上功能受损 | 迁移脚本幂等可重复执行并输出对账清单（文件数 vs DB 行数）；切换前在容器内跑通 chat/research/kb/investment 各一次冒烟；删除 md 前 git 保留提交点以便整体回滚；loader 提供 DB 不可用时的明确报错而非静默降级 |
| 4 | **前端路由冲突**：/agents/:id 与现有 /agents 共存 | 路由匹配歧义 | router.tsx 中 `/agents` 与 `/agents/:id` 分开声明（React Router v6 支持），AgentsPage 保持 index 语义 |
| 5 | **内置 Agent 无持久化行**：AGENT_REGISTRY 的 4 个内置 Agent 在 agents 表无记录，配置编辑无落点 | P1-6 保存失败 | 服务启动 lifespan 中对内置 Agent 做 upsert（`INSERT ... ON CONFLICT(name) DO NOTHING`），保证表行存在 |
| 6 | **MCP 探测阻塞健康接口**：/health 同步探测多个 MCP 延迟叠加 | MonitorPage 轮询超时 | 探测并发化（asyncio.gather，现状已如此）+ 独立超时 3s；MCP 状态走独立缓存键，避免与全局 `['health']` 键竞争刷新（遵守 React Query 缓存键隔离原则） |
| 7 | **工具埋点侵入性**：tool_metrics 包装 12 个工具模块，改动面大 | 回归风险 | 采用非侵入方式：在 tools 的统一出口（如 postgres_tool.query 的调用方 BaseAgent/节点层）或装饰器按模块逐个接入，每接一个跑一次既有回归路径 |
| 8 | **WorkflowPage 语义漂移**：该页已是任务中心，再加 Workflow 图 Tab 可能过载 | 页面职责混乱 | 图可视化放独立 Tab 且懒加载；若后续膨胀，再将任务中心拆为 /tasks、图留在 /workflow |
| 9 | **后端 API 缺失导致前端空态**：Phase 2/3 多个端点新建 | 前端联调阻塞 | 前端先用 MSW/固定 mock 数据开发 Tabs 骨架，后端按 P2 顺序交付；每个 Tab 必须有 EmptyState 降级 |
| 10 | **WSL 开发环境**：前端在 WSL 挂载盘需重启 vite 才生效；Docker 命令需 docker.exe | 验证环节误判 | 验证阶段遵循既有环境约定，重启 dev server 后再做浏览器验证 |

---

# 附录：涉及文件清单（速查）

**新建**
- `postgres/init/13-agent-center.sql`（含 agent_prompts / agent_configs_history / agent_runs，无需 14 迁移）
- `langgraph/api/prompts.py`、`api/skills.py`、`api/tools.py`、`api/mcp.py`、`api/memory.py`
- `langgraph/scripts/migrate_prompts_to_db.py`（Prompt 全量迁移脚本，已确认）
- `langgraph/config/agent_meta.yaml`
- `langgraph/services/tool_metrics.py`
- `frontend/src/app/pages/AgentDetailPage.tsx`

**删除（Prompt 全量迁移验证通过后）**
- `langgraph/prompts/*.md` 全部模板文件（保留 `loader.py`，改为 DB 读取）

**修改**
- `langgraph/api/agents.py`、`api/server.py`、`api/health.py`
- `langgraph/agents/base_agent.py`（agent_runs 埋点，本批）、`prompts/loader.py`（全量改 DB，本批）、`skills/registry.py`
- `langgraph/config/mcp_servers.yaml`、`runtime/scheduler.py`（agent_runs 归档 job，本批）
- `frontend/src/app/router.tsx`、`app/pages/AgentsPage.tsx`
- `frontend/src/services/agents.ts`（+ 新增 prompts/tools/mcp/memory service 文件）

**下批（Phase 3 时再动）**
- `langgraph/api/workflows.py`、`api/metrics.py`、`api/logs.py`
- `frontend/src/app/pages/WorkflowPage.tsx`（新增 Workflow 图 Tab，ReactFlow）

**复用（不改或仅加 Tab）**
- 任务系统：`api/tasks.py` + `tasks`/`task_logs` 表 + `services/tasks.ts`
- 健康检测：`api/health.py` 探测框架、HealthProvider、`['health']` 缓存键
- 知识中台组件模式：`components/knowledge/`（布局范式参考）
