# Document Pipeline + Knowledge Package 设计方案（V3.0）

> Version: v3.0  
> Status: Architecture Design  
> Module: Document Pipeline  
> Project: AI Investment Research Platform

---

# 1. 模块定位（Positioning）

Document Pipeline 是 AI Investment Research Platform 的**统一知识生产流水线（Unified Knowledge Production Pipeline）**。

它负责接收来自各种数据源的内容，完成解析、知识抽取、向量化，并输出标准化的 **Knowledge Package**。

Document Pipeline 的唯一职责：

> **Produce Knowledge Package**

它不负责：

- Knowledge Graph
- Knowledge Search
- Knowledge Governance
- Knowledge Analytics
- Research
- Watchlist

这些全部属于 **Knowledge Operations Center**。

---

# 2. 在整体架构中的位置

```text
                Knowledge Sources
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   Documents        News Feed     API / Crawler
        │              │              │
        └──────────────┼──────────────┘
                       ▼
──────────────────────────────────────────────────
              Document Pipeline
──────────────────────────────────────────────────
Acquire
Routing
Parse
Chunk
Knowledge Extraction
Embedding
Knowledge Package
Publish
──────────────────────────────────────────────────
                       │
                       ▼
──────────────────────────────────────────────────
       Knowledge Operations Center
──────────────────────────────────────────────────
Inbox
Validation
Merge
Governance
Graph
Search
Analytics
Services
──────────────────────────────────────────────────
                       │
                       ▼
Research
Watchlist
Workflow
AI Agents
```

---

# 3. 设计目标

Document Pipeline 必须具备：

- Unified Ingestion（统一接入）
- Intelligent Routing（智能路由）
- Standard Processing（标准处理）
- Retryable（可重试）
- Traceable（可追踪）
- Scalable（可扩展）
- Publishable（可发布）

---

# 4. Pipeline Overview

整个 Pipeline 分为八个阶段：

```text
Acquire
    │
Routing
    │
Parse
    │
Chunk
    │
Knowledge Extraction
    │
Embedding
    │
Knowledge Package
    │
Publish
```

每个阶段只负责一件事情。

---

# Stage 1：Acquire（统一采集）

## 定位

所有知识来源统一进入平台。

---

## Supported Sources

### Documents

- PDF
- Word
- Markdown
- HTML
- TXT
- Excel
- CSV
- Image

---

### News

- RSS
- Reuters
- Bloomberg
- EastMoney
- Sina
- Xinhua

---

### Structured Sources

- REST API
- GraphQL
- JSON Feed
- Database

---

### Collectors

- Scheduled Job
- Folder Sync
- MinIO Import
- Webhook
- Manual Upload

---

## Output

```
Raw Document
```

---

## Metadata

```yaml
document_id:

source_type:

source_name:

document_type:

priority:

trigger:

checksum:

created_time:

received_time:
```

---

## Source Type

支持：

```
NEWS

REPORT

FILING

POLICY

ANNOUNCEMENT

RESEARCH

GENERAL
```

---

## Trigger

```
Manual

Scheduler

API

Webhook

RSS

Crawler

Watchlist
```

---

## Priority

```
HIGH

NORMAL

LOW
```

例如：

Breaking News：

```
HIGH
```

Annual Report：

```
LOW
```

---

# Stage 2：Routing（智能路由）

新增阶段。

Routing 根据来源决定后续处理策略。

```text
Acquire

↓

Routing

↓

Different Processing Strategy
```

---

## Routing Rules

支持：

```
News

Annual Report

Research Report

Policy

Exchange Filing

General Document
```

---

不同类型使用：

- 不同 Prompt
- 不同 Parser
- 不同 Extraction Pipeline

例如：

News：

```
Company

Event

Impact
```

Annual Report：

```
Financial Metrics

Guidance

Risk

Segment
```

---

## Output

```
Processing Strategy
```

---

# Stage 3：Parse（文档解析）

负责理解文档。

---

支持：

```
OCR

Docling

Layout Analysis

Table Extraction

Image Extraction

Metadata Extraction
```

