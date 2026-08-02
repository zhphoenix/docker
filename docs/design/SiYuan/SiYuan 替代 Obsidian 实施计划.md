# SiYuan 替代 Obsidian 实施计划
## AI Investment Research Platform

---

# 1. 项目定位调整

## 1.1 原 Obsidian 定位

```text
Obsidian
 |
 ├── Markdown 文件
 ├── 双向链接
 ├── 插件
 └── 人工整理笔记
```

### 适用场景

- 个人知识管理
- 少量研究笔记
- 手工维护知识网络

---

## 1.2 新 SiYuan 定位

SiYuan **不作为最终知识数据库**，而是作为：

> **Knowledge Workspace（知识工作台）**

主要职责：

- 人工审核 AI 生成知识
- 浏览 Entity / Fact / Event
- 修改知识对象
- 编写研究笔记
- 展示知识关系

---

### 整体架构

```text
                 Research Agent
                       │
                       ▼
              Knowledge MCP Server
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
 PostgreSQL      Apache AGE       Qdrant
 (Source of Truth) (Knowledge Graph) (Vector Index)
        │
        ▼
Knowledge Ingestion Agent
        │
        ▼
      SiYuan
(Knowledge Workspace)
```

---

# 2. 部署规划

## 2.1 Docker 服务结构

```text
AI-Platform/


├── siyuan/
│   ├── docker-compose.yml
│   └── data/
│
├── postgres/
├── qdrant/
├── minio/
└── langgraph/
```

---

## 2.2 Docker Compose

文件：

```
siyuan/docker-compose.yml
```

```yaml
services:

  siyuan:
    image: b3log/siyuan
    container_name: siyuan

    ports:
      - "6806:6806"

    volumes:
      - ./data/workspace:/siyuan/workspace

    command:
      - --workspace=/siyuan/workspace

    restart: unless-stopped
```

启动：

```bash
docker compose up -d
```

访问：

```
http://localhost:6806
```

---

# 3. 数据目录设计

> **不要把所有数据直接存放到 SiYuan。**

推荐目录：

```text
data/

├── knowledge/
│
├── siyuan/
│   └── workspace/
│
├── documents/
│   ├── annual_reports/
│   ├── news/
│   └── research_pdf/
│
├── generated/
│
└── archive/
```

---

# 4. SiYuan 知识模型设计

## 4.1 Notebook 设计

创建 Notebook：

```
Investment Research
```

目录结构：

```text
Investment Research

├── Companies
├── Industries
├── Markets
├── Macro
├── Events
├── Research Reports
├── Knowledge Inbox
└── Templates
```

---

# 5. Knowledge Object 映射

Knowledge Schema：

- Entity
- Relation
- Fact
- Event
- Document
- Evidence
- Metric
- Timeline

对应 SiYuan：

| Knowledge Schema | SiYuan |
|-----------------|---------|
| Entity | Document |
| Fact | Block Attribute |
| Event | Document + Tag |
| Relation | Reference |
| Evidence | Attachment |
| Metric | Block Attribute |
| Timeline | Database Block |

---

# 6. 创建知识模板

## Company Template

路径：

```
Templates/company.sy
```

模板：

```markdown
# Company Name

## Basic Information

Ticker:

Industry:

Country:

## Business Model

## Financial Metrics

Revenue:

Growth:

Margin:

## Management

CEO:

## Competitors

## Events

## Risks

## Evidence
```

---

# 7. AI 自动写入流程

示例新闻：

```
NVIDIA announces new AI chip
```

工作流：

```text
News Intelligence Agent
      │
      ▼
MinIO
(Document Storage)
      │
      ▼
Knowledge Ingestion Agent
      │
      ▼
Entity Extraction

NVIDIA
Blackwell
AI GPU

      │
      ▼
Knowledge Ingestion Agent
(Merger Node)
      │
      ├─────────────┐
      ▼             ▼
 PostgreSQL      SiYuan
 Entity          Note
```

