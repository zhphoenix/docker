# AI Platform 分层架构重构计划

## 一、整体评估

### 1.1 当前架构与目标架构的主要差距

| 维度 | 当前状态 | 目标状态 | 差距等级 |
|------|---------|---------|---------|
| 交互层 | Gradio WebUI（单体） | Open WebUI + OpenAI Compatible API | 高 |
| 编排层 | 无（直接函数调用） | LangGraph Workflow + Agent Dispatcher | 高 |
| 知识层 | 无统一管理 | Prompt Hub / Skill Hub / MCP Registry / Provider Registry / Policy Center / Memory | 高 |
| 数据层 | SQLite + 本地文件 + 零散 Qdrant | PostgreSQL(业务真相源) + Qdrant(语义索引) + MinIO(文件真相源) | 中 |
| 运行环境 | 本地 Python 进程 | Docker Compose 统一编排 + Resource Scheduler | 中 |
| Agent 体系 | 单一 research_agent 模块 | 多 Agent（Chat/Research/Knowledge/Investment）+ 可扩展 | 高 |
| 任务系统 | TaskManager + PostgreSQL（已部分实现） | Queue + Checkpoint + Retry + Human Approval | 中 |
| 数据源管理 | providers.yaml（103 Provider，已有） | Provider Registry（数据库化 + API 化） | 低 |

### 1.2 重构优先级和预期收益

**优先级排序**（按依赖关系和价值）：
1. Infrastructure 层（PostgreSQL/MinIO/Qdrant 统一） — 一切的基础
2. Runtime 层（LangGraph + FastAPI） — 系统核心引擎
3. Knowledge 层（Prompt/Skill/MCP/Provider/Memory） — Agent 能力基座
4. Environment 层（Docker Sandbox/Scheduler） — 运维自动化
5. 多 Agent 协作 — 最终业务价值

**预期收益**：
- 新增 Agent 从"改代码"变为"加配置 + 写 Graph"
- 数据源切换/升级只需重跑 Pipeline，无需数据迁移
- 统一任务追踪、断点恢复、人工审批
- Open WebUI 提供专业对话界面，支持多模型切换

### 1.3 潜在风险及缓解措施

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 重构期间旧系统不可用 | 投研工作中断 | 新旧共存，逐模块切换 |
| LangGraph 学习曲线 | 开发效率下降 | 先实现最简 Graph，逐步复杂化 |
| 数据量大（~20000 PDF） | 迁移/重建耗时长 | 分批处理，优先高频股票 |
| Docker 资源占用 | WSL2 内存不足 | 按需启停服务，非核心服务延迟加载 |
| Checkpoint 数据膨胀 | PostgreSQL 性能下降 | 定期清理过期 Checkpoint |

---

## 二、分阶段重构路线图

### Phase 1: Infrastructure 统一数据底座（预计 5-7 天）

**目标**：建立 PostgreSQL + MinIO + Qdrant 统一数据底座，替代 SQLite + 本地文件。

**具体任务**：

1. Docker Compose 基础设施确认
   - 确认 `/mnt/e/docker/` 下 postgres/qdrant/minio 服务正常运行
   - 创建 `ai` 和 `langgraph` 两个数据库
   - 执行建表 SQL（documents/chunks/tasks/agents/collections/companies）
   - 文件：`/mnt/e/docker/postgres/init/01-init.sql`

2. MinIO Bucket 初始化
   - 创建 5 个 Bucket：documents/knowledge/datasets/artifacts/staging
   - 配置 Access Key 角色（agent/docling/backup/readonly）
   - 文件：`/mnt/e/docker/minio/init_buckets.py`（新建）

3. 数据底座 SDK 层
   - 从 Value_capitalism 提取并重构：
     - `src/core/minio_client.py` → 新平台 `tools/minio.py`
     - `src/data_layer/vector_store.py` → 新平台 `tools/qdrant.py`
     - `src/data_layer/financials_db.py` → 新平台 `tools/postgres.py`
   - 统一连接配置（Pydantic Settings）

4. PDF 资产导入脚本
   - 将 `data/stock_a/`、`data/stock_h/`、`data/stock_us/` 中的 PDF 上传到 MinIO `documents/` Bucket
   - 将 `data/analysis_reports/` 上传到 `artifacts/research/`
   - 生成 metadata.json 并写入 PostgreSQL documents 表