---

输出：

```
Structured Document
```

---

包括：

- Text
- Tables
- Figures
- Sections
- Page Structure

---

# Stage 4：Chunk

统一切分。

支持：

```
Semantic Chunk

Recursive Split

Token Split

Sliding Window
```

---

Chunk Metadata：

```yaml
chunk_id:

page:

section:

token_count:

language:
```

---

输出：

```
Document Chunks
```

---

# Stage 5：Knowledge Extraction

这是 Pipeline 的核心。

统一命名：

> Knowledge Extraction

而不是：

Entity Extraction。

---

## Entity Extraction

抽取：

```
Company

Industry

Person

Organization

Country

Technology

Product

Policy
```

---

## Relation Extraction

例如：

```
Tencent

INVEST

OpenAI
```

---

## Fact Extraction

例如：

```
Tencent

Revenue

184 Billion RMB
```

---

## Event Extraction

例如：

```
Quarterly Report

Acquisition

Policy

Investment

Product Release
```

---

## Keyword Extraction

```
AI

GPU

Cloud

Semiconductor
```

---

## Financial Metrics

针对财报：

```
Revenue

EPS

ROE

Gross Margin

Net Profit

Cash Flow
```

---

## Output

```
Knowledge Objects
```

---

# Stage 6：Embedding

负责向量化。

支持：

```
Chunk Embedding

Entity Embedding

Summary Embedding
```

---

Metadata：

```yaml
embedding_model:

dimension:

collection:

vector_id:
```

---

输出：

```
Knowledge Vectors
```

---

# Stage 7：Knowledge Package

Knowledge Package 是整个 Pipeline 的最终输出。

---

## 定义

Knowledge Package 是：

> Document Pipeline 的标准输出。

也是：

> Knowledge Operations Center 的唯一输入。

---

## Schema

```text
Knowledge Package
│
├── Package Metadata
├── Source Metadata
├── Entities
├── Relations
├── Facts
├── Events
├── Embeddings
├── Evidence
├── Confidence
├── Processing Metadata
└── Version
```

---

# Package Metadata

```yaml
package_id:

package_version:

schema_version:

created_time:

pipeline_version:
```

---

# Source Metadata

```yaml
document_id:

source_type:

source_name:

document_type:

priority:

trigger:

language:
```

---

# Entities

字段：

```yaml
entity_id:

type:

name:

alias:

description:

confidence:
```

---

# Relations

字段：

```yaml
source:

target:

relation:

confidence:

evidence:
```

---

# Facts

字段：

```yaml
subject:

predicate:

object:

unit:

effective_date:

confidence:
```

---

# Events

字段：

```yaml
event_type:

participants:

time:

location:

impact:
```

---

# Embeddings

```yaml
model:

dimension:

collection:

vector_id:
```

---

# Evidence

Knowledge 必须可追溯。

```yaml
document:

page:

chunk:

offset:

quote:
```

---

# Confidence

```yaml
entity:

relation:

fact:

overall:
```

---

# Processing Metadata

新增。

```yaml
pipeline:

routing_strategy:

parser:

ocr_engine:

embedding_model:

llm_model:

processing_time:
```

方便以后排查。

---

# Version

```yaml
package_version:

schema_version:

history:
```

支持：

- Version
- Rollback
- Diff

---

# Stage 8：Publish

Publish 是 Pipeline 最后一步。

Document Pipeline 到这里结束。

---

## Publish

```text
Knowledge Package

↓

Publish

↓

Knowledge Operations Center
```

---

Publish Metadata：

```yaml
publish_time:

destination:

status:

retry_count:
```

---

支持：

```
Publish

Retry

Re-Publish

Rollback
```

---

# 5. Pipeline Dashboard

顶部建议：

```text
Acquire

↓

Routing

↓

Parse

↓

Chunk

↓

Knowledge Extraction

↓

Embedding

↓

Knowledge Package

↓

Publish
```

每个阶段：

```
Running

Pending

Completed

Failed
```

