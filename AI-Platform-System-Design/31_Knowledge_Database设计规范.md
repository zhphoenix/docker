# 31 - Knowledge Database 设计规范

## 定位

针对目标链路：

> 全球数据采集 → Knowledge Organization Agent → Knowledge Base → Research Agent → 自动生成投资研究报告

PostgreSQL 不是普通业务数据库，而是：

> **Knowledge Graph + Knowledge Management System（知识管理系统）**

## 核心要求

- 保存实体（Entity）
- 保存关系（Relation）
- 保存事实（Fact）
- 保存来源证据（Evidence）
- 支持版本变化
- 支持知识生命周期
- 支持 AI 置信度
- 支持时间演化（Temporal Knowledge）
- 支持 pgvector 混合检索

---

## 一、总体数据库架构

```
knowledge_db

schemas:
├── core
│   ├── entity
│   ├── relation
│   ├── fact
│   └── event
│
├── document
│   ├── document
│   ├── chunk
│   └── source
│
├── vector
│   └── embedding
│
├── audit
│   ├── version
│   └── change_log
│
└── taxonomy
    ├── entity_type
    ├── relation_type
    └── knowledge_status
```

---

## 二、启用扩展

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

| 扩展 | 用途 |
|------|------|
| pgvector | 向量搜索 |
| pg_trgm | 模糊匹配实体 |
| uuid-ossp | ID 生成 |

---

## 三、Entity（知识实体表）

知识图谱节点。

### 表设计

```sql
CREATE TABLE core.entities (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    name            TEXT NOT NULL,

    entity_type     TEXT NOT NULL,

    description     TEXT,

    aliases         JSONB,

    properties      JSONB,

    canonical_name  TEXT,

    status          TEXT DEFAULT 'active',

    confidence      FLOAT DEFAULT 1.0,

    created_by      TEXT,

    created_at      TIMESTAMP DEFAULT now(),

    updated_at      TIMESTAMP DEFAULT now()
);
```

### 示例

```json
{
  "name": "NVIDIA",
  "entity_type": "Company",
  "properties": {
    "ticker": "NVDA",
    "country": "USA",
    "industry": "Semiconductor"
  }
}
```

---

## 四、Entity 类型表

不要硬编码，建立独立分类表：

```sql
CREATE TABLE taxonomy.entity_types (
    id          UUID PRIMARY KEY,
    name        TEXT UNIQUE,
    description TEXT
);
```

预置数据：

- Company
- Person
- Technology
- Product
- Industry
- Country
- Organization
- Metric
- Event

---

## 五、Entity Alias（实体别名）

解决同一实体多种称呼问题：`NVIDIA` / `Nvidia Corp` / `NVIDIA Corporation` / `英伟达`

```sql
CREATE TABLE core.entity_aliases (
    id          UUID PRIMARY KEY,

    entity_id   UUID REFERENCES core.entities(id),

    alias       TEXT,

    language    TEXT,

    confidence  FLOAT
);
```

索引：

```sql
CREATE INDEX idx_entity_alias ON core.entity_aliases(alias);
```

---

## 六、Relation（关系表）

知识图谱核心。

示例：`TSMC ──supplier──▶ NVIDIA`

```sql
CREATE TABLE core.relations (
    id              UUID PRIMARY KEY,

    source_entity   UUID,

    target_entity   UUID,

    relation_type   TEXT,

    properties      JSONB,

    confidence      FLOAT,

    valid_from      DATE,

    valid_to        DATE,

    status          TEXT DEFAULT 'active',

    created_at      TIMESTAMP DEFAULT now()
);
```

示例：

```json
{
  "source": "TSMC",
  "relation": "supplier",
  "target": "NVIDIA",
  "confidence": 0.92
}
```

---

## 七、Relation Type

```sql
CREATE TABLE taxonomy.relation_types (
    id          UUID PRIMARY KEY,
    name        TEXT UNIQUE,
    description TEXT
);
```

推荐类型：

- `supplier`
- `customer`
- `competitor`
- `owns`
- `uses`
- `depends_on`
- `invests_in`
- `located_in`
- `impacts`
- `causes`

---

## 八、Fact（事实表）

投资分析最重要的数据。不要存「NVIDIA 很好」，要存结构化事实：

```
NVIDIA / Revenue Growth / 56% / 2026Q2
```

### Schema

```sql
CREATE TABLE core.facts (
    id                  UUID PRIMARY KEY,

    subject_entity      UUID,

    predicate           TEXT,

    object_value        JSONB,

    unit                TEXT,

    time_start          DATE,

    time_end            DATE,

    source_document     UUID,

    confidence          FLOAT,

    verification_status TEXT,

    created_at          TIMESTAMP DEFAULT now()
);
```

