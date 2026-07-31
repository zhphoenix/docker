# 30 - Knowledge Schema 与 Knowledge Organization Agent 设计规范

## 定位

Knowledge Schema + Knowledge Organization Agent 作为整个投研 AI Agent 系统的**核心中间层**：

> 采集全球信息 → 自动组织知识 → Agent 查询 → 生成研究报告

## 设计原则

- **不要**把知识库设计成文档仓库
- **不要**只做向量检索
- **必须**保存 Entity（实体）、Relation（关系）、Fact（事实）、Event（事件）、Source（来源）
- 所有 AI 生成知识**必须可追溯**

---

## 一、Knowledge Schema 总体设计

推荐采用三层模型：

```
Knowledge Object Model
        +
Knowledge Graph Model
        +
Vector Retrieval Model
```

分层结构：

```
                 Knowledge
                    |
        ----------------------------
        |       |       |       |
   Entity   Relation  Fact    Event
   Layer     Layer    Layer   Layer
        |       |       |       |
   Document  Evidence  Metric  Timeline
   Layer     Layer     Layer   Layer
```

---

## 二、核心 Entity Schema（实体）

Entity 是知识系统的节点。

示例实体：`NVIDIA`、`TSMC`、`Blackwell`、`AI GPU`、`美国出口管制`

### 数据库表

```sql
CREATE TABLE entities (
    id              UUID PRIMARY KEY,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL,
    description     TEXT,
    aliases         JSONB,
    properties      JSONB,

    embedding       VECTOR(2560),

    source_count    INT DEFAULT 0,
    confidence      FLOAT,

    created_at      TIMESTAMP,
    updated_at      TIMESTAMP
);
```

### Entity Type 枚举

```yaml
entity_types:
  Company:
    description: 企业
  Person:
    description: 人物
  Product:
    description: 产品
  Technology:
    description: 技术
  Industry:
    description: 行业
  Country:
    description: 国家
  Organization:
    description: 机构
  Event:
    description: 事件
  Metric:
    description: 指标
  Concept:
    description: 概念
```

### 示例

```json
{
  "name": "NVIDIA",
  "type": "Company",
  "properties": {
    "ticker": "NVDA",
    "industry": "Semiconductor",
    "country": "USA"
  }
}
```

---

## 三、Relation Schema（关系）

关系表示实体之间发生什么。

示例：

```
NVIDIA ──supplier──▶ TSMC
```

### 数据库表

```sql
CREATE TABLE relations (
    id              UUID PRIMARY KEY,

    source_entity   UUID,
    target_entity   UUID,

    relation_type   TEXT,

    properties      JSONB,

    confidence      FLOAT,

    source_fact     UUID,

    created_at      TIMESTAMP
);
```

### Relation 类型

```yaml
relation_types:
  owns:
    example: NVIDIA owns Mellanox
  supplies:
    example: TSMC supplies NVIDIA
  competes_with:
    example: NVIDIA competes AMD
  uses:
    example: OpenAI uses NVIDIA GPU
  located_in:
  invests_in:
  depends_on:
  causes:
  impacts:
```

---

## 四、Fact Schema（事实）

投资研究中最重要的部分。不要只存「NVIDIA 很好」，要存**结构化事实**：

| 字段 | 说明 |
|------|------|
| Subject | 主体实体 |
| Predicate | 谓词/指标 |
| Object | 值 |
| Source | 来源 |
| Confidence | 置信度 |
| Time | 时间范围 |

### 数据库表

```sql
CREATE TABLE facts (
    id                  UUID PRIMARY KEY,

    subject_entity      UUID,

    predicate           TEXT,

    object_value        JSONB,

    time_range          JSONB,

    source_document     UUID,

    confidence          FLOAT,

    verification_status TEXT,

    created_at          TIMESTAMP
);
```

### 示例

```json
{
  "subject": "NVIDIA",
  "predicate": "Data Center Revenue Growth",
  "object": {
    "value": "56%",
    "period": "2026Q2"
  },
  "source": "NVIDIA Financial Report",
  "confidence": 0.96
}
```

---

## 五、Document Schema（来源）

所有知识必须能回溯。

```sql
CREATE TABLE documents (
    id              UUID PRIMARY KEY,

    title           TEXT,

    type            TEXT,

    source          TEXT,

    url             TEXT,

    file_path       TEXT,

    publish_date    DATE,

    hash            TEXT,

    metadata        JSONB
);
```

### Document 类型

```yaml
document_types:
  - Financial_Report
  - News
  - Research_Report
  - Announcement
  - Regulatory
  - Academic_Paper
  - Social_Media
```

