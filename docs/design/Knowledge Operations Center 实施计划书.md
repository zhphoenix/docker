# Knowledge Operations Center 实施计划书

> Version: v1.0
> Status: Implementation Plan（待执行）
> 依据: 《Knowledge Operations Center 设计方案》（v1.0）
> 范围: langgraph/（api、storage、nodes/knowledge）、postgres/init/（DDL）、frontend/src/app/pages/KnowledgePage.tsx 及 components/knowledge/、mcp-knowledge/（SiYuan adapter/rendering 运营编排）
> 核心目标（不可变更）: Knowledge Operations Center 负责知识运营、治理、搜索、分析与服务；唯一输入为 Document Pipeline 输出的 Knowledge Package。

---

# 0. 对齐结论摘要（跨模块分歧决策表）

本计划书与《Document Pipeline + Knowledge Package 实施计划书》《Agent Center 后续演进实施计划书》共享以下决策：

| # | 分歧 | 决策 |
|---|---|---|
| 1 | 术语冲突：旧术语规范 vs V3.0 新术语 | 设计文档为目标态；UI 入口保留现名（知识中台），模块对外命名采用 Knowledge Operations Center |
| 2 | Knowledge Extraction 归属 | 生产归 Document Pipeline（Stage 5）；治理（Validation/Merge/Review）归本模块 |
| 3 | 数据契约 | 消费 `knowledge_packages` 表（Publish→Inbox 拉模式）；旧直写 core.* 路径为过渡通道 |
| 4 | Schema 双轨：`knowledge.*`（06）vs `core.*`（07） | `core.*` 为权威（实际读写均在此）；`knowledge.*` 由本计划书 Phase B 标记 deprecated 并迁移废弃 |
| 5 | News 接入 | News Package（source_type=NEWS）经 Inbox 统一消费，与文档 Package 同等待遇 |
| 7 | "Document Lifecycle" 命名 | 统一为 Document Pipeline，本模块不再出现旧名 |
| 8 | KnowledgeReviewPage 归属 | 收编为本模块 Governance 子模块（Inbox HITL），不重建 |
| 11 | SiYuan 集成归属 | 主体归本计划书（Phase F，Knowledge Delivery）；Document Pipeline 与 Agent Center 仅保留依赖说明 |

---

# 1. 模块定位（Positioning）

Knowledge Operations Center 是平台的**知识运营中心**：组织、治理、分析、运营和服务知识。

**负责**：Knowledge Organization / Governance / Discovery / Analytics / Evolution / Services（含 SiYuan 展示交付）。

**不负责**：Upload、OCR、Chunk、Embedding、Pipeline、Queue、GPU、Processing（均属 Document Pipeline）；Agent 注册与运行监控（属 Agent Center）。

职责总表（照设计 §17）：

| 子模块 | 核心职责 |
|---|---|
| Knowledge Inbox + Validation | 消费 Knowledge Package，校验、合并、入库 |
| Knowledge Explorer | 浏览知识资产（实体/知识卡/时间线） |
| Knowledge Graph | 图谱浏览与关系探索（AGE） |
| Knowledge Governance | 冲突/重复/低置信度治理 + HITL Review |
| Knowledge Search | 统一检索（Semantic/Graph/Hybrid） |
| Knowledge Analytics / Insights / Evolution | 增长、趋势、时间线 |
| Knowledge Impact | 影响链分析（投资平台特色） |
| AI Knowledge Services | 向 Agent/MCP/API 提供知识服务 + SiYuan 展示交付 |

---

# 2. 与现有项目的差距分析

## 2.1 已实现（复用基座）

