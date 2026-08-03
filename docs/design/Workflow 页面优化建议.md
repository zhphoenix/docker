# Workflow 页面优化建议（Workflow Center）

## 总体评价

Workflow 页面已经明确承担 **Pipeline 执行中心** 的职责，相比 Documents 和 Knowledge Hub，定位更加准确。

但目前页面更像：

> 后台 Worker 任务列表

而不是：

> AI Workflow Orchestrator（工作流编排中心）

---

# 页面评分

| 项目 | 评分 | 说明 |
|------|------|------|
| 页面布局 | ★★★★☆ | 简洁统一 |
| 任务展示 | ★★★☆☆ | 能看到任务，但信息不足 |
| Pipeline 可视化 | ★★☆☆☆ | 没体现完整流程 |
| 可操作性 | ★★☆☆☆ | 几乎没有任务操作 |
| 扩展性 | ★★★☆☆ | 后期 Agent 增多后不够用 |

---

# 一、增加「创建任务」

目前页面只能看任务。

应该首先提供：

```
+ New Workflow
```

例如：

```
────────────────────────────

＋ New Workflow

＋ Batch Processing

＋ Rebuild Embedding

＋ Rebuild Graph

────────────────────────────
```

以后所有 Pipeline 都从这里创建。

例如：

```
Batch Embed

Batch Graph

Research

News

Knowledge Sync

```

---

# 二、Workflow 不应该只有 Embedding

目前只有：

```
batch_embed
```

实际上 Workflow 应该支持：

```
Document Pipeline

News Pipeline

Knowledge Pipeline

Research Pipeline

Training Pipeline
```

例如：

```
Document Processing

News Crawling

Knowledge Extraction

Research Analysis

Knowledge Synchronization
```

Workflow 是整个平台的任务调度中心。

---

# 三、增加 Pipeline 可视化

不要只显示：

```
100%
```

建议：

```
Docling

✓

↓

Chunk

✓

↓

Embedding

✓

↓

Entity

○

↓

Relation

○

↓

Graph

○
```

或者：

```
██████████

Parse

███████

Chunk

████

Embedding

██

Graph
```

这样用户知道卡在哪一步。

---

# 四、增加任务详情

点击任务：

```
Batch Embed

↓

Task Detail
```

进入：

```
Overview

Pipeline

Logs

Statistics

History
```

例如：

```
Overview

Task ID

...

Start

...

End

...

Worker

...

GPU

RTX5060Ti

Duration

...

```

---

# 五、增加任务日志

建议：

```
Logs

────────────────

10:21

Docling Start

10:22

Chunk

10:23

Embedding

10:25

Entity

10:26

Completed
```

失败时：

```
Embedding Error

CUDA OOM
```

方便排查。

---

# 六、增加任务操作

目前没有操作按钮。

建议：

```
Pause

Resume

Retry

Cancel

Delete

Clone
```

例如：

```
Batch Embed

[Retry]

[Cancel]

[Logs]

```

生产环境必须支持。

---

# 七、增加运行统计

顶部增加：

```
Running

Pending

Completed

Failed
```

例如：

```
Running

3

Pending

18

Completed

928

Failed

4
```

一眼看到系统负载。

---

# 八、增加 Worker 状态

建议：

```
Workers

────────────

Embedding Worker

Running

GPU

56%

────────────

Graph Worker

Idle

────────────

Docling Worker

Busy
```

了解后台资源。

---

# 九、增加任务来源

建议显示：

```
Source

Documents

News

Research

Knowledge
```

例如：

| Workflow | Source |
|----------|---------|
| Batch Embed | Documents |
| News Crawl | News |
| Graph Build | Knowledge |
| Generate Report | Research |

以后任务很多时非常重要。

---

# 十、增加调度能力

Workflow 不只是立即执行。

建议支持：

```
Run Now

Schedule

Cron

Queue Priority
```

例如：

```
每天凌晨

重新Embedding

────────────

每天8点

News Crawl

────────────

每周日

Knowledge Cleanup
```

Workflow 才真正成为调度中心。

---

# 十一、增加任务类型

建议分类：

```
Documents

Knowledge

News

Research

System
```

例如：

```
Documents

Embedding

Knowledge

Graph

News

Crawler

Research

Analysis

System

Backup
```

方便过滤。

---

# 推荐页面布局

```
Workflow
│
├── Statistics
│     ├── Running
│     ├── Pending
│     ├── Completed
│     └── Failed
│
├── New Workflow
│
├── Search & Filter
│
├── Running Tasks
│
├── Workflow Queue
│
├── Worker Status
│
└── Failed Tasks
```

---

# 页面示意

```
┌────────────────────────────────────────────┐
│ Workflow                                   │
├────────────────────────────────────────────┤
│ Running Pending Completed Failed           │
├────────────────────────────────────────────┤
│ +New Workflow +Batch +Schedule             │
├────────────────────────────────────────────┤
│ Search  Type  Status  Source               │
├────────────────────────────────────────────┤
│ Running Tasks                              │
│                                            │
│ Batch Embed                                │
│ Parse → Chunk → Embedding → Graph          │
│ ██████████ 82%                             │
│ [Logs] [Pause] [Retry]                     │
├────────────────────────────────────────────┤
│ Worker Status                              │
│ Embedding Worker  GPU 68%                  │
│ Graph Worker      Running                  │
├────────────────────────────────────────────┤
│ Failed Tasks                               │
└────────────────────────────────────────────┘
```

---

# 结合平台架构的职责划分

## Documents（文档中心）

负责：

- 上传 PDF
- 导入 MinIO
- 浏览文档
- 文档元数据
- 查看处理状态
- 选择需要处理的文档

---

## Workflow（工作流中心）

负责：

- 创建 Workflow
- Pipeline 编排
- Worker 调度
- 队列管理
- 日志查看
- 重试
- 暂停
- 定时任务
- 批量执行

---

## Knowledge Hub（知识中心）

负责：

- Knowledge Dashboard
- Collection
- Entity
- Fact
- Graph
- Search
- Statistics

---

# 推荐整体流程

```
Documents
（选择文档）

        │

        ▼

Workflow
（创建 Processing Workflow）

        │

        ▼

Docling

        │

        ▼

Chunk

        │

        ▼

Embedding

        │

        ▼

Entity

        │

        ▼

Relation

        │

        ▼

Knowledge Graph

        │

        ▼

Knowledge Hub
```

---

# 总结

Workflow 页面应定位为 **AI Platform 的任务调度与执行中心**，而不是仅展示 `batch_embed` 等后台任务。

核心设计原则：

1. **Workflow First**：所有 AI Pipeline 都应通过 Workflow 创建和管理，而不是直接由业务页面执行。
2. **Pipeline Visible**：完整展示每个任务的处理阶段和进度，而不仅是百分比。
3. **Task Operable**：支持暂停、恢复、重试、取消、查看日志等任务管理能力。
4. **Scheduler Native**：支持定时执行、批处理和优先级调度，为长期自动化运行提供基础。
5. **Worker Monitoring**：实时展示 Worker、GPU 和队列状态，便于运维和性能分析。
6. **Platform Unified**：统一管理 Documents、News、Knowledge、Research 等所有 Workflow，而不仅限于 Embedding。