# Agent Center 设计规范（Agent Control Center）

> Version: v1.0  
> Status: Planning  
> Module: Frontend / AI Platform

---

# 1. 模块定位

Agent Center 是整个 AI Platform 的 **Agent 管理中心（Agent Control Center）**，负责统一管理、监控、配置和调度所有 AI Agent。

它不仅展示 Agent 状态，更承担 Agent 生命周期管理、能力管理、运行监控、日志分析和工作流管理等职责。

整体定位：

```
                    Agent Center
                         │
        ┌────────────────┼────────────────┐
        │                │                │
   Agent Registry   Agent Runtime   Agent Monitoring
        │                │                │
        └────────────────┼────────────────┘
                         │
                  LangGraph Runtime
                         │
          ┌──────────────┼──────────────┐
          │              │              │
       Skills         MCP Server      Tools
```

---

# 2. 建设目标

Agent Center 应具备以下能力：

- Agent 注册与发现
- Agent 生命周期管理
- Agent 配置管理
- Agent Prompt 管理
- Skill 管理
- Tool 管理
- MCP 管理
- Workflow 管理
- Agent 运行监控
- Agent 日志分析
- Agent 性能统计

最终成为整个 AI Platform 的控制中心。

---

# 3. 页面结构

```
Agent Center
│
├── Agent Registry
├── Agent Detail
├── Agent Skills
├── Agent Tools
├── Agent Prompt
├── Agent Workflow
├── MCP Connections
├── Memory
├── Runtime Metrics
├── Logs
└── Configuration
```

---

# 4. Agent Registry

## 功能

统一展示系统所有 Agent。

当前：

- Chat Agent
- Research Agent
- Knowledge Agent
- Investment Agent

未来：

- News Collector Agent
- Knowledge Organization Agent
- Document Analysis Agent
- Watchlist Agent
- Report Generator Agent
- Workflow Scheduler Agent

---

## 每张卡片展示

```
● Running

Research Agent

负责投资研究

Version

v1.0

Status

Running

Last Active

2 min ago
```

展示内容：

- 名称
- 描述
- 在线状态
- 版本
- 最后运行时间
- 当前模型

---

# 5. Agent Detail

点击 Agent 后进入详情页。

包括：

## 基本信息

```
Name

Research Agent

Description

负责投资分析

Version

v1.2

Author

System

Created

2026-08-01
```

---

## Runtime

```
Running

Model

Qwen3-32B

Temperature

0.2

Context

32000

Timeout

180s
```

---

## Dependencies

- Skills
- Tools
- MCP
- Workflow
- Memory

---

# 6. Prompt Management

管理 Agent Prompt。

包括：

- System Prompt
- Prompt Version
- Prompt History
- Prompt Variables
- Prompt Preview

示例：

```
Research Agent

System Prompt

Version

5

Updated

2026-08-05

Variables

{{query}}

{{context}}

{{news}}
```

支持：

- 在线编辑

---

# 7. Skill Management

展示当前 Agent 加载的 Skill。

例如：

```
architecture

coding

knowledge

review

workflow

report

glossary
```

每个 Skill 显示：

- 名称
- Version
- 更新时间
- 是否启用

支持：

- Enable
- Disable
- Reload

---

# 8. Tool Management

展示 Agent 可调用 Tool。

例如：

```
PostgreSQL

Qdrant

MinIO

Docling

Embedding

Reranker

Browser

Search

Python
```

每个 Tool 展示：

- 状态
- 平均耗时
- 调用次数
- 错误率

---

# 9. MCP Management

展示 Agent 当前连接 MCP。

例如：

```
Knowledge MCP

Connected

News MCP

Connected

Data MCP

Connected

Search MCP

Connected
```

展示：

- Connection Status
- Last Heartbeat
- Latency
- Retry Count

---

# 10. Workflow(在workflow页建立)

展示 Agent Workflow。

例如：

```
START

↓

Search

↓

Retrieve

↓

Knowledge Graph

↓

Reasoning

↓

Generate Report

↓

END
```

支持：

- Workflow Preview
- Workflow Version
- Workflow Source
- Workflow Graph