| 能力 | 现状 | 复用方式 |
|---|---|---|
| 知识 Schema | `postgres/init/07-knowledge-database.sql`：core.entities/relations/facts/events/evidence/entity_aliases/knowledge_conflicts、document.documents/chunks、taxonomy.*、audit.knowledge_versions | 全量复用为知识底座 |
| SiYuan 集成底座 | `postgres/init/11-knowledge-siyuan.sql`：core.knowledge_inbox（NEW/EXTRACTED/READY_REVIEW/APPROVED/REJECTED/ARCHIVED）、core.knowledge_render_jobs（pending/running/done/failed + priority + retry）、audit.knowledge_review_log、core.entities 同步字段（last_synced_at/last_modified_by/sync_version/sync_status） | Phase A/F 直接复用 |
| Knowledge Ingestion HITL | `langgraph/storage/knowledge/postgres.py`（knowledge_inbox 写入）、`langgraph/api/approvals.py`、`frontend/src/app/pages/KnowledgeReviewPage.tsx`（审核 UI，记录写 audit.knowledge_review_log） | Phase A 收编为 Inbox Validation 的审核环节 |
| 知识 API | `langgraph/api/knowledge.py`：collections/stats/entities/facts/search/search/rag/extract/ingest/ingest-minio | Phase C 搜索增强的基础 |
| 前端知识组件 | `frontend/src/components/knowledge/`：KnowledgeDashboard/EntityBrowser/EntityDetailDialog/GraphWorkspace/SemanticSearchPanel/CollectionGrid/KnowledgeTasksPanel | Phase C/D 组件基座 |
| 图数据库 | `postgres/init/08-age-init.sql`（Apache AGE）+ `scripts/sync_to_age.py` | Phase E Impact 分析基础 |
| SiYuan 展示层全链路 | 容器 `siyuan/compose.yml`（:6806，workspace 挂载 data/siyuan-workspace）；`mcp-knowledge/server/adapters/siyuan/`（client/sync/mapper/config/templates，幂等同步）；`mcp-knowledge/server/tools/siyuan.py`（6 工具）+ `tools/inbox.py`；`mcp-knowledge/server/rendering/`（engine.py + worker.py 消费 render_jobs，模板驱动）；测试 test_siyuan*.py | Phase F 运营闭环的执行体，不重写 |
| 知识访问层 | mcp-knowledge（FastMCP，16+ 工具：entity/fact/semantic/write/analysis） | Phase E Services 统计对象 |

## 2.2 待实现（差距清单）

| # | 差距 | 对应设计章节 |
|---|---|---|
| 1 | Inbox 未与 Knowledge Package 对接：knowledge_inbox 目前仅接收抽取侧低置信实体，不消费 knowledge_packages | §2/§18 知识入口 |
| 2 | Governance 面板缺失：knowledge_conflicts 表存在但无 UI/处理流；重复/低置信度/过期知识无治理入口 | §8 |
| 3 | `knowledge.*`（06）与 `core.*`（07）schema 双轨并存，需收口废弃旧轨 | 决策 #4 |
| 4 | Knowledge Explorer 不完整：EntityBrowser 存在但无按类型统计浏览/快速筛选（Industry/Market/Region/Confidence）/知识卡时间线 | §5 |
| 5 | Search 未统一：search 与 search/rag 分离，无 Hybrid/Graph Search 统一入口 | §9 |
| 6 | Analytics/Insights/Evolution 缺失：无增长趋势、覆盖率、使用量统计，无实体时间线 UI | §10/§7/§11 |
| 7 | Impact 分析缺失：AGE 已初始化但无影响链/风险传播查询与 UI | §12 |
| 8 | AI Knowledge Services 统计缺失：mcp-knowledge 调用量无面板 | §13 |
| 9 | **SiYuan 运营闭环缺失**（重点）：adapter/工具/rendering worker/表结构均已实现，但缺——审核通过后自动入 Render Queue 的编排、render_jobs 失败重试监控 UI、sync_status Conflict/Pending Review 治理入口、Package 落库后的渲染触发策略 | §13/§18 Delivery |

---

# 3. 阶段划分与任务清单

> 依赖链：`KOC-A（Inbox/Validation）→ KOC-B（Governance）→ KOC-C（Explorer/Search）→ KOC-D（Analytics/Insights/Evolution）→ KOC-E（Impact/Services）`；`KOC-F（SiYuan 闭环）与 KOC-A 联动，可并行推进`。
> 优先级：P0 阻塞知识消费主链路，P1 运营主干，P2 增值分析。

## Phase A：Inbox + Validation（P0，依赖 DP 计划书 Phase A 契约）

**目标**：knowledge_packages 成为唯一知识入口，校验→合并→落 core.*，低置信走 HITL。

