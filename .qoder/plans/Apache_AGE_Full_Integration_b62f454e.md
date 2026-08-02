# AI-Platform 系统性结构审查与重整计划

## 现状诊断摘要

经全面探查，项目存在以下核心问题：

| 问题类别 | 严重度 | 描述 |
|----------|--------|------|
| `graph/` 目录职责混乱 | Critical | 9 个不相关文件堆积（workflow、pipeline、router、task_queue、approval...） |
| "Knowledge Agent" 命名冲突 | Critical | `agents/knowledge_agent.py`(Chat Agent) vs `knowledge_agent/`(Ingestion Pipeline) 是两个完全不同的东西 |
| DB 存在未使用 Schema | Important | `vector`、`taxonomy` schema 已创建但代码中无引用 |
| `Web_pipeline/` 空目录 | Nice-to-have | 根目录空壳，实际代码在 `src/` |
| `src/` 路径操纵导入 | Important | `web_collector.py` 通过 `sys.path.insert` 导入 `src/`，脆弱 |
| specs 与代码偏差 | Important | agent-registry 中 Knowledge Agent 描述混淆两个实现 |
| 设计文档过时 | Important | 43 个设计文件中多数不反映当前架构 |
| `__pycache__` 残留 | Nice-to-have | 30 个目录（.gitignore 已有但本地残留） |

---

## Phase 1: 结构审计（只读，不修改任何文件）

**目标**: 产出精确的依赖图和"使用/未使用"清单，为后续 Phase 提供决策依据。

### 子任务 1.1: 代码依赖审计

**输入文件**:
- `langgraph/agent/graph/` 全部 9 个 .py 文件
- `langgraph/agent/api/` 全部 13 个 .py 文件
- `langgraph/agent/agents/` 全部 5 个 .py 文件
- `langgraph/agent/nodes/` 全部 9 个 .py 文件

**输出**: 每个 `graph/*.py` 文件的被引用表（谁 import 了它），判定哪些可以安全移动。

已知依赖关系（本次审计确认）：
```
api/chat.py        → graph/router.py (dispatch_agent)
api/agents.py      → graph/router.py (AGENT_REGISTRY)
api/models.py      → graph/router.py (AGENT_REGISTRY)
api/tasks.py       → graph/task_queue.py, graph/pipeline.py
api/knowledge.py   → graph/task_queue.py, knowledge_agent/storage/
api/approvals.py   → graph/approval.py
api/vault.py       → graph/vault_generator.py
agents/base_agent.py → nodes/planner, nodes/retrieve, nodes/rerank
graph/graph.py     → nodes/* (全部 RAG 节点)
```

### 子任务 1.2: 数据库 Schema 使用审计

**输入文件**:
- `postgres/init/07-knowledge-database.sql`（创建 vector/taxonomy/audit schema）
- 全项目 grep: `vector\.`, `taxonomy\.`, `audit\.`

**输出**: 确认 `vector`、`taxonomy`、`audit` schema 下是否有表被代码实际查询。

预判结论：
- `vector` schema: 未使用（Qdrant 承担向量存储）
- `taxonomy` schema: 未使用（ontology.yaml 承担类型定义）
- `audit` schema: 需验证 `audit.mcp_access_log` 是否在 mcp-knowledge 中写入

### 子任务 1.3: Specs 与代码对齐审计

**输入文件**:
- `specs/architecture.yaml`（223 行）
- `specs/agent-registry.yaml`（114 行）
- `specs/ontology.yaml`
- 实际代码目录结构

**输出**: 偏差清单（每条含：specs 描述 vs 代码现实 vs 修复方向）

已识别偏差：
1. agent-registry §1 "Knowledge Agent" 代码目录写 `agents/ + knowledge_agent/`，但这是两个不同系统
2. architecture.yaml DEP-001 依赖链 `api → agents → graph → nodes → tools` 不适用于 `knowledge_agent/` 和 `news_agent/`（它们有自己的 nodes/storage）
3. ORG-002 "类型定义放在 schemas/" — 新模块的 State 定义在各自目录内（`news_agent/state.py`），未放 `schemas/`

### 子任务 1.4: 文档时效性审计

**输入文件**:
- `AI-Platform-System-Design/` 43 个文件（扫描标题和首段）
- `docs/design/` 10 个文件

**输出**: 分类为"当前有效 / 需更新 / 已废弃"三级

---

## Phase 2: 安全清理（低风险，不影响运行时）

**优先级**: Critical（消除混淆源）

### 2.1 删除空目录和残留

