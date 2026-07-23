# OpenAI 兼容 API

## 一、定位

FastAPI 实现 OpenAI Compatible API，使 Open WebUI 可以无缝对接。

---

## 二、支持的端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/chat/completions` | POST | 聊天补全 |
| `/v1/models` | GET | 列出模型 |
| `/health` | GET | 健康检查 |

---

## 三、/v1/chat/completions

### 3.1 请求格式

```json
{
    "model": "qwen3",
    "messages": [
        {"role": "system", "content": "你是一个投研助手"},
        {"role": "user", "content": "分析宁德时代"}
    ],
    "stream": true,
    "temperature": 0.7,
    "max_tokens": 4096,
    "stop": null
}
```

### 3.2 非流式响应

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
                "content": "根据分析..."
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

### 3.3 流式响应（SSE）

```text
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1234567890,"model":"qwen3","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"根据"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

---

## 四、/v1/models

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

## 五、错误格式

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

| type | 场景 |
|------|------|
| `invalid_request_error` | 请求格式错误 |
| `server_error` | 内部错误 |
| `service_unavailable` | 下游服务不可用 |

---

## 六、对接 Open WebUI

Open WebUI 配置：

```yaml
environment:
  OPENAI_API_BASE_URL: http://host.docker.internal:8100/v1
  OPENAI_API_KEY: dummy
```

- `OPENAI_API_KEY` 设为 `dummy`，因为本地服务不需要认证
- `host.docker.internal` 用于容器访问宿主机