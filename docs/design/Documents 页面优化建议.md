# Documents 页面优化建议（Document Center）

## 总体评价

相比前面的 **Knowledge Hub** 页面，这个 **Documents** 页面已经更接近实际业务，因为 **Embedding 的入口应该在 Documents，而不是 Knowledge Hub**。

但是，按照当前 AI Investment Research Platform 的整体定位（**投资研究 + MinIO + Docling + Qdrant + Knowledge Graph**），目前页面更像一个**状态页（Status Page）**，而不是一个完整的**文档管理中心（Document Center）**。

---

# 页面评分

| 项目 | 评分 | 说明 |
|------|------|------|
| 页面布局 | ★★★★☆ | 简洁、统一 |
| 信息层级 | ★★★☆☆ | 重要操作缺失 |
| 文档管理 | ★★☆☆☆ | 基本没有管理能力 |
| Pipeline 展示 | ★★☆☆☆ | 未体现完整处理流程 |
| 扩展性 | ★★★☆☆ | 后期功能增加后页面容易拥挤 |

---

# 一、增加「导入文档」区域（最高优先级）

## 当前问题

目前页面只有：

- 搜索
- Filter

但没有体现：

> **文档从哪里来？**

作为文档中心，应该首先提供文档导入能力。

---

## 建议

在统计信息下方增加导入区域：

```
──────────────────────────────────────────

＋ Import From MinIO

＋ Upload PDF

＋ Sync Folder

＋ Batch Processing

──────────────────────────────────────────
```

建议对应功能：

| 功能 | 说明 |
|------|------|
| Import From MinIO | 从 MinIO 导入已有文档 |
| Upload PDF | 上传新的 PDF 文件 |
| Sync Folder | 同步指定目录 |
| Batch Processing | 创建批量处理任务 |

这样整个文档生命周期的入口就非常清晰。

---

# 二、Documents 应该展示真正的文档

目前页面中间：

```
暂无文档
```

以后应该显示真实文档列表，例如：

```
000001 平安银行

2024 Annual Report.pdf

420 MB

2026-08-02

────────────────────────

Status

✓ Parsed

✓ Chunked

✓ Embedded

✓ Graph

[查看]

[重新处理]

────────────────────────

600519 贵州茅台

2024 Annual Report.pdf

...
```

Documents 页面最核心的内容应该是：

> **文档列表（Document List）**

而不是统计数字。

---

# 三、增加 Pipeline 状态

建议每个文档展示处理流水线。

例如：

```
Docling

██████████

Chunk

████████

Embedding

██████

Entity

███

Graph

█
```

或者：

```
✓ Parse

✓ Chunk

○ Embedding

○ Entity

○ Graph
```

这样可以一眼看出：

- 当前执行到哪里
- 是否失败
- 是否完成

---

# 四、增加文档操作按钮

目前页面没有任何文档操作。

建议增加：

- 查看
- 重新处理
- 删除
- 重新 Embedding
- 查看 Graph
- 查看 Chunk

例如：

```
000001.pdf

[Open]

[Reprocess]

[Graph]

[Chunks]
```

方便：

- Agent 调试
- 数据检查
- 重新生成向量
- 查看知识图谱

---

# 五、调整顶部统计

目前统计：

```
Documents

Pending

Parsed

Embedded
```

建议修改为：

```
Documents

Chunks

Entities

Facts
```

例如：

```
Documents

13,242

Chunks

578,136

Entities

36,291

Facts

281,994
```

相比 Parsed，更能反映知识库规模。

---

# 六、增加处理队列（Running Tasks）

建议增加：

```
Running Tasks

────────────

000001

Embedding

45%

────────────

腾讯

Graph

88%

────────────

Apple

Waiting
```

用户无需进入 Workflow 页面，就可以了解后台正在执行哪些任务。

---

# 七、增加失败任务区域

建议增加：

```
Failed Tasks

────────────

Apple

Embedding Timeout

Retry

────────────

Google

Chunk Failed

Retry
```

生产环境一定存在失败任务，因此需要：

- 查看失败原因
- 一键 Retry
- 查看日志

---

# 八、增强搜索能力

目前：

```
搜索股票代码
```

