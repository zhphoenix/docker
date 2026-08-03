# SiYuan Knowledge Workspace 集成实施计划

## 一、Exploration Summary（关键发现）

### 1.1 设计文档核心意图（已通读 6 份）
- **统一术语.md**：红线原则——PostgreSQL 为唯一 SoT；AGE 仅图谱；Qdrant 仅语义检索；SiYuan 仅展示；所有访问经 Knowledge MCP Server；页面由模板渲染非 LLM 拼接。定义 `Knowledge Inbox`（PostgreSQL）、`Render Queue`（`knowledge_render_jobs` 表）、`Knowledge Rendering Engine`（独立模块）等 55 术语。
- **AI 自动生成知识页面设计规范.md**（§16 Render Queue，L573-620）：`knowledge_render_jobs` 表字段 `id/entity/type/status/retry/priority`；流程 Queue→Worker→Render→Sync；页面增量更新（按 Section，如仅刷 Financial Section）。
- **SiYuan 接入 MCP Server 设计规范.md**（L654-681）：PG 推荐增加 `last_synced_at/last_modified_by/sync_version/sync_status`；`sync_status` 枚举 Synced/Pending Review/Conflict；同步先查版本再决定自动更新/Diff/人工审核。
- **HITL 知识审核设计规范.md**（§4，L114-159）：Inbox 数据结构 `id/type/status/confidence/source/created_time/reviewer/review_time`；状态 NEW→EXTRACTED→READY_REVIEW→APPROVED/REJECTED→ARCHIVED。
- **Knowledge Object Template 设计规范.md**：三层模板（Knowledge Schema→Knowledge Object Template→SiYuan Template），12 种核心对象，Phase1-3。
- **SiYuan 替代 Obsidian 实施计划.md**：SiYuan Docker 部署（端口 6806），Notebook 设计（Companies/Industries/Events/Knowledge Inbox 等），Phase0-5。

### 1.2 现有基础设施（已核实文件与行号）
- **PG schema**：`/mnt/e/ai-platform/postgres/init/07-knowledge-database.sql` 已建 4-schema（core/document/audit/taxonomy）。已有 `audit.knowledge_versions`（L234，版本化）、`core.knowledge_conflicts`（L202）、`core.facts.lifecycle_status`（L113）、`core.events`（L184）。**缺口**：无 `inbox` 表、无 `knowledge_render_jobs` 表、`core.entities` 无 sync 字段（last_synced_at/sync_version/sync_status）。
- **Knowledge MCP Server**：`/mnt/e/ai-platform/mcp-knowledge/server/main.py`（L61-73）注册 6 模块 tools；`tools/write.py` 已有写入工具；`storage/postgres.py`（L504 `update_knowledge` 事务内版本快照）。
- **现有可复用服务**（`/mnt/e/ai-platform/langgraph/agent/services/`）：
  - `task_queue.py`（L23-162）：PG 任务队列，create/start/complete/fail/retry（指数退避），**可直接复用为 Render Queue 基础**。
  - `approval.py`（L36-179）：HITL 审批，基于 tasks 表（task_type='approval'），回调注册表，**可直接复用为 Knowledge Review Center 后端**。
  - `lifecycle.py`：DLM 生命周期管理。
- **Ingestion Agent**：`/mnt/e/ai-platform/langgraph/agent/knowledge_agent/graph.py`（L41-76）6 节点管线（Parser→Entity→[Relation||Fact]→Validator→Merger），带 `_timed` 计时装饰器（性能基线已存在）。
- **compose.yml（当前打开文件）**：`/mnt/e/ai-platform/mcp-knowledge/compose.yml`（L1-49），mcp-knowledge 服务 :8200，cpus 1.0 / memory 1G，经 localhost:5433/6333/8001 通信。

### 1.3 数据目录现状
- **vault**：`/mnt/e/ai-platform/data/vault/` 含 `companies/`（**7894 个目录，严重混乱**：`000001`/`000001_平安银行`/`000001_長和` 重复，且 `000002` 与 `000002_万  科Ａ`（含空格）与 `000002_万科A` 并存）、`queries/`、`skills/`、`templates/`、残留 `.obsidian/`、`MCP_SETUP.md`、`Untitled.md`。
  - 年报结构：`companies/000001_平安银行/2023/2023_年度报告.md`（公司代码_公司名/年份/年份_年度报告.md）。
- **MinIO**:`/mnt/e/ai-platform/minio/data/documents/cn/600519/annual_report/2024__XLDIR__/xl.meta`（MinIO 内部格式，实际 PDF 需经 API 访问，不能直接文件系统读取）；含 cn/hk/us 分区。`/mnt/e/ai-platform/minio/data/knowledge/` 有 cn/hk/us 各公司目录。

