# Knowledge Hub 页面优化建议

## 总体评价

当前页面已经具备 **MVP（Minimum Viable Product）** 的基本形态，但如果定位为生产级的 **AI Investment Research Platform 知识中台**，目前仍存在信息层级不清晰、核心功能展示不足的问题。

建议不要仅优化 UI，而是按照 **Knowledge Hub（知识中台）** 的思路重新组织页面功能。

---

# 一、当前存在的问题

## 1. Collection 成为了页面主角

当前页面主要展示：

- documents_cn
- documents_hk
- documents_us
- knowledge_entities
- knowledge_facts

这些实际上只是 **Qdrant Collection**，属于底层存储实现。

对于用户而言，更关注的是：

- 当前有多少知识？
- 处理进度如何？
- 是否有异常？
- 最近是否更新？
- 知识质量如何？

而不是 Collection 本身。

---

## 2. 顶部操作区域过于简单

目前仅包含：

- 路径输入
- 选择目录
- 开始处理

建议改为完整的数据处理 Pipeline。

例如：

```
选择目录
      │
      ▼
Docling 解析
      │
      ▼
Chunk
      │
      ▼
Embedding
      │
      ▼
Entity Extraction
      │
      ▼
Knowledge Graph
      │
      ▼
完成
```

每个阶段实时显示状态：

```
正在解析...

Embedding...

Graph Building...

Completed
```

这样用户能够清楚知道当前执行到了哪个阶段。

---

## 3. Collection 卡片信息不足

当前展示：

```
documents_cn

Qdrant:7373
```

对于用户意义不大。

建议改为：

```
Documents

13242

Chunks

578136

Embedding

578136

Entities

36291

Facts

281004

Last Update

2026-08-03 09:11
```

这些数据更能反映知识库状态。

---

# 二、首页建议改成 Dashboard

首页应展示整个知识库运行状态。

例如：

```
Knowledge Dashboard
```

顶部四个统计卡：

```
Documents

Chunks

Entities

Facts
```

下面展示：

```
Embedding Queue

Processing Queue

Failed Queue

Knowledge Graph
```

最后再展示 Collection。

页面结构建议：

```
────────────────────────────

Documents

32412

Chunks

580231

Embedding

580231

Entities

36422

Facts

281994

────────────────────────────

Processing

Running

12

Pending

84

Failed

2

────────────────────────────

Latest Tasks

...

────────────────────────────

Collections

documents_cn

documents_hk

documents_us

...
```

---

# 三、增加 Processing Tasks（处理任务）

知识库真正重要的是处理任务，而不是 Collection。

建议增加：

```
Knowledge Tasks
```

例如：

```
✓ 000001 年报

Completed

2026-08-02

----------------------------

✓ 腾讯公告

Completed

2026-08-03

----------------------------

○ NVIDIA

Embedding...

56%

----------------------------

× Apple

Failed

Token Limit
```

这样可以直观查看所有处理任务。

---

# 四、Collection 独立页面

首页无需展开所有 Collection。

点击：

```
documents_cn
```

进入：

```
Overview

Documents

Chunks

Entities

Facts

Vector

Knowledge Graph

Settings
```

首页只展示概要信息即可。

---

# 五、统一搜索

目前只有普通搜索框。

建议升级为 **Knowledge Search**。

例如：

```
🔍 BYD
```

返回：

```
Entity

比亚迪

Company

----------------

Facts

营业收入增长...

----------------

Documents

2025 Annual Report

----------------

Knowledge Graph

供应商

宁德时代
```

实现跨：

- 文档
- Chunk
- Entity
- Fact
- Graph

统一搜索。

---

# 六、增加系统状态

增加运行状态区域：

```
Healthy Status

MinIO

Qdrant

PostgreSQL

Embedding

Knowledge Graph
```

例如：

```
🟢 MinIO

🟢 PostgreSQL

🟢 Qdrant

🟡 Embedding Queue

🔴 Graph Extractor
```

便于快速定位问题。

---

# 七、增加最近更新

增加：

```
Recent Updates
```

例如：

```
09:12

Added

NVIDIA 10-Q

----------------

09:10

Updated

BYD

----------------

08:50

Deleted

Test.pdf
```

方便了解知识库最新变化。

---

# 八、增加知识质量指标

建议增加：

```
Knowledge Quality
```

例如：

```
Coverage

89%

Chunk Avg

1200 Tokens

Duplicate

1.8%

Embedding

100%

Entity Confidence

93%
```

后续调优 Prompt、Chunk、Embedding 时非常有价值。

---

# 九、左侧导航建议

当前：

```
Knowledge
```

功能过于集中。

建议拆分：

```
Knowledge

├── Dashboard
├── Documents
├── Processing
├── Search
├── Collections
├── Entities
├── Facts
├── Knowledge Graph
├── Tasks
├── Settings
```

后续扩展无需修改整体结构。

---

# 十、结合 AI Platform 的整体定位

当前平台已经规划了：

- News Pipeline
- Knowledge Organization Agent
- Knowledge Graph
- Research Agent
- MCP Knowledge Server
- PostgreSQL
- Qdrant
- MinIO

因此建议不再命名为：

```
Knowledge Base
```

而改为：

```
Knowledge Hub
```

定位为整个 AI Platform 的知识中台。

推荐整体结构：

```
Knowledge Hub
│
├── Dashboard
│   ├── 总体统计
│   ├── 服务状态
│   ├── 最新任务
│   └── 最近更新
│
├── Documents
│   ├── 文档管理
│   ├── 上传
│   ├── 分类
│   └── 元数据
│
├── Processing
│   ├── Docling
│   ├── Chunk
│   ├── Embedding
│   ├── Entity Extraction
│   ├── Knowledge Graph
│   └── Processing Queue
│
├── Search
│   ├── Keyword Search
│   ├── Semantic Search
│   ├── Hybrid Search
│   └── Graph Search
│
├── Knowledge Graph
│   ├── Entities
│   ├── Relations
│   ├── Facts
│   ├── Events
│   └── Visualization
│
├── Collections
│   ├── documents_cn
│   ├── documents_hk
│   ├── documents_us
│   ├── knowledge_entities
│   └── knowledge_facts
│
├── Tasks
│   ├── Running
│   ├── Pending
│   ├── Failed
│   └── History
│
├── Monitoring
│   ├── MinIO
│   ├── PostgreSQL
│   ├── Qdrant
│   ├── Embedding Service
│   └── Graph Service
│
└── Settings
    ├── Chunk Strategy
    ├── Embedding Model
    ├── Collection Settings
    ├── Graph Settings
    └── Index Settings
```

---

# 总结

建议将当前页面从 **Collection 管理页面** 升级为 **Knowledge Hub（知识中台）**。

核心设计原则：

1. **Dashboard First**：先展示知识库整体状态，而不是底层 Collection。
2. **Pipeline Visible**：可视化文档处理流程，实时反馈处理状态。
3. **Task Driven**：以任务为核心管理知识处理，而非存储结构。
4. **Unified Search**：统一搜索文档、实体、事实和知识图谱。
5. **Knowledge Graph Native**：将知识图谱作为核心能力，而不是后续附加功能。
6. **Operational Monitoring**：集成服务状态、处理队列和知识质量指标，便于生产环境运维。
7. **Scalable Architecture**：页面结构与 AI Platform 的整体架构保持一致，为 Research Agent、Knowledge Organization Agent、MCP Knowledge Server 等模块预留扩展空间。