| 操作 | 路径 | 风险 |
|------|------|------|
| 删除 | `Web_pipeline/`（空目录） | 无 |
| 清理 | 所有 `__pycache__/` 目录 | 无 |
| 删除 | `scripts/__pycache__/` | 无 |

### 2.2 归档一次性脚本

将 `scripts/` 中的一次性测试/导入脚本移至 `scripts/archive/`：
- `test_downstream_pipeline.py`
- `test_pipeline_integration.py`
- `test_web_ingestion.py`
- `crawl_qiushi_summary.py`

保留活跃脚本：
- `sync_to_age.py`（AGE 数据同步）
- `init_news_qdrant.py`（News Qdrant 初始化）
- `batch_embed_to_qdrant.py`（批量 Embedding）
- `web_scheduler.py`（Web 采集调度）
- `generate_vault_platform.py`（Vault 生成）
- `import_company_basic.py` / `import_providers.py`（数据导入工具）

### 2.3 数据库 Schema 清理（需评估后执行）

**前提**: Phase 1.2 审计确认无代码引用后执行。

在 `postgres/init/07-knowledge-database.sql` 中：
- 如果 `vector` schema 下无表且无代码引用 → 移除 `CREATE SCHEMA IF NOT EXISTS vector;`
- 如果 `taxonomy` schema 下无表且无代码引用 → 移除 `CREATE SCHEMA IF NOT EXISTS taxonomy;`
- 如果 `audit` schema 仅被 MCP-006 规则引用但未实现 → 保留但标注为"规划中"

**风险**: 低。这些 schema 在当前数据库中可能根本不存在（init 脚本仅在全新数据库时执行）。

---

## Phase 3: 目录结构重整（核心 Phase）

**优先级**: Critical（消除架构混淆）
**风险**: 中等 — 涉及 import 路径变更，需逐步执行并验证

### 3.1 拆分 `graph/` 目录

当前 `graph/` 包含 9 个不同职责的文件，按功能域拆分：

```
langgraph/agent/
├── graph/                    # 仅保留 Chat/Research Agent 的 Workflow 定义
│   ├── __init__.py
│   ├── state.py             # AgentState re-export（保留）
│   ├── graph.py             # build_research/chat/knowledge_graph（保留）
│   └── builder.py           # Graph 缓存（保留）
│
├── services/                 # [新建] 平台级服务（非 Agent 专属）
│   ├── __init__.py
│   ├── router.py            # ← graph/router.py（Agent 路由）
│   ├── pipeline.py          # ← graph/pipeline.py（文档处理 Pipeline）
│   ├── task_queue.py        # ← graph/task_queue.py（任务队列）
│   ├── approval.py          # ← graph/approval.py（审批流）
│   ├── batch_embed.py       # ← graph/batch_embed.py（批量 Embedding）
│   └── vault_generator.py   # ← graph/vault_generator.py（Vault 生成）
│
├── checkpoint.py            # ← graph/checkpoint.py（LangGraph Checkpoint）
```

**影响的 import 修改**（约 8 个文件）：
- `api/chat.py`: `from graph.router import` → `from services.router import`
- `api/agents.py`: 同上
- `api/models.py`: 同上
- `api/tasks.py`: `from graph.task_queue import` → `from services.task_queue import`
- `api/knowledge.py`: 同上
- `api/approvals.py`: `from graph.approval import` → `from services.approval import`
- `api/vault.py`: `from graph.vault_generator import` → `from services.vault_generator import`
- `scheduler/scheduler.py`: 如有引用 `graph.pipeline` → `services.pipeline`

### 3.2 解决 "Knowledge Agent" 命名冲突

**问题**: 两个完全不同的系统共享 "Knowledge Agent" 名称：
- `agents/knowledge_agent.py` = Chat 模式 Agent（RAG + Obsidian Vault 读写）
- `knowledge_agent/` = 文档摄入 Pipeline（6 节点，非对话型）

**方案**: 重命名 Chat 模式 Agent

| 当前 | 重命名为 | 理由 |
|------|----------|------|
| `agents/knowledge_agent.py` | `agents/vault_agent.py` | 其核心能力是 Obsidian Vault 读写 |
| class `KnowledgeAgent` | class `VaultAgent` | 与文件名对齐 |
| router 中 `"knowledge"` key | `"vault"` | 路由标识 |
| `prompts/knowledge/system.md`（如存在）| 保留（这是 knowledge_agent/ pipeline 用的）| 不冲突 |

**注意**: `api/knowledge.py` 路由文件同时引用了 `knowledge_agent/storage/`（Pipeline 的存储）和 `graph/task_queue.py`，它是 Knowledge Pipeline 的 API 入口，不需要改名。

