# 32 - Knowledge Organization Agent 三层接口规范

## 定位

设计 Knowledge Organization Agent 的三层接口规范：

| 层 | 职责 |
|----|------|
| PostgreSQL Schema | 结构化知识层 |
| Qdrant Collection Schema | 语义知识层 |
| MCP Tool API | Agent 访问层 |

**目标**：让采集系统、Knowledge Organization Agent、Research Agent、Report Agent 都通过统一知识接口工作。

## 整体架构

```
                    Data Sources
                         |
                         v
              Document Processing Layer
              (OCR / Docling / Crawl4AI)
                         |
                         v
              Knowledge Organization Agent
                         |
        ┌────────────────┴────────────────┐
        v                                 v
   PostgreSQL                         Qdrant
   Knowledge Graph                    Semantic Memory
   ┌──────────────┐                   ┌──────────────────┐
   │ Entity       │                   │ Chunk            │
   │ Relation     │                   │ Fact             │
   │ Fact         │                   │ Summary          │
   │ Event        │                   │ Entity Desc      │
   └──────────────┘                   └──────────────────┘
        └────────────────┬────────────────┘
                         v
                  MCP Knowledge Server
                         |
        ┌────────────────┼────────────────┐
        v                v                v
  Research Agent   Analyst Agent   Report Agent
```

---

## 一、PostgreSQL Knowledge Schema

### 设计原则

PostgreSQL 负责：

- 精确查询
- 关系推理
- 时间分析
- 知识版本
- 可信度管理

**不负责**：大规模文本搜索

### 1. Schema 划分

```sql
CREATE SCHEMA knowledge;
CREATE SCHEMA document;
CREATE SCHEMA audit;
CREATE SCHEMA taxonomy;
```

结构：

```
knowledge
├── entities
├── relations
├── facts
├── events
├── metrics
└── claims

document
├── documents
├── chunks
└── sources

audit
├── versions
├── changes
└── conflicts

taxonomy
├── entity_types
└── relation_types
```

---

## 二、Entity Schema

### entities

```sql
CREATE TABLE knowledge.entities (
    id              UUID PRIMARY KEY,

    canonical_name  TEXT NOT NULL,

    entity_type     TEXT NOT NULL,

    description     TEXT,

    properties      JSONB DEFAULT '{}',

    status          TEXT DEFAULT 'active',

    confidence      FLOAT DEFAULT 1,

    created_at      TIMESTAMP DEFAULT now(),

    updated_at      TIMESTAMP DEFAULT now()
);
```

示例：

```json
{
  "id": "uuid",
  "canonical_name": "NVIDIA",
  "entity_type": "Company",
  "properties": {
    "ticker": "NVDA",
    "market": "NASDAQ"
  }
}
```

### Entity Alias

解决 `英伟达` / `Nvidia` / `NVIDIA Corp` / `NVDA` 统一问题。

```sql
CREATE TABLE knowledge.entity_aliases (
    id          UUID PRIMARY KEY,
    entity_id   UUID REFERENCES knowledge.entities(id),
    alias       TEXT,
    language    TEXT,
    confidence  FLOAT
);
```

---

## 三、Relation Schema

### relations

```sql
CREATE TABLE knowledge.relations (
    id              UUID PRIMARY KEY,

    source_entity   UUID,

    target_entity   UUID,

    relation_type   TEXT,

    properties      JSONB,

    confidence      FLOAT,

    valid_from      DATE,

    valid_to        DATE,

    status          TEXT,

    created_at      TIMESTAMP DEFAULT now()
);
```

示例：

```json
{
  "source": "NVIDIA",
  "relation": "depends_on",
  "target": "TSMC",
  "confidence": 0.93
}
```

### Relation Type

- `supplier`
- `customer`
- `competitor`
- `depends_on`
- `owns`
- `uses`
- `invests_in`
- `located_in`
- `impacts`
- `causes`

---

## 四、Fact Schema

研究系统核心。

```sql
CREATE TABLE knowledge.facts (
    id                  UUID PRIMARY KEY,

    subject_entity      UUID,

    predicate           TEXT,

    object_value        JSONB,

    time_start          DATE,

    time_end            DATE,

    source_id           UUID,

    confidence          FLOAT,

    verification_status TEXT,

    lifecycle_status    TEXT,

    created_at          TIMESTAMP DEFAULT now()
);
```

示例：

```json
{
  "subject": "NVIDIA",
  "predicate": "Data Center Revenue Growth",
  "object": {
    "value": 56,
    "unit": "%"
  },
  "time": "2026Q2",
  "confidence": 0.96
}
```

---

## 五、Event Schema

用于宏观研究。

```sql
CREATE TABLE knowledge.events (
    id          UUID PRIMARY KEY,

    event_type  TEXT,

    title       TEXT,

    description TEXT,

    event_date  DATE,

    impact      JSONB,

    confidence  FLOAT
);
```

示例：

```json
{
  "title": "US AI Chip Export Restriction",
  "impact": {
    "NVIDIA": "negative"
  }
}
```

---

## 六、Document Schema

```sql
CREATE TABLE document.documents (
    id              UUID PRIMARY KEY,

    title           TEXT,

    document_type   TEXT,

    source          TEXT,

    url             TEXT,

    file_path       TEXT,

    hash            TEXT,

    publish_time    TIMESTAMP,

    metadata        JSONB
);
```

文档类型：

