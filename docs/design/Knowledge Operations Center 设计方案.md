# Knowledge Operations Center 设计方案

> Version: v1.0  
> Module: Knowledge Operations Center  
> Project: AI Investment Research Platform

---

# 1. 模块定位（Positioning）

## 模块名称

**Knowledge Operations Center**

副标题：

> Operate, Govern and Deliver Knowledge Intelligence

---

## 定位

Knowledge Operations Center 是整个 AI Investment Research Platform 的**知识运营中心（Knowledge Operations Platform）**。

它不是：

- 文档管理系统（Document Management）
- 文档处理流水线（Document Pipeline）
- 系统监控中心（System Monitor）

而是负责：

> **组织、治理、分析、运营和服务知识。**

Knowledge 在这里已经不是"文档"，而是平台最重要的数据资产。

---

# 2. 与其它模块职责划分

整个系统建议采用四层架构。

```text
Documents
    │
    ▼
Document Lifecycle
    │
    ▼
Knowledge Operations Center
    │
    ▼
Research / Watchlist / Agents
```

---

## Documents

负责：

> 文档资产管理

包括：

- Upload
- Import
- Sync
- Preview
- Version
- Metadata
- Storage

关注对象：

```
PDF

Word

Markdown

HTML
```

一句话：

> 管理文档。

---

## Document Lifecycle

负责：

> 文档如何变成知识。

包括：

```
Upload

↓

Parse

↓

Chunk

↓

Embedding

↓

Entity Extraction

↓

Knowledge Graph

↓

Index
```

关注对象：

```
Pipeline

Queue

Retry

GPU

Processing
```

一句话：

> 生产知识。

---

## Knowledge Operations Center

负责：

> 知识如何组织、治理、运营和服务。

关注对象：

```
Entity

Relation

Fact

Event

Knowledge Graph

Knowledge Intelligence
```

一句话：

> 运营知识。

---

## Research

负责：

> 消费知识。

包括：

- Research Agent
- Watchlist
- Workflow
- AI Report

一句话：

> 使用知识。

---

# 3. 设计原则（Design Principles）

Knowledge Operations Center 不负责：

❌ Upload

❌ OCR

❌ Chunk

❌ Embedding

❌ Pipeline

❌ Queue

❌ GPU

❌ Processing

这些全部属于 Document Lifecycle。

---

Knowledge Operations Center 负责：

✅ Knowledge Organization

✅ Knowledge Governance

✅ Knowledge Discovery

✅ Knowledge Analytics

✅ Knowledge Evolution

✅ Knowledge Services

---

# 4. 页面整体结构

建议页面重新设计为：

```text
Knowledge Operations Center
│
├── Knowledge Explorer
│
├── Knowledge Graph
│
├── Knowledge Insights
│
├── Knowledge Governance
│
├── Knowledge Search
│
├── Knowledge Analytics
│
├── Knowledge Evolution
│
├── Knowledge Impact
│
├── AI Knowledge Services
│
└── Recent Activities
```

整个页面围绕：

> Knowledge Operations

展开。

而不是：

> Document Processing。

---

# 5. Knowledge Explorer（知识浏览）

定位：

> 浏览所有知识资产。

---

展示：

```
Companies

Industries

Products

Events

Policies

People

Organizations
```

例如：

```
Companies

18,423
```

点击：

```
Tencent

↓

Knowledge Card

↓

Timeline

↓

Graph

↓

Facts

↓

Related Companies

↓

Related Documents
```

这里浏览的是：

知识。

不是文档。

---

## 建议统计

```
Companies

Industries

Events

Policies

Organizations

Products

People
```

---

## 快速筛选

支持：

```
Industry

Market

Region

Date

Source

Confidence
```

---

# 6. Knowledge Graph

定位：

> Knowledge Network

展示：

```
Entities

Relationships

Communities

Connected Components

Graph Density

Coverage
```

---

建议展示：

```
Today's New Entities

Today's New Relations

Most Connected Companies

Most Active Industries

Largest Communities
```

---

支持：

```
Graph Explorer
```

查看：

```
Node

↓

Neighbors

↓

Relationship

↓

Evidence

↓

Timeline
```

---

# 7. Knowledge Insights

定位：

> 从知识中发现洞察。

例如：

```
Today's Hot Topics

Trending Companies

Trending Industries

Emerging Concepts

Policy Impact

Market Signals
```

支持：

```
Top Growing Knowledge

Top Mentioned Companies

Knowledge Heatmap
```

帮助用户快速了解：

> 今天知识库发生了什么。

---

# 8. Knowledge Governance

定位：

> 知识治理。

包括：

```
Duplicate Knowledge

Conflict Facts

Expired Knowledge

Low Confidence

Missing Relations

Need Merge

Need Review

Need Validation
```

例如：

```
Conflict Facts

38
```

```
Duplicate Entities

21
```

```
Low Confidence Relations

73
```

所有治理任务可直接进入 Review 页面处理。

---

# 9. Knowledge Search

定位：

> 全局知识搜索。

支持统一搜索：

```
Entity

Fact

Event

Relation

Company

Industry

Document
```

例如：

搜索：

```
腾讯
```

返回：

```
Knowledge Card

↓

Facts

↓

Relations

↓

Timeline

↓

Industry

↓

Graph

↓

Related Documents
```

而不是：

```
PDF 文件
```

---

支持：

```
Semantic Search

Graph Search

Hybrid Search
```

---

# 10. Knowledge Analytics

定位：

> Knowledge Analytics

统计：

```
Knowledge Growth

Knowledge Coverage

Knowledge Usage

Knowledge Quality

Knowledge Freshness
```

建议增加：