| 编号 | 任务 | 涉及文件 | 验收标准 |
|---|---|---|---|
| KOC-A1 | Package 消费器：轮询 `knowledge_packages` status='published' → 解析 payload → 置 consumed/failed（未知 schema_version 拒绝并告警） | `langgraph/services/package_consumer.py`（新建）+ `runtime/scheduler.py`（挂消费 job） | 一条 published Package 被消费后状态变 consumed，失败置 failed 且可重试 |
| KOC-A2 | Validation 规则：Evidence 完整性、Confidence 阈值（policy 配置）、实体类型合法性（taxonomy.entity_types） | `langgraph/services/knowledge_validation.py`（新建） | 不合规对象进入 knowledge_inbox READY_REVIEW，合规对象直接合并 |
| KOC-A3 | Merge 落库：复用 `nodes/knowledge/merger.py` 的实体对齐/别名合并逻辑写 core.*；写 audit.knowledge_versions | `nodes/knowledge/merger.py`、`storage/knowledge/postgres.py` | 同一实体重复入库不产生重复行，alias 合并正确 |
| KOC-A4 | Inbox 审核流打通：KnowledgeReviewPage 审核（approve/reject）写 audit.knowledge_review_log，APPROVED 后落 core.* | `api/approvals.py`、`KnowledgeReviewPage.tsx` | 审核通过实体出现在 core.entities 且状态 active |

**阶段验收**：端到端——DP Publish 一条 Package → KOC 消费 → 合规知识入 core.* / 低置信进审核队列，全程无人工 SQL。

## Phase B：Governance（P1）

| 编号 | 任务 | 涉及文件 | 验收标准 |
|---|---|---|---|
| KOC-B1 | 治理检测：重复实体（trgm 相似+别名）、冲突事实（同 subject/predicate 不同 object）、低置信关系、过期知识（facts.lifecycle_status）检测 job，结果写 core.knowledge_conflicts | `langgraph/services/knowledge_governance.py`（新建）+ scheduler job | 构造冲突样例后 conflicts 表有对应记录与类型 |
| KOC-B2 | Governance 面板：Duplicate/Conflict/Low Confidence/Need Review 计数卡 + 处理队列（合并/保留/驳回操作） | `frontend/src/components/knowledge/KnowledgeGovernancePanel.tsx`（新建）、`api/knowledge.py`（扩展治理端点） | 每类治理任务可处理并回写状态 |
| KOC-B3 | Schema 收口：`knowledge.*`（06）标记 deprecated，出数据迁移/核对脚本，确认无读写后废弃 | `scripts/migrate_knowledge_schema.py`（新建）、`postgres/init/06-knowledge-schema.sql`（加注释标记） | 迁移前后 core.* 数据计数一致；langgraph 与 mcp-knowledge 无 knowledge.* 引用残留 |

**阶段验收**：治理面板四类指标有真实数据；`knowledge.*` schema 不再被任何代码读写。

## Phase C：Explorer + Search 增强（P1）

| 编号 | 任务 | 涉及文件 | 验收标准 |
|---|---|---|---|
| KOC-C1 | Knowledge Explorer：按类型统计卡（Companies/Industries/Events/Policies/People...）+ 快速筛选（Industry/Market/Date/Source/Confidence）+ 知识卡（Timeline/Facts/Related） | `components/knowledge/EntityBrowser.tsx`（扩展）、`api/knowledge.py` | 任一实体可展示知识卡全要素；筛选生效 |
| KOC-C2 | 统一搜索入口：合并 search/search/rag 为 Hybrid Search（向量+全文+AGE 图查询可选） | `api/knowledge.py`、`components/knowledge/SemanticSearchPanel.tsx` | 一次查询返回 Entity/Fact/Event/Document 混合结果并标注来源通道 |

## Phase D：Analytics + Insights + Evolution（P2）

| 编号 | 任务 | 涉及文件 | 验收标准 |
|---|---|---|---|
| KOC-D1 | Analytics：Knowledge Growth/Coverage/Usage/Quality/Freshness 统计 + 7/30/90 天趋势 | `api/knowledge.py`（stats 扩展）、KnowledgeDashboard | 首页统计展示 Entities/Relations/Facts/Events/Communities/Coverage（设计 §15） |
| KOC-D2 | Insights：Hot Topics/Trending Companies/Emerging Concepts（基于近期入库统计） | `services/knowledge_insights.py`（新建） | 今日热点卡片有真实来源 |
| KOC-D3 | Evolution：实体时间线 UI（audit.knowledge_versions + facts.time_start/end） | EntityDetailDialog 扩展 | 任一实体可查看版本/事实时间线 |

## Phase E：Impact + AI Knowledge Services（P2）