5. 财务数据 ETL
   - AkShare → PostgreSQL（financial_income/financial_balance/financial_cashflow/company_basic）
   - 复用 `src/data_layer/financials_db.py` 逻辑，改写入 PostgreSQL

**验收标准**：
- PostgreSQL 中 documents 表有完整文档索引
- MinIO 中 PDF 按 `documents/{market}/{symbol}/{type}/{year}/report.pdf` 组织
- Qdrant Collection（documents_cn/hk/us）已创建
- 旧 SQLite 不再被任何新代码引用

---

### Phase 2: Runtime 核心引擎（预计 7-10 天）

**目标**：搭建 FastAPI + LangGraph 核心引擎，实现 OpenAI Compatible API。

**具体任务**：

1. 项目骨架搭建（在 `/mnt/e/docker/langgraph/agent/` 下）
   ```
   agent/
   ├── app/main.py              # FastAPI 实例
   ├── api/chat.py              # /v1/chat/completions
   ├── api/models.py            # /v1/models
   ├── api/health.py            # /health
   ├── graph/builder.py         # Graph 构建器
   ├── graph/state.py           # AgentState
   ├── graph/router.py          # Agent Dispatcher
   ├── graph/checkpoint.py      # PostgreSQL Checkpoint
   ├── agents/base_agent.py     # Agent 基类
   ├── agents/chat_agent.py     # Chat Agent
   ├── nodes/                   # planner/retrieve/rerank/reason/reflect/finish
   ├── tools/                   # llm/qdrant/postgres/embedding/reranker/minio/obsidian
   ├── prompts/                 # Markdown 模板
   ├── config/settings.py       # Pydantic Settings
   └── schemas/                 # Pydantic 模型
   ```

2. LangGraph 基础 Workflow
   - 实现 State 定义（AgentState TypedDict）
   - 实现 6 个核心 Node：planner → retrieve → rerank → reason → reflect → finish
   - 条件路由：reflect 质量不足时回到 retrieve（最多 2 次）
   - Checkpoint：AsyncPostgresSaver → `langgraph` 数据库

3. OpenAI Compatible API
   - POST `/v1/chat/completions`（流式 + 非流式）
   - GET `/v1/models`
   - GET `/health`
   - 请求链路：Open WebUI → FastAPI → Agent Dispatcher → LangGraph → 流式返回

4. Tool 层实现
   - `tools/llm.py`：调用 llama.cpp / 百炼 API
   - `tools/qdrant.py`：向量检索（复用 Value_capitalism 逻辑）
   - `tools/postgres.py`：SQL 查询
   - `tools/embedding.py`：调用 Embedding Service :8001
   - `tools/reranker.py`：调用 Reranker :8002
   - `tools/minio.py`：文件读写
   - `tools/obsidian.py`：通过 MCP 读写 Vault

5. Docker 化部署
   - 编写 `Dockerfile`（Python 3.11-slim）
   - 编写 `compose.yml`（加入 ai-platform 网络）
   - 环境变量从 `/mnt/e/docker/.env` 加载

**验收标准**：
- `curl http://localhost:8100/health` 返回 200
- Open WebUI 配置后端为 `http://langgraph:8100/v1` 后可正常对话
- 对话触发 RAG 检索（Qdrant）并返回基于文档的回答
- Checkpoint 正常写入 `langgraph` 数据库

---

### Phase 3: Knowledge 层 + 多 Agent（预计 7-10 天）

**目标**：实现知识中心六大组件，支持多 Agent 协作。

**具体任务**：

1. Prompt Hub
   - `prompts/` 目录管理所有 Prompt 模板（Markdown 格式）
   - `prompts/loader.py`：统一加载器，支持变量插值
   - 按 Agent 分子目录：`prompts/chat/`、`prompts/research/`、`prompts/investment/`

2. Skill Hub
   - 定义 Skill 接口：`skills/base_skill.py`
   - 将 Value_capitalism 的分析能力封装为 Skill：
     - `skills/master_analysis/`（大师分析框架）
     - `skills/financial_analysis/`（财务分析）
     - `skills/rag_search/`（RAG 检索）
   - Skill 注册表：`skills/registry.py`