```
Top Queried Entity

Top Used Fact

Top Accessed Industry

Top Referenced Event

Knowledge Growth Trend
```

展示：

```
7 Days

30 Days

90 Days
```

增长趋势。

---

# 11. Knowledge Evolution

定位：

> Knowledge Evolution

知识不是静态。

每一个 Entity 都有：

```
Version

History

Timeline
```

例如：

```
Tencent

↓

2024

↓

2025

↓

2026
```

新增：

```
Facts

Events

Relations

Documents
```

支持：

```
Knowledge Timeline
```

查看：

```
Knowledge 如何演化。
```

---

# 12. Knowledge Impact

这是投资平台特色模块。

定位：

> Knowledge Impact Analysis

例如：

```
AI

↓

NVIDIA

↓

TSMC

↓

腾讯

↓

阿里

↓

产业链
```

支持：

```
Policy Impact

Industry Impact

Supply Chain

Risk Propagation

Event Propagation
```

实现：

知识影响分析。

---

# 13. AI Knowledge Services

定位：

Knowledge 被哪些 Agent 使用。

展示：

```
Research Agent

News Agent

Watchlist

Workflow

MCP Knowledge

API
```

例如：

```
Research Agent

Calls

432
```

```
Watchlist

Knowledge Hits

218
```

```
Hybrid Search

Today's

1321
```

说明：

Knowledge 真正发挥价值。

---

# 14. Recent Activities

展示：

```
New Knowledge

Knowledge Updated

New Relations

Knowledge Review

Knowledge Merge

Knowledge Validation
```

例如：

```
14:02

New Relation

Tencent

↓

NVIDIA
```

```
14:20

Knowledge Updated

Semiconductor Industry
```

---

# 15. 首页统计（Dashboard Metrics）

首页不再展示：

```
Documents

Chunks

Embedding
```

这些属于 Document Lifecycle。

建议展示：

```
Entities

Relationships

Facts

Events

Communities

Knowledge Coverage
```

例如：

| 指标 | 数量 |
|------|------|
| Entities | 18,326 |
| Relationships | 123,452 |
| Facts | 2,300,000 |
| Events | 53,821 |
| Industries | 186 |
| Companies | 12,483 |
| Knowledge Coverage | 92% |

---

# 16. 页面布局建议

```text
┌──────────────────────────────────────────────────────────────┐
│              Knowledge Operations Center                     │
│ Organize • Govern • Analyze • Deliver Knowledge             │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Knowledge Overview                                           │
│ Entities | Relations | Facts | Events | Coverage             │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────┬───────────────────────────────────────┐
│ Knowledge Explorer   │ Knowledge Graph                       │
│ Companies            │ Entity Graph                          │
│ Industries           │ Communities                           │
│ Events               │ Central Nodes                         │
└──────────────────────┴───────────────────────────────────────┘

┌──────────────────────┬───────────────────────────────────────┐
│ Knowledge Insights   │ Knowledge Governance                  │
│ Trending Topics      │ Duplicate                             │
│ Hot Companies        │ Conflict                              │
│ Emerging Concepts    │ Low Confidence                        │
└──────────────────────┴───────────────────────────────────────┘

┌──────────────────────┬───────────────────────────────────────┐
│ Knowledge Analytics  │ Knowledge Evolution                   │
│ Growth               │ Timeline                              │
│ Usage                │ Version                               │
│ Coverage             │ History                               │
└──────────────────────┴───────────────────────────────────────┘

┌──────────────────────┬───────────────────────────────────────┐
│ Knowledge Impact     │ AI Knowledge Services                 │
│ Industry Chain       │ Research Agent                        │
│ Policy Impact        │ Watchlist                             │
│ Risk Propagation     │ MCP                                   │
└──────────────────────┴───────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Recent Activities                                            │
└──────────────────────────────────────────────────────────────┘
```

---

# 17. 模块职责总结

| 模块 | 核心职责 |
|------|----------|
| Knowledge Explorer | 浏览和管理知识资产 |
| Knowledge Graph | 图谱浏览与关系探索 |
| Knowledge Insights | 发现趋势、热点和洞察 |
| Knowledge Governance | 知识质量治理与审核 |
| Knowledge Search | 统一知识检索入口 |
| Knowledge Analytics | 知识增长、覆盖率与使用分析 |
| Knowledge Evolution | 知识版本、历史与时间演化 |
| Knowledge Impact | 行业、政策、事件影响分析 |
| AI Knowledge Services | 向 Agent、MCP、Research 提供知识服务 |
| Recent Activities | 知识变更与运营日志 |

---

# 18. 最终定位

Knowledge Operations Center 是整个 AI Investment Research Platform 的**知识运营层（Knowledge Operations Layer）**。

它位于 **Document Lifecycle** 与 **Research / AI Agents** 之间，是平台的知识中枢，承担四项核心职责：

1. **Knowledge Organization（知识组织）**：统一组织实体、关系、事实、事件及知识图谱。
2. **Knowledge Governance（知识治理）**：持续管理知识质量、冲突、重复、时效与版本。
3. **Knowledge Intelligence（知识智能）**：从知识中发现趋势、关联、影响和投资洞察。
4. **Knowledge Delivery（知识服务）**：为 Research Agent、Watchlist、Workflow、MCP 和外部 API 提供统一、可复用的知识能力。

最终形成如下平台架构：

```text
Documents
    │
    ▼
Document Lifecycle
（生产知识）
    │
    ▼
Knowledge Operations Center
（运营知识）
    │
    ▼
Research
Watchlist
Workflow
AI Agents
（消费知识）
```

> **Documents 负责生产知识，Knowledge Operations Center 负责运营知识，Research 与 AI Agents 负责消费知识。**