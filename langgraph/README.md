# AI Platform Agent 服务使用说明

## 一、项目概述

基于 LangGraph 构建的多 Agent 投研平台，提供 OpenAI 兼容 API，支持 RAG 检索增强生成、多 Agent 路由、反思重试机制和真实流式输出。

**服务端口**: `8100`  
**API 协议**: OpenAI Compatible (`/v1/chat/completions`)

---

## 二、项目结构

```
langgraph/
├── compose.yml                 # Docker Compose 编排
├── Dockerfile                  # 构建镜像（python:3.11-slim）
├── requirements.txt            # Python 依赖
├── .env.example                # 环境变量示例
│
└── agent/                      # 应用根目录（COPY 到 /app）
    ├── main.py                 # 入口：启动 uvicorn
    │
    ├── app/
    │   └── main.py             # FastAPI 实例、中间件、生命周期
    │
    ├── api/                    # API 层（HTTP 路由）
    │   ├── chat.py             #   POST /v1/chat/completions
    │   ├── health.py           #   GET  /health
    │   └── models.py           #   GET  /v1/models
    │
    ├── agents/                 # Agent 层（业务编排）
    │   ├── base_agent.py       #   基类：run() / stream_run()
    │   ├── chat_agent.py       #   简单问答 Agent（RAG）
    │   └── research_agent.py   #   研究分析 Agent（Planner + RAG + Reflect）
    │
    ├── graph/                  # LangGraph 图定义
    │   ├── graph.py            #   StateGraph 构建（Research/Chat 两种图）
    │   ├── builder.py          #   图编译工厂
    │   ├── router.py           #   Agent 路由分发（关键词匹配）
    │   ├── checkpoint.py       #   PostgreSQL Checkpoint 持久化
    │   └── state.py            #   AgentState TypedDict 定义
    │
    ├── nodes/                  # 图节点（Workflow 步骤）
    │   ├── planner.py          #   理解问题 → 生成执行计划
    │   ├── retrieve.py         #   Embedding → Qdrant 语义检索
    │   ├── rerank.py           #   Reranker 重排序
    │   ├── reason.py           #   LLM 推理生成回答
    │   ├── reflect.py          #   LLM 评估答案质量
    │   ├── writer.py           #   （预留）长文写作
    │   └── finish.py           #   收尾：写入 answer
    │
    ├── tools/                  # 基础设施工具层
    │   ├── llm.py              #   LLM 调用（httpx 连接池复用）
    │   ├── embedding.py        #   Embedding 向量化
    │   ├── reranker.py         #   Reranker 重排序
    │   ├── qdrant.py           #   Qdrant 向量检索（asyncio.to_thread）
    │   ├── postgres.py         #   PostgreSQL 连接池
    │   ├── minio.py            #   MinIO 对象存储
    │   ├── obsidian.py         #   Obsidian Vault 读写（Local REST API）
    │   ├── docling.py          #   Docling 文档解析
    │   ├── search.py           #   （预留）Web 搜索
    │   └── filesystem.py       #   （预留）文件系统
    │
    ├── schemas/                # 数据模型
    │   ├── chat.py             #   OpenAI 兼容请求/响应模型
    │   └── state.py            #   AgentState 状态定义
    │
    ├── prompts/                # Prompt 模板
    │   ├── loader.py           #   模板加载器（变量替换）
    │   ├── planner.md          #   Planner 节点 prompt
    │   ├── reason.md           #   Reason 节点 prompt
    │   ├── reflect.md          #   Reflect 节点 prompt
    │   └── writer.md           #   Writer 节点 prompt
    │
    ├── config/
    │   └── settings.py         #   Pydantic Settings（从 .env 加载）
    │
    └── tests/                  # 测试
        ├── unit/               #   单元测试
        ├── api/                #   API 测试
        └── integration/        #   集成测试
```

---

## 三、调用逻辑（请求生命周期）

```
Open WebUI / curl
       │
       ▼
┌─────────────────────────────────────────────────┐
│  POST /v1/chat/completions                      │
│  api/chat.py                                    │
│                                                 │
│  1. 解析 ChatRequest                            │
│  2. dispatch_agent(request) → 选择 Agent         │
│  3. stream ? agent.stream_run() : agent.run()   │
└─────────────┬───────────────────────────────────┘
              │
     ┌────────┴────────┐
     ▼                 ▼
 ChatAgent        ResearchAgent
 (简单问答)        (研究分析)
     │                 │
     ▼                 ▼
 Chat Graph       Research Graph
```

### Chat Graph（简单问答）

```
START → Retrieve → Rerank → Reason → Finish → END
```

### Research Graph（研究分析）

```
START → Planner → Retrieve → Rerank → Reason → Reflect
                                                      │
                                          ┌───────────┴───────────┐
                                          │                       │
                                     quality=good            quality=bad
                                     或 retry≥2              且 retry<2
                                          │                       │
                                       Finish               → Retrieve（重试）
                                          │
                                        END
```