3. MCP Registry
   - 配置 Obsidian MCP Server（已有 obsidian-vault）
   - 预留 GitHub/Filesystem/Database MCP
   - `tools/mcp_client.py`：MCP 协议客户端封装

4. Provider Registry（数据库化）
   - 将 `agents/providers.yaml`（103 Provider）导入 PostgreSQL `providers` 表
   - 新建表：providers(id, name, category, base_url, priority, status, config)
   - API：GET `/api/providers`、POST `/api/providers/{id}/test`
   - 保留 Source Selection Agent 的决策逻辑

5. Policy Center
   - 定义策略配置：`config/policies.yaml`
   - 包含：数据源优先级、Fallback 规则、Rate Limit、重试策略
   - 运行时可热更新

6. Memory 系统
   - 工作记忆：LangGraph Checkpoint（PostgreSQL `langgraph` 库）
   - 情景记忆：PostgreSQL `research_tasks` 表
   - 知识记忆：Qdrant + Obsidian Vault

7. 多 Agent 实现
   - Chat Agent：简单 RAG 问答（Retrieve → Reason → Finish）
   - Research Agent：完整 Workflow（已有设计）
   - Knowledge Agent：Vault 读写 + 索引维护
   - Investment Agent：DCF + 竞争分析 + 多工具
   - Agent Dispatcher：基于意图分类路由

**验收标准**：
- 新增 Agent 只需：创建 Graph 文件 + 注册路由，不改现有代码
- Open WebUI 中可选择不同 Agent 对话
- Research Agent 完成分析后自动写入 Obsidian Vault
- Provider Registry API 可查询、测试数据源

---

### Phase 4: Environment 层 + 自动化 Pipeline（预计 5-7 天）

**目标**：实现 Docker Sandbox、Resource Scheduler 和全自动数据 Pipeline。

**具体任务**：

1. 统一 Docker Compose
   - 保持独立 compose + 共享网络）
   - 服务清单：PostgreSQL / MinIO / Qdrant / Docling / Embedding / Reranker / LangGraph / OpenWebUI 
   - 健康检查 + 依赖顺序（depends_on + healthcheck）

2. 文档处理 Pipeline（LangGraph Workflow）
   ```
   下载 PDF → MinIO staging → Docling 解析 → report.md + chunks.json
   → Embedding → Qdrant → PostgreSQL 状态更新 → 完成
   ```
   - 实现为独立 Graph：`graphs/pipeline_graph.py`
   - 支持批量处理、断点续传

3. Resource Scheduler
   - 基于 `schedule` 或 APScheduler 的定时任务：
     - 每日：下载新公告/年报 → 触发 Pipeline
     - 每周：全量 Embedding 一致性检查
     - 每月：清理 staging Bucket + 过期 Checkpoint
   - 集成到 FastAPI 生命周期

4. Queue 机制
   - 短期：PostgreSQL `tasks` 表作为简单队列（status: pending → running → done）
   - 中期：引入 Redis + Celery（如果并发需求增大）
   - 任务优先级 + 并发限制

5. Retry 机制
   - Node 级别：LangGraph 条件路由实现自动重试（reflect → retrieve）
   - Task 级别：tasks 表记录 retry_count，超过阈值标记 failed
   - 指数退避策略

6. Human Approval（人审）
   - LangGraph `interrupt_before` / `interrupt_after` 机制
   - 应用场景：Agent 生成报告后等待人工确认再写入 Vault
   - Open WebUI 中展示待审批任务

**验收标准**：
- `docker compose up -d` 一键启动全部服务
- 新 PDF 放入指定目录后自动完成全链路处理
- 任务失败后自动重试（最多 3 次）
- 人审流程：Agent 输出 → 等待 → 人工确认 → 继续

---

### Phase 5: 旧系统退役 + 数据重建（预计 3-5 天）

**目标**：完成 Value_capitalism 历史数据重建，旧系统正式退役。

**具体任务**：

1. 批量文档重建
   - 对 MinIO 中所有 PDF 重新跑 Docling → Chunk → Embedding → Qdrant
   - 分批处理（每批 100 个），优先高频股票（茅台、腾讯、苹果等）
   - 进度追踪：tasks 表记录每个文档状态

2. Vault 自动生成
   - Vault Generator 从 Platform 数据自动生成 Obsidian 笔记
   - 目录：`03_Investment/Companies/{symbol}/`
   - 包含：README.md / Financial.md / Timeline.md / Research.md