建议支持统一搜索：

```
🔍

股票

公司

PDF

年份

行业
```

例如：

```
000001

平安银行

2024

银行

pdf
```

支持：

- 股票代码
- 公司名称
- PDF 文件名
- 年份
- 行业

统一搜索。

---

# 九、增强 Filter

目前：

```
all

all
```

建议扩展为：

### 状态

```
全部

Pending

Running

Completed

Failed
```

### 市场

```
A股

港股

美股
```

### 年份

```
2024

2025
```

### 行业

```
银行

半导体

新能源
```

未来管理几万份年报时非常重要。

---

# 十、增加文档详情页

点击：

```
2024.pdf
```

进入详情：

```
Overview

Metadata

Chunks

Embedding

Entities

Facts

Graph

History
```

例如：

```
Overview

────────────

文件大小

420 MB

页数

368

Chunk

1924

Embedding

1924

Entity

328

Facts

2501
```

方便：

- Agent 调试
- Chunk 检查
- Embedding 检查
- Knowledge Graph 检查

---

# 推荐页面布局

```
Documents
│
├── Statistics
│     ├── Documents
│     ├── Chunks
│     ├── Entities
│     └── Facts
│
├── Import
│     ├── Upload PDF
│     ├── Import MinIO
│     ├── Sync Folder
│     └── Batch Process
│
├── Search & Filter
│
├── Running Tasks
│
├── Document List
│
└── Failed Tasks
```

---

# 页面布局示意

```
┌──────────────────────────────────────────┐
│ Documents                               │
├──────────────────────────────────────────┤
│ Documents  Chunks  Entities  Facts       │
├──────────────────────────────────────────┤
│ +Upload  +MinIO  +Sync  +Batch           │
├──────────────────────────────────────────┤
│ Search   Status   Market   Year          │
├──────────────────────────────────────────┤
│ Running Tasks                            │
├──────────────────────────────────────────┤
│ Document List                            │
│                                          │
│ 000001.pdf                               │
│ ✓ Parse ✓ Chunk ✓ Embedding ✓ Graph      │
│ [Open] [Graph] [Reprocess]               │
│                                          │
│ 600519.pdf                               │
│ ...                                      │
├──────────────────────────────────────────┤
│ Failed Tasks                             │
└──────────────────────────────────────────┘
```

---

# 结合平台架构的职责划分

建议采用单一职责设计，不让 Documents 页面承担 Pipeline 执行。

## Documents（文档中心）

负责：

- 上传 PDF
- 导入 MinIO
- 同步目录
- 浏览文档
- 搜索文档
- 查看状态
- 查看详情
- 选择文档

定位：

> 文档管理中心（Document Center）

---

## Workflow（处理中心）

负责：

- 创建处理任务
- Docling
- OCR
- Chunk
- Embedding
- Entity Extraction
- Relation Extraction
- Knowledge Graph
- 查看日志
- 暂停任务
- 重试任务
- 批量处理

定位：

> Pipeline 执行中心（Processing Center）

---

## Knowledge Hub（知识中心）

负责：

- Knowledge Dashboard
- Collection 管理
- Entity 浏览
- Fact 浏览
- Knowledge Graph
- Semantic Search
- Statistics
- System Health

定位：

> 知识中台（Knowledge Hub）

---

# 推荐的数据流

```
Import PDF / MinIO

        │

        ▼

Documents

（文档管理）

        │

        ▼

Workflow

（Docling → Chunk → Embedding → Entity → Graph）

        │

        ▼

Knowledge Hub

（Knowledge Graph + Search + Collection + Dashboard）
```

---

# 总结

推荐采用三层职责划分：

| 模块 | 职责 | 核心目标 |
|------|------|----------|
| **Documents** | 文档生命周期管理 | 管理文档，不执行 Pipeline |
| **Workflow** | 文档处理 Pipeline | 解析、Chunk、Embedding、Graph 全流程执行 |
| **Knowledge Hub** | 知识管理与检索 | 管理知识、知识图谱、语义搜索与统计 |

这种设计符合单一职责原则（SRP），同时能够支持未来的大规模扩展，包括 Research Agent、Knowledge Organization Agent、MCP Knowledge Server 等模块。