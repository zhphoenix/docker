# SiYuan 接入 MCP Server 设计规范
## AI Investment Research Platform

---

# 1. 设计原则

对于整个 AI Investment Research Platform，**SiYuan 不应被 Research Agent 直接调用**。

所有对 SiYuan 的访问都应通过 **Knowledge MCP Server** 完成，以保持统一的数据访问层（Data Access Layer）。

这样即使未来将 SiYuan 替换为 Anytype、Outline 或其他知识管理系统，**Research Agent、Knowledge Ingestion Agent 和整体工作流都无需修改**。

---

## SiYuan 定位

SiYuan 的定位应为：

> **Knowledge Workspace（知识工作台）**

而不是：

> **Knowledge Database（知识数据库）**

真正的知识数据仍然存储在：

- PostgreSQL（结构化知识）
- Apache AGE（知识图谱）
- Qdrant（向量检索）

---

# 2. 整体架构

推荐整体架构如下：

```text
                 Web UI
                    │
                    ▼
             Research Agent
                    │
                    ▼
          Knowledge MCP Server
                    │
        ┌───────────┼────────────┐
        │           │            │
        ▼           ▼            ▼
 PostgreSQL     Apache AGE     Qdrant
 (Source of Truth) (Knowledge Graph) (Vector Index)
        │
        ▼
Knowledge Ingestion Agent
        │
        ▼
      SiYuan API
```

---

## 各组件职责

### PostgreSQL

唯一事实来源（Source of Truth）。

负责存储：

- Entity
- Fact
- Event
- Metric
- Document Metadata
- Knowledge Object

---

### Apache AGE

负责：

- Entity Relation
- Graph Query
- Path Query

---

### Qdrant

负责：

- Semantic Search
- RAG Retrieval
- Similarity Search

---

### SiYuan

负责：

- Knowledge Workspace
- Human Review
- Research Notebook
- Knowledge Visualization

---

## 设计原则

**Research Agent 不允许直接修改 SiYuan。**

所有知识更新必须经过：

```
Research Agent
        │
        ▼
Knowledge Ingestion Agent
        │
        ▼
SiYuan
```

---

# 3. SiYuan Adapter

不要把 SiYuan API 直接写进 MCP Server。

建议增加独立 Adapter。

---

## 模块结构

```text
Knowledge MCP Server

tools/

├── postgres/
├── graph/
├── vector/
└── siyuan/
```

推荐目录：

```text
mcp-knowledge/

├── adapters/

│   ├── postgres/
│   ├── qdrant/
│   ├── age/
│   └── siyuan/
│       ├── client.py
│       ├── mapper.py
│       ├── templates.py
│       └── sync.py
```

---

## 各模块职责

### client.py

负责：

- HTTP API
- Authentication
- Error Handling

---

### mapper.py

负责：

```
Knowledge Object

        │

        ▼

SiYuan Block
```

实现 Knowledge Object 到 SiYuan 页面结构的映射。

---

### templates.py

负责：

- 页面模板
- Markdown 渲染
- Block Layout

---

### sync.py

负责：

```
Database

        │

        ▼

SiYuan
```

同步数据库与知识页面。

---

# 4. MCP Tools 设计

不要暴露全部 SiYuan API。

建议只暴露业务级 Tool。

---

## search_notes

查询知识页面。

### 输入

```json
{
  "keyword":"NVIDIA"
}
```

### 输出

```json
[
  {
    "title":"Company/NVIDIA",
    "id":"..."
  }
]
```

---

## get_note

获取页面内容。

### 输入

```json
{
  "id":"..."
}
```

---

## create_knowledge_object

推荐使用：

```
create_knowledge_object
```

而不是：

```
create_note()
```

### 输入

```json
{
  "type":"Company",
  "entity_id":"company_nvidia"
}
```

说明：

页面应由模板自动生成，而不是自由文本。

---

## update_knowledge_object

更新指定章节。

### 输入

```json
{
  "entity_id":"company_nvidia",
  "section":"Financial",
  "content":{
      "Revenue":"120B"
  }
}
```

优势：

- 增量更新
- 保留人工编辑内容
- 避免覆盖整个页面

---

## create_research_report

创建研究报告。

### 输入

```json
{
  "company":"NVIDIA",
  "report_id":"..."
}
```

模板自动生成：

```
Executive Summary
Investment Thesis
Financial Analysis
Valuation
Risk
```

---

## create_event_note

创建事件页面。

### 输入

```json
{
  "event":"Blackwell Release"
}
```

自动关联：

- Company
- Industry
- Timeline

---

# 5. 推荐同步策略

不要采用：

```text
Research Agent

↓

SiYuan
```

建议采用：

```text
Research Agent

↓

PostgreSQL

↓

Knowledge Ingestion Agent

↓

SiYuan
```

原则：

- SiYuan 永远是同步目标。
- SiYuan 不是知识数据源。

---

# 6. Knowledge Ingestion Agent

Knowledge Ingestion Agent 负责：

```text
Entity

↓

Template

↓

Markdown

↓

SiYuan
```

例如：

数据库：