| 编号 | 任务 | 涉及文件 | 验收标准 |
|---|---|---|---|
| KOC-E1 | Impact 分析：AGE 影响链查询（Policy/Event → Industry → Company，supplies/impacts/regulates 关系遍历） | `scripts/sync_to_age.py`（保障数据新鲜）、`api/knowledge.py`（impact 端点）、GraphWorkspace 扩展 | 给定事件可返回受影响公司链 |
| KOC-E2 | AI Knowledge Services 面板：mcp-knowledge 各工具调用统计（Research Agent Calls/Knowledge Hits/Today's Search） | mcp-knowledge 调用埋点（复用现有 cache/日志）+ KOC Services 区块 | 面板展示真实调用量 |

## Phase F：SiYuan 展示交付闭环（P1，SiYuan 主体展开方）

**前提**：设计红线——PostgreSQL 为唯一 SoT，SiYuan 仅为展示层；写入必须经 Knowledge MCP Server；渲染经 SiYuan Sync adapter 模板驱动（非 LLM 拼接）。执行体均已实现，本阶段补齐运营闭环。

| 编号 | 任务 | 涉及文件 | 验收标准 |
|---|---|---|---|
| KOC-F1 | 审核→渲染编排：Inbox 审核通过（APPROVED）后按对象类型自动 `INSERT core.knowledge_render_jobs`（优先级策略：Company/Event 优先，priority 越小越优先），打通 KnowledgeReviewPage 审核动作与 Render Queue 触发链路 | `langgraph/api/approvals.py` 或 `mcp-knowledge/server/tools/inbox.py`（审核钩子）、`core.knowledge_render_jobs` | 审核通过一条实体后 render_jobs 出现 pending 记录 |
| KOC-F2 | Render Queue 监控：render_jobs 状态/重试/失败原因面板（复用 WorkflowPage 任务面板范式或 KOC 独立 Tab）；失败自动重试上限（retry 字段）与告警 | `frontend/src/components/knowledge/KnowledgeTasksPanel.tsx`（扩展）、`mcp-knowledge/server/rendering/worker.py`（重试上限）、`api/knowledge.py`（render-jobs 端点） | 面板可见 pending/running/done/failed；failed job 可手动重试恢复 |
| KOC-F3 | 同步冲突治理：core.entities.sync_status 为 Pending Review / Conflict 的实体进入 Governance 面板处理队列（并入 KOC-B2），处理后重置 Synced | KnowledgeGovernancePanel、`api/knowledge.py` | 构造 Conflict 实体后出现在治理队列，处理后 sync_status='Synced' |
| KOC-F4 | 渲染触发策略：定义 Package 落库后的渲染规则——新增实体全量 `sync_entity`，已有实体增量 `sync_section`；策略以 policy 配置可开关（总开关可整体停用 SiYuan 渲染） | `langgraph/config/policy_loader.py` 策略项、`mcp-knowledge/server/adapters/siyuan/sync.py`（已具备 sync_entity/sync_section） | 策略切换行为符合预期；关闭后不产生 render_jobs |
| KOC-F5 | 服务健康展示：SiYuan 容器与 Sync adapter 可用性纳入 KOC Services 区块（复用 `langgraph/api/health.py` 现有 SiYuan 探测） | KnowledgeDashboard Services 区块 | SiYuan 宕机时 Services 区块显示不可用，恢复后自动转绿 |

### SiYuan 接口契约与数据流（写入本计划书，其他计划书不重复）

```text
KOC 审核 API（APPROVED）
    │ INSERT core.knowledge_render_jobs (entity, type, section, priority)
    ▼
mcp-knowledge rendering/worker.py（取 pending job，按 priority 排序）
    │ templates.py 模板渲染（模板驱动，非 LLM 拼接）
    ▼
adapters/siyuan/sync.py
    │ SiYuan HTTP API 幂等更新（新版 API 已移除 getDocByPath/updateDoc）：
    │   getIDsByHPath → removeDocByID → createDocWithMd
    ▼
SiYuan workspace（data/siyuan-workspace，仅展示层）
    │ 回写 core.entities：
    ▼
sync_version +1 / last_synced_at / sync_status='Synced'
```

契约要点：
- PG 为唯一 SoT：SiYuan workspace 任何内容可被随时重建（`mcp-knowledge/scripts/rebuild_siyuan_graph.py`）。
- 渲染失败不回滚知识入库：render_jobs 置 failed，知识已在 core.*，展示层故障与数据层解耦。
- sync_version 单调递增，mapper 路径规则（notebook_for/entity_to_path）为展示层唯一寻址方式。

### Phase F 验收标准（汇总）

