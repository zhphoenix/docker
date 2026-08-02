# AI 自动生成知识页面设计规范
## AI Investment Research Platform

---

# 1. 设计原则

对于 AI Investment Research Platform，**AI 自动生成知识页面**并不意味着：

> **LLM 自动编写 Markdown。**

真正应该生成的是：

> **Knowledge Object View（知识对象视图）**

页面只是 **Knowledge Object** 的一种可视化表达。

推荐架构：

```text
Knowledge Object（数据库）
        │
        ▼
Template Engine
        │
        ▼
Knowledge Page（SiYuan）
```

而不是：

```text
LLM
        │
        ▼
直接输出 Markdown
```

这是两种完全不同的设计思想。

---

# 2. 总体架构

建议新增一个独立模块：

> **Knowledge Rendering Engine**

整体流程：

```text
News Intelligence Agent
      │
      ▼
Knowledge Ingestion Agent
      │
      ▼
Knowledge Database
(PostgreSQL)
      │
      ▼
Knowledge Rendering Engine
      │
      ▼
SiYuan
```

> **注意：LLM 到 Knowledge Ingestion Agent 为止。**

之后的页面生成全部由程序完成，而不是再次调用 LLM。

---

# 3. Knowledge Rendering Engine

建议新增独立模块：

```text
knowledge-render/

├── renderer/
│   ├── company.py
│   ├── industry.py
│   ├── report.py
│   └── event.py
│
├── templates/
│   ├── company.md.j2
│   ├── event.md.j2
│   └── report.md.j2
│
├── assets/
│
├── markdown/
│
└── sync.py
```

---

## 模块职责

```text
Knowledge Object
        │
        ▼
Template
        │
        ▼
Markdown
        │
        ▼
SiYuan
```

主要负责：

- 模板渲染
- Markdown 生成
- 页面同步
- 增量更新
- 版本管理

---

# 4. Company 页面自动生成

## Knowledge Object

```json
{
  "id":"company_nvidia",
  "name":"NVIDIA",
  "industry":"AI GPU",
  "market_cap":"4T",
  "events":[...],
  "financial":[...]
}
```

---

## Jinja2 模板

```jinja2
# {{ company.name }}

## Company Profile

{{ company.profile }}

## Financial

...

## Events

...
```

---

## 渲染结果

```markdown
# NVIDIA

## Company Profile

...

## Financial

Revenue

...

## Events

...
```

同步至：

```
Company/NVIDIA
```

> 整个过程中 **LLM 不参与页面生成**。

---

# 5. 页面统一布局

建议所有页面采用统一结构。

```text
Company

├── Header
├── Metadata
├── AI Summary
├── Business
├── Financial
├── Events
├── Timeline
├── Documents
├── Research
├── Graph
└── References
```

统一布局带来的优势：

- 页面一致性
- 模板可维护
- 支持自动更新
- 支持局部刷新

---

# 6. AI Summary

唯一允许由 LLM 生成的内容。

示例：

```markdown
## AI Summary

NVIDIA 是全球 AI GPU 龙头企业。

Blackwell 产品推动增长。

未来三年的主要催化剂：

……

主要风险：

……
```

> AI Summary 只是摘要，不是事实来源。

所有事实仍来自：

- PostgreSQL
- Knowledge Graph
- Evidence

---

# 7. Fact 自动渲染

Fact：

```text
Apple

acquired

Beats
```

自动渲染：

```markdown
## Facts

Apple acquired Beats.

Source

SEC Filing

Confidence

0.98
```

无需 LLM 重写。

---

# 8. Event 自动渲染

数据库：

```text
Event

↓

Title

Date

Entities

Impact

Evidence
```

模板：

```markdown
## Event

### Summary

...

### Related Companies

...

### Evidence

...
```

由模板自动完成。

---

# 9. Research Report

Research Agent 输出统一 JSON。

例如：

```json
{
  "executive_summary":"",
  "financial_analysis":"",
  "risk":""
}
```

模板：

```markdown
# Research Report

## Executive Summary

...

## Business

...

## Risk

...
```

> 不允许 LLM 直接拼接 Markdown。

---

# 10. Timeline 自动生成

来源：

```
Event
```

自动按照时间排序：

```text
2023

...

2024

...

2025

...
```

无需 AI。

---

# 11. Graph 自动生成

Knowledge Graph：

```text
NVIDIA

↓

Partner

↓

TSMC
```

页面：

```markdown
## Relations

Partner

TSMC

Competitor

AMD

Customer

Microsoft
```

