---
name: project-inventory
description: >
  Acts as a senior software architect to inventory the project's real implementation
  and generate/maintain docs/00_Project_Inventory.md as the single source of truth
  for all subsequent architecture, planning, UI/API/Agent design. Use when asked to
  inventory the project, audit what is actually implemented, establish a repository
  baseline, or before starting architecture/API/UI/Agent design that must reference
  real code. Follows three principles: code is the source of truth, no speculation,
  only the current implementation. Covers frontend pages/components/routes, backend
  FastAPI routes/services, database schema, Docker services, MinIO buckets, Qdrant
  collections, AI services, API endpoints, agents and skills. Emits a 15-section
  markdown inventory document.
---

# Project_Inventory 技能

## Purpose（目的）

扮演资深软件架构师，**全面盘点当前项目的真实实现**，建立项目的唯一事实索引
（Single Source of Truth），生成并持续维护 `docs/00_Project_Inventory.md`。

后续所有架构设计、开发计划、UI 设计、API 设计、Agent 设计都必须基于本文件。
因此，本文档必须：

- 客观
- 可验证
- 不推测
- 不包含未来规划
- 与当前代码保持一致

## 三大工作原则

### 第一原则：代码是真实来源（Source of Truth）

分析顺序必须严格遵循：

```
代码
↓
目录结构
↓
Docker Compose
↓
配置文件
↓
数据库
↓
API
↓
历史设计文档（仅作为参考）
```

如果设计文档与代码不一致，**始终以代码为准**。

### 第二原则：禁止推测

如果项目中不存在某模块（例如 Knowledge Graph、Agent、Workflow、API、Docker
Service），不得根据历史文档补充，统一标记为：

```
Status: Not Implemented
```

或：

```
Status: Unknown
```

### 第三原则：只描述当前实现

不得将规划中的内容写成已完成状态。例如代码没有 `Apache AGE` 时，应写：

```
Apache AGE
Status: Planned
Current: Not Implemented
```

而非写"系统采用 Apache AGE"。

## 数据采集步骤（覆盖真实实现）

按以下清单逐项定位真实实现，采集结果与脚本映射见第 4 节：

| # | 采集领域 | 脚本 | 覆盖章节 |
| --- | --- | --- | --- |
| 1 | 仓库结构：`os.walk` 扫描根目录，记录各目录职责，空目录注明 | `collect_01_repo.py` | §2 |
| 2 | 前端：`frontend/src/`（app 路由/pages、components、hooks、services、stores、lib、types），统计页面/组件/路由/API 调用 | `collect_02_frontend.py` | §3 |
| 3 | 后端：`langgraph/`（api 路由、agents、services、tools、graphs、nodes、pipelines、collectors、storage、schemas、providers、skills） | `collect_03_backend.py` | §4、§10 |
| 4 | 数据库：解析 `postgres/init/*.sql` 表/视图/函数/扩展；确认是否存在 Knowledge Graph（Apache AGE） | `collect_04_database.py` | §5 |
| 5 | 对象存储：解析 `minio/`（bucket 初始化脚本、`init-buckets.sh`） | `collect_06_storage_vector.py` | §6 |
| 6 | 向量库：解析 `qdrant/init_qdrant.py` 与 `scripts/batch_embed_to_qdrant.py`（collection、vector size、distance、payload） | `collect_06_storage_vector.py` | §7 |
| 7 | AI 服务：解析 `embedding/`、`reranker/`、`docling/`、`paddleocr/`、`sisyphus/` 的 compose 与配置 | `collect_07_ai_agents.py` | §8 |
| 8 | Docker 服务：解析根 `compose.yml` 及各子目录 compose（image、port、health、dependency） | `collect_05_docker.py` | §9 |
| 9 | API：读取 `langgraph/api/` 的 FastAPI 路由注册，收集 Method/Path/Description/Status | `collect_03_backend.py` | §10 |
| 10 | Agent/技能：扫描 `langgraph/agents/`、`langgraph/skills/`、`.qoder/skills/`、`mcp-knowledge/`、`mcp-news/` | `collect_07_ai_agents.py` | §11、§12 |

## 自动采集脚本设计（选项B 实现方案，多脚本防溢出）

技能执行时，Agent 按领域生成多个轻量采集脚本（临时，采集后由用户决定是否保留），
每个脚本只输出**结构化摘要**（清单/元数据），落盘到 `scripts/collect_out/<domain>.json`
（**统一技能分析输出目录**：glossary 的 code-analysis 术语事实清单也输出到此处），
Agent 按章节**分批读取**，避免单次注入全部上下文导致溢出。

**脚本映射（每脚本 ↔ 一个/多个章节）**：

| 脚本 | 输出文件 | 覆盖章节 | 采集内容 |
| --- | --- | --- | --- |
| `collect_01_repo.py` | `repo.json` | §2 | 目录树 + 文件计数，空目录注明 |
| `collect_02_frontend.py` | `frontend.json` | §3 | app 路由/pages、components、hooks、services、stores、lib 清单与 API 调用 |
| `collect_03_backend.py` | `backend.json` | §4、§10 | FastAPI 路由 Method/Path/函数名、模块结构（agents/services/tools/graphs/nodes） |
| `collect_04_database.py` | `database.json` | §5 | 解析 `postgres/init/*.sql`，仅输出表名/列名/类型/扩展摘要，不输出 DDL 全文 |
| `collect_05_docker.py` | `docker.json` | §9 | 根 compose + 子 compose 服务名/image/port/health/dependency |
| `collect_06_storage_vector.py` | `storage.json` | §6、§7 | MinIO bucket + Qdrant collection/vector size/distance |
| `collect_07_ai_agents.py` | `ai_agents.json` | §8、§11、§12 | AI 服务（embedding/reranker/docling/paddleocr）+ Agent/MCP/技能清单 |

