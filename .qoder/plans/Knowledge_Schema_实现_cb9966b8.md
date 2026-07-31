# Knowledge Schema + Knowledge Organization Agent 实现计划

## 概述

在现有 `langgraph/agent/` 架构内新增 `knowledge_agent/` 子包，实现设计文档 30 定义的完整知识提取流水线。复用现有 `postgres_tool`、`qdrant_tool`、`embedding_tool`、`llm_tool` 单例，遵循项目既有模式（模块级单例、policies.yaml 策略、prompt loader、worker handler 注册）。

---

## 一、PostgreSQL Knowledge Schema

**新建文件:** `/mnt/e/ai-platform/postgres/init/06-knowledge-schema.sql`

### 变更内容
- 启用 `pg_trgm` 扩展（用于实体名模糊匹配）
- 创建 `knowledge` schema（逻辑隔离，不影响 public 表）
- 5 张核心表 + 2 张分类枚举表：

| 表名 | 说明 | 关键索引 |
|------|------|----------|
| `knowledge.entities` | 实体节点 | HNSW(embedding), GIN(name gin_trgm_ops), entity_type |
| `knowledge.relations` | 实体关系 | (source_entity, target_entity), relation_type |
| `knowledge.facts` | 结构化事实 | subject_entity, predicate, (time_start, time_end) |
| `knowledge.documents` | 来源文档 | document_type, hash |
| `knowledge.evidence` | 证据链 | fact_id, document_id |
| `knowledge.entity_types` | 实体类型枚举 | name UNIQUE |
| `knowledge.relation_types` | 关系类型枚举 | name UNIQUE |

### 性能设计
- entities.embedding 使用 HNSW 索引 (`m=16, ef_construction=64`) 加速实体消歧
- `gin_trgm_ops` 支持模糊名称匹配
- relations 复合索引 `(source_entity, target_entity)` 加速图遍历
- 预置 entity_types (Company/Person/Product/Technology/Industry/Country/Organization/Event/Metric/Concept)
- 预置 relation_types (owns/supplies/competes_with/uses/located_in/invests_in/depends_on/causes/impacts)

### 依赖
- 无前置依赖，可独立执行

---

## 二、Qdrant Knowledge Collections

**修改文件:** `/mnt/e/ai-platform/qdrant/init_qdrant.py`

### 变更内容
在 `COLLECTIONS` 列表追加 2 个集合：

```python
{"name": "knowledge_entities", "vector_size": 2560, "distance": Distance.COSINE, "domain": "knowledge"}
{"name": "knowledge_facts", "vector_size": 2560, "distance": Distance.COSINE, "domain": "knowledge"}
```

**修改文件:** `/mnt/e/ai-platform/postgres/init/01-init.sql`（collections 预置记录追加）

```sql
INSERT INTO collections (name, description, vector_size, distance, domain) VALUES
    ('knowledge_entities', '知识实体描述向量', 2560, 'Cosine', 'knowledge'),
    ('knowledge_facts', '知识事实描述向量', 2560, 'Cosine', 'knowledge')
ON CONFLICT (name) DO NOTHING;
```

### 依赖
- 无前置依赖

---

## 三、Knowledge Agent 代码结构

**新建目录:** `/mnt/e/ai-platform/langgraph/agent/knowledge_agent/`

```
knowledge_agent/
├── __init__.py
├── graph.py              # LangGraph StateGraph 定义
├── state.py              # KnowledgeState TypedDict
├── nodes/
│   ├── __init__.py
│   ├── parser.py         # Node 1: 文档解析/分片
│   ├── entity.py         # Node 2: 实体提取
│   ├── relation.py       # Node 3: 关系提取
│   ├── fact.py           # Node 4: 事实提取
│   ├── validator.py      # Node 5: 知识校验（去重/冲突）
│   └── merger.py         # Node 6: 知识合并 + 存储
└── storage/
    ├── __init__.py
    ├── postgres.py       # 批量 PG 写入 + 图查询
    └── qdrant.py         # 批量向量索引 + 语义检索
```

### 依赖
- Step 1 (PG Schema) 和 Step 2 (Qdrant Collections) 完成后才能运行

---

## 四、KnowledgeState 定义

**新建文件:** `/mnt/e/ai-platform/langgraph/agent/knowledge_agent/state.py`

```python
class KnowledgeState(TypedDict):
    # 输入
    document_id: str
    document_type: str
    raw_text: str
    source_metadata: dict
    # 分片
    chunks: list[dict]
    # 提取结果
    entities: list[dict]
    relations: list[dict]
    facts: list[dict]
    evidence: list[dict]
    # 校验
    conflicts: list[dict]
    confidence_score: float
    # 存储追踪
    stored_entity_ids: list[str]
    stored_fact_ids: list[str]
    # 控制
    errors: list[str]
```

注意：**不含** `messages` 字段（非对话型 Agent，是处理流水线）。

---

## 五、Storage Layer（批量优化）

### 5.1 PostgreSQL Storage

**新建文件:** `/mnt/e/ai-platform/langgraph/agent/knowledge_agent/storage/postgres.py`

