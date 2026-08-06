# Document Pipeline + Knowledge Package 实施计划书

> Version: v1.0
> Status: Implementation Plan（待执行）
> 依据: 《Document Pipeline + Knowledge Package 设计方案（V3.0）》
> 范围: langgraph/（pipelines、graphs、nodes、schemas、api）、postgres/init/（DDL）、frontend/src/app/pages/WorkflowPage.tsx
> 核心目标（不可变更）: Document Pipeline 负责知识生产并输出 Knowledge Package；Knowledge Package 是 Document Pipeline 与 Knowledge Operations Center 之间唯一的数据交换格式。

---

# 0. 对齐结论摘要（跨模块分歧决策表）

本计划书与《Knowledge Operations Center 实施计划书》《Agent Center 后续演进实施计划书》共享以下决策：

| # | 分歧 | 决策 |
|---|---|---|
| 1 | 术语冲突：旧术语规范（Documents/Workflow/Knowledge Hub、3 阶段）vs V3.0（Document Pipeline/KOC、8 阶段） | 设计文档为目标态；UI 入口保留现名，模块对外命名采用新术语；术语规范文档随实施同步修订 |
| 2 | Knowledge Extraction 归属：Pipeline Stage 5 vs KOC 知识组织 | 生产归 Pipeline（Knowledge Ingestion Agent 即 Stage 5 执行器）；治理归 KOC（Validation/Merge/Review） |
| 3 | 数据契约：现状抽取后直写 core.* | 新增 `knowledge_packages` 表 + Publish→Inbox 流程；现有直写路径标记为过渡通道，逐步收口 |
| 4 | Schema 双轨：`knowledge.*`（06）vs `core.*`（07） | `core.*` 为权威；`knowledge.*` 标记 deprecated，由 KOC 计划书负责迁移废弃 |
| 5 | News 是否走统一 Pipeline | News 保留实时专链，其输出封装为 `source_type=NEWS` 的 Knowledge Package 发布到 KOC；Routing 先覆盖文档类源 |
| 6 | Documents 模块 vs Pipeline Acquire 重叠 | Documents 页保留为文档资产管理入口；上传动作触发 Pipeline 任务；Pipeline 不重建资产管理 |
| 7 | KOC 设计中 "Document Lifecycle" 命名 | 统一更名为 Document Pipeline |
| 8 | KnowledgeReviewPage 归属 | 收编为 KOC Governance 子模块（Inbox HITL） |
| 9 | `specs/agent-registry.yaml` 目录映射失效 | 由 Agent Center 计划书负责修正 |
| 10 | WorkflowPage 任务中心 vs Workflow 图可视化 | 任务监控保留，图可视化作为新 Tab（Agent Center P3-2） |
| 11 | SiYuan 集成归属 | 主体归 KOC 计划书（Knowledge Delivery）；本计划书 Publish 后仅声明依赖，不调用 SiYuan API |

---

# 1. 模块定位（Positioning）

Document Pipeline 是平台**唯一知识生产层（Knowledge Production Layer）**：

- 统一接收所有知识来源（Documents / News / API / Crawler）。
- 通过八阶段标准流程（Acquire → Routing → Parse → Chunk → Knowledge Extraction → Embedding → Knowledge Package → Publish）生产知识。
- 唯一输出：**Knowledge Package**（知识数据契约）。

不负责：Knowledge Graph、Knowledge Search、Knowledge Governance、Knowledge Analytics、Research、Watchlist、SiYuan 渲染（均属 Knowledge Operations Center）。

目标数据流：

```text
Knowledge Sources → Document Pipeline（8 阶段）→ Knowledge Package → Publish
    → KOC Inbox → Validation → Merge → Governance → core.* + AGE
    → Knowledge Services → Research / Watchlist / Agents
```

---

# 2. 与现有项目的差距分析

## 2.1 已实现（复用基座）

