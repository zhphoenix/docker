# EmbeddingTool 设计规范

> Version: v1.0
> Status: Production Ready
> Last Updated: 2026-07-27
> Scope: LangGraph / RAG / GraphRAG / Knowledge Base / Index Builder

---

# 一、目标

EmbeddingTool 是整个 AI Platform 的统一 Embedding 调用层。

所有需要生成向量的模块，都必须调用 EmbeddingTool。

禁止业务代码直接调用：

- httpx
- requests
- OpenAI SDK
- embedding server API

EmbeddingTool 是唯一入口。

架构如下：

```
Business Logic
        │
        ▼
EmbeddingTool
        │
        ▼
Embedding Service
(Qwen3-Embedding-4B)
```

---

# 二、职责

EmbeddingTool 负责：

- 管理 HTTP 连接池
- 请求 Embedding Server
- 统一异常处理
- 自动 Retry
- 限制并发
- 生命周期管理
- 日志记录
- 响应校验

EmbeddingTool 不负责：

- Chunk 切分
- 文本预处理
- 向量存储(Qdrant)
- 检索逻辑

保持职责单一。

---

# 三、生命周期

EmbeddingTool 应为整个进程唯一实例。

推荐：

```
embedding_tool = EmbeddingTool()
```

整个程序运行期间：

```
Application Start

↓

创建 AsyncClient

↓

一直复用

↓

Application Shutdown

↓

关闭连接池
```

禁止：

```
每次请求：

创建 AsyncClient

↓

请求

↓

关闭

↓

再次创建
```

原因：

每次建立 TCP 连接都会增加延迟和系统开销。

---

# 四、HTTP Client

必须使用：

```
httpx.AsyncClient
```

并启用连接池。

推荐：

```
keep-alive
connection pool
```

禁止：

```
async with AsyncClient()

每调用一次创建一次
```

---

# 五、连接池

推荐配置：

```
max_connections = 100

max_keepalive_connections = 20
```

原因：

未来平台可能同时存在：

- LangGraph
- OpenWebUI
- Index Builder
- Batch Import
- Graph Builder
- API Service

多个模块会共享同一个 Embedding Server。

连接数应充足。

---

# 六、Timeout

不要：

```
Timeout(30)
```

建议分别配置：

```
connect = 5 秒

read = 120 秒

write = 30 秒

pool = 5 秒
```

说明：

Embedding 推理主要耗时发生在 GPU。

因此：

Read Timeout 应明显大于 Connect Timeout。

---

# 七、配置参数

所有配置必须来自 Settings。

例如：

```
EMBEDDING_URL

EMBEDDING_MODEL

EMBEDDING_CONNECT_TIMEOUT

EMBEDDING_READ_TIMEOUT

EMBEDDING_WRITE_TIMEOUT

EMBEDDING_MAX_CONNECTIONS

EMBEDDING_KEEPALIVE_CONNECTIONS

EMBEDDING_MAX_CONCURRENCY
```

禁止：

```
model="embedding"

timeout=30

写死在代码
```

以后更换模型无需修改代码。

---

# 八、URL 规范

初始化时：

```
rstrip("/")
```

保证：

```
http://host:8001
```

而不是：

```
http://host:8001/
```

拼接统一：

```
/embeddings
```

避免：

```
http://host//embeddings
```

---

# 九、请求格式

统一采用：

```
POST /embeddings
```

请求：

```
{
    "model": "...",
    "input": [...]
}
```

禁止：

多个地方自行拼接 JSON。

---

# 十、响应校验

收到响应后必须检查：

是否存在：

```
data
```

是否存在：

```
embedding
```

是否：

```
len(result)

==

len(input)
```

否则立即抛出异常。

禁止：

直接：

```
response.json()["data"]
```

---

# 十一、异常处理

至少处理：

```
ConnectError
```

表示：

Embedding 服务不可达。

---

处理：

```
ReadTimeout
```

表示：

GPU 推理超时。

---

处理：

```
HTTPStatusError
```

记录：

```
HTTP Status

Response Body
```

方便排查。

---

未知异常：

统一：

```
logger.exception()
```

保留完整 Traceback。

禁止：

```
except Exception:

pass
```

---

# 十二、Retry

Embedding 服务可能因为：

- GPU 忙
- 容器重启
- 网络抖动
- 502
- 504

短时间失败。

建议：

最多：

```
Retry = 3
```

退避：

```
500 ms

↓

1 s

↓

2 s
```

避免立即失败。

---

# 十三、并发限制

EmbeddingTool 应限制：

同时请求数量。

推荐：

```
Semaphore
```

例如：

```
8
```

表示：

最多：

```
8 个 Embedding 请求
```

进入 GPU。

防止：

几十个 Agent 同时打爆服务。

---

# 十四、日志

正常：

```
Embedding 16 texts
```

DEBUG。

失败：

记录：

- URL
- Status
- Exception
- Retry 次数

未知异常：

```
logger.exception()
```

保证完整 Traceback。

---

# 十五、关闭资源

程序退出时：

```
await embedding_tool.close()
```

释放：

- Keep Alive
- Socket
- Connection Pool

FastAPI：

```
shutdown event
```

统一调用。

---

# 十六、返回值

统一返回：

```
list[list[float]]
```

不返回：

```
response

JSON

dict
```

业务层无需了解 HTTP。

---

# 十七、线程安全

EmbeddingTool 应支持：

多个 Coroutine 并发调用。

不得：

共享可变状态。

允许：

共享：

```
AsyncClient
```

---

# 十八、推荐架构

```
                 AI Platform

          ┌─────────────────────┐
          │     LangGraph       │
          ├─────────────────────┤
          │     OpenWebUI       │
          ├─────────────────────┤
          │    Index Builder    │
          ├─────────────────────┤
          │   Graph Builder     │
          ├─────────────────────┤
          │     Search API      │
          └──────────┬──────────┘
                     │
                     ▼
             ┌─────────────────┐
             │ EmbeddingTool   │
             ├─────────────────┤
             │ AsyncClient     │
             │ Retry           │
             │ Semaphore       │
             │ Logging         │
             │ Validation      │
             └────────┬────────┘
                      │
                      ▼
      Qwen3-Embedding-4B (:8001)
```

---

# 十九、设计原则

EmbeddingTool 应遵循：

- 单一职责（Single Responsibility）
- 配置优先（Configuration First）
- 长生命周期（Long-lived Client）
- 连接复用（Connection Reuse）
- 自动恢复（Retry）
- 并发可控（Concurrency Control）
- 完整日志（Observability）
- 生命周期管理（Lifecycle Management）
- 易于替换（Provider Agnostic）

---

# 二十、质量要求

满足以下要求方可视为 Production Ready：

- 全局单例
- AsyncClient 连接池
- Keep-Alive
- 配置化参数
- URL 标准化
- 请求统一封装
- 响应完整校验
- 自动 Retry
- Semaphore 并发限制
- 分类异常处理
- 完整日志
- 生命周期管理
- FastAPI Shutdown 自动关闭
- 返回值统一
- 可替换任意 Embedding Provider