# RerankNode 设计规范

> Version: v1.0
> Status: Production Ready
> Last Updated: 2026-07-27
> Scope: LangGraph / RAG / GraphRAG / Search Pipeline

---

# 一、目标

RerankNode 是 LangGraph Workflow 中负责文档重排序的节点。

职责只有：

```
State
    │
    ▼
读取 Documents
    │
    ▼
调用 RerankerTool
    │
    ▼
更新 Documents
```

Node 不应包含任何模型相关逻辑。

---

# 二、职责

负责：

- 读取 AgentState
- 判断是否需要 Rerank
- 调用 RerankerTool
- 更新 documents
- 写入 rerank 元数据
- 返回新的 State

不负责：

- HTTP 请求
- Prompt
- Retry
- 超时控制
- 文档截断
- Batch
- GPU 调度
- 模型名称

这些全部属于 RerankerTool。

---

# 三、Node 应保持极简

推荐：

```
读取 State

↓

documents 是否为空

↓

调用 Tool

↓

更新 documents

↓

Return
```

Node 不应超过几十行代码。

---

# 四、禁止硬编码

禁止：

```
_MAX_DOCS_TO_RERANK = 5

_MAX_CHARS_PER_DOC = 1000
```

改为：

```
settings.RERANK_TOP_K

settings.RERANK_MAX_CHARS
```

以后更换模型无需修改 Node。

---

# 五、文档截断

Node 不负责：

```
content[:1000]
```

原因：

不同模型：

```
Qwen

BGE

Jina

NVIDIA
```

Context Length 都不同。

应由：

```
RerankerTool
```

自动处理。

---

# 六、Top-K

Node 不负责：

```
documents[:5]
```

原因：

以后：

```
Top10

Top20

Top50
```

无需修改 Node。

由：

```
RerankerTool
```

根据配置决定。

---

# 七、返回格式

Node 应始终返回：

```
{
    "documents": ...
}
```

不要：

```
dict
list
tuple
```

保持 LangGraph State 更新一致。

---

# 八、异常处理

Rerank 属于：

```
Enhancement Step
```

不是必须成功。

因此：

失败：

```
记录 Warning

↓

返回原排序
```

禁止：

```
raise
```

导致整个 Workflow 中断。

---

# 九、日志

建议：

开始：

```
Rerank start

documents=30
```

结束：

```
Rerank finished

input=30

reranked=10

elapsed=0.32s
```

失败：

```
Rerank failed

reason=...
```

所有日志统一结构化。

---

# 十、计时

Node 应统计：

```
start

↓

rerank

↓

elapsed
```

用于：

- Performance Dashboard
- Grafana
- LangSmith
- OpenTelemetry

---

# 十一、Metadata

Node 应更新：

```
document["rerank_score"]
```

同时增加：

```
document["rerank_rank"]
```

方便后续：

```
Explainability
```

例如：

```
Top1

Top2

Top3
```

---

# 十二、保持 Immutable

不要：

```
documents.sort(...)
```

推荐：

```
copy()

new list
```

避免污染：

```
Checkpoint
```

---

# 十三、Tool 返回

推荐：

```
[
    {
        index: 3,
        score: 0.98
    },
    ...
]
```

Node 负责：

映射：

```
documents[index]
```

保持职责清晰。

---

# 十四、未来兼容

Node 不关心：

当前：

```
Qwen3-Reranker
```

未来：

```
BGE-Reranker

Jina-Reranker

CrossEncoder

NVIDIA NeMo

Cohere
```

Node 不需要修改。

---

# 十五、Pipeline

推荐：

```
Retriever

↓

Top50

↓

RerankNode

↓

Top10

↓

Generator
```

Node 不负责：

Retriever 参数。

---

# 十六、可观测性

建议记录：

```
Question Length

Documents

TopK

Latency

Success

Failure

Retry
```

方便线上分析。

---

# 十七、设计原则

RerankNode 应遵循：

- Single Responsibility
- Tool First
- Configuration First
- Immutable State
- Fail Open
- Observable
- Provider Agnostic

---

# 十八、推荐结构

```
LangGraph

      │

      ▼

 RerankNode
      │
      ▼
 RerankerTool
      │
      ▼
 HTTP Client
      │
      ▼
Qwen3-Reranker
```

---

# 十九、质量要求

满足以下要求视为 Production Ready：

- Node 无 HTTP 代码
- Node 无模型参数
- Node 无硬编码
- Node 无截断逻辑
- Node 无 Top-K 逻辑
- Tool 统一处理推理
- 返回统一 State
- Fail Open
- Immutable 更新
- 完整日志
- 性能统计
- 可替换任意 Reranker Provider