---

# 8. MCP Server 接入 SiYuan

## 当前架构

```text
Research Agent
      │
      ▼
     MCP
      │
      ▼
PostgreSQL
Qdrant
Apache AGE
```

---

## 增加 SiYuan Tool

```text
Knowledge MCP Server

Tools

├── create_note
├── update_note
├── query_note
├── link_entity
└── search_block
```

---

## MCP Tool 示例

### create_entity_note

输入：

```json
{
  "name":"NVIDIA",
  "type":"Company",
  "content":{
    "industry":"GPU",
    "market":"AI"
  }
}
```

输出：

```
SiYuan Document ID
```

---

### update_fact

更新内容：

```
Company/NVIDIA

Financial Metrics

Revenue Growth

56%
```

---

# 9. 与 Knowledge Graph 集成

> **不要让 SiYuan 维护 Knowledge Graph。**

正确架构：

```text
SiYuan
   │
   ▼
 MCP
   │
   ▼
Knowledge Graph
```

示例：

SiYuan：

```text
NVIDIA.md

Related

TSMC
Microsoft
OpenAI
```

Apache AGE：

```text
(NVIDIA)
   │
 produces
   │
(AI GPU)

(NVIDIA)
   │
 partner
   │
(TSMC)
```

---

# 10. AI Agent 工作流

用户：

```
分析 NVIDIA 投资价值
```

工作流：

```text
Research Agent
      │
      ▼
MCP Query
      │
      ▼
Knowledge Graph
      │
      ▼
Vector Search
      │
      ▼
Financial Data
      │
      ▼
Generate Report
      │
      ▼
Knowledge Ingestion Agent
      │
      ▼
Update SiYuan
```

输出：

```
Research Reports

2026-08 NVIDIA Analysis
```

---

# 11. 数据迁移计划

## 不直接迁移整个 Vault

当前 Vault：

```text
companies/

9.3GB

大量 PDF
```

这些属于：

```
Document Storage
```

而不是知识对象。

---

## Markdown

迁移：

```text
 Markdown

        │

        ▼

      SiYuan
```

---

## PDF

迁移：

```text
Obsidian Vault

        │

        ▼

      MinIO
```

数据库仅保存：

- Document
- Metadata
- Location
- Embedding

---

# 12. 搜索体系

不要依赖 SiYuan 搜索。

推荐：

```text
User
 │
 ▼
MCP
 │
 ▼
Hybrid Search

 BM25
   +
Vector
   +
Graph

 │
 ▼
Answer
```

组件：

| 能力 | 组件 |
|------|------|
| 全文搜索 | PostgreSQL FTS |
| 向量检索 | Qdrant |
| 图查询 | Apache AGE |
| 页面展示 | SiYuan |

---

# 13. 实施阶段

## Phase 0：准备（1 天）

任务：

-Obsidian经全部删除 
-


---

## Phase 1：部署 SiYuan（1~2 天）

完成：
- 创建目录
- Docker 部署
- 登录
- Workspace 规划
- 基础模板

---

## Phase 2：知识模型（3~5 天）

完成：

- Company Template
- Industry Template
- Event Template
- Report Template

---

## Phase 3：MCP 集成（1~2 周）

开发：

```
SiYuan MCP Adapter
```

功能：

- 创建知识
- 更新知识
- 查询知识
- 链接知识

---

## Phase 4：Agent 自动化（2~4 周）

流程：

```text
News
   │
   ▼
Knowledge Ingestion Agent
   │
   ▼
Knowledge Graph
   │
   ▼
SiYuan Update
```

---

## Phase 5：生产化

增加：

- Version Control
- Knowledge Review
- Approval Workflow
- Knowledge Quality Score

---

# 14. 最终生产架构