3. 旧系统退役
   - Value_capitalism 保留为只读历史存档
   - 移除 Gradio WebUI 入口
   - SQLite 文件归档备份后不再使用
   - 旧 Qdrant Collection 删除（已由新 Pipeline 重建）

4. 监控与告警（基础版）
   - FastAPI `/health` 端点聚合所有依赖服务状态
   - 日志统一输出（structlog / loguru）
   - 关键指标：任务成功率、Pipeline 延迟、Qdrant 查询延迟

**验收标准**：
- 所有 PDF 已完成 Docling + Embedding + Qdrant 索引
- Obsidian Vault 自动生成的公司笔记可正常浏览
- Value_capitalism 不再有任何活跃进程
- 系统健康检查全部绿色

---

## 三、Knowledge 层实现方案

### 3.1 组件设计

```
Knowledge Layer
├── Prompt Hub          # prompts/ 目录 + loader.py
│   ├── chat/           # Chat Agent 提示词
│   ├── research/       # Research Agent 提示词
│   ├── investment/     # Investment Agent 提示词
│   └── loader.py       # 统一加载 + 变量插值
│
├── Skill Hub           # skills/ 目录 + registry.py
│   ├── base_skill.py   # Skill 接口定义
│   ├── master_analysis/# 大师分析框架
│   ├── financial_analysis/
│   └── registry.py     # Skill 注册 + 发现
│
├── MCP Registry        # config/mcp_servers.yaml
│   ├── obsidian-vault  # 已配置
│   ├── github          # 预留
│   └── filesystem      # 预留
│
├── Provider Registry   # PostgreSQL providers 表 + API
│   ├── 103 Providers   # 从 providers.yaml 导入
│   ├── 优先级 + Fallback
│   └── 健康检查 API
│
├── Policy Center       # config/policies.yaml
│   ├── 数据源优先级
│   ├── Rate Limit
│   └── 重试策略
│
└── Memory              # 三层记忆
    ├── 工作记忆        # LangGraph Checkpoint
    ├── 情景记忆        # PostgreSQL research_tasks
    └── 知识记忆        # Qdrant + Obsidian
```

### 3.2 新增 Agent 简化流程

新增一个 Agent 只需 3 步：

1. 创建 Graph 文件：`agents/my_agent.py`（继承 BaseAgent，定义 Workflow）
2. 创建 Prompt：`prompts/my_agent/system.md`
3. 注册路由：在 `graph/router.py` 添加意图匹配规则

无需修改：现有 Agent、Node、Tool、API 层代码。

---

## 四、Runtime 层实现方案

### 4.1 LangGraph Workflow 设计

```
用户请求 → FastAPI → Agent Dispatcher
                         │
                    ┌────┴────┐
                    ▼         ▼
              Chat Agent   Research Agent   Investment Agent
                    │         │                    │
                    ▼         ▼                    ▼
              [简单Graph] [完整Graph]        [多工具Graph]
                    │         │                    │
                    └────┬────┘                    │
                         ▼                         ▼
                   流式返回 → Open WebUI → 用户
```

### 4.2 队列/检查点/重试/人审

| 机制 | 实现方案 | 存储 |
|------|---------|------|
| Queue | PostgreSQL tasks 表（短期）→ Redis+Celery（中期） | PostgreSQL / Redis |
| Checkpoint | LangGraph AsyncPostgresSaver | PostgreSQL `langgraph` 库 |
| Retry | Node 级：条件路由回环；Task 级：retry_count + 指数退避 | State + tasks 表 |
| Human Approval | LangGraph interrupt_before("finish") | Checkpoint 暂停 |

---

## 五、Environment 与 Infrastructure 层

### 5.1 Docker 服务编排

```
AI Platform (docker network: ai-platform)
│
├── postgres:16         :5432   (ai + langgraph 两个库)
├── qdrant              :6333   (documents_cn/hk/us)
├── minio               :9000   (5 Buckets)
├── docling             :8003   (文档解析)
├── embedding           :8001   (Qwen3-Embedding)
├── reranker            :8002   (BGE-Reranker)
├── langgraph           :8100   (FastAPI + LangGraph Agent)
├── openwebui           :3000   (用户界面)

```

### 5.2 存储分工