### 示例

```json
{
  "subject": "NVIDIA",
  "predicate": "Data Center Revenue Growth",
  "value": 56,
  "unit": "%",
  "period": "2026Q2"
}
```

---

## 九、Event（事件）

金融研究必须有时间轴。例如：美联储加息、AI GPU 出口限制、财报发布。

```sql
CREATE TABLE core.events (
    id          UUID PRIMARY KEY,

    event_type  TEXT,

    title       TEXT,

    description TEXT,

    event_date  DATE,

    entities    JSONB,

    impact      JSONB,

    confidence  FLOAT
);
```

示例：

```json
{
  "title": "US restricts AI chip export",
  "impact": {
    "NVIDIA": "negative"
  }
}
```

---

## 十、Document（原始资料）

所有知识必须追溯来源。

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

    metadata        JSONB,

    created_at      TIMESTAMP
);
```

示例：

```json
{
  "title": "NVIDIA Q2 Earnings Report",
  "type": "Financial_Report",
  "source": "NVIDIA IR"
}
```

---

## 十一、Chunk（RAG 切片）

与 Qdrant 对应。

```sql
CREATE TABLE document.chunks (
    id          UUID PRIMARY KEY,

    document_id UUID,

    content     TEXT,

    chunk_index INT,

    metadata    JSONB,

    created_at  TIMESTAMP
);
```

示例：

```
Chunk 001: Data center revenue increased 56%
```

---

## 十二、Embedding（pgvector）

虽然主向量检索使用 Qdrant，PostgreSQL 可保存小规模 embedding（如实体 embedding）：

```sql
CREATE TABLE vector.entity_embeddings (
    entity_id   UUID,
    embedding   vector(2560)
);
```

索引：

```sql
CREATE INDEX entity_embedding_idx
ON vector.entity_embeddings
USING hnsw (embedding vector_cosine_ops);
```

---

## 十三、知识版本管理

AI 知识不是静态的，必须保存历史。

例如：
- 2025：NVIDIA 供应紧张
- 2026：供应改善

### Version Table

```sql
CREATE TABLE audit.knowledge_versions (
    id          UUID PRIMARY KEY,

    object_type TEXT,

    object_id   UUID,

    version     INT,

    content     JSONB,

    created_by  TEXT,

    created_at  TIMESTAMP DEFAULT now()
);
```

示例：

```
Entity: NVIDIA
  version 1: AI GPU shortage
  version 2: Supply improving
```

---

## 十四、Knowledge Lifecycle（知识生命周期）

状态定义：

```yaml
knowledge_status:
  discovered: 新发现
  extracted: AI提取
  validated: 已验证
  trusted: 高可信
  outdated: 过期
  archived: 归档
```

字段：

```sql
ALTER TABLE core.facts ADD COLUMN lifecycle_status TEXT;
```

---

## 十五、知识可信度模型

不要只有单一 confidence，建议多维评分：

```
Confidence Score = Source Reliability × Extraction Confidence × Validation Score
```

字段：

| 字段 | 说明 |
|------|------|
| source_quality | 来源可靠度 |
| extraction_confidence | AI 提取置信度 |
| validation_score | 验证得分 |
| final_confidence | 最终置信度 |

示例（财报）：

```
Source:      0.95
Extraction:  0.92
Validation:  0.90
─────────────────
Final:       0.79
```

---

## 十六、知识冲突管理

金融数据经常冲突，不要覆盖，建立冲突表：

例如：
- 机构 A：2026 AI 市场增长 20%
- 机构 B：增长 35%

```sql
CREATE TABLE core.knowledge_conflicts (
    id              UUID,

    fact_a          UUID,

    fact_b          UUID,

    conflict_type   TEXT,

    resolution      TEXT,

    status          TEXT
);
```

---

## 十七、关键索引设计

### Entity 搜索

```sql
CREATE INDEX idx_entity_name ON core.entities(name);
```

模糊匹配：

```sql
CREATE INDEX idx_entity_trgm
ON core.entities
USING gin(name gin_trgm_ops);
```

### Relation 查询

找 NVIDIA 供应商：

```sql
CREATE INDEX idx_relation_source ON core.relations(source_entity);
```

### Fact 时间查询

```sql
CREATE INDEX idx_fact_time ON core.facts(time_start);
```

---

## 十八、Agent 查询路径设计

不要直接查表，建立 Knowledge API（MCP Tool）：

```python
find_entity()
get_related_entities()
search_facts()
get_timeline()
semantic_search()
```

查询示例：「NVIDIA 供应链风险」

```
Research Agent
    ↓
