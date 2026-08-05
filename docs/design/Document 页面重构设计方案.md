# Document 页面重构设计方案

## 1. 设计目标

当前 Documents 页面存在的主要问题不是 UI，而是**信息架构（Information Architecture）**。

目前页面将：

- Upload PDF
- Import MinIO
- Sync Folder
- Batch Process
- Documents
- Chunks
- Entities
- Facts

全部放在同一级别，导致用户第一次进入页面时无法理解：

- 应该先点击哪个按钮？
- Upload 与 Import MinIO 有什么区别？
- Sync Folder 与 Batch Process 有什么关系？
- Parse、Chunk、Embedding 分别什么时候执行？
- 为什么文档已经上传却还是 Pending？
- Facts 为什么是 0？
- 一个文档完整经历了哪些处理流程？

因此，需要重新设计页面，使整个页面围绕**Document （文档处理流水线）**组织，而不是围绕各种独立功能组织。

---



副标题：

> 文档从导入 → 解析 → 知识化 → 可检索 的完整生命周期

让用户进入页面第一眼就知道：

这里不是文件管理器，而是整个知识处理流水线。

---

# 3. 页面整体结构

建议整个页面分为四大区域：

```
Document
──────────────────────────────

① Pipeline（流程介绍）

② Import（导入入口）

③ Processing（处理状态）

④ Documents（处理结果）
```

整个页面逻辑按照文档生命周期展开。

---

# 4. Pipeline（流程介绍）

页面顶部不再放大量统计数字，而是首先展示整个 Pipeline。

## Pipeline

```
Upload
   │
   ▼
Parse
   │
   ▼
Chunk
   │
   ▼
Entity Extraction
   │
   ▼
Embedding
   │
   ▼
Knowledge Graph
   │
   ▼
Search / Agent
```

每一步都增加一句说明。

---

### Upload

导入 PDF、Word、HTML 等文档。

---

### Parse

Docling 提取：

- 正文
- 表格
- 图片
- Metadata

---

### Chunk

按照 Token 或语义进行切块。

---

### Entity Extraction

抽取：

- Company
- Person
- Industry
- Organization
- Product

---

### Embedding

生成向量并存入 Qdrant。

---

### Knowledge Graph

生成：

- Entity
- Relation
- Fact
- Event

---

### Search

Research Agent 可进行：

- Vector Search
- Graph Query
- Hybrid Retrieval

---

# 5. Import（导入入口）

当前页面四个按钮容易混淆。

建议仅保留三个入口：

```
Import Documents

+ Upload Local Files

+ Import From MinIO

+ Folder Sync
```

分别对应：

---

## Upload Local Files

上传本地 PDF。

适合：

- 单个文件
- 少量文件

---

## Import From MinIO

扫描已有 Bucket。

适合：

- 已存在文档
- 批量导入

---

## Folder Sync

持续同步指定目录。

适合：

- NAS
- 网络共享目录
- 定时同步

---

Batch Process 不属于导入，应移动到 Processing。

---

# 6. Processing（处理中心）

页面中央展示 Pipeline 当前状态。

建议采用真正的流水线状态，而不是：

- 已索引
- 等待解析

这种跨度较大的状态。

推荐：

```
Pending

↓

Parsing

↓

Chunking

↓

Embedding

↓

Extracting Entity

↓

Building Graph

↓

Completed

↓

Failed
```

例如：

| 状态 | 数量 |
|------|------|
| Pending | 388 |
| Parsing | 18 |
| Chunking | 52 |
| Embedding | 103 |
| Graph Building | 7 |
| Completed | 745 |
| Failed | 0 |

用户可以立即知道：

当前卡在哪一步。

---

# 7. Pipeline Control（流程控制）

Pipeline 操作统一放在 Processing 区域。

例如：

```
Pipeline Control

▶ Start Pipeline

▶ Resume Failed

▶ Retry

▶ Pause

▶ Batch Run
```

未来还能扩展：

- Re-Chunk
- Re-Embedding
- Re-Extract Entity
- Re-Build Graph

无需重新设计页面。

---

# 8. Statistics（统计信息）

当前统计：

```
Documents
Chunks
Entities
Facts
```

意义不够明确。

建议拆成两组。

---

## Storage Statistics

```
Documents

Chunks

Storage Size

Raw Files
```

反映存储情况。

---

## Knowledge Statistics

```
Entities

Relations

Facts

Events
```