| 能力 | 现状 | 复用方式 |
|---|---|---|
| Parse→Chunk→Embedding→Index | `langgraph/pipelines/document_pipeline.py`（Docling 解析、断点续传、失败重试、暂停/取消、`reembed_document`、MinIO 扫描注册 `register_pending_from_minio`） | 作为 Parse/Chunk/Embedding 三阶段执行体保留 |
| 任务调度 | `runtime/worker.py` + `runtime/queue.py`：`doc_pipeline` / `batch_embed` / `knowledge_extraction` / `ingest_minio` / `upload_folder` 统一由 Worker 处理（SELF_MANAGED_TYPES） | 八阶段进度复用 `tasks.stage` / `task_logs` |
| Knowledge Extraction 执行器 | `langgraph/graphs/knowledge_graph.py`（Parser→Entity→[Relation‖Fact]→Validator→Merger，fan-out/fan-in）+ `nodes/knowledge/*` | 编入 Stage 5，不重写 |
| 知识存储层 | `langgraph/storage/knowledge/postgres.py` 写 `core.entities/relations/facts/evidence` + `core.knowledge_inbox` | Extraction 直写路径保留为过渡通道 |
| Web 采集支线 | `langgraph/pipelines/web_pipeline.py` + `pipelines/web/*`（chunker/diff_detector/link_extractor/rate_limiter/retry） | Phase D 以 source_type=GENERAL 接入 Acquire |
| News 实时链路 | `langgraph/graphs/news_analysis_graph.py` + `nodes/news/*`（cleaner→dedup→classifier→entity→event→impact→publisher）+ `runtime/scheduler.py` 三档采集 job | Phase D 仅在 publisher 输出侧封装 Package，不改实时链路 |
| 文档资产管理 | `langgraph/api/documents.py` + `frontend/src/app/pages/DocumentsPage.tsx`（上传/导入/预览/重处理） | Acquire 入口触发器，不重建 |
| 策略配置 | `langgraph/config/policy_loader.py`（`get_policy`） | Routing 策略与双通道开关挂载点 |

## 2.2 待实现（差距清单）

| # | 差距 | 对应 V3.0 章节 |
|---|---|---|
| 1 | Acquire 阶段无统一抽象：文档/MinIO/Web/News 各自独立入口，缺统一 source metadata（document_id/source_type/trigger/priority/checksum） | Stage 1 |
| 2 | Routing 阶段不存在：所有文档走同一处理策略，无按类型分派 Prompt/Parser/Extraction 策略 | Stage 2 |
| 3 | Knowledge Package 契约完全缺失：代码库中 0 匹配，无 schema、无表、无 pydantic 模型 | Stage 7 |
| 4 | Publish 阶段不存在：Extraction 结果直写 core.*，无发布/重试/回滚语义 | Stage 8 |
| 5 | Knowledge Extraction 未编入主流水线：doc_pipeline 只做索引，`knowledge_extraction` 任务与 `doc_pipeline` 相互独立 | Stage 5 |
| 6 | 多源接入缺失：Word/Excel/Image/REST API 无统一接入（仅 PDF/Markdown/年报路径） | Stage 1 |
| 7 | Pipeline Dashboard 无八阶段视图：WorkflowPage 只展示任务级 stage | §5/§8 |

---

# 3. 阶段划分与任务清单

> 依赖链：`DP-A 契约 → DP-B 阶段化 → DP-C Extraction 编入 → DP-D Publish/多源 → DP-E Dashboard`
> 优先级：P0 阻塞下游（KOC Phase A），P1 主干，P2 增强。

## Phase A：Knowledge Package 契约先行（P0）

**目标**：定义并落地唯一数据契约，为 KOC Inbox 提供对接基础。