**影响文件**（约 5 个）：
- `agents/knowledge_agent.py` → `agents/vault_agent.py`
- `graph/router.py`（→ `services/router.py`）: 更新 AGENT_REGISTRY
- `graph/graph.py`: `build_knowledge_graph()` → `build_vault_graph()`
- `graph/builder.py`: `get_knowledge_graph()` → `get_vault_graph()`
- `agents/base_agent.py`: 如有 knowledge 引用

### 3.3 将 `src/` 整合为 `langgraph/agent/` 可正式导入的模块

**问题**: `news_agent/collector/web_collector.py` 通过 `sys.path.insert` 导入 `src/`，脆弱且违反模块边界。

**方案**: 将 `src/` 移至 `langgraph/agent/providers/`（或保留 `src/` 但改为正式 Python 包）

推荐方案 A（最小改动）：
- 保留 `src/` 位置不变
- 在 `langgraph/requirements.txt` 中添加 `-e ../` 或在 Dockerfile 中设置 `PYTHONPATH=/app/src`
- 移除 `web_collector.py` 中的 `sys.path` hack，改为直接 `from ingestion.web.link_extractor import LinkExtractor`

推荐方案 B（彻底整合）：
- 将 `src/ingestion/` 移至 `langgraph/agent/ingestion/`
- 将 `src/providers/` 移至 `langgraph/agent/providers/`
- 将 `src/pipelines/web_pipeline.py` 移至 `langgraph/agent/services/web_pipeline.py`
- 删除 `src/` 目录

**建议**: 方案 A 风险更低，方案 B 更整洁。需用户决策。

### 3.4 重命名 `nodes/` 为 `rag_nodes/`（可选）

**问题**: `nodes/` 目录名与 `knowledge_agent/nodes/`、`news_agent/nodes/` 冲突，容易混淆。实际内容是 RAG 检索链路的共享节点。

**方案**: 重命名为 `rag_nodes/` 或 `shared_nodes/`

**影响**: `graph/graph.py` 和 `agents/base_agent.py` 中约 10 处 import。

**优先级**: Nice-to-have（Phase 3 中风险最高的改动，收益有限）

---

## Phase 4: Specs 规范同步

**优先级**: Important

### 4.1 更新 `specs/architecture.yaml`

需修改：
1. `meta.scope` 追加 `"src/"` 或 `"langgraph/agent/providers/"`（取决于 Phase 3.3 决策）
2. `dependency_rules.DEP-001` 补充 Pipeline Agent 的依赖链：
   ```yaml
   - id: DEP-001b
     level: MUST
     rule: "Pipeline Agent 依赖方向：{agent}/graph → {agent}/nodes → {agent}/storage + tools/"
     check: "knowledge_agent/ 和 news_agent/ 内部遵循独立分层"
   ```
3. `organization_rules.ORG-002` 放宽：允许 Pipeline Agent 在自身目录内定义 State（不强制放 `schemas/`）
4. 新增 `services/` 层规则（如 Phase 3.1 执行）

### 4.2 更新 `specs/agent-registry.yaml`

需修改：
1. §1 表格中 "Knowledge Agent" 拆分为两行：
   - **Vault Agent** | `agents/vault_agent.py` | Chat Agent | Obsidian Vault 读写 + RAG
   - **Knowledge Ingestion Agent** | `knowledge_agent/` | Pipeline | 文档 → 结构化知识（6 节点）
2. §4 命名映射表追加：`Knowledge Agent (chat) → Vault Agent`
3. §2 Knowledge MCP Server Tools 数量验证（当前写 15，需确认实际）

### 4.3 验证 `specs/ontology.yaml` 完整性

确认：
- 10 Entity Types 与 `knowledge_agent/nodes/entity.py` + `news_agent/nodes/entity.py` 中的 `VALID_ENTITY_TYPES` 一致
- 9 Event Types 与 `news_agent/nodes/event.py` 中的 `VALID_EVENT_TYPES` 一致
- 6 News Categories 与 `news_agent/nodes/classifier.py` 中的 `VALID_CATEGORIES` 一致

---

## Phase 5: 文档整理

**优先级**: Nice-to-have（不影响运行时）

### 5.1 AI-Platform-System-Design/ 处理策略