### 流式模式（stream=true）

流式模式跳过 LangGraph 图执行，手动调用前置节点后直接透传 LLM 流：

```
1. 发送 role chunk
2. [Research] Planner → Retrieve → Rerank
3. [Chat]       Retrieve → Rerank
4. 直接调用 LLM stream_chat()，逐 token 透传给客户端
```

---

## 四、下游服务依赖

| 服务 | 容器名 | 端口 | 用途 | 必需 |
|------|--------|------|------|------|
| LLM | qwythos-9b | 8080 | 推理生成 | ✅ |
| Embedding | embedding | 8080 | 文本向量化 | ✅ |
| Reranker | reranker | 8080 | 检索重排序 | ✅ |
| Qdrant | qdrant | 6333 | 向量检索 | ✅ |
| PostgreSQL | postgres | 5432 | Checkpoint + 业务数据 | ✅ |
| Docling | docling | 5001 | 文档解析 | ❌ |
| Obsidian | host:27124 | 27124 | 知识库读写 | ❌ |
| MinIO | minio | 9000 | 对象存储 | ❌ |

所有服务通过 Docker 网络 `ai-platform` 互联。

---

## 五、API 使用

### 5.1 非流式请求

```bash
curl -X POST http://localhost:8100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-8b",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": false
  }'
```

响应：
```json
{
  "id": "chatcmpl-1784277624258",
  "object": "chat.completion",
  "created": 1784277624,
  "model": "qwen3-8b",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "您好！..."},
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 234,
    "completion_tokens": 296,
    "total_tokens": 530
  }
}
```

### 5.2 流式请求

```bash
curl -X POST http://localhost:8100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-8b",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": true
  }'
```

响应为 SSE 格式，逐 token 推送：
```
data: {"id":"chatcmpl-...","choices":[{"delta":{"role":"assistant"}}]}
data: {"id":"chatcmpl-...","choices":[{"delta":{"content":"你好"}}]}
data: {"id":"chatcmpl-...","choices":[{"delta":{"content":"！"}}]}
data: [DONE]
```

### 5.3 健康检查

```bash
curl http://localhost:8100/health
```

### 5.4 触发研究模式

消息中包含以下关键词时自动路由到 ResearchAgent：
`分析`、`研究`、`报告`、`年报`、`财务`、`对比`、`评估`、`投资`、`行业`、`市场`

---

## 六、配置管理

所有配置通过 `/mnt/e/docker/.env` 管理，关键变量：

| 变量 | 说明 | 示例 |
|------|------|------|
| `OPENAI_BASE_URL` | LLM 服务地址 | `http://qwythos-9b:8080/v1` |
| `OPENAI_API_KEY` | API Key（可为空） | `not-needed` |
| `MODEL_NAME` | 模型名 | `qwen3` |
| `EMBEDDING_URL` | Embedding 服务 | `http://embedding:8080/v1` |
| `RERANKER_URL` | Reranker 服务 | `http://reranker:8080/v1` |
| `QDRANT_HOST` | Qdrant 地址 | `qdrant` |
| `OBSIDIAN_URL` | Obsidian API | `https://host.docker.internal:27124` |
| `OBSIDIAN_API_KEY` | Obsidian API Key | `Bearer xxx` 或纯 key |

---

## 七、运维命令

```bash
# 构建并启动
cd /mnt/e/docker/langgraph
docker compose up -d --build

# 查看日志
docker logs -f langgraph

# 健康检查
curl -s http://localhost:8100/health | python3 -m json.tool

# 停止服务
docker compose down
```

---

## 八、性能特性

| 优化项 | 实现方式 |
|--------|----------|
| HTTP 连接池 | httpx 模块级复用（max_connections=20） |
| Qdrant 异步化 | `asyncio.to_thread()` 避免阻塞事件循环 |
| 真实流式 | LLM stream 直接透传，非假流式 |
| Token 用量 | 从 LLM 响应提取并透传到 API 响应 |
| 优雅关闭 | 生命周期管理，shutdown 时关闭所有连接池 |





1. **项目概述** - 基于 LangGraph 的多 Agent 投研平台
2. **项目结构** - 完整的目录树 + 每个文件的职责说明
3. **调用逻辑** - 从请求到响应的完整生命周期：
   - `POST /v1/chat/completions` → `dispatch_agent()` 路由
   - **Chat Graph**: `Retrieve → Rerank → Reason → Finish`
   - **Research Graph**: `Planner → Retrieve → Rerank → Reason → Reflect → (retry/finish)`
   - **流式模式**: 手动执行前置节点后直接透传 LLM SSE
4. **下游服务依赖** - 7 个服务（LLM/Embedding/Reranker/Qdrant/PostgreSQL/Docling/Obsidian）
5. **API 使用** - curl 示例（流式/非流式/健康检查）
6. **配置管理** - 所有环境变量说明
7. **运维命令** - 构建/日志/停止
8. **性能特性** - httpx 连接池、Qdrant 异步化、真实流式、Token 用量