| 存储 | 保存什么 | 不保存什么 |
|------|---------|----------|
| PostgreSQL | 文档索引、公司信息、财务数据、任务状态、Agent 配置、Checkpoint | 向量、文件内容 |
| Qdrant | Chunk Embedding 向量 + Payload（content/metadata） | 原始文件、精确数值 |
| MinIO | PDF、Markdown、chunks.json、metadata.json、研究报告 | 向量、关系型数据 |
| Redis(可选) | 任务队列、缓存、Rate Limit 计数 | 持久化业务数据 |

---

## 六、迁移与共存策略

### 6.1 逐步切换方案

```
Phase 1-2: 新旧并行
  - 旧系统（Gradio + SQLite）继续可用
  - 新平台搭建基础设施 + 核心引擎
  - 新数据直接写入新平台

Phase 3-4: 功能迁移
  - 年报分析 → Research Agent
  - 实时行情 → Tool 层
  - 大师分析 → Skill Hub
  - 每迁移一个模块，旧系统对应功能标记 deprecated

Phase 5: 旧系统退役
  - 确认所有功能已在新平台可用
  - 历史数据重建完成
  - 关闭旧系统进程
```

### 6.2 数据迁移方案

| 数据 | 策略 | 原因 |
|------|------|------|
| PDF（~20000） | 上传 MinIO，重新 Docling | 唯一 Source of Truth |
| 大师分析报告 | 上传 MinIO artifacts/ | 人工资产，不可再生 |
| SQLite 数据 | 不迁移，AkShare 重新拉取 | 可再生数据 |
| 旧 Markdown | 不迁移，Docling 重新生成 | 中间产物 |
| 旧 Qdrant 向量 | 不迁移，重新 Embedding | 可重建 |
| Vault | 不迁移，Vault Generator 重新生成 | 展示层 |

### 6.3 回滚计划

- 每个 Phase 完成后打 Git Tag
- 旧系统代码保留在独立分支，随时可切回
- PostgreSQL 每日 pg_dump 备份
- MinIO 开启版本控制
- 回滚操作：`git checkout v{phase-1}` + `docker compose -f old-compose.yml up`

---

## 七、后续演进建议

| 方向 | 说明 | 时间窗口 |
|------|------|---------|
| 更多 Agent | Learning Agent（读书笔记）、News Agent（舆情监控） | Phase 5 后 |
| 插件市场 | Skill Hub 开放注册，第三方 Skill 接入 | 6 个月后 |
| 监控系统 | Prometheus + Grafana 监控服务指标 | Phase 4 后 |
| 多用户 | Open WebUI 多用户 + 权限隔离 | 按需 |
| 增量更新 | 实时监听交易所公告，自动触发 Pipeline | Phase 4 后 |
| 知识图谱 | 公司关联关系、行业图谱（Neo4j 或 pg_graphql） | 远期 |
| 多模态 | Vision Model 分析年报图表（figures/ 目录） | 远期 |
| 回测系统 | Investment Agent + 历史数据回测投资策略 | 远期 |

---

## 关键模块调用关系图

```
Open WebUI (:3000)
    │ POST /v1/chat/completions
    ▼
FastAPI (:8100)
    │
    ├── api/chat.py ──→ graph/router.py (Agent Dispatcher)
    │                        │
    │                   ┌────┼────────────┐
    │                   ▼    ▼            ▼
    │              ChatAgent ResearchAgent InvestmentAgent
    │                   │    │            │
    │                   ▼    ▼            ▼
    │              LangGraph StateGraph (各自 Workflow)
    │                   │
    │              ┌────┼────┬────┬────┐
    │              ▼    ▼    ▼    ▼    ▼
    │           planner retrieve rerank reason reflect finish
    │                      │      │      │
    │                      ▼      ▼      ▼
    │              ┌─── Tool Layer ───┐
    │              │                  │
    │         tools/qdrant.py   tools/llm.py
    │         tools/postgres.py tools/embedding.py
    │         tools/minio.py    tools/reranker.py
    │         tools/obsidian.py (MCP)
    │              │
    │              ▼
    │     ┌─── Infrastructure ───┐
    │     │                      │
    │  PostgreSQL  Qdrant  MinIO  Embedding  Reranker  LLM
    │     │
    │     ▼
    └── Checkpoint (langgraph DB) ──→ 断点恢复 / 人审
```
