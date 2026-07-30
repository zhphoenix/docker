# Tool 设计

## 一、定位

Tool 只负责访问基础设施，不包含业务逻辑。

---

## 二、Tool 列表

| Tool | 文件 | 访问目标 | 端口 |
|------|------|---------|------|
| LLM | `tools/llm.py` | llama.cpp | :8080 |
| Embedding | `tools/embedding.py` | llama.cpp Embedding | :8001 |
| Reranker | `tools/reranker.py` | llama.cpp Reranker | :8002 |
| Qdrant | `tools/qdrant.py` | Qdrant | :6333 |
| PostgreSQL | `tools/postgres.py` | PostgreSQL | :5432 |
| MinIO | `tools/minio.py` | MinIO | :9000 |
| Docling | `tools/docling.py` | Docling | :5001 |
| Obsidian | `tools/obsidian.py` | Obsidian Vault | MCP |
| Filesystem | `tools/filesystem.py` | 本地文件系统 | - |
| FinancialData | `tools/financial_data.py` | AKShare / yfinance SDK | - |
| Search | `tools/search.py` | Web 搜索（预留） | - |

---

## 三、各 Tool 详细说明

### 3.1 LLM Tool

```python
import httpx
from config.settings import settings

class LLMTool:
    """调用 llama.cpp LLM 服务"""
    
    def __init__(self):
        self.base_url = settings.OPENAI_BASE_URL  # http://sisyphus:8080/v1
    
    async def chat(self, messages: list[dict], **kwargs) -> str:
        """聊天补全"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": settings.MODEL_NAME,
                    "messages": messages,
                    **kwargs
                },
                timeout=120.0
            )
            return response.json()["choices"][0]["message"]["content"]
    
    async def stream_chat(self, messages: list[dict], **kwargs):
        """流式聊天"""
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json={"stream": True, "messages": messages, **kwargs},
                timeout=120.0
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        yield line[6:]
```

### 3.2 Embedding Tool

```python
class EmbeddingTool:
    """调用 Embedding 服务"""
    
    def __init__(self):
        self.base_url = "http://embedding:8080/v1"
    
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """文本向量化"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                json={"input": texts, "model": "embedding"},
                timeout=30.0
            )
            return [item["embedding"] for item in response.json()["data"]]
```

### 3.3 Reranker Tool

```python
class RerankerTool:
    """调用 Reranker 服务"""
    
    def __init__(self):
        self.base_url = "http://reranker:8080/v1"
    
    async def rerank(self, query: str, documents: list[str]) -> list[dict]:
        """重排序"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/rerank",
                json={"query": query, "documents": documents},
                timeout=30.0
            )
            return response.json()["results"]
```

### 3.4 Qdrant Tool

```python
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance, MatchValue

class QdrantTool:
    """Qdrant 向量检索"""
    
    def __init__(self):
        self.client = QdrantClient(host="qdrant", port=6333)
    
    async def search(self, collection: str, vector: list[float], 
                     limit: int = 10, filter: dict = None) -> list[dict]:
        """语义检索"""
        response = self.client.query_points(
            collection_name=collection,
            query=vector,
            query_filter=filter,
            limit=limit
        )
        return [{"id": str(p.id), "score": p.score, "payload": p.payload} for p in response.points]
    
    async def upsert(self, collection: str, points: list[dict]):
        """插入/更新向量"""
        self.client.upsert(
            collection_name=collection,
            points=[PointStruct(**p) for p in points]
        )
```

### 3.5 PostgreSQL Tool

```python
import asyncpg

class PostgresTool:
    """PostgreSQL 查询"""
    
    def __init__(self):
        self.pool = None
    
    async def connect(self):
        self.pool = await asyncpg.create_pool(
            "postgresql://postgres:postgres@postgres:5432/ai"
        )
    
    async def query(self, sql: str, *args) -> list[dict]:
        """查询"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
            return [dict(r) for r in rows]
    
    async def execute(self, sql: str, *args):
        """执行"""
        async with self.pool.acquire() as conn:
            await conn.execute(sql, *args)
```

### 3.6 MinIO Tool

```python
from minio import Minio

class MinIOTool:
    """MinIO 文件操作"""
    
    def __init__(self):
        self.client = Minio(
            "minio:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            secure=False
        )
    
    async def upload(self, bucket: str, key: str, data: bytes):
        """上传文件"""
        from io import BytesIO
        self.client.put_object(bucket, key, BytesIO(data), len(data))
    
    async def download(self, bucket: str, key: str) -> bytes:
        """下载文件"""
        response = self.client.get_object(bucket, key)
        return response.read()
    
    async def list_objects(self, bucket: str, prefix: str) -> list[str]:
        """列出对象"""
        objects = self.client.list_objects(bucket, prefix=prefix, recursive=True)
        return [obj.object_name for obj in objects]
```