MCP
    ↓
find_entity("NVIDIA")
    ↓
get_related_entities(relation="supplier")
    ↓
search_facts("risk")
    ↓
Qdrant semantic search
    ↓
Report Agent
```

---

## 十九、最终数据库结构

### PostgreSQL

```
knowledge
├── entities
├── entity_aliases
├── relations
├── facts
├── events
├── documents
├── chunks
├── embeddings
├── knowledge_versions
├── conflicts
└── audit_logs
```

### Qdrant

```
├── document_chunks
├── facts
├── summaries
└── entity_descriptions
```

### MinIO

```
├── pdf
├── html
├── images
└── reports
```

---

## 二十、与现有 AI Platform 的连接

```
              Crawl4AI
                 |
              Docling
                 |
              MinIO
                 |
                 ↓
      Knowledge Organization Agent
                 |
        ┌────────┴────────┐
        ↓                 ↓
   PostgreSQL          Qdrant
   (Entity/Relation    (Vector
    Fact/Event)         Search)
        └────────┬────────┘
                 ↓
            MCP Server
                 |
                 ↓
         Research Agents
                 |
                 ↓
        Investment Report
```

---

## 二十一、实现映射说明

### 规范 → 实际落地映射

本规范定义了 5 个 Schema（core/document/vector/audit/taxonomy），已完整落地：

| 规范 Schema | 实际实现 | 包含表 |
|-------------|----------|--------|
| core | `core` schema | entities, relations, facts, evidence, entity_aliases, events, knowledge_conflicts |
| document | `document` schema | documents, chunks |
| vector | `vector` schema | entity_embeddings |
| audit | `audit` schema | knowledge_versions |
| taxonomy | `taxonomy` schema | entity_types, relation_types, knowledge_statuses |

### 兼容策略

- 原 `knowledge` schema 保留为**视图层**，映射到新 schema
- SELECT 查询可通过 `knowledge.*` 或新 schema 路径访问
- INSERT ... ON CONFLICT 必须直接引用新 schema（视图不支持）
- 应用层 `storage/postgres.py` 已全部改为新 schema 路径

### 部署操作

**全新部署**（volume 为空）：
```bash
docker compose up -d postgres
# init 脚本自动执行（01 → 07）
```

**已有部署**（volume 已存在）：
```bash
python scripts/migrate_knowledge_db.py
```

**验证**：
```bash
python scripts/verify_knowledge_db.py
```

### 回滚方案

```sql
-- 恢复表到 knowledge schema
ALTER TABLE core.entities SET SCHEMA knowledge;
ALTER TABLE core.relations SET SCHEMA knowledge;
ALTER TABLE core.facts SET SCHEMA knowledge;
ALTER TABLE core.evidence SET SCHEMA knowledge;
ALTER TABLE document.documents SET SCHEMA knowledge;
ALTER TABLE taxonomy.entity_types SET SCHEMA knowledge;
ALTER TABLE taxonomy.relation_types SET SCHEMA knowledge;

-- 删除新增对象
DROP VIEW IF EXISTS knowledge.entities CASCADE;
DROP VIEW IF EXISTS knowledge.relations CASCADE;
DROP VIEW IF EXISTS knowledge.facts CASCADE;
DROP VIEW IF EXISTS knowledge.evidence CASCADE;
DROP VIEW IF EXISTS knowledge.documents CASCADE;
DROP VIEW IF EXISTS knowledge.entity_types CASCADE;
DROP VIEW IF EXISTS knowledge.relation_types CASCADE;

DROP TABLE IF EXISTS core.entity_aliases CASCADE;
DROP TABLE IF EXISTS core.events CASCADE;
DROP TABLE IF EXISTS core.knowledge_conflicts CASCADE;
DROP TABLE IF EXISTS document.chunks CASCADE;
DROP TABLE IF EXISTS vector.entity_embeddings CASCADE;
DROP TABLE IF EXISTS audit.knowledge_versions CASCADE;
DROP TABLE IF EXISTS taxonomy.knowledge_statuses CASCADE;

DROP SCHEMA IF EXISTS core, document, vector, audit, taxonomy;
```

### 性能配置

| 参数 | 值 | 用途 |
|------|-----|------|
| shared_buffers | 1GB | 缓存 |
| maintenance_work_mem | 512MB | HNSW 索引构建 |
| work_mem | 64MB | 图遍历 CTE + 排序 |
| max_parallel_workers | 4 | 并行查询 |
| hnsw.ef_search | 100 | 向量搜索精度（会话级） |
| 连接池 | min=5, max=20 | asyncpg pool |