| 文件 | 状态 | 操作 |
|------|------|------|
| 01-05（总体架构/组件/目录/Docker/FastAPI） | 部分过时 | 标注"历史参考" |
| 06-08（LangGraph/State/Node 设计） | 仅适用于 Chat Agent | 补充 Pipeline Agent 说明 |
| 09-11（Tool/Memory/RAG） | 当前有效 | 保留 |
| 12（数据库设计） | 过时（缺 news schema） | 需更新 |
| 13（MCP 设计） | 当前有效 | 保留 |
| 16（开发规范） | architecture.yaml 的解释源 | 同步更新 |
| 26（Crawl4AI） | 当前有效 | 保留 |
| 28（图工程架构） | 当前有效（AGE） | 保留 |
| 30-34（Knowledge 系列） | 当前有效 | 保留 |

**操作**: 在 `AI-Platform-System-Design/README.md` 中添加"文档状态索引表"，标注每个文件的状态。

### 5.2 docs/design/ 处理

| 文件 | 状态 |
|------|------|
| `新闻智能管线规范.md` | 当前有效（已实施） |
| `Knowledge MCP Server 设计规范.md` | 当前有效 |
| `Apache_AGE_Knowledge_Graph_DDL_Schema.md` | 当前有效 |
| `apache-age-cypher-query-library.md` | 当前有效 |
| `knowledge-graph-ingestion-agent.md` | 当前有效（已实施为 knowledge_agent/） |
| `mcp-access-control.md` | 部分实施（MCP-005/006 规则存在但审计日志未实现） |
| `monitoring-sla-spec.md` | 规划中 |
| `invenst_platform.md` | 总体设计，部分过时 |
| `新闻生命周期管理（DLM）总体原则.md` | 规划中 |
| `design-document-template.md` | 模板，保留 |

---

## Phase 6: 合规自动化（可选）

**优先级**: Nice-to-have

### 6.1 创建 `scripts/check_architecture.py`

自动化检查 architecture.yaml 中的规则：
- ARCH-003: 扫描 `nodes/` 文件的 import 语句，检测 asyncpg/httpx 直接导入
- MCP-002: 扫描 `mcp-*/server/tools/` 的 import，检测 asyncpg 直接导入
- PRM-004: 检查每个注册 Agent 是否有 `prompts/{name}/system.md`
- DEP-002: 检测反向依赖

### 6.2 集成到 CI（如有）或 pre-commit hook

---

## 执行策略与多 Agent 协作方案

### 推荐执行顺序

```
Phase 1 (审计) ──→ Phase 2 (清理) ──→ Phase 3 (重构) ──→ Phase 4 (specs) ──→ Phase 5 (文档)
                                                                              ──→ Phase 6 (自动化)
```

### 多 Agent 协作分工

本审查适合拆分为 3 个并行子任务（Phase 1 阶段）：

| Agent | 职责 | 输入 | 输出 |
|-------|------|------|------|
| Agent A: 代码结构 | 依赖图绘制 + 死代码识别 | graph/, nodes/, agents/, api/, services/ | 依赖矩阵 + 移动方案 |
| Agent B: 数据库 | Schema/表使用审计 | postgres/init/*.sql + 全项目 grep | 未使用表清单 + 删除建议 |
| Agent C: 规范文档 | specs 对齐 + 文档时效 | specs/*.yaml + AI-Platform-System-Design/ + docs/ | 偏差清单 + 更新建议 |

Phase 3（重构）建议串行执行（import 路径变更有级联影响）。

### 风险评估

| 改动 | 风险等级 | 影响范围 | 缓解措施 |
|------|----------|----------|----------|
| Phase 2: 删除空目录/缓存 | 无 | 无运行时影响 | 直接执行 |
| Phase 3.1: graph/ → services/ | 中 | 8 个 api 文件 + scheduler | 逐文件修改 + py_compile 验证 |
| Phase 3.2: Knowledge → Vault 重命名 | 中 | 5 个文件 + 前端（如有调用） | 检查 frontend/ API 调用 |
| Phase 3.3: src/ 整合 | 高 | web_collector + web_pipeline + Dockerfile | 需 Docker 构建验证 |
| Phase 3.4: nodes/ 重命名 | 中 | 10+ import 变更 | 可选，收益有限 |
| Phase 4: specs 更新 | 无 | 纯文档 | 直接执行 |

---

## 待用户决策项

1. **Phase 3.3**: `src/` 整合选方案 A（PYTHONPATH）还是方案 B（移入 langgraph/agent/）？
2. **Phase 3.4**: 是否执行 `nodes/` → `rag_nodes/` 重命名？（收益有限，风险中等）
3. **Phase 3.2**: Vault Agent 命名是否可接受？或有其他偏好（如 `obsidian_agent`）？
4. **Phase 6**: 是否需要合规自动化脚本？
