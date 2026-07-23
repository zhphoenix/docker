# API Reference

## 一、基础信息

| 项目 | 值 |
|------|-----|
| Base URL | `http://localhost:8100` |
| 协议 | HTTP |
| 数据格式 | JSON |
| 流式响应 | Server-Sent Events (SSE) |

---

## 二、端点列表

| 端点 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/v1/chat/completions` | POST | 聊天补全 | 无（本地服务） |
| `/v1/models` | GET | 列出模型 | 无 |
| `/health` | GET | 健康检查 | 无 |

---

## 三、POST /v1/chat/completions

### 请求参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `model` | string | 是 | - | 模型名称，如 `qwen3` |
| `messages` | array | 是 | - | 消息列表 |
| `stream` | boolean | 否 | false | 是否流式响应 |
| `temperature` | float | 否 | 0.7 | 温度参数（0-2） |
| `max_tokens` | integer | 否 | 4096 | 最大输出 Token 数 |
| `stop` | array/null | 否 | null | 停止序列 |

### messages 格式

| 字段 | 类型 | 说明 |
|------|------|------|
| `role` | string | `system` / `user` / `assistant` |
| `content` | string | 消息内容 |

### 响应（非流式）

```json
{
    "id": "chatcmpl-xxx",
    "object": "chat.completion",
    "created": 1234567890,
    "model": "qwen3",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "回答内容"
            },
            "finish_reason": "stop"
        }
    ],
    "usage": {
        "prompt_tokens": 100,
        "completion_tokens": 200,
        "total_tokens": 300
    }
}
```

### 响应（流式 SSE）

```text
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"delta":{"content":"回答"},"finish_reason":null}]}

data: [DONE]
```

### 错误响应

```json
{
    "error": {
        "message": "错误描述",
        "type": "invalid_request_error",
        "param": null,
        "code": null
    }
}
```

---

## 四、GET /v1/models

### 响应

```json
{
    "object": "list",
    "data": [
        {
            "id": "qwen3",
            "object": "model",
            "created": 1234567890,
            "owned_by": "local"
        }
    ]
}
```

---

## 五、GET /health

### 响应

```json
{
    "status": "healthy",
    "services": {
        "postgres": "up",
        "qdrant": "up",
        "embedding": "up",
        "reranker": "up",
        "llm": "up"
    }
}
```

---

## 六、HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求格式错误 |
| 422 | 参数校验失败 |
| 500 | 内部服务器错误 |
| 503 | 服务不可用（下游服务故障） |

---

## 七、示例

### 7.1 非流式请求

```bash
curl http://localhost:8100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3",
    "messages": [{"role": "user", "content": "分析贵州茅台"}],
    "stream": false
  }'
```

### 7.2 流式请求

```bash
curl http://localhost:8100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3",
    "messages": [{"role": "user", "content": "分析贵州茅台"}],
    "stream": true
  }'
```