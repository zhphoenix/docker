# Research Workspace（研究中心）设计方案

**Version:** 3.0  
**Status:** Architecture Stable  
**Role:** Business Workspace

---

# 一、设计原则

Research 不再承担系统管理职责。

Research 是整个 AI 投研平台的**业务入口（Business Workspace）**，负责组织一次研究任务，并展示最终研究成果。

Research **不管理**：

- Agent
- Workflow
- Documents
- Knowledge
- News
- Review

这些模块都拥有自己的页面。

Research 只负责：

> 发起研究 → 查看研究 → 管理研究成果 → 导出成果

因此不会与其它模块发生职责重叠。

---

# 二、模块定位

Research 位于整个业务流程的中心。

```text
                Dashboard
                     │
                     ▼
            New Research
                     │
                     ▼
      Workflow（执行流程）
                     │
                     ▼
        Agent Center（执行）
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
      News      Documents   Knowledge Hub
        │            │            │
        └────────────┼────────────┘
                     ▼
             Research Workspace
                     │
          Report / Knowledge Package
                     │
                     ▼
                 Review
```

Research 不拥有数据。

Research 只负责聚合。

---

# 三、职责边界

## Research 负责

✔ 创建研究任务

✔ 查看研究状态

✔ 阅读研究报告

✔ 管理研究成果

✔ 导出成果

✔ 查看引用来源

---

## Research 不负责

❌ 新闻采集

→ News Center

---

❌ 文档管理

→ Documents

---

❌ Agent 配置

→ Agent Center

---

❌ Workflow 编辑

→ Workflow

---

❌ Knowledge 管理

→ Knowledge Hub

---

❌ Review

→ Review Center

---

# 四、页面结构

```text
Research Workspace

──────────────────────────────

Header

Research Statistics

Quick Actions

Research List

Research Detail

Export

History
```

页面保持轻量。

---

# 五、Header

```
Research Workspace

AI Investment Research
```

右侧：

```
+ New Research

Search

Refresh
```

不再出现：

Agent

Workflow

Review

这些入口。

---

# 六、Statistics

顶部显示统计。

```
Running

Completed

Draft

Archived
```

例如：

```
Running

5

Completed

326

Draft

12

Archived

142
```

这里只显示研究数据。

不显示：

GPU

LLM

Workflow

Agent

---

# 七、Quick Actions

快速入口。

```
+ New Company Research

+ Industry Research

+ Theme Research

+ Watchlist Research

+ Import Existing Task
```

以后可以增加模板。

---

# 八、Research List

这是整个页面主体。

采用 Card。

```
────────────────────────────

腾讯控股

Company Research

Completed

昨天

Open

────────────────────────────

宁德时代

Valuation

Running

42%

Open

────────────────────────────

AI芯片产业

Theme Research

Draft

Open
```

支持：

收藏

Tag

Archive

Delete

Duplicate

---

# 九、筛选器

支持：

```
Keyword

Status

Research Type

Date

Tag

Sort
```

Research 自己的数据即可。

不需要 Workflow Filter。

---

# 十、Research Detail

点击研究进入。

结构如下：

```
Overview

Report

Sources

Export

History
```

只有五个页面。

---

# 十一、Overview

显示：

```
Title

Research Type

Target

Status

Created Time

Finished Time

Duration

Workflow

Model

Summary
```

这里只显示概要。

Workflow 只是引用。

点击：

```
Open Workflow
```

跳转 Workflow 页面。

---

# 十二、Report

最终研究成果。

支持：

```
Markdown

PDF

HTML
```

支持：

全文搜索

目录

代码高亮

Mermaid

数学公式

引用

---

右上角：

```
Edit

Share

Export
```

---

# 十三、Sources

这里只显示：

引用来源。

例如：

```
News

12 Items

View
```

点击：

跳转 News。

---

```
Documents

AnnualReport.pdf

View
```

跳转 Documents。

---

```
Knowledge Package

View
```

跳转 Knowledge Hub。

---