```json
{
  "entity":"NVIDIA",
  "industry":"GPU",
  "market_cap":"..."
}
```

自动生成：

```markdown
# NVIDIA

## Profile

...

## Financial

...

## Events

...

## Risks

...
```

随后写入 SiYuan。

---

# 7. Template Engine

建议增加统一模板引擎。

目录：

```text
templates/

company.md.j2

industry.md.j2

report.md.j2

event.md.j2
```

渲染流程：

```text
Knowledge Object

↓

Jinja2

↓

Markdown

↓

SiYuan
```

> 不建议在代码中拼接 Markdown。

---

# 8. 同步模块

建议实现统一同步模块。

```text
sync.py

├── sync_company()
├── sync_event()
├── sync_report()
├── sync_metric()
├── sync_document()
└── sync_fact()
```

示例：

```text
sync_company()

↓

读取 PostgreSQL

↓

Company Template

↓

生成 Markdown

↓

SiYuan
```

---

# 9. Agent Workflow

推荐工作流：

```text
News

↓

News Intelligence Agent

↓

Knowledge Ingestion Agent

↓

PostgreSQL

↓

Knowledge Graph

↓

Vector

↓

SiYuan Sync

↓

Research Agent
```

注意：

Research Agent 不负责维护 SiYuan。

Knowledge Ingestion Agent 才负责同步。

---

# 10. 推荐目录结构

```text
mcp-knowledge/

├── adapters/

│   └── siyuan/
│       ├── client.py
│       ├── mapper.py
│       ├── templates.py
│       └── sync.py

├── tools/
│   ├── create_company.py
│   ├── update_company.py
│   ├── create_report.py
│   └── search_note.py

├── schemas/
│   ├── company.py
│   └── report.py

└── templates/
    ├── company.md.j2
    ├── report.md.j2
    └── event.md.j2
```

实现：

- Schema（知识模型）
- Templates（页面模板）
- Sync（同步逻辑）

三者完全解耦。

---

# 11. 版本管理

为了防止 AI 覆盖人工修改，建议增加同步版本控制。

```text
PostgreSQL
        │
        ▼
Knowledge Object
        │
        ▼
Change Detector
        │
   ┌────┴────┐
   │         │
无人工修改  有人工修改
   │         │
自动覆盖    生成待审核差异
   │         │
   └────┬────┘
        ▼
     SiYuan
```

---

## PostgreSQL 推荐增加字段

```
last_synced_at

last_modified_by
(AI / Human)

sync_version

sync_status
```

---

### sync_status 建议枚举

- Synced
- Pending Review
- Conflict

Knowledge Ingestion Agent 在同步时首先检查版本，再决定：

- 自动更新
- 生成差异（Diff）
- 等待人工审核

避免直接覆盖用户修改。

---

# 12. 推荐实施顺序

结合当前项目（News Pipeline、Knowledge Schema、Knowledge Graph、Research Agent、Knowledge MCP Server），建议按以下顺序实施：

## Phase 1

完成：

- 定义统一 Knowledge Object Schema（已完成）

---

## Phase 2

建立模板库：

- Company
- Event
- Document
- Research Report

统一采用：

```
Jinja2 Template
```

---

## Phase 3

实现：

```
SiYuan Adapter
```

包括：

- HTTP API
- Markdown Render
- Template Engine
- Sync

---

## Phase 4

在 MCP Server 中暴露业务级 Tool：

- create_knowledge_object
- update_knowledge_object
- search_notes
- get_note
- create_research_report

而不是直接暴露 SiYuan API。

---

## Phase 5

由：

```
Knowledge Ingestion Agent
```

负责同步。

Research Agent 永远只操作：

- Entity
- Fact
- Event
- Knowledge Object

不直接编辑 SiYuan 页面。

---

# 13. 最终架构

```text
                  Web UI
                     │
                     ▼
              Research Agent
                     │
                     ▼
           Knowledge MCP Server
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
   PostgreSQL    Apache AGE     Qdrant
   (Source of Truth) (Knowledge Graph) (Vector Index)
                     │
                     ▼
      Knowledge Ingestion Agent
                     │
                     ▼
             Knowledge Rendering
                     │
                     ▼
               SiYuan Adapter
                     │
                     ▼
           SiYuan Knowledge Workspace
```

---

# 14. 设计总结

## 核心原则

- MCP Server 是唯一知识访问入口。
- SiYuan 是 Knowledge Workspace，而不是数据库。
- Knowledge Ingestion Agent 负责页面同步。
- 页面全部由模板自动生成。
- Schema、Template、Sync 三层解耦。
- 支持未来替换 SiYuan，而无需修改 Agent 或知识存储层。

最终形成：

```text
Knowledge Object

        │

        ▼

Knowledge MCP Server

        │

        ▼

Knowledge Ingestion Agent

        │

        ▼

Knowledge Rendering Engine

        │

        ▼

SiYuan Workspace
```

这种架构可以保证系统具有良好的可维护性、可扩展性和可迁移性，并为未来替换知识工作台（如 Anytype、Outline 等）提供稳定的架构基础。