核心方法（复用 `tools.postgres.postgres_tool` 单例）：

| 方法 | 说明 | 性能设计 |
|------|------|----------|
| `bulk_upsert_entities()` | 批量写入实体 | `execute_many` 单次网络往返，ON CONFLICT 合并 aliases/properties |
| `bulk_insert_relations()` | 批量写入关系 | `execute_many` |
| `bulk_insert_facts()` | 批量写入事实+证据 | `execute_many`，事务包裹 |
| `search_entity_by_embedding()` | 向量相似搜索（实体消歧） | HNSW 索引，threshold=0.85 |
| `find_entity_by_name()` | 精确/模糊名称查找 | `gin_trgm_ops` + `similarity()` |
| `get_entity_neighbors()` | 图遍历（递归 CTE） | depth 限制 ≤ 2，`statement_timeout` |

### 5.2 Qdrant Storage

**新建文件:** `/mnt/e/ai-platform/langgraph/agent/knowledge_agent/storage/qdrant.py`

核心方法（复用 `tools.qdrant.qdrant_tool` + `tools.embedding.embedding_tool`）：

| 方法 | 说明 | 性能设计 |
|------|------|----------|
| `index_entities()` | 批量 embed + upsert 实体描述 | 复用 embedding_tool semaphore，upsert batch=200 |
| `index_facts()` | 批量 embed + upsert 事实描述 | 同上 |
| `hybrid_search()` | 向量检索 + entity_id 过滤 | Qdrant Filter + MatchAny |

### 依赖
- Step 1, 2 完成

---

## 六、Agent Nodes 实现

### 通用模式
- 每个 Node = `async def node_name(state: KnowledgeState) -> dict`（返回 partial state 更新）
- LLM 调用通过 `tools.llm.llm_tool.chat()`
- Prompt 通过 `prompts.loader.load_prompt("knowledge/xxx")`
- 并发提取使用 `asyncio.Semaphore(4)` + `asyncio.gather`（尊重 LLM 30 req/min 限制）

### 6.1 parser.py
- 输入: `raw_text`
- 输出: `chunks` (复用 `tools.chunker.chunk_markdown`)
- 大文档保护: `max_chunks_per_document` 策略限制

### 6.2 entity.py
- 并发从每个 chunk 提取实体（Semaphore(4)）
- 内存去重 by `(name.lower(), entity_type)`
- 输出: `entities` list

### 6.3 relation.py
- 输入: entities + chunks
- LLM 提取实体间关系
- 输出: `relations` list

### 6.4 fact.py
- 提取结构化事实 (subject/predicate/object/time)
- 金融文档额外提取数值指标
- 输出: `facts` + `evidence`

### 6.5 validator.py
- 实体消歧: 对每个提取的实体，调用 `search_entity_by_embedding()` 查找已有实体
- 冲突检测: 同 subject+predicate 但不同 value → 记录 conflicts
- 输出: 更新 entities（合并已有 ID）、conflicts

### 6.6 merger.py
- 合并重复实体（更新 aliases, source_count+1）
- 合并关系（已有相同 source-target-type → 更新 confidence）
- 调用 storage 层批量写入
- 调用 qdrant storage 索引向量
- 输出: `stored_entity_ids`, `stored_fact_ids`

### 依赖
- Step 4 (State), Step 5 (Storage) 完成

---

## 七、Graph 定义

**新建文件:** `/mnt/e/ai-platform/langgraph/agent/knowledge_agent/graph.py`

```python
def build_knowledge_organization_graph():
    graph = StateGraph(KnowledgeState)
    graph.add_node("parser", document_parser)
    graph.add_node("entity_extractor", entity_extractor)
    graph.add_node("relation_extractor", relation_extractor)
    graph.add_node("fact_extractor", fact_extractor)
    graph.add_node("validator", knowledge_validator)
    graph.add_node("merger", knowledge_merger)

    graph.add_edge(START, "parser")
    graph.add_edge("parser", "entity_extractor")
    graph.add_edge("entity_extractor", "relation_extractor")
    graph.add_edge("relation_extractor", "fact_extractor")
    graph.add_edge("fact_extractor", "validator")
    graph.add_edge("validator", "merger")
    graph.add_edge("merger", END)
    return graph.compile()
```

### 依赖
- Step 6 (Nodes) 完成

---

## 八、Prompt Templates

**新建文件（4个）:**
- `/mnt/e/ai-platform/langgraph/agent/prompts/knowledge/entity_extraction.md`
- `/mnt/e/ai-platform/langgraph/agent/prompts/knowledge/relation_extraction.md`
- `/mnt/e/ai-platform/langgraph/agent/prompts/knowledge/fact_extraction.md`
- `/mnt/e/ai-platform/langgraph/agent/prompts/knowledge/validation.md`

遵循现有 prompt loader 模式（`load_prompt("knowledge/entity_extraction")`），输出格式要求 JSON。

### 依赖
- 无前置依赖，可与 Step 3-6 并行

---

## 九、Worker 集成

**修改文件:** `/mnt/e/ai-platform/langgraph/agent/scheduler/worker.py`

追加 handler 注册：