```
Workflow

Deep Research

View
```

跳转 Workflow。

---

```
Research Agent

View
```

跳转 Agent Center。

Research 永远不重复实现这些功能。

---

# 十四、Export

支持：

```
Markdown

PDF

HTML

Word

PowerPoint

Knowledge Package

JSON
```

以后增加：

Podcast

Video

Poster

---

# 十五、History

记录版本。

```
Version 1

Created

昨天

────────────────

Version 2

Review Updated

今天

────────────────

Version 3

Knowledge Updated
```

支持：

恢复历史版本。

---

# 十六、新建研究

点击：

```
+ New Research
```

进入 Wizard。

---

## Step 1

研究类型

```
Company

Industry

Theme

Macro

Watchlist

Custom
```

---

## Step 2

输入目标。

例如：

```
腾讯

00700

Tesla

新能源

AI芯片
```

---

## Step 3

选择模板。

```
Quick Research

Standard Research

Deep Research

Investment Analysis

Risk Analysis

Custom Template
```

模板实际对应 Workflow。

Research 不管理模板。

---

## Step 4

输出格式。

```
Markdown

PDF

Knowledge Package

Presentation
```

---

点击：

```
Start Research
```

Research 调用 Workflow。

之后等待完成。

---

# 十七、研究生命周期

```
Create Research

↓

Workflow

↓

Agent Execute

↓

News

↓

Documents

↓

Knowledge

↓

LLM Analysis

↓

Report

↓

Review

↓

Publish
```

Research 只是展示。

---

# 十八、数据来源

Research 不保存业务数据。

所有数据来自：

```
PostgreSQL

Research

Reports
```

```
MinIO

Original Files
```

```
Knowledge Hub

Knowledge Package
```

```
News

News Records
```

```
Workflow

Execution Status
```

```
Agent Center

Agent Metadata
```

Research 只是聚合。

---

# 十九、页面跳转关系

```
Research

│

├── Open Workflow

│      ▼

│   Workflow

│

├── Open News

│      ▼

│   News

│

├── Open Documents

│      ▼

│   Documents

│

├── Open Knowledge

│      ▼

│   Knowledge Hub

│

├── Open Agent

│      ▼

│   Agent Center

│

└── Open Review

       ▼

    Review
```

Research 永远通过跳转访问其它模块。

---

# 二十、与其它模块关系

| 模块 | 职责 | Research 是否重复 |
|------|------|------------------|
| Dashboard | 系统总览 | ❌ |
| Chat | AI 对话 | ❌ |
| Agent Center | Agent 管理 | ❌ |
| Workflow | 流程设计 | ❌ |
| News | 新闻采集 | ❌ |
| Documents | 文档管理 | ❌ |
| Knowledge Hub | 知识管理 | ❌ |
| Review | 人工审核 | ❌ |
| Watchlist | 自选股监控 | ❌ |
| Models | 模型管理 | ❌ |
| Vector DB | 向量数据库 | ❌ |
| Monitor | 系统监控 | ❌ |

Research 是唯一负责**研究业务**的模块。

---

# 二十一、数据库建议

Research 仅维护自己的业务数据。

建议建立：

```
research_projects
```

研究项目

---

```
research_tasks
```

研究任务

---

```
research_reports
```

最终报告

---

```
research_versions
```

版本历史

---

```
research_exports
```

导出记录

Research 不复制 News、Knowledge、Documents 等数据，仅通过 ID 建立关联。

---

# 二十二、未来扩展（保持低耦合）

未来新增能力时，不修改现有模块，而是在 Research 中增加引用能力。

例如：

- Research Template
- Research Schedule（定时研究）
- Batch Research（批量研究）
- Compare Reports（报告对比）
- Multi-Version Compare（版本比较）
- AI Executive Summary（高管摘要）
- Research Subscription（订阅推送）

以上扩展均不影响 News、Workflow、Knowledge Hub、Documents、Agent Center 等模块，保证整体架构保持单一职责、低耦合、高可维护性。