未来支持：

LangGraph 可视化。

---

# 11. Memory

展示 Agent Memory。

包括：

```
Conversation Memory

Knowledge Memory

Vector Memory

Graph Memory
```

展示：

```
Current Context

15000 Tokens

History

Enabled

Compression

Enabled
```

---

# 12. Runtime Metrics

统计 Agent 运行指标。

包括：

```
Today Runs

248

Success

247

Failed

1

Average Latency

5.8 s

Average Tokens

12K

Average Cost

0
```

图表：

- Runs Trend
- Latency Trend
- Token Usage
- Error Rate

---

# 13. Logs

查看 Agent 最近运行记录。

例如：

```
2026-08-05

Research

Started

↓

Retrieve

↓

Tool

↓

Finished

8.2s
```

失败示例：

```
Tool Timeout

Embedding Error

MCP Error
```

支持：

- 搜索
- 筛选
- 下载
- Trace

---

# 14. Configuration

在线修改 Agent 参数。

例如：

```
Model

Qwen3-32B

Temperature

0.2

Top P

0.95

Max Tokens

32000

Timeout

180

Retry

3
```

支持：

- 保存
- 回滚
- 热更新

---

# 15. 推荐建设 Agent

| Agent | 职责 | 优先级 |
|--------|------|---------|
| Chat Agent | 通用聊天 | ⭐⭐⭐ |
| Research Agent | 投资研究 | ⭐⭐⭐⭐⭐ |
| Knowledge Agent | 知识查询 | ⭐⭐⭐⭐⭐ |
| Investment Agent | 股票分析 | ⭐⭐⭐⭐⭐ |
| News Collector Agent | 新闻采集 | ⭐⭐⭐⭐⭐ |
| Knowledge Organization Agent | 实体、关系、事实抽取 | ⭐⭐⭐⭐⭐ |
| Document Analysis Agent | PDF/研报解析 | ⭐⭐⭐⭐ |
| Watchlist Agent | 自选股监控 | ⭐⭐⭐⭐⭐ |
| Report Generator Agent | 自动生成研究报告 | ⭐⭐⭐⭐ |
| Workflow Scheduler Agent | 定时调度 | ⭐⭐⭐⭐ |

---

# 16. 推荐页面布局

```
┌─────────────────────────────────────────────────────────────┐
│ Agent Center                                                │
├─────────────────────────────────────────────────────────────┤
│ Agent Registry │ Runtime Metrics │ Recent Logs              │
├─────────────────────────────────────────────────────────────┤
│ Agent Detail                                            │
├─────────────────────────────────────────────────────────────┤
│ Prompt │ Skills │ Tools │ MCP │ Memory                    │
├─────────────────────────────────────────────────────────────┤
│ Workflow (LangGraph Visualization)                        │
├─────────────────────────────────────────────────────────────┤
│ Runtime Statistics                                        │
├─────────────────────────────────────────────────────────────┤
│ Logs                                                      │
└─────────────────────────────────────────────────────────────┘
```

---

# 17. 建设优先级

## Phase 1（核心功能）

- Agent Registry
- Agent Detail
- Runtime Status
- Prompt Management
- Configuration

---

## Phase 2（能力管理）

- Skill Management
- Tool Management
- MCP Management
- Memory Management

---

## Phase 3（可视化）

- Workflow Graph
- Runtime Metrics
- Dashboard
- Logs
- Trace

---

## Phase 4（高级能力）

- Agent 热更新
- Prompt Version Control
- A/B Prompt Test
- Agent Marketplace
- 多 Agent 协同监控
- Agent 权限管理

---

# 18. 最终目标

Agent Center 不应只是一个 Agent 状态展示页面，而应成为整个 AI Platform 的统一控制中心。

最终负责：

- Agent 生命周期管理
- Agent 配置管理
- Prompt 管理
- Skill 管理
- Tool 管理
- MCP 管理
- Workflow 管理
- Memory 管理
- 运行监控
- 日志分析
- 性能统计
- 多 Agent 协同调度
- 生成的数据生命周期管理

成为整个 AI Investment Research Platform 的「Agent Control Center」。