**防溢出关键原则**：

- **轻量摘要**：只列清单/字段名/统计，绝不输出文件正文（SQL 只输出 `CREATE TABLE`
  名+列名+类型，不输出全部 DDL；路由只输出 method/path/函数名，不输出函数体）
- **分批注入**：Agent 每次只读取一个 JSON 文件并填充对应章节，章节间互不污染
- **遇超限再拆分**：若某领域（如后端模块多）单文件仍过大，随即按子模块再拆
  （如 `backend_router.json` / `backend_services.json`）
- **前置检查**：脚本运行前确认 `docker compose ps` 与 `.env` 存在（技能**不读取** `.env` 内容）

## 输出文档结构（15 章节模板）

定义 `docs/00_Project_Inventory.md` 的章节，每章给出表格/字段模板：

1. **Project Overview**：项目名称、定位、当前版本（如存在）、技术栈、当前实现状态
2. **Repository Structure**：目录职责表（frontend/、langgraph/、docker/、docs/、scripts/…），空目录注明
3. **Frontend Inventory**：Module / Status / Description（Pages、Layout、Components、Hooks、Context、Store、API、Routes）
4. **Backend Inventory**：Router / Service / Repository / Models / Schemas / Middleware / Dependency / Background Tasks（真实存在内容）
5. **Database Inventory**：Schema / Table / View / Function / Extension；Knowledge Graph 不存在必须明确说明
6. **Object Storage Inventory**：Bucket / 用途 / 当前状态
7. **Vector Database Inventory**：Collection / Vector Size / Distance / Payload
8. **AI Services Inventory**：Embedding / Reranker / LLM / Docling / OCR，标注 Implemented / Running / Planned
9. **Docker Services Inventory**：Image / Port / Health / Dependency
10. **API Inventory**：Method / Path / Description / Status
11. **Agent Inventory**：LangGraph / MCP / Workflow / Scheduler（当前真实存在；没有不得推测）
12. **Knowledge Inventory**：Documents / Chunks / Embedding / Metadata / Knowledge Graph / Entity / Relation，说明哪些已实现、哪些仍属规划
13. **Current Module Status**：模块矩阵 Module / Status / Progress / Notes
14. **Current Technical Debt**：只记录事实（模块职责不清、API 不统一、页面重复、数据流混乱、文档与代码不一致），不给解决方案
15. **Architecture Baseline**：前端 / 后端 / 数据 / AI / 部署架构，一律依据代码

**防溢出策略（与第 4 节同源）**：

- **按章节增量写入**：生成时逐章写入（Write/SearchReplace 追加），不一次性输出完整 15 章；每章仅填表格/清单，控制单次输出 token
- **按需读取/更新**：维护时只读取需变更章节 + 对应采集 JSON，对文档用 grep 定位相关章节而非全文读入
- **保持摘要性质**：全文档为摘要索引，依赖第 4 节的 JSON 落盘作为原始数据源，不将详细内容重复写入文档
- **遇文档过大再细分**：若文档增长超限，将章节压缩为更紧凑表格形式，或按模块拆分为带索引的多个文件（保留单文件入口）

## 状态分类与进度估算规范

- **状态枚举**：`Implemented` / `Partial` / `Planned` / `Unknown`；不存在 → `Not Implemented`
- **进度估算**：Progress 必须依据真实实现（如：模块已实现页面+后端+API 计 80%，仅页面存在计 20%，未开始计 0%），禁止凭空赋值

## 更新/维护 Workflow（运行方式）

可重复执行的流程：

1. **触发**：用户输入 `/project-inventory` 或描述"盘点项目 / 更新项目清单"。
2. **采集**：按第 4 节生成并运行各领域采集脚本，输出 JSON 落盘到 `scripts/collect_out/`
   （统一技能分析输出目录，与 glossary 的 code-analysis 产物同处）。
3. **对比**：对照现有 `docs/00_Project_Inventory.md`，按章节定位差异（grep 定位，不全读）。
4. **更新**：按章节增量写入 15 章节，严格遵循三大原则。
5. **输出**：给出变更摘要（新增/更新/移除的章节与条目）。

技能遵循：不静默修改、改动以代码为准。

## Constraints（约束）

本技能**绝不**：

- 推测或发明不存在的模块（标记 `Not Implemented` / `Unknown`）
- 将规划中的内容写成已完成状态
- 修改代码、提出架构优化建议、设计未来功能
- 读取 `.env` 文件内容
- 静默重命名已有产物；新发现模块标注 `Unknown` / `Not Implemented`

## Success Criteria（成功标准）

- `docs/00_Project_Inventory.md` 中每项均可通过当前代码验证
- 状态区分准确（Implemented / Partial / Planned / Unknown / Not Implemented）
- 与代码一致，可作后续架构 / API / UI / Agent 设计的唯一事实来源