```text
                 Web UI
                    │
                    ▼
             Research Agent
                    │
                    ▼
              Knowledge MCP Server
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
 PostgreSQL     Apache AGE       Qdrant
 (Source of Truth) (Knowledge Graph) (Vector Index)
                    │
                    ▼
      Knowledge Ingestion Agent
                    │
                    ▼
                 SiYuan
        Knowledge Workspace
                    │
                    ▼
                  MinIO
          Document Storage
```

---

# 15. 后续实施路线（推荐）

## 15.1 建立 Knowledge Object 模板

建立统一知识对象模板：

- Company
- Industry
- Security
- Event
- Fact
- Metric
- Person
- Document
- Research Report
- Theme
- Watchlist
- Knowledge Inbox

统一采用：

```
Knowledge Schema
        │
        ▼
Knowledge Object Template
        │
        ▼
SiYuan Template
```

---

## 15.2 接入 MCP Server

新增 SiYuan Adapter：

```text
Knowledge MCP Server
        │
        ▼
SiYuan Adapter
        │
        ├── create_knowledge_object
        ├── update_knowledge_object
        ├── search_notes
        ├── get_note
        └── create_research_report
```

通过业务级 Tool 操作 SiYuan，而不是直接调用底层 API。

---

## 15.3 AI 自动生成知识页面

新增：

```
Knowledge Rendering Engine
```

流程：

```text
Knowledge Object
        │
        ▼
Template Engine (Jinja2)
        │
        ▼
Markdown Render
        │
        ▼
SiYuan Adapter
        │
        ▼
SiYuan Knowledge Pages
```

页面统一采用模板渲染，不由 LLM 直接拼接 Markdown。

---

## 15.4 人工审核后进入长期知识库

建立完整审核流程：

```text
News / PDF
      │
      ▼
Knowledge Ingestion Agent
      │
      ▼
Knowledge Inbox（草稿）
      │
      ▼
Knowledge Review Center
      │
 ┌────┴─────┐
 ▼          ▼
Approve   Reject
 │
 ▼
Trusted Knowledge
 │
 ├── PostgreSQL
 ├── Apache AGE
 └── Qdrant
```

增加两个核心模块：

### Knowledge Review Center

负责：

- 待审核队列
- Evidence 查看
- 冲突检测
- 批量审批
- Merge / Split
- 审核历史

### Knowledge Governance

负责：

- 自动审批规则
- 来源可信度
- Confidence 管理
- 数据质量评分
- 版本控制
- 审计日志

---

# 16. 结论

SiYuan 的定位不是替代 PostgreSQL、Apache AGE 或 Qdrant，而是：

> **Knowledge Platform 的人机协作工作台（Knowledge Workspace）**

它负责知识展示、人工审核、研究记录和协作，而真正的知识存储与检索仍由 PostgreSQL、Apache AGE、Qdrant 和 MinIO 共同完成。

---

## 实施优先级

| 优先级 | 任务 | 状态 |
|---------|------|------|
| P1 | 部署 SiYuan Docker | ⬜ |
| P1 | 建立 Knowledge Object 模板 | ⬜ |
| P1 | 接入 MCP Server | ⬜ |
| P2 | AI 自动生成知识页面 | ⬜ |
| P2 | 建立 Knowledge Review Center | ⬜ |
| P2 | 建立 Knowledge Governance | ⬜ |
| P3 | 人工审核后进入长期知识库 | ⬜ |
| P3 | Version Control 与 Audit Log | ⬜ |

---

## 最终目标

将当前的 **Obsidian 文件仓库** 升级为真正的 **Knowledge Platform**：

- **PostgreSQL**：结构化知识
- **Apache AGE**：知识图谱
- **Qdrant**：语义检索
- **MinIO**：文档存储
- **SiYuan**：知识工作台
- **Knowledge MCP Server**：统一访问层
- **Knowledge Ingestion Agent**：知识摄取
- **Knowledge Rendering Engine**：知识页面生成
- **Knowledge Review Center**：人工审核
- **Knowledge Governance**：知识治理