- 审核通过一条实体 → render_jobs pending→done，SiYuan workspace 出现对应笔记且路径符合 mapper 规则。
- 故意使 SiYuan 容器宕机 → job 置 failed，面板可见错误原因；恢复后手动重试成功。
- sync_status=Conflict 的实体进入治理队列并可恢复 Synced。
- policy 关闭渲染总开关后，审核通过不再产生 render_jobs。

---

# 4. 依赖关系

```text
【外部】DP 计划书 Phase A（knowledge_packages 契约）──→ KOC-A（Inbox 消费）
KOC-A ──→ KOC-B / KOC-C（可并行）──→ KOC-D ──→ KOC-E
KOC-A ──→ KOC-F1（审核→渲染钩子依赖审核流）；KOC-F2~F5 可独立并行
【外部】AC 计划书：mcp-knowledge 的 MCP 注册/心跳由 Agent Center P2-3 负责（已落地）
```

# 5. 优先级总表

| 优先级 | 任务 |
|---|---|
| P0 | KOC-A1~A4 |
| P1 | KOC-B1~B3、KOC-C1~C2、KOC-F1~F5 |
| P2 | KOC-D1~D3、KOC-E1~E2 |

---

# 6. 风险与回滚建议

| # | 风险 | 影响 | 应对/回滚 |
|---|---|---|---|
| 1 | Package 消费器与旧直写通道双轨期间知识重复入库 | 实体重复 | KOC-A3 Merge 幂等（ON CONFLICT + alias 对齐）；双轨期以 Package 通道为准，直写通道按 DP 计划书 C2 开关逐步关闭 |
| 2 | `knowledge.*` schema 废弃遗漏引用 | 运行时报错 | KOC-B3 先全局 grep 确认无读写，再出迁移脚本；废弃前双读核对一周 |
| 3 | 治理检测误报（trgm 相似度阈值不当） | 大量无效治理任务 | 阈值走 policy 配置，先只写 conflicts 不自动动作，人工确认后逐步放开 |
| 4 | SiYuan 新版 API 变更（已移除 getDocByPath/updateDoc） | 同步失败 | adapter 已按 getIDsByHPath→removeDocByID→createDocWithMd 实现；版本升级前先跑 test_siyuan*.py 回归 |
| 5 | SiYuan 渲染故障波及知识服务 | 展示层与数据层耦合 | 红线保障：渲染失败仅置 render_jobs failed；policy 总开关可整体停用渲染链路，PG SoT 与 MCP 知识服务不受影响 |
| 6 | 前端新增面板与 KnowledgePage 现有 Tab 冲突 | 页面过载 | 新面板走独立 Tab 懒加载 + EmptyState 降级；遵循 React Query 缓存键隔离原则 |
| 7 | 存量 DB 迁移不生效（init 仅首次执行） | 新表缺失 | 本计划书不新增表（11/07 已建）；如有增量迁移沿用幂等 + 手动 `psql -f` 先例 |

**整体回滚策略**：每阶段独立 API/组件，前端 EmptyState 降级；KOC-A 消费 job 可整体停用以回退至旧直写通道；Phase F 渲染链路可经 policy 开关完全停用。

---

# 附录：涉及文件清单（速查）

**新建**
- `langgraph/services/package_consumer.py`、`services/knowledge_validation.py`、`services/knowledge_governance.py`、`services/knowledge_insights.py`
- `frontend/src/components/knowledge/KnowledgeGovernancePanel.tsx`
- `scripts/migrate_knowledge_schema.py`

**修改**
- `langgraph/api/knowledge.py`、`api/approvals.py`、`runtime/scheduler.py`、`config/policy_loader.py`
- `langgraph/nodes/knowledge/merger.py`（写入目标复用）
- `frontend/src/app/pages/KnowledgePage.tsx`、`KnowledgeReviewPage.tsx`、`components/knowledge/*`（扩展）
- `mcp-knowledge/server/rendering/worker.py`（重试上限）、`server/tools/inbox.py`（审核钩子）

**复用（不改或仅配置）**
- `postgres/init/07-knowledge-database.sql`、`11-knowledge-siyuan.sql`、`08-age-init.sql`
- `mcp-knowledge/server/adapters/siyuan/*`、`server/tools/siyuan.py`、`server/rendering/engine.py`
- `siyuan/compose.yml`、`scripts/sync_to_age.py`、`mcp-knowledge/scripts/rebuild_siyuan_graph.py`
