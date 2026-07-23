# RAG 设计

## 一、定位

RAG（Retrieval-Augmented Generation）是系统的核心检索能力，为 Agent 提供基于文档的问答。

---

## 二、RAG 流程

```text
用户提问
    │
    ▼
Embedding Model（Qwen3-Embedding-4B, :8001）
    │  将查询向量化
    ▼
Qdrant（:6333）
    │  语义检索 Top-K Chunk
    ▼
Reranker（Qwen3-Reranker-0.6B, :8002）
    │  对 Top-K 重新排序
    ▼
LLM（llama.cpp, :8080）
    │  根据排序后的 Chunk 生成回答
    ▼
返回用户
```

---

## 三、文档处理流水线

> **完整规范见 [24_数据底座规范](24_数据底座规范.md) 第三、六章。**

```text
PDF / Word / HTML
    │
    ▼
MinIO（staging/ — 原始文件上传）
    │
    ▼
Docling Parser（:5001）
    │  PDF → Layout Model → TableFormer → Reading Order
    ▼
DoclingDocument（完整文档对象：标题、段落、表格、图片、页码）
    │
    ├──→ 导出到 documents/{market}/{symbol}/{type}/{year}/
    │    ├── report.md（完整 Markdown）
    │    ├── metadata.json（元数据）
    │    ├── chunks.json（切块结果）
    │    ├── tables/（独立表格）
    │    └── figures/（独立图片）
    │
    ├──→ chunks.json → Embedding(:8001) → Qdrant:6333（语义检索）
    │
    └──→ 表格数据 → Extract → PostgreSQL（精确查询）
```

### 关键设计决策

- **表格数据不进入 Qdrant**：向量数据库不擅长精确数字查询、比较计算、财务建模
- **Docling 先解析成文档对象，再 Chunk，最后可导出 Markdown**
- **MinIO 是文件真相源，PostgreSQL 是业务真相源，Qdrant 是语义检索索引**

---

## 四、各组件说明

### 4.1 Embedding（:8001）

| 项目 | 值 |
|------|-----|
| 模型 | Qwen3-Embedding-4B |
| 精度 | f16（未量化） |
| 镜像 | `ghcr.io/ggml-org/llama.cpp:server-cuda13` |
| API | `POST /v1/embeddings` |
| 说明 | 向量化对精度敏感，使用 f16 未量化版本 |

### 4.2 Qdrant（:6333）

| 项目 | 值 |
|------|-----|
| 用途 | 存储文档 Chunk 的 Embedding 向量 |
| 检索 | 语义相似度搜索（Top-K） |
| 优化 | ON_DISK_PAYLOAD=true, HNSW_INDEX_ON_DISK=true |
| 不存储 | 原始文件、精确数值 |

### 4.3 Reranker（:8002）

| 项目 | 值 |
|------|-----|
| 模型 | Qwen3-Reranker-0.6B |
| 精度 | Q8_0（量化） |
| API | `POST /v1/rerank` |
| 参数 | `--reranking --embedding --pooling rank --ctx-size 4096` |
| 说明 | 0.6B 体量下 Q8_0 对排序质量影响极小，节省显存 |

### 4.4 Docling（:5001）

| 项目 | 值 |
|------|-----|
| 用途 | PDF 解析 |
| 流程 | PDF → DoclingDocument → Chunk → Embedding → Qdrant |
| 内部模型 | Layout Detection, Table Recognition, OCR, Reading Order 等 |
| GPU | CUDA 12.8 加速 |

---

## 五、Qdrant Collection 设计

> **完整规范见 [24_数据底座规范](24_数据底座规范.md) 第五章。**

### 5.1 Collection 命名

```text
documents_{market}
```

| Collection | 内容 |
|------------|------|
| documents_cn | A 股文档（年报、公告、研报等） |
| documents_hk | 港股文档 |
| documents_us | 美股文档 |

通过 Payload 中的 `document_type`、`tags` 等字段区分文档类型，而不是拆分 Collection。

### 5.2 Payload 标准

每个 Point 的 Payload 包含以下 8 个字段：

```json
{
    "document_id": "uuid",
    "chunk_id": "uuid",
    "content": "贵州茅台2025年营业收入...",
    "page": 15,
    "section": "财务摘要",
    "title": "贵州茅台2025年报",
    "tags": ["财报", "白酒"],
    "language": "zh"
}
```

文本内容（content）同时存入 Payload，检索后直接送 LLM，无需回查 PostgreSQL。

### 5.3 向量参数

```python
from qdrant_client.models import VectorParams, Distance

VectorParams(
    size=2560,           # Qwen3-Embedding-4B 向量维度
    distance=Distance.COSINE
)
```

---

## 六、检索策略

### 6.1 基础检索

```python
async def retrieve(query: str, market: str = "cn", limit: int = 10) -> list[dict]:
    # 1. Embedding
    vectors = await embedding_tool.embed([query])
    
    # 2. Qdrant 检索
    results = await qdrant_tool.search(
        collection=f"documents_{market}",
        vector=vectors[0],
        limit=limit
    )
    
    # 3. Rerank
    reranked = await reranker_tool.rerank(
        query=query,
        documents=[r["payload"]["content"] for r in results]
    )
    
    return reranked
```

### 6.2 过滤条件

支持按 market、symbol、year、document_type 过滤：

```python
from qdrant_client.models import Filter, FieldCondition, MatchValue

filter = Filter(must=[
    FieldCondition(key="market", match=MatchValue(value="cn")),
    FieldCondition(key="symbol", match=MatchValue(value="600519")),
    FieldCondition(key="year", match=MatchValue(value=2025))
])
```

---

## 七、设计原则

| 原则 | 说明 |
|------|------|
| 语义 + 精确分离 | 文本走 Qdrant，表格数据走 PostgreSQL |
| Embedding 不量化 | f16 精度保证向量质量 |
| Reranker 可量化 | Q8_0 节省显存，对排序质量影响极小 |
| 按市场分 Collection | 支持快速过滤，扩展新市场不改结构 |
| 元数据完整 | 每个 Chunk 保留来源、页码、公司等信息 |