---

## 二、Approach Overview

方案使 SiYuan 作为纯展示层接入，一切知识对象仍以 PostgreSQL 为 SoT，通过新增的 `adapters/siyuan/` 适配层（client/mapper/templates/sync）与 `Knowledge Rendering Engine` 将 PG 数据渲染/增量同步到 SiYuan 页面。核心权衡：**复用现有 task_queue.py 与 approval.py 作为渲染队列与审核后端**（避免重复造轮子），但需新增 PG 迁移（inbox 表、render jobs 表、entities 同步字段）并引入 SiYuan API 幂等写入与限流，以控制同步吞吐量。性能上采用"按 Section 增量更新 + 版本 Diff + 批处理 + 限流"，避免全量重渲染与 API 并发打满。

---

## 三、Implementation Steps（按 Phase 拆分为 PR 粒度）

### Phase 0 — 前置：数据目录治理（P1）
**目标**：清理 vault 混乱目录，为 SiYuan 挂载做准备；回答用户两个补充问题。
**涉及文件**：
- `/mnt/e/ai-platform/data/vault/companies/`（治理）
- `/mnt/e/ai-platform/data/vault/.obsidian/`、`MCP_SETUP.md`、`Untitled.md`（清理残留）
- `/mnt/e/ai-platform/scripts/`（新增 `dedupe_vault.py`）

**关键代码片段**（`dedupe_vault.py` 核心逻辑）：
```python
# 按 6 位码识别公司，保留规范名目录，删除/合并重复目录
import re, shutil, os
VAULT = "/mnt/e/ai-platform/data/vault/companies"
def norm_key(name):  # 去空格/全半角，提取 6 位代码
    m = re.match(r"^(\d{6})", name.strip())
    return m.group(1) if m else None
# 1. 扫描建立 code -> [dirs] 映射
# 2. 规范化: 优先保留 "代码_公司名" 且无多余空格者
# 3. 重复目录走 ESG 归档: 移到 data/vault/_archive/
```
**验证方式**：`ls data/vault/companies/ | wc -l` 从 7894 降至约 3000+；无重复代码目录；`000002_万 科Ａ` 与 `000002_万科A` 合并为唯一规范名。

**回答补充问题**：
- **① 文件夹名称是否应改**：`data/vault/` 名称保留（承载 SiYuan workspace 语义），但目录内 `companies/` 需规范化为 `公司代码_公司名/`（去空格），并清理 `.obsidian/` 残留。建议将 `data/vault/` 作为 SiYuan 容器的数据卷挂载根。
- **② 目录结构**：`companies/代码_公司名/年份/年份_年度报告.md`（如 `000001_平安银行/2023/2023_年度报告.md`）；`queries/`、`skills/`、`templates/` 为辅助目录。

### Phase 1 — PG Schema 迁移（P1）
**目标**：补齐设计文档要求的 Inbox 表、Render Queue 表、同步字段。
**涉及文件**：`/mnt/e/ai-platform/postgres/init/08-knowledge-siyuan.sql`（新增，幂等）

**关键代码片段**：
```sql
-- Knowledge Inbox 表（HITL 规范 §4）
CREATE TABLE IF NOT EXISTS core.knowledge_inbox (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    object_type   TEXT NOT NULL,
    object_id     UUID,
    status        TEXT NOT NULL DEFAULT 'NEW',  -- NEW/EXTRACTED/READY_REVIEW/APPROVED/REJECTED/ARCHIVED
    confidence    FLOAT,
    source        TEXT,
    content       JSONB DEFAULT '{}',
    reviewer      TEXT,
    review_time   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_inbox_status ON core.knowledge_inbox(status);
CREATE INDEX IF NOT EXISTS idx_inbox_obj ON core.knowledge_inbox(object_type, object_id);

-- Render Queue 表（AI 自动生成页面规范 §16）
CREATE TABLE IF NOT EXISTS core.knowledge_render_jobs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity       UUID REFERENCES core.entities(id) ON DELETE CASCADE,
    type         TEXT NOT NULL,       -- Company/Industry/Event/...
    section      TEXT,                -- 增量用：Financial/Operations/...
    status       TEXT DEFAULT 'pending', -- pending/running/done/failed
    retry        INT DEFAULT 0,
    priority     INT DEFAULT 5,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_render_jobs_status ON core.knowledge_render_jobs(status, priority);

-- entities 同步字段（SiYuan 接入规范 L654-665）
ALTER TABLE core.entities ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMPTZ;
ALTER TABLE core.entities ADD COLUMN IF NOT EXISTS last_modified_by TEXT;  -- AI/Human
ALTER TABLE core.entities ADD COLUMN IF NOT EXISTS sync_version INT DEFAULT 0;
ALTER TABLE core.entities ADD COLUMN IF NOT EXISTS sync_status TEXT DEFAULT 'Synced';
-- sync_status 枚举: Synced / Pending Review / Conflict
```
**验证方式**：`psql -d ai -c '\d core.knowledge_inbox'` 确认表存在；`\d core.entities` 确认 4 个新列；重复执行脚本幂等不报错。