由程序自动生成。

---

# 12. Documents 自动生成

自动列出：

- Annual Report
- 10-Q
- Research Report
- Presentation
- Conference Call

数据来源：

```
Document
```

数据库。

---

# 13. 页面增量更新

不要：

```
覆盖整个 Markdown
```

建议：

按 Section 更新：

- Header
- Financial
- Timeline
- Events
- Research

例如：

```python
update_section(
    company_id,
    "Financial"
)
```

这样：

```
我的备注
```

不会被覆盖。

---

# 14. 页面版本控制

页面：

```
Version 12
```

数据库：

```
Version 13
```

同步流程：

```text
Diff

↓

Patch

↓

Update
```

不要：

```text
DELETE

重新生成
```

---

# 15. 页面生成流程

推荐事件驱动：

```text
Knowledge Object Changed

↓

Event Bus

↓

Render Queue

↓

Template Render

↓

Markdown

↓

SiYuan API

↓

Done
```

例如：

```
Financial 更新
```

仅刷新：

```
Financial Section
```

不会重新生成整个 Company 页面。

---

# 16. Render Queue

新增任务队列：

```
knowledge_render_jobs
```

建议字段：

```
id

entity

type

status

retry

priority
```

执行流程：

```text
Queue

↓

Worker

↓

Render

↓

Sync
```

优势：

- 不阻塞 Agent
- 支持重试
- 支持优先级
- 支持异步更新

---

# 17. 推荐页面分类

建议统一 Renderer。

```
Company

Industry

Security

Event

Person

Document

Research Report

Macro

Theme

Watchlist
```

对应：

```text
renderer/

company.py

industry.py

event.py

report.py
```

每种页面对应一个 Renderer。

---

# 18. 最终自动生成流程

```text
                    News
                      │
                      ▼
           Knowledge Ingestion Agent
                      │
                      ▼
      PostgreSQL（事实源 / Source of Truth）
                      │
          ┌───────────┼────────────┐
          ▼           ▼            ▼
   Apache AGE      Qdrant      Event Bus
  (Knowledge    (Vector         │
    Graph)       Index)         ▼
                           Render Queue
                                │
                                ▼
                 Knowledge Rendering Engine
                                │
                     Jinja2 Templates
                                │
                                ▼
                        SiYuan Adapter
                                │
                                ▼
                  SiYuan Knowledge Pages
```

---

# 19. Knowledge Rendering Engine 定位

建议将：

> **Knowledge Rendering Engine**

独立为新的核心模块，而不是放入 MCP Server。

---

## 输入

Knowledge Object：

- Company
- Event
- Fact
- Document
- Metric
- Research Report

---

## 处理

负责：

- Template Render
- Markdown Render
- Incremental Update
- Diff Compare
- Version Control
- Render Queue

---

## 输出

输出：

- SiYuan 页面
- （未来可扩展至 Anytype、Outline 等知识工作台）

---

# 20. 推荐系统分层

建议形成四层清晰架构。

```text
Knowledge Ingestion Agent
        │
        ▼
Knowledge Storage
(PostgreSQL + Apache AGE + Qdrant)
        │
        ▼
Knowledge Rendering Engine
        │
        ▼
Knowledge Workspace
(SiYuan)
```

各层职责：

| 层级 | 职责 |
|------|------|
| Knowledge Ingestion Agent | 知识抽取、知识组织、Knowledge Object 生成 |
| Knowledge Storage | 保存事实、关系、向量等长期知识 |
| Knowledge Rendering Engine | 将 Knowledge Object 渲染为可阅读页面 |
| SiYuan | 人工浏览、审核、补充编辑、研究记录 |

---

# 21. 设计总结

## 核心原则

- LLM 不负责生成 Markdown 页面。
- 页面来源于 Knowledge Object，而不是自然语言。
- 页面全部采用模板渲染。
- 支持局部更新，不覆盖人工编辑。
- 页面只是 Knowledge Object 的一种 View。
- Knowledge Rendering Engine 独立于 MCP Server。
- 支持未来切换 SiYuan、Anytype、Outline 等知识工作台。

最终形成：

```text
Knowledge Object
        │
        ▼
Knowledge Rendering Engine
        │
        ▼
Knowledge Page
        │
        ▼
Knowledge Workspace（SiYuan）
```

这种架构相比让 LLM 直接生成 Markdown，更稳定、更可维护，也更符合企业级 AI 知识平台长期演进的需求。