| 编号 | 任务 | 涉及文件 | 验收标准 |
|---|---|---|---|
| DP-A1 | 定义 Package JSON Schema：Package Metadata、Source Metadata、Entities、Relations、Facts、Events、Embeddings（引用）、Evidence、Confidence、Processing Metadata、Version（含 history，支持 Rollback/Diff） | `langgraph/schemas/knowledge_package.py`（新建，pydantic v2 模型）+ `AI-Platform-System-Design/schemas/ai_platform/knowledge_package.schema.json`（新建，JSON Schema 导出） | pydantic 模型可序列化/反序列化样例 Package；JSON Schema 与 pydantic 模型字段一一对应 |
| DP-A2 | `knowledge_packages` 幂等迁移表 | `postgres/init/15-knowledge-package.sql`（新建：id/package_version/schema_version/source_type/document_id/status(draft/published/consumed/failed)/payload JSONB/processing_metadata JSONB/publish_time/retry_count/created_at，索引 status+created_at、document_id） | 存量库 `psql -f` 手动应用一次 + 可重复执行不报错；字段与 DP-A1 模型对应 |
| DP-A3 | Package 仓储层 | `langgraph/storage/knowledge/package.py`（新建：save_draft/publish/get/retry/rollback 接口） | 单测覆盖 draft→published 状态流转与幂等重发 |

**阶段验收**：可手工构造一个 Package 落表并查询；KOC 计划书 Phase A 可据此开工。

## Phase B：Pipeline 阶段化重构（P1）

**目标**：将现有流水线升级为八阶段模型，进度与 processing metadata 全程可追踪。

| 编号 | 任务 | 涉及文件 | 验收标准 |
|---|---|---|---|
| DP-B1 | Stage 抽象：定义 acquire/routing/parse/chunk/extraction/embedding/package/publish 枚举与阶段记录 | `langgraph/pipelines/stages.py`（新建） | 每阶段进入/完成/失败均写 `task_logs`（stage 字段）与 documents.metadata.processing |
| DP-B2 | Acquire 统一入口：文档上传/MinIO 扫描/Web 抓取统一产出 Raw Document + source metadata（source_type/trigger/priority/checksum） | `pipelines/document_pipeline.py`、`api/documents.py`、`api/knowledge.py`（ingest-minio） | 三种入口产生的 documents 记录均含统一 metadata 字段；checksum 判重生效 |
| DP-B3 | Routing 策略：按 document_type 分派处理策略，先支持 `annual_report` 与 `general` 两策略（不同 chunk 参数/extraction 开关/prompt） | `langgraph/config/pipeline_routing.yaml`（新建）+ `pipelines/document_pipeline.py` | 年报与通用文档分别命中不同策略；策略可在 policy 覆盖 |
| DP-B4 | Processing Metadata 落库：parser/ocr_engine/embedding_model/llm_model/routing_strategy/processing_time 写入 Package 草稿 | `pipelines/document_pipeline.py`、`storage/knowledge/package.py` | 任一处理完成的文档可查到完整 processing metadata |

**阶段验收**：一个年报文档走完 Acquire→Routing→Parse→Chunk→Embedding，tasks.stage 与 metadata 完整反映各阶段；Docling 不可用时降级行为不变（waiting_parser）。

## Phase C：Knowledge Extraction 编入 Stage 5（P1）

**目标**：Knowledge Ingestion Agent 成为主流水线的 Stage 5 执行器，产出写入 Package 草稿。

| 编号 | 任务 | 涉及文件 | 验收标准 |
|---|---|---|---|
| DP-C1 | doc_pipeline 编排扩展：Embedding 完成后调用 `build_knowledge_ingestion_graph()`，输出（entities/relations/facts/evidence/confidence）写入 Package 草稿 | `pipelines/document_pipeline.py`、`graphs/knowledge_graph.py` | 一篇年报处理后 Package 草稿含非空 Entities/Relations/Facts 与 Evidence |
| DP-C2 | 双通道开关：`pipeline.extraction.mode = package | direct`（policy 配置），direct 保留现直写 core.* 路径作为回退 | `config/policy_loader.py` 策略项、`pipelines/document_pipeline.py` | 切换 mode 后行为符合预期；异常时自动回退 direct 并告警 |
| DP-C3 | Merger 解耦：`nodes/knowledge/merger.py` 写入目标改为可注入（Package 草稿 or core.*），knowledge_inbox HITL 触发逻辑保持不变 | `nodes/knowledge/merger.py`、`storage/knowledge/postgres.py` | 两种模式下 merger 回归通过；低置信实体仍进 knowledge_inbox |

