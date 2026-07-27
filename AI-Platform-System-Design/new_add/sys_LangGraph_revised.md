# 本地 Agent 服务架构（LangGraph + FastAPI）

> 目标：完全离线、本地部署、无需 LangSmith、无需官方 LangGraph Server、无需许可证。

## 一、总体架构

```text
Open WebUI
      │
OpenAI Compatible API
      │
FastAPI
      │
Agent Dispatcher
      │
LangGraph Workflow
      │
├── Nodes
├── Memory
└── Tool Router
      │
┌─────┼───────────────┐
│     │               │
LLM  Qdrant      PostgreSQL
│                  │
│                  ├── Checkpoint
│                  └── User Memory
├── Docling
├── MinIO
└── Obsidian
```

## 二、目录结构

```text
agent/
├── app/
├── api/
│   ├── chat.py
│   └── health.py
├── graph/
│   ├── builder.py
│   ├── graph.py
│   ├── router.py
│   ├── state.py
│   └── checkpoint.py
├── agents/
│   ├── base_agent.py
│   ├── research_agent.py
│   ├── knowledge_agent.py
│   └── math_agent.py
├── nodes/
│   ├── planner.py
│   ├── retrieve.py
│   ├── rerank.py
│   ├── reason.py
│   ├── reflect.py
│   ├── writer.py
│   └── finish.py
├── tools/
│   ├── llm.py
│   ├── qdrant.py
│   ├── postgres.py
│   ├── embedding.py
│   ├── reranker.py
│   ├── docling.py
│   ├── obsidian.py
│   ├── minio.py
│   ├── filesystem.py
│   └── search.py
├── prompts/
├── schemas/
├── memory/
├── config/
├── tests/
├── main.py
├── Dockerfile
└── requirements.txt
```

## 三、职责划分

### FastAPI
- 提供 OpenAI Compatible API
- 调用 Agent Dispatcher
- 不包含业务逻辑

### Agent Dispatcher
- 根据请求选择 Agent
- Research Agent
- Knowledge Agent
- Math Agent

### Graph
- 仅负责 Workflow
- 不直接访问数据库
- 不直接创建模型

Workflow：

```text
START
 ↓
Planner
 ↓
Retrieve
 ↓
Reason
 ↓
Reflect
 ↓
Finish
 ↓
END
```

### State

统一使用 AgentState：

- messages
- question
- plan
- documents
- tool_results
- answer
- metadata

所有 Node 只能修改 State。

### Nodes

一个 Node 只负责一件事情。

Planner
- 生成计划

Retrieve
- 调用 Embedding
- 调用 Qdrant

Reason
- 推理

Reflect
- 检查答案

Writer
- 输出最终结果

### Tools

Tool 只负责访问基础设施：

- llama.cpp/vLLM
- PostgreSQL
- Qdrant
- MinIO
- Docling
- Obsidian
- Filesystem

Tool 不包含业务逻辑。

### Prompt

所有 Prompt 独立保存在 prompts/：

- planner.md
- reason.md
- reflect.md
- writer.md

统一由 Prompt Loader 加载。

## 四、数据流

```text
Open WebUI
      │
FastAPI
      │
Dispatcher
      │
Graph
      │
Nodes
      │
Tool Router
      │
Tools
      │
LLM / PostgreSQL / Qdrant / MinIO / Docling
```

## 五、设计原则

1. API 与 Workflow 解耦
2. Workflow 与 Tool 解耦
3. Node 单一职责
4. Tool 只访问基础设施
5. Prompt 独立管理
6. PostgreSQL 保存 Checkpoint
7. Redis 非必需，可按需扩展
8. FastAPI 提供 OpenAI Compatible API
9. 全部支持本地离线部署
10. 后续可扩展 MCP、多 Agent、后台任务