### Phase 2 — SiYuan Docker 部署（P1）
**目标**：部署 SiYuan 容器，作为展示层。
**涉及文件**：`/mnt/e/ai-platform/siyuan/compose.yml`（新增）、`/mnt/e/ai-platform/siyuan/.env`（新增）

**关键代码片段**（siyuan/compose.yml）：
```yaml
services:
  siyuan:
    image: b3log/siyuan:latest
    container_name: siyuan
    ports:
      - "6806:6806"
    volumes:
      - ../data/vault:/workspace   # 挂载治理后的 vault
    environment:
      - SIYUAN_ACCESS_AUTH_CODE=<token>   # 从 .env 读
    restart: unless-stopped
    networks:
      - ai-platform
```
**验证方式**：`docker compose -f siyuan/compose.yml up -d` 后浏览器访问 `http://localhost:6806`，确认 Notebook 正常加载。

### Phase 3 — SiYuan Adapter 模块（P1）
**目标**：实现封装 SiYuan HTTP API 的适配层，置于 knowledge 服务内。
**涉及文件**（新增）：
- `/mnt/e/ai-platform/mcp-knowledge/server/adapters/__init__.py`
- `/mnt/e/ai-platform/mcp-knowledge/server/adapters/siyuan/client.py`：HTTP 客户端，含**限流/批处理/幂等重试**
- `/mnt/e/ai-platform/mcp-knowledge/server/adapters/siyuan/mapper.py`：Knowledge Object ↔ SiYuan 文档映射
- `/mnt/e/ai-platform/mcp-knowledge/server/adapters/siyuan/templates.py`：Jinja2 模板渲染
- `/mnt/e/ai-platform/mcp-knowledge/server/adapters/siyuan/sync.py`：增量同步 + 版本 Diff
- `/mnt/e/ai-platform/mcp-knowledge/server/adapters/siyuan/config.py`：SiYuan 连接配置

**关键代码片段**（client.py 限流 + 幂等）：
```python
import asyncio, aiohttp, hashlib

class SiYuanClient:
    def __init__(self, base_url, token, concurrency=4, queue_size=100):
        self._sem = asyncio.Semaphore(concurrency)  # 并发控制
        self._q = asyncio.Queue(maxsize=queue_size)  # 背压
    async def create_doc(self, notebook, path, content):
        # 幂等: 先查是否存在, 存在则更新
        async with self._sem:
            r = await self._post("/api/filetree/createDocWithMd", {...})
            return r
    async def render_worker(self):
        # 从渲染队列消费, 背压保护
        while True:
            job = await self._q.get()
            await self._render(job)
            await self._q.task_done()
```
**验证方式**：单测 `pytest mcp-knowledge/tests/test_siyuan_client.py` 验证并发限流（>4 并发被阻塞）与幂等（重复 create 不产生重复文档）。

### Phase 4 — Knowledge Rendering Engine（P1）
**目标**：独立渲染引擎，消费 `knowledge_render_jobs`，渲染知识页面并同步到 SiYuan。
**涉及文件**（新增）：
- `/mnt/e/ai-platform/mcp-knowledge/server/rendering/engine.py`：渲染引擎主循环
- `/mnt/e/ai-platform/mcp-knowledge/server/rendering/renderer.py`：按 Section 增量渲染
- `/mnt/e/ai-platform/mcp-knowledge/server/rendering/diff.py`：基于 `audit.knowledge_versions` 做 Diff
- `/mnt/e/ai-platform/mcp-knowledge/server/rendering/worker.py`：后台 Worker（复用 task_queue 模式）

**关键代码片段**（engine.py 增量渲染 + 复用 task_queue）：
```python
from langgraph.agent.services.task_queue import task_queue  # 复用现有队列

async def render_job(job):
    # 1. 从 PG 读取实体数据
    # 2. 查 audit.knowledge_versions 做 Diff，仅刷新变更 Section
    changed = await diff.get_changed_sections(job["entity"], job["section"])
    # 3. 渲染变更 Section
    md = await renderer.render_section(job["entity"], changed)
    # 4. 同步到 SiYuan（幂等）
    await siyuan_client.update_section(job["entity"], md)
    # 5. 更新 sync_status = 'Synced', last_synced_at
```
**验证方式**：手动插入一条 `knowledge_render_jobs` 记录，观察 Worker 消费、SiYuan 页面生成、`core.entities.sync_status` 更新。