**阶段验收**：`knowledge_extraction` 独立任务类型与 doc_pipeline 内嵌 Stage 5 两路径结果一致（同一文档对比）。

## Phase D：Publish 与多源接入（P2）

**目标**：完成 Stage 8 Publish，News/Web 源以 Package 形式接入。

| 编号 | 任务 | 涉及文件 | 验收标准 |
|---|---|---|---|
| DP-D1 | Publish 实现：Package 草稿校验（JSON Schema）→置 published→写 publish metadata（publish_time/destination/status/retry_count）→通知 KOC Inbox（HTTP 调用或 DB 置位，见接口契约 §5） | `storage/knowledge/package.py`、`pipelines/document_pipeline.py` | 发布失败的 Package 可 Retry/Re-Publish；rollback 可回到上一版本 |
| DP-D2 | News 发布封装：`nodes/news/publisher.py` 输出侧将已抽取结果封装为 `source_type=NEWS` 的 Package 并走同一 Publish 出口（实时链路本身不改动） | `nodes/news/publisher.py`、`storage/knowledge/package.py` | 一次新闻入库在 knowledge_packages 产生一条 NEWS 记录且 KOC Inbox 可见 |
| DP-D3 | Web 源接入：web_pipeline 产物按 `source_type=GENERAL` 走 Acquire/Routing | `pipelines/web_pipeline.py` | Web 抓取页面经统一入口进入流水线 |
| DP-D4 | 优先级队列支持：HIGH/NORMAL/LOW 三级（Breaking News=HIGH，Annual Report=LOW），复用 task_queue 排序 | `runtime/queue.py`、`pipelines/document_pipeline.py` | HIGH 任务优先被 Worker 认领 |

**阶段验收**：三类来源（年报/News/Web）各产出一条 published Package，KOC Inbox 均能消费。

## Phase E：Pipeline Dashboard（P2）

**目标**：WorkflowPage 呈现八阶段视图与生产统计。

| 编号 | 任务 | 涉及文件 | 验收标准 |
|---|---|---|---|
| DP-E1 | 后端统计 API：八阶段 Running/Pending/Completed/Failed 计数、Incoming Documents/Knowledge Packages/Processed Today/Publish Success Rate/Queue Length/Average Latency | `langgraph/api/tasks.py`（扩展）或 `api/pipeline.py`（新建） | curl 返回真实统计数 |
| DP-E2 | 前端八阶段视图：WorkflowPage 流水线 Tab 升级为八阶段链路 + 任务详情按阶段打点 | `frontend/src/app/pages/WorkflowPage.tsx`、`frontend/src/services/tasks.ts` | 任一任务可看到八阶段进度与失败阶段定位 |

---

# 4. 依赖关系

```text
DP-A（契约）──→ DP-B（阶段化）──→ DP-C（Extraction 编入）──→ DP-D（Publish/多源）──→ DP-E（Dashboard）
   │
   └──→ 【外部】KOC 计划书 Phase A（Inbox 消费 knowledge_packages）依赖 DP-A1/A2 完成
        【外部】AC 计划书对齐任务：doc_pipeline / knowledge ingestion 运行记录纳入 agent_runs 口径
```

- DP-B/C 可部分并行：DP-B1/B3 与 DP-C3 无冲突。
- DP-D2 依赖 DP-D1。
- 外部依赖：Docling 服务（解析）、Embedding 服务（向量化）可用性策略沿用现状（优雅降级）。

# 5. 接口契约（与 KOC 的边界）

