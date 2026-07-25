# FastAPI 设计

## 一、定位

FastAPI 作为 API 网关，提供 OpenAI Compatible API，对接 Open WebUI。

**核心原则**：
- FastAPI 只负责 HTTP 协议，不包含业务逻辑
- 所有请求通过 Agent Dispatcher 路由到 LangGraph Workflow
- 支持流式响应（SSE）

---

## 二、API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | 聊天补全（OpenAI 兼容） |
| `/v1/models` | GET | 列出可用模型 |
| `/health` | GET | 健康检查 |

---

## 三、请求/响应格式

### 3.1 Chat Completions 请求

```json
{
  "model": "sisyphus",
  "messages": [
    {"role": "system", "content": "你是一个投研助手"},
    {"role": "user", "content": "分析宁德时代未来三年竞争力"}
  ],
  "stream": true,
  "temperature": 0.7,
  "max_tokens": 4096
}
```

### 3.2 流式响应（SSE）

```text
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"delta":{"content":"根据"},"index":0}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"delta":{"content":"分析"},"index":0}]}

data: [DONE]
```

### 3.3 Models 响应

```json
{
  "object": "list",
  "data": [
    {
      "id": "sisyphus",
      "object": "model",
      "owned_by": "local"
    }
  ]
}
```

---

## 四、核心代码结构

### 4.1 应用入口（main.py）

```python
from fastapi import FastAPI
from api.chat import router as chat_router
from api.models import router as models_router
from api.health import router as health_router

app = FastAPI(title="AI Platform Agent Service")

app.include_router(health_router)
app.include_router(models_router)
app.include_router(chat_router)
```

### 4.2 Chat 路由（api/chat.py）

```python
from fastapi import APIRouter
from schemas.chat import ChatRequest
from graph.router import dispatch_agent

router = APIRouter()

@router.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    # 1. 解析请求
    # 2. 调用 Agent Dispatcher 选择 Agent
    # 3. 执行 LangGraph Workflow
    # 4. 返回流式/非流式响应
    agent = dispatch_agent(request)
    return await agent.run(request)
```

---

## 五、Agent Dispatcher

Dispatcher 根据请求特征选择对应 Agent：

```python
def dispatch_agent(request: ChatRequest) -> BaseAgent:
    """根据请求选择 Agent"""
    # 简单路由：根据消息内容或参数判断
    # 未来可扩展为 LLM 路由
    if is_research_task(request):
        return ResearchAgent()
    elif is_knowledge_task(request):
        return KnowledgeAgent()
    else:
        return ChatAgent()
```

---

## 六、流式响应实现

使用 `StreamingResponse` + `async generator`：

```python
from fastapi.responses import StreamingResponse

@router.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    agent = dispatch_agent(request)
    
    if request.stream:
        return StreamingResponse(
            agent.stream_run(request),
            media_type="text/event-stream"
        )
    else:
        return await agent.run(request)
```

---

## 七、错误处理

| HTTP 状态码 | 场景 | 响应格式 |
|------------|------|---------|
| 200 | 正常 | OpenAI 格式 |
| 400 | 请求格式错误 | `{"error": {"message": "...", "type": "invalid_request_error"}}` |
| 422 | 参数校验失败 | FastAPI 默认格式 |
| 500 | 内部错误 | `{"error": {"message": "...", "type": "server_error"}}` |
| 503 | 下游服务不可用 | `{"error": {"message": "...", "type": "service_unavailable"}}` |

---

## 八、中间件

| 中间件 | 用途 |
|--------|------|
| CORS | 允许 Open WebUI 跨域访问 |
| Request ID | 为每个请求生成唯一 ID，贯穿日志 |
| Timing | 记录请求处理时间 |