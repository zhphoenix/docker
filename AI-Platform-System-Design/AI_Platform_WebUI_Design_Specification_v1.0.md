# AI Platform WebUI Design Specification (v1.0)

## 一、设计目标

构建一个以 **AI First** 为核心的 AI Platform
控制中心，而不是传统后台管理系统。

设计理念融合： - OpenWebUI（AI Chat） - n8n（Workflow） -
LangSmith（Agent） - Kubernetes Dashboard（资源监控） -
VSCode（开发体验） - Grafana（监控）

------------------------------------------------------------------------

# 二、设计原则

## 1. Mac 风格

-   毛玻璃（Glassmorphism）
-   圆角
-   柔和阴影
-   Sidebar
-   Toolbar
-   Dock 风格按钮
-   大量留白

参考产品： - Raycast - Notion - Arc Browser - Linear - Apple System
Settings

------------------------------------------------------------------------

## 2. AI First

所有功能均可从 Chat 发起：

``` text
Chat
 ↓
Planner Agent
 ↓
执行
 ↓
反馈
```

------------------------------------------------------------------------

## 3. Everything is a Task

所有操作统一抽象为 Task。

Task 包含：

-   状态
-   日志
-   耗时
-   Agent
-   输入
-   输出

------------------------------------------------------------------------

## 4. Everything is Observable

所有 Agent 必须可观测：

-   Prompt
-   Token
-   Latency
-   Memory
-   Tool Calls
-   Logs

------------------------------------------------------------------------

## 5. Everything is Configurable

全部配置化：

-   Models
-   Prompt
-   Workflow
-   Buckets
-   Collections
-   Chunk Strategy

------------------------------------------------------------------------

# 三、整体布局

``` text
┌────────────────────────────────────┐
│ Toolbar                            │
├────────────┬───────────────────────┤
│ Sidebar    │ Workspace             │
├────────────┼───────────────────────┤
│ StatusBar                          │
└────────────────────────────────────┘
```

## Toolbar

-   Logo
-   Search
-   Global Chat
-   Notification
-   GPU
-   CPU
-   Memory
-   Settings
-   User

## Sidebar

-   Dashboard
-   AI Chat
-   Data
-   Documents
-   Knowledge
-   Retrieval
-   Agents
-   Workflow
-   Tasks
-   Monitoring
-   Settings

------------------------------------------------------------------------

# 四、核心页面

## Dashboard

-   Today's Tasks
-   Running Agents
-   Recent Documents
-   News
-   OCR Queue
-   Embedding Queue
-   GPU
-   PostgreSQL
-   Qdrant
-   MinIO
-   Docker

## Chat Center

流程：

``` text
Prompt
 ↓
Planner
 ↓
Workflow
 ↓
Agent
 ↓
Logs
 ↓
Artifacts
```

## Task Center

展示： - ID - 状态 - Agent - 开始时间 - 结束时间 - Token - 耗时 - 日志

## Agent Center

展示： - Prompt - Tools - Memory - Workflow - Logs

## Workflow Center

支持拖拽节点：

Planner → Downloader → OCR → Docling → Chunk → Embedding → Qdrant

## Knowledge Center

支持： - Collection - Document - Metadata - Chunk - Payload - Version

## Monitoring Center

监控： - GPU - CPU - Memory - Docker - PostgreSQL - Qdrant - MinIO -
Embedding - LLM - Crawl4AI

## Settings Center

配置： - LLM - Embedding - Reranker - Buckets - Collections - Prompt -
Workflow

------------------------------------------------------------------------

# 五、Design System

  项目         规范
  ------------ -------------------------------------------
  Layout       Toolbar + Sidebar + Workspace + StatusBar
  Grid         8pt
  Radius       Card 16px / Button 12px
  Icons        Lucide
  UI           shadcn/ui + Radix UI
  Font         Inter + Noto Sans SC
  Theme        Light / Dark / System
  Motion       150\~250ms
  Responsive   Desktop / Tablet / Mobile

------------------------------------------------------------------------

# 六、AI Platform 专属能力

1.  Agent Trace
2.  Knowledge Graph
3.  Data Pipeline
4.  Model Hub
5.  Experiment Lab
6.  Research Workspace

------------------------------------------------------------------------

# 七、推荐技术栈

  层         推荐
  ---------- ---------------------------
  React      React + TypeScript + Vite
  UI         shadcn/ui
  CSS        Tailwind CSS
  State      Zustand
  Query      TanStack Query
  Charts     ECharts
  Workflow   React Flow
  Markdown   TipTap
  Realtime   WebSocket + SSE