```python
async def _handle_knowledge_extraction(task: dict) -> None:
    """处理 knowledge_extraction 类型任务"""
    from knowledge_agent.graph import build_knowledge_organization_graph
    # 从 params 获取 document_ids，逐个执行 graph
    ...

register_handler("knowledge_extraction", _handle_knowledge_extraction)
```

### 依赖
- Step 7 (Graph) 完成

---

## 十、Hybrid Retrieval API

**修改文件:** `/mnt/e/ai-platform/langgraph/agent/api/knowledge.py`

在现有 `/api/knowledge/collections` 基础上追加：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/knowledge/entities` | GET | 查询实体（by name/type） |
| `/api/knowledge/entities/{id}/neighbors` | GET | 图遍历（depth≤2） |
| `/api/knowledge/facts` | GET | 查询事实（by subject/predicate） |
| `/api/knowledge/search` | POST | Hybrid 检索（图查询 + 向量检索 + RRF 合并） |
| `/api/knowledge/extract` | POST | 触发知识提取任务（创建 task → worker 处理） |

### 依赖
- Step 5 (Storage), Step 7 (Graph) 完成

---

## 十一、配置与策略扩展

**修改文件:** `/mnt/e/ai-platform/langgraph/agent/config/policies.yaml`

追加 `knowledge` 策略块：

```yaml
knowledge:
  extraction:
    max_concurrent_llm: 4
    chunk_max_chars: 3000
    max_chunks_per_document: 200
    entity_similarity_threshold: 0.85
  storage:
    entity_batch_size: 50
    relation_batch_size: 100
    fact_batch_size: 100
    qdrant_upsert_batch: 200
  retrieval:
    graph_max_depth: 2
    vector_limit: 10
    hybrid_merge_strategy: "rrf"
```

### 依赖
- 无前置依赖

---

## 十二、PostgreSQL 连接池调优（可选）

**修改文件:** `/mnt/e/ai-platform/langgraph/agent/tools/postgres.py`

```python
self.pool = await asyncpg.create_pool(dsn, min_size=5, max_size=20, command_timeout=60)
```

**修改文件:** `/mnt/e/ai-platform/postgres/compose.yml`

```yaml
- "-c"
- "max_connections=80"   # 从 50 提升到 80
```

> 注意：此为可选优化，初始实现可暂不修改，待负载验证后再调整。

---

## 执行顺序与依赖图

```
Step 1 (PG Schema) ─────────┐
Step 2 (Qdrant Collections) ─┼──▶ Step 5 (Storage Layer) ──┐
Step 4 (State) ──────────────┘                              │
Step 8 (Prompts) ─────────────────▶ Step 6 (Nodes) ────────┼──▶ Step 7 (Graph) ──▶ Step 9 (Worker)
Step 11 (Policies) ────────────────────────────────────────┘         │
                                                                      ▼
                                                              Step 10 (API)
Step 12 (Pool Tuning) ── 可选，独立
```

**关键路径:** Step 1 → Step 5 → Step 6 → Step 7 → Step 9

**可并行:** Step 1, 2, 4, 8, 11 可同时开始

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| PG max_connections=50 不够用 | 连接拒绝 | Step 12 可选提升到 80；asyncpg pool max_size=20 |
| LLM 30 req/min 限制 | 提取超时 | Semaphore(4) 限流 + 每 chunk 截断 3000 chars |
| 大文档 chunk 爆炸 (500页PDF) | OOM | `max_chunks_per_document=200` 策略 + 分波处理 |
| Qdrant 4G 内存压力 | OOM Kill | 新集合独立 indexing_threshold；监控 points_count |
| 图遍历深度爆炸 | 查询超时 | 硬限 depth≤2 + statement_timeout |
| 实体消歧 N+1 查询 | 慢 | 批量 `ANY($1)` 数组查询；LRU 缓存热点实体 |

---

## 被拒绝的替代方案

| 方案 | 拒绝原因 |
|------|----------|
| 在 public schema 建表 | 知识图谱表与现有文档管理表耦合，不利于未来独立分区/迁移 |
| 使用 Neo4j 做图存储 | 引入新基础设施，运维成本高；当前规模下 recursive CTE 足够 |
| 每个 Node 独立微服务 | 过度设计；当前单进程 LangGraph 已满足吞吐需求 |
| 同步逐条 INSERT | 性能差（N 次网络往返）；`execute_many` 批量写入更优 |
| 复用 AgentState (含 messages) | Knowledge Agent 是处理流水线非对话，messages 字段无意义且增加 checkpoint 开销 |

---

## 代码规范

- 遵循现有模式：模块级单例、`logging.getLogger(__name__)`、async/await
- Import 路径基于 `langgraph/agent/` 为根（如 `from tools.postgres import postgres_tool`）
- Prompt 文件使用 Markdown 格式，JSON 输出要求写在 prompt 中
- 所有新表使用 `gen_random_uuid()` 主键、`TIMESTAMPTZ DEFAULT NOW()` 时间戳
- 批量操作使用 `postgres_tool.execute_many()`
- Qdrant 操作使用 `asyncio.to_thread` 包装（已由 qdrant_tool 封装）