### Phase 5 — Knowledge Inbox 与审核流（P1）
**目标**：Ingestion Agent 输出先进 Inbox，结合现有 approval.py 实现审核。
**涉及文件**：
- `/mnt/e/ai-platform/langgraph/agent/knowledge_agent/nodes/merger.py`（改：写入前先入 Inbox）
- `/mnt/e/ai-platform/langgraph/agent/services/approval.py`（复用，无需大改）
- `/mnt/e/ai-platform/mcp-knowledge/server/tools/inbox.py`（新增：Inbox 工具）

**关键代码片段**（merger.py 接入 Inbox）：
```python
async def knowledge_merger(state):
    # ... 原有合并逻辑 ...
    # 新增: 写入 Inbox 而非直接入正式库
    await pg.execute(
        "INSERT INTO core.knowledge_inbox (object_type, object_id, status, confidence, content) VALUES ($1,$2,'EXTRACTED',$3,$4)",
        obj_type, obj_id, confidence, json.dumps(content)
    )
    # 高置信度且来源可信 → 自动 APPROVED；否则等待人工
    if should_auto_approve(state): await set_approved(obj_id)
    else: await create_approval(...)  # 复用 approval.py
```
**验证方式**：运行一次知识摄取，确认实体先进入 `core.knowledge_inbox`，low-confidence 记录生成 `approval` 任务。

### Phase 6 — Knowledge MCP Tools 扩展（P2）
**目标**：新增 SiYuan/Inbox 相关业务级 Tool（设计文档要求的 search_notes 等）。
**涉及文件**：
- `/mnt/e/ai-platform/mcp-knowledge/server/tools/siyuan.py`（新增）
- `/mnt/e/ai-platform/mcp-knowledge/server/main.py`（改：注册新工具）

**关键代码片段**（main.py 注册）：
```python
from server.tools.siyuan import register_siyuan_tools
register_siyuan_tools(mcp)   # 新增 search_notes / get_note / create_knowledge_object / update_knowledge_object / create_research_report / create_event_note
```
**验证方式**：MCP 客户端能发现并调用新工具；`knowledge_render_jobs` 无积压。

### Phase 7 — 前端 Knowledge Review Center（P2）
**目标**：Web UI 审核界面（非 SiYuan）。
**涉及文件**：
- `/mnt/e/ai-platform/frontend/src/app/pages/KnowledgeReviewPage.tsx`（新增）
- `/mnt/e/ai-platform/frontend/src/app/routes.tsx`（改：注册路由）
- 复用 `/mnt/e/ai-platform/frontend/src/components/knowledge/` 现有组件

**关键代码片段**（KnowledgeReviewPage 核心）：
```tsx
// 调 approval.py 的 list_pending_approvals 后端接口
const { data } = useQuery({ queryKey: ['pending-approvals'], queryFn: () => api.get('/knowledge/approvals/pending') });
// 渲染待审核卡片 + 通过/拒绝按钮（调 approve/reject）
```
**验证方式**：本地启动前端，`/knowledge/review` 路由显示待审核项，可执行通过/拒绝。

### Phase 8 — 性能与可扩展性优化（P2）
**目标**：针对任务要求的 4 大性能点做工程化。
**涉及文件**：
- `/mnt/e/ai-platform/mcp-knowledge/server/rendering/worker.py`（改：多 worker + 背压）
- `/mnt/e/ai-platform/mcp-knowledge/server/adapters/siyuan/client.py`（已含限流，可调参）
- `/mnt/e/ai-platform/mcp-knowledge/server/rendering/diff.py`（改：Diff 复用 audit.knowledge_versions）

**性能评估与对策**：
| 关注点 | 评估 | 对策 |
|--------|------|------|
| Render Queue 吞吐量 | 5000+ 公司 × 多 Section，单 worker 会慢 | 复用 task_queue.py 多 worker + 优先级队列 + 背压（Asyncio Queue maxsize） |
| SiYuan API 并发限制 | 过高并发会触发 API 限流/内存崩 | client.py 用 Semaphore(concurrency=4) + 重试退避 |
| 增量 Diff 开销 | `audit.knowledge_versions` 已存版本快照 | 复用做 Section 级 Diff，仅刷变更区，避免全量重渲染 |
| Inbox 队列积压 | 大量 AI 输出涌入 | 自动审批策略（高置信+可信来源直接 APPROVED）+ lifecycle.py 归档阈值 |