| 契约项 | 约定 |
|---|---|
| 交换格式 | Knowledge Package（DP-A1 pydantic 模型），`payload` 以 JSONB 存 `knowledge_packages` 表 |
| 交接方式 | Publish 置 `status='published'`；KOC Inbox 按 `status='published'` 拉取（首期拉模式，避免跨服务强耦合），消费后置 `consumed` |
| 版本语义 | `package_version` 单调递增，`schema_version` 标识契约版本；KOC 拒绝消费未知 schema_version |
| 重试 | Publish 失败 retry_count+1，上限 3 次后 failed，人工 Re-Publish |
| 下游说明 | Publish 成功后的展示渲染（SiYuan）由 KOC 负责（见《Knowledge Operations Center 实施计划书》Phase F）；Pipeline 不直接调用 SiYuan API，不产生 render_jobs |

---

# 6. 优先级总表

| 优先级 | 任务 |
|---|---|
| P0（阻塞 KOC） | DP-A1、DP-A2、DP-A3 |
| P1（主干） | DP-B1~B4、DP-C1~C3 |
| P2（增强） | DP-D1~D4、DP-E1~E2 |

---

# 7. 风险与回滚建议

| # | 风险 | 影响 | 应对/回滚 |
|---|---|---|---|
| 1 | 存量 DB 迁移不生效（init 脚本仅首次初始化执行，已验证的项目坑） | knowledge_packages 表缺失，Publish 失败 | 迁移文件保持幂等；上线时对运行中容器手动 `psql -f` 一次（沿用 12/13 迁移先例） |
| 2 | Extraction 编入改变现有直写行为，影响既有知识入库 | 知识缺失或重复 | DP-C2 双通道开关（policy `pipeline.extraction.mode`），默认 direct，灰度切 package；异常自动回退 |
| 3 | Package 契约过早冻结，KOC 消费时字段不匹配 | 返工 | schema_version 字段预留演进；DP-A1 评审时同步 KOC 计划书作者确认字段 |
| 4 | News publisher 封装 Package 引入额外延迟 | 实时链路变慢 | 封装动作异步化（fire-and-forget + 落表补偿），失败仅告警不阻塞新闻入库 |
| 5 | 八阶段重构破坏断点续传语义 | 文档卡死在中间态 | DP-B 各阶段保持 documents.status 现有枚举（pending/waiting_parser/parse_failed/parsed/indexed/error）兼容，新状态仅增量追加 |
| 6 | WSL 开发环境：挂载盘需重启 vite；Docker 命令用 docker.exe | 验证误判 | 验证阶段遵循既有环境约定 |

**整体回滚策略**：Phase A 纯新增（表/schema/仓储），回滚 = 弃用；Phase B/C 通过 policy 开关回退至现状流水线；Phase D Publish 关闭后 Package 仅存 draft，不影响既有索引链路。

---

# 附录：涉及文件清单（速查）

**新建**
- `langgraph/schemas/knowledge_package.py`
- `AI-Platform-System-Design/schemas/ai_platform/knowledge_package.schema.json`
- `postgres/init/15-knowledge-package.sql`
- `langgraph/storage/knowledge/package.py`
- `langgraph/pipelines/stages.py`
- `langgraph/config/pipeline_routing.yaml`

**修改**
- `langgraph/pipelines/document_pipeline.py`（阶段化 + Extraction 编排 + Publish）
- `langgraph/graphs/knowledge_graph.py`、`nodes/knowledge/merger.py`（写入目标可注入）
- `langgraph/nodes/news/publisher.py`（Package 封装）
- `langgraph/pipelines/web_pipeline.py`（统一 Acquire）
- `langgraph/api/tasks.py`、`api/knowledge.py`、`api/documents.py`（metadata 与统计）
- `langgraph/runtime/queue.py`（优先级队列）
- `frontend/src/app/pages/WorkflowPage.tsx`、`frontend/src/services/tasks.ts`（八阶段视图）

**复用（不改）**
- 任务系统（tasks/task_logs）、Worker/Scheduler、Docling/Embedding 工具、Documents 资产管理页