---

## 六、Evidence Schema（证据链）

金融研究必须有证据链。

例如 AI 生成「AI GPU 需求持续增长」，必须知道来源：Morgan Stanley Report, Page 23。

```sql
CREATE TABLE evidence (
    id              UUID,

    fact_id         UUID,

    document_id     UUID,

    location        TEXT,

    quote           TEXT,

    confidence      FLOAT
);
```

---

## 七、Knowledge Organization Agent 架构

采用 LangGraph 实现。

```
              Input Document
                    |
                    v
         Document Understanding
                    |
                    v
           Entity Extraction
                    |
                    v
         Relation Extraction
                    |
                    v
           Fact Extraction
                    |
                    v
        Knowledge Validation
                    |
                    v
          Knowledge Merge
                    |
                    v
             Storage
```

---

## 八、LangGraph State 设计

```python
class KnowledgeState(TypedDict):
    document_id: str

    raw_content: str

    chunks: list

    entities: list

    relations: list

    facts: list

    evidence: list

    confidence: float

    errors: list
```

---

## 九、Agent Node 设计

### Node 1：Document Parser

- **输入**：PDF / HTML
- **输出**：

```json
{
  "title": "NVIDIA Q2 Report",
  "chunks": ["..."]
}
```

### Node 2：Entity Extractor

- **Prompt**：Extract all important entities. Return: name, type, description.
- **输出**：

```json
[
  {"name": "NVIDIA", "type": "Company"},
  {"name": "Blackwell", "type": "Product"}
]
```

### Node 3：Relation Extractor

- **输入**：Entity 列表 + 文本
- **输出**：

```json
[
  {"source": "NVIDIA", "relation": "uses", "target": "TSMC"}
]
```

### Node 4：Fact Extractor

- **输出**：

```json
[
  {
    "subject": "NVIDIA",
    "predicate": "Revenue Growth",
    "value": "56%",
    "time": "2026Q2"
  }
]
```

### Node 5：Knowledge Validation Agent

检查重复与冲突：

| 场景 | 已有 | 新提取 | 判断 |
|------|------|--------|------|
| 数值冲突 | NVIDIA Revenue Growth 56% | NVIDIA Revenue Growth 55% | 更新？冲突？保留两个？ |

### Node 6：Knowledge Merge Agent

合并示例：

```
已有：TSMC ──supplier──▶ NVIDIA
新增：TSMC manufactures Blackwell

合并后：
TSMC ──supplier──▶ NVIDIA ──product──▶ Blackwell
```

---

## 十、LangGraph Workflow

### 代码结构

```
knowledge_agent/
├── graph.py
├── state.py
├── nodes/
│   ├── parser.py
│   ├── entity.py
│   ├── relation.py
│   ├── fact.py
│   ├── validator.py
│   └── merger.py
└── storage/
    ├── postgres.py
    └── qdrant.py
```

### Graph 定义

```python
workflow.add_node("parser", parser_agent)
workflow.add_node("entity", entity_agent)
workflow.add_node("relation", relation_agent)
workflow.add_node("fact", fact_agent)
workflow.add_node("validate", validation_agent)
workflow.add_node("merge", merge_agent)

workflow.add_edge("parser", "entity")
workflow.add_edge("entity", "relation")
workflow.add_edge("relation", "fact")
workflow.add_edge("fact", "validate")
workflow.add_edge("validate", "merge")
```

---

## 十一、与 Qdrant 的结合

**不要把所有东西放 Qdrant。**

### 存储分工

| 存储 | 内容 |
|------|------|
| **PostgreSQL** | Entity、Relation、Fact、Evidence、Document Metadata |
| **Qdrant** | Document Chunk、Fact Description、Entity Description、Research Summary |

### 查询策略：Hybrid Retrieval

```
1. 先图查询：NVIDIA ──supplier──▶ ?
2. 再向量检索：供应链风险相关文档
3. 合并形成 Hybrid Retrieval
```

---

## 十二、最终 AI Research 查询流程

用户提问：「分析 NVIDIA 未来风险」

### Research Agent 拆解

```
Company Analysis
    + Supply Chain
    + Competition
    + Macro
    + Valuation
```

### 调用 MCP Tools

```python
query_entity("NVIDIA")
query_relation("supplier")
search_fact("risk")
semantic_search("AI GPU competition")
```

### Report Agent 输出结构

```
Executive Summary
Business Model
Growth Drivers
Supply Chain
Competition
Risk
Valuation
Conclusion
References
```