**验证方式**：对 100 个实体压测，确认渲染队列消费速率稳定、无 API 429、PG 无积压。

### Phase 9 — 监控与文档资产（P3）
**目标**：日志/监控补齐，统一术语校验。
**涉及文件**：
- `/mnt/e/ai-platform/AI-Platform-System-Design/17_日志监控.md`（对齐补充）
- `/mnt/e/ai-platform/mcp-knowledge/server/rendering/`（加 metric 埋点）
- 依赖 `_timed` 装饰器（`knowledge_agent/graph.py` L24）扩展性能基线

**验证方式**：渲染任务有 metric 输出；Grafana/Prometheus 可观测（若已配置）。

---

## 四、Dependencies（DAG）

```
Phase0 (vault 治理)
   │
   v
Phase1 (PG schema 迁移) ──── Phase2 (SiYuan 部署)
   │                              │
   └────────────┬─────────────────┘
                v
        Phase3 (SiYuan Adapter)
                │
                v
        Phase4 (Rendering Engine)
                │
                ├──> Phase5 (Inbox/审核流)  ──> Phase6 (MCP Tools) ──> Phase7 (Review Center)
                │
                └──> Phase8 (性能优化, 依赖 Phase3/4)
                            │
                            v
                       Phase9 (监控, 依赖 Phase8)
```

说明：
- Phase1 需先于 Phase3/4/5（依赖新表）。
- Phase2 需先于 Phase3 联调（Adapter 需真实 SiYuan 实例）。
- Phase4 依赖 Phase3（Adapter 是渲染引擎的输出通道）。
- Phase5 依赖 Phase1（inbox 表）与 Phase4（渲染联动）。
- Phase6 依赖 Phase5（Inbox 工具需要审核流）。
- Phase7 依赖 Phase5/6（Review Center 调 approval + Inbox MCP）。
- Phase8 依赖 Phase3/4（对已有实现做性能增强）。
- Phase9 依赖 Phase8（对性能指标做监控）。

---

## 五、Risks and Mitigations

| 风险 | 影响 | 缓解/回退方案 |
|------|------|--------------|
| **SiYuan API 并发超限** | 渲染任务失败/积压 | Semaphore 限流（concurrency=4）+ 指数退避重试；失败任务回退 pending 由 task_queue 重试 |
| **渲染队列积压**（5000+ 公司） | 页面更新滞后 | 优先级队列 + 多 worker + 背压；突发时降级为"仅同步变更 Section"增量模式 |
| **vault 治理误删**（7894 目录） | 数据丢失 | 治理脚本先 dry-run 生成报告；重复目录移入 `_archive/` 而非直接删；git 提交前人工确认 |
| **Diff 开销过大** | 版本表膨胀 | 复用 `audit.knowledge_versions` 做 Section 级 Diff 而非全量；定期归档旧版本（复用 lifecycle.py） |
| **Inbox 积压** | 审核堆积 | 自动审批策略（高置信+可信来源）+ 归档阈值；reviewer 超时提醒 |
| **MinIO 路径不可直接读**（xl.meta） | PDF 取数失败 | 一律经 MinIO API 访问，不直接读文件系统；文档解析/渲染入口统一走 API |
| **违反"PG 为 SoT"红线** | 架构偏离 | 所有写入必须经 Knowledge MCP Server；SiYuan 仅读；渲染源只读 PG |
| **回退方案** | 整体不可用 | 若 SiYuan 适配层故障，关闭 render worker 即可，PG 数据无损，可从任一阶段恢复 |

---

## 六、优先级总结

- **P1（必须）**：Phase0 vault 治理、Phase1 PG 迁移、Phase2 SiYuan 部署、Phase3 SiYuan Adapter、Phase4 Rendering Engine、Phase5 Inbox/审核流
- **P2（重要）**：Phase6 MCP Tools 扩展、Phase7 前端 Review Center、Phase8 性能优化
- **P3（可选）**：Phase9 监控与文档资产

## 七、Assumptions

- SiYuan 以 Docker 容器部署在 `ai-platform` 网络，端口 6806，数据卷挂载 `data/vault/`。
- 设计文档中"新增 Inbox 表、render jobs 表、sync 字段"是本方案新增的 PG 迁移，不改变现有 4-schema 核心架构。
- 现有 `task_queue.py`、`approval.py`、`audit.knowledge_versions` 直接复用，避免重复实现。
- MinIO 全部经 API 访问（因 `xl.meta` 内部格式，文件系统不可直接读）。