- `Financial_Report`
- `News`
- `Research_Report`
- `Announcement`
- `Policy`
- `Paper`

---

## 七、Chunk Schema

与 Qdrant 对应。

```sql
CREATE TABLE document.chunks (
    id          UUID PRIMARY KEY,

    document_id UUID,

    content     TEXT,

    chunk_index INT,

    metadata    JSONB
);
```

---

## 八、Knowledge Version Schema

金融知识必须可追溯。

```sql
CREATE TABLE audit.versions (
    id          UUID PRIMARY KEY,

    object_type TEXT,

    object_id   UUID,

    version     INT,

    snapshot    JSONB,

    created_by  TEXT,

    created_at  TIMESTAMP DEFAULT now()
);
```

示例：

```
NVIDIA supply status
  v1: Shortage
  v2: Improving
  v3: Normalizing
```

---

## 九、Qdrant Collection 设计

### Embedding 配置

| 项目 | 值 |
|------|-----|
| 模型 | Qwen3-Embedding-4B |
| 维度 | 2560 |
| 距离 | Cosine |

### Collection 拆分

不要一个 Collection，拆分为：

| Collection | 用途 |
|------------|------|
| `knowledge_chunks` | 原始语义 |
| `knowledge_facts` | 事实 |
| `knowledge_entities` | 实体描述 |
| `knowledge_reports` | 历史报告 |

### 1. knowledge_chunks

保存原始语义。

Payload：

```json
{
  "id": "chunk_uuid",
  "type": "document_chunk",
  "text": "NVIDIA revenue increased...",
  "document_id": "xxx",
  "entities": ["NVIDIA", "AI GPU"],
  "date": "2026-07-01",
  "source": "NVIDIA Report"
}
```

Vector：

```json
{
  "size": 2560,
  "distance": "Cosine"
}
```

### 2. knowledge_facts

保存事实，支持查询如「NVIDIA 最近增长数据」直接命中。

Payload：

```json
{
  "type": "fact",
  "subject": "NVIDIA",
  "predicate": "Revenue Growth",
  "value": "56%",
  "time": "2026Q2",
  "confidence": 0.95
}
```

### 3. knowledge_entities

保存实体描述。

Payload：

```json
{
  "type": "entity",
  "name": "TSMC",
  "entity_type": "Company",
  "description": "Taiwan Semiconductor Manufacturing Company"
}
```

### 4. knowledge_reports

保存历史报告（如 `NVIDIA Investment Report 2026`），方便报告迭代。

---

## 十、MCP Knowledge Server 设计

### 原则

> Agent 不能直接访问数据库。

架构：

```
Agent → MCP → Knowledge Service → PostgreSQL / Qdrant
```

### MCP Tools 分类

#### Entity Tools

**1. search_entity**

用途：找实体。

```json
// Input
{"name": "NVIDIA"}

// Output
{"id": "xxx", "type": "Company", "description": "..."}
```

**2. get_entity_graph**

查询关系图谱。

```json
// Input
{"entity": "NVIDIA", "depth": 2}

// Output
{
  "nodes": ["NVIDIA", "TSMC", "SK Hynix"],
  "edges": ["supplier"]
}
```

#### Fact Tools

**3. search_facts**

```json
// Input
{"entity": "NVIDIA", "topic": "growth", "time_range": "2025-2026"}

// Output
[
  {
    "fact": "Data center revenue grew 56%",
    "source": "NVIDIA Q2 Report",
    "confidence": 0.96
  }
]
```

**4. get_timeline**

用于事件分析。

```json
// Input
{"entity": "NVIDIA"}

// Output
[{"date": "2026-01", "event": "Blackwell launch"}]
```

#### Semantic Tools

**5. semantic_search**

调用 Qdrant。

```json
// Input
{"query": "AI semiconductor supply chain risk", "top_k": 10}

// Output
[{"text": "...", "score": 0.91}]
```

#### Knowledge Update Tools

**6. create_fact**

Knowledge Agent 使用。

```json
// Input
{"subject": "NVIDIA", "predicate": "Revenue", "value": "56%"}
```

**7. update_knowledge**

更新版本。

```json
// Input
{"id": "fact_id", "new_value": "..."}
```

---

## 十一、MCP Tool 完整列表

第一版建议：

```yaml
knowledge_tools:
  # Entity
  - search_entity
  - get_entity
  - get_entity_graph

  # Relation
  - find_relationships

  # Fact
  - search_facts
  - get_fact_history

  # Event
  - get_timeline

  # Semantic
  - semantic_search
  - similar_documents

  # Write
  - create_entity
  - create_fact
  - create_relation
  - update_knowledge

  # Analysis
  - get_company_profile
  - get_supply_chain
  - get_risk_factors
```

---

## 十二、Research Agent 调用示例

用户：「分析 NVIDIA 未来风险」

### Research Agent 调用链

```
search_entity
    ↓
get_supply_chain
    ↓
search_facts
    ↓
get_timeline
    ↓
semantic_search
```

### 获取结果

```
Entity:     NVIDIA
Supply:     TSMC, HBM
Facts:      Revenue, Margin
Events:     Export Control
Documents:  Reports
```

### 输出

Report Agent 生成最终投资研究报告。

---

## 十三、与现有项目整合

最终 Docker 服务拓扑：

```
AI Platform
├── postgres
├── qdrant
├── minio
├── docling
├── embedding
├── reranker
├── langgraph
├── mcp-server
├── knowledge-agent
└── report-agent
```