---

# 6. Statistics

建议：

```
Incoming Documents

Knowledge Packages

Processed Today

Processing Time

Publish Success Rate

Queue Length

Average Latency
```

---

# 7. Queue Management

支持：

```
Priority Queue

Retry Queue

Dead Letter Queue

Schedule Queue
```

---

# 8. Pipeline Detail

查看某个任务：

```text
Acquire

✓

↓

Routing

✓

↓

Parse

✓

↓

Chunk

✓

↓

Knowledge Extraction

✓

↓

Embedding

✓

↓

Knowledge Package

✓

↓

Publish

Running
```

同时查看：

- Source
- Strategy
- Parser
- Chunk 数量
- Entity 数量
- Processing Time
- Publish Status

---

# 9. Pipeline 生命周期

```text
Knowledge Source

↓

Acquire

↓

Routing

↓

Parse

↓

Chunk

↓

Knowledge Extraction

↓

Embedding

↓

Knowledge Package

↓

Publish

↓

Knowledge Operations Center
```

---

# 10. 与其它模块关系

| 模块 | 输入 | 输出 | 职责 |
|------|------|------|------|
| News Intelligence Center | News Sources | Collect Request | 新闻采集、监控、调度 |
| Document Pipeline | Documents / News / API | Knowledge Package | 知识生产 |
| Knowledge Operations Center | Knowledge Package | Knowledge Graph / Search / Services | 知识运营 |
| Research Center | Knowledge Services | Research Report | 深度研究 |
| Watchlist Intelligence | Knowledge Services | Alert / Monitoring | 投资监控 |

---

# 11. 数据流

```text
                    Knowledge Sources
        ┌────────────┬─────────────┬──────────────┐
        ▼            ▼             ▼
    Documents      News       API / Crawler
        │            │             │
        └────────────┴─────────────┘
                     │
                     ▼
──────────────────────────────────────────────────
              Document Pipeline
──────────────────────────────────────────────────
Acquire
        │
Routing
        │
Parse
        │
Chunk
        │
Knowledge Extraction
        │
Embedding
        │
Knowledge Package
        │
Publish
──────────────────────────────────────────────────
                     │
                     ▼
──────────────────────────────────────────────────
       Knowledge Operations Center
──────────────────────────────────────────────────
Knowledge Inbox
        │
Validation
        │
Merge
        │
Governance
        │
Knowledge Graph
        │
├── Knowledge Search
├── Knowledge Analytics
├── Knowledge Services
└── Knowledge Evolution
──────────────────────────────────────────────────
                     │
                     ▼
Research
Watchlist
Workflow
AI Agents
External API
```

---

# 12. 最终定位

Document Pipeline 是平台唯一的**知识生产层（Knowledge Production Layer）**。

它负责统一接收所有知识来源，通过标准化流程生成 Knowledge Package，并发布到 Knowledge Operations Center。

Knowledge Package 是整个 AI Investment Research Platform 的统一知识数据契约（Knowledge Data Contract），也是 Document Pipeline 与 Knowledge Operations Center 之间唯一的数据交换格式。

整个知识架构形成四层模型：

```text
Knowledge Sources
（Documents / News / API / Reports）
        │
        ▼
Document Pipeline
（Produce Knowledge）
        │
        ▼
Knowledge Package
（Knowledge Data Contract）
        │
        ▼
Knowledge Operations Center
（Operate Knowledge）
        │
        ▼
Knowledge Services
（Deliver Knowledge）
        │
        ▼
Research Center
Watchlist Intelligence
Workflow
AI Agents
```

**职责边界：**

- **Knowledge Sources**：提供原始信息。
- **Document Pipeline**：负责知识生产，输出 Knowledge Package。
- **Knowledge Operations Center**：负责知识校验、治理、组织、搜索与服务。
- **Business Modules（Research、Watchlist 等）**：消费 Knowledge Services，实现具体业务能力。

这一设计确保所有知识来源遵循统一处理流程，同时实现知识生产、知识运营和业务应用之间的完全解耦。