### 3.7 Docling Tool

```python
class DoclingTool:
    """Docling 文档解析"""
    
    def __init__(self):
        self.base_url = "http://docling:5001"
    
    async def parse(self, file_url: str) -> dict:
        """解析文档"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v1/parse",
                json={"url": file_url},
                timeout=300.0
            )
            return response.json()
```

### 3.8 FinancialData Tool

**定位**：纯 SDK 封装，不包含业务逻辑。市场路由和数据聚合在 Skill 层处理。

**依赖**：`akshare>=1.14.0`（A 股/港股）、`yfinance>=0.2.40`（美股）

```python
import asyncio
from datetime import datetime, timezone

class FinancialDataTool:
    """金融数据基础设施 Tool -- 纯 SDK 封装"""
    
    def __init__(self):
        self.timeout = settings.FINANCIAL_DATA_TIMEOUT  # 默认 30s
    
    async def get_cn_stock_quote(self, symbol: str) -> dict:
        """调用 AKShare 获取 A 股实时行情
        返回: {symbol, name, price, change, change_pct, volume, amount, source, updated_at}
        SDK: akshare.stock_zh_a_spot_em()
        """
    
    async def get_hk_stock_quote(self, symbol: str) -> dict:
        """调用 AKShare 获取港股实时行情
        SDK: akshare.stock_hk_spot_em()
        """
    
    async def get_us_stock_quote(self, symbol: str) -> dict:
        """调用 yfinance 获取美股实时行情
        SDK: yfinance.Ticker(symbol).fast_info
        """
    
    async def get_forex_rate(self, base: str, target: str) -> dict:
        """调用 AKShare 获取汇率（数据源: 国家外汇管理局 safe）
        返回: {base_currency, target_currency, rate, inverse_rate, source, updated_at}
        SDK: akshare.currency_boc_safe()
        """
```

**设计要点**：
- 同步 SDK 用 `asyncio.to_thread()` 包装，避免阻塞事件循环
- SDK import 失败时返回 `{"error": "..."}`，不抛异常
- 每个方法返回原始 dict，不做市场路由/数据聚合（业务逻辑在 Skill 层）

### 3.9 Obsidian Tool

```python
import httpx
from config.settings import settings

class ObsidianTool:
    """通过 MCP (Local REST API) 访问 Obsidian Vault"""
    
    def __init__(self):
        self.base_url = settings.OBSIDIAN_URL  # https://host.docker.internal:27124
        self.headers = {
            "Authorization": settings.OBSIDIAN_API_KEY,
            "Content-Type": "application/json"
        }
    
    async def get_note(self, path: str) -> str:
        """读取笔记内容"""
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/note",
                params={"path": path},
                headers=self.headers,
                timeout=10.0
            )
            return response.json()["content"]
    
    async def write_note(self, path: str, content: str, metadata: dict = None) -> bool:
        """写入/创建笔记（支持 frontmatter）"""
        body = {"path": path, "content": content}
        if metadata:
            body["metadata"] = metadata
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.put(
                f"{self.base_url}/api/v1/note",
                json=body,
                headers=self.headers,
                timeout=10.0
            )
            return response.status_code == 200
    
    async def search_notes(self, query: str, limit: int = 10) -> list[dict]:
        """搜索笔记"""
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/search",
                params={"query": query, "limit": limit},
                headers=self.headers,
                timeout=10.0
            )
            return response.json()
    
    async def list_notes(self, path: str = "") -> list[str]:
        """列出指定目录下的笔记"""
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(
                f"{self.base_url}/api/v1/note/list",
                params={"path": path},
                headers=self.headers,
                timeout=10.0
            )
            return response.json().get("files", [])
    
    async def manage_tags(self, path: str, tags: list[str]) -> bool:
        """管理笔记标签"""
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.patch(
                f"{self.base_url}/api/v1/note/tags",
                json={"path": path, "tags": tags},
                headers=self.headers,
                timeout=10.0
            )
            return response.status_code == 200
```

---

## 四、Tool 设计原则

| 原则 | 说明 |
|------|------|
| 只访问基础设施 | 不包含业务逻辑 |
| 统一接口 | 同类操作接口一致 |
| 错误处理 | 统一异常捕获，返回有意义的错误信息 |
| 可测试 | 可 Mock 外部服务进行单元测试 |
| 配置驱动 | 连接信息从 settings 加载 |