反映知识库建设情况。

例如：

| 指标 | 数量 |
|------|------|
| Documents | 745 |
| Chunks | 11,568 |
| Entities | 835 |
| Relations | 4,231 |
| Facts | 2,145 |
| Events | 412 |

---

# 9. Documents List（文档列表）

建议增加：

## Pipeline Progress

而不是仅显示：

```
已索引
```

推荐：

```
Upload ✓

Parse ✓

Chunk ✓

Embedding ✓

Graph ✓
```

或者：

```
██████████

100%
```

用户一眼知道：

当前文档已经完成哪些步骤。

---

建议列表字段：

| 字段 | 说明 |
|------|------|
| 股票代码 | 股票 |
| 公司 | 公司名称 |
| 年份 | 报告年份 |
| 类型 | Annual / Quarterly |
| Pipeline Progress | 当前流程 |
| Chunks | 分块数量 |
| Updated | 更新时间 |
| Action | 操作 |

---

# 10. Document Detail（文档详情）

点击文档后打开右侧 Drawer。

展示完整生命周期。

例如：

```
Uploaded

↓

Docling Parsed

↓

Generated 768 Chunks

↓

Embedding Finished

↓

Extracted

125 Entities

↓

Generated

63 Facts

↓

Stored

Qdrant

↓

Stored

Knowledge Graph
```

同时展示：

## Metadata

- 文件大小
- 页数
- 上传时间
- 上传来源

## Chunk Statistics

- Chunk 数量
- 平均 Token
- 最大 Token

## Knowledge Statistics

- Entity 数量
- Relation 数量
- Fact 数量
- Event 数量

---

# 11. 页面顶部改为系统状态

相比 Documents 数量，更建议展示 Pipeline 运行状态。

例如：

```
Pipeline

Running

Queue

123

Workers

4

GPU

Idle

Parser

Healthy

Embedding

Healthy
```

因为这是运维人员每天关注的信息。

---

# 12. 推荐页面布局

```
┌──────────────────────────────────────────────────────────────┐
│                  Document                                   │
│ 文档导入 → 解析 → Chunk → Embedding → KG → Search            │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Pipeline Flow                                                │
│ Upload → Parse → Chunk → Entity → Embedding → Graph → Ready │
└──────────────────────────────────────────────────────────────┘

┌──────────────┬───────────────────────────────────────────────┐
│ Import       │ Pipeline Control                              │
│ Upload       │ ▶ Start Pipeline                              │
│ MinIO        │ ▶ Retry Failed                                │
│ Folder Sync  │ ▶ Batch Run                                   │
└──────────────┴───────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Processing Queue                                              │
│ Pending | Parsing | Chunking | Embedding | Graph | Completed │
└──────────────────────────────────────────────────────────────┘

┌────────────────────┬─────────────────────────────────────────┐
│ Storage Statistics │ Knowledge Statistics                    │
│ Documents          │ Entities                                │
│ Chunks             │ Relations                               │
│ Storage Size       │ Facts / Events                          │
└────────────────────┴─────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Documents List                                                │
│ Code | Year | Type | Pipeline Progress | Updated | Actions   │
└──────────────────────────────────────────────────────────────┘
```

---

# 13. 文档生命周期（Document Lifecycle）

整个页面建议围绕文档生命周期组织，而不是围绕功能按钮组织。

```
导入
    │
    ▼
原始文档（MinIO）
    │
    ▼
Docling 解析
    │
    ▼
Chunk 切分
    │
    ▼
Embedding（Qdrant）
    │
    ▼
Entity / Relation / Fact 提取
    │
    ▼
Knowledge Graph（PostgreSQL / Graph）
    │
    ▼
Research Agent 检索
```

---

# 14. 预期效果

## 用户体验

- 明确每个功能的职责。
- 明确文档当前处理阶段。
- 明确整个 Pipeline 的执行流程。
- 降低首次使用成本。

## 系统可扩展性

后续新增：

- OCR
- Table Extraction
- Image Caption
- Multi-language Translation
- Summary Generation
- Graph Enhancement
- Re-Embedding

均可直接插入 Pipeline，而无需重新设计页面结构。

最终，该页面将从传统的**文档管理（Document Management）**升级为**文档生命周期管理（Document Lifecycle Management）**，既满足日常文档导入需求，又能完整呈现 AI 知识处理流水线，为后续 Research Agent、Knowledge Graph 与智能检索提供统一的管理入口。