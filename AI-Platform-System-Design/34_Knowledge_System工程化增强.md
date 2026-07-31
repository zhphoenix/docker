# 34 - Temporal Knowledge Graph + Evidence-driven RAG + Agentic Research System

## 定位

针对知识系统方案的工程化增强版，将系统从「RAG 知识库」升级为：

> **AI 驱动的投资研究知识操作系统（Knowledge Operating System）**

---

## 一、总体架构升级

### 原设计

```
Knowledge Object Model + Knowledge Graph Model + Vector Retrieval Model
```

### 升级为

```
Knowledge Object Model
        +
Temporal Knowledge Graph
        +
Evidence Management
        +
Vector Retrieval
        +
Agent Reasoning Layer
```

### 完整分层

```
                    Knowledge System
                         |
 ┌───────────────────────────────────────────┐
 │  Entity Layer                             │
 │  Relation Layer                           │
 │  Fact Layer                               │
 │  Event Layer                              │
 │  Document Layer                           │
 │  Evidence Layer                           │
 │  Metric Layer                             │
 │  Timeline Layer                           │
 │  Version Layer                            │
 │  Confidence Layer                         │
 └───────────────────────────────────────────┘
                         |
 ┌───────────────────────────────────────────┐
 │              Retrieval Layer              │
 │                                           │
 │  Graph Retrieval       Vector Retrieval   │
 │  (PostgreSQL)          (Qdrant)           │
 └───────────────────────────────────────────┘
                         |
 ┌───────────────────────────────────────────┐
 │              Agent Layer                  │
 │                                           │
 │  Research Agent                           │
 │  Analyst Agent                            │
 │  Report Agent                             │
 └───────────────────────────────────────────┘
```

---

## 二、Knowledge Schema 新增三个核心对象

### 1. Claim（观点/声明）

金融研究大量内容不是事实，而是机构观点、分析师判断、市场预期。

例如：Morgan Stanley — "AI CapEx will remain elevated through 2027"

这不是 Fact，应该是 Claim：

```json
{
  "subject": "AI Infrastructure",
  "claim": "Growth remains strong",
  "author": "Morgan Stanley",
  "confidence": 0.75,
  "source": "Research Report"
}
```

```sql
CREATE TABLE claims (
    id              UUID PRIMARY KEY,
    subject_entity  UUID,
    statement       TEXT,
    claim_type      TEXT,
    author          TEXT,
    source_document UUID,
    confidence      FLOAT,
    created_at      TIMESTAMP
);
```

### 2. Metric（指标）

投资分析大量是指标：Revenue Growth、Gross Margin、CapEx、Market Share、EPS、P/E。不要全部塞 Fact。

```sql
CREATE TABLE metrics (
    id              UUID PRIMARY KEY,
    entity_id       UUID,
    metric_name     TEXT,
    value           NUMERIC,
    unit            TEXT,
    period_start    DATE,
    period_end      DATE,
    source_document UUID
);
```

示例：

```
NVIDIA / Revenue / 46740 / USD Million / 2026Q2
```

### 3. Knowledge Version（知识版本）

市场知识会变化：

- 2025：HBM Supply Constraint
- 2026：HBM Supply Improved

```sql
CREATE TABLE knowledge_versions (
    id                UUID PRIMARY KEY,
    object_type       TEXT,
    object_id         UUID,
    previous_version  UUID,
    change_type       TEXT,
    old_value         JSONB,
    new_value         JSONB,
    reason            TEXT,
    created_at        TIMESTAMP
);
```

---

## 三、Entity Schema 增强

增加 Entity 生命周期：

```yaml
entity_status:
  - discovered
  - verified
  - active
  - merged
  - deprecated
```

例如：`Nvidia Corp` → merge → `NVIDIA`

```sql
ALTER TABLE entities ADD COLUMN status TEXT;
ALTER TABLE entities ADD COLUMN canonical_id UUID;
```

---

## 四、Relation Schema 增强

金融关系必须增加：

### 时间

```
TSMC supplies NVIDIA (valid: 2025-2028)
```

字段：`valid_from`、`valid_to`

### 强度

```json
{"importance": "critical"}
```

等级：`Critical` / `High` / `Medium` / `Low`

---

## 五、Fact Schema 升级

Fact = **Atomic Knowledge Unit**

完整结构：

| 字段 | 说明 |
|------|------|
| Subject | 主体 |
| Predicate | 谓词 |
| Object | 值 |
| Time | 时间 |
| Source | 来源 |
| Evidence | 证据 |
| Confidence | 置信度 |
| Status | 状态 |

示例：

```
NVIDIA / Data Center Revenue Growth / 56% / 2026Q2 / NVIDIA Report / Page 35 / Confidence 0.96
```

新增 `fact_type` 分类：

- `financial_fact`
- `market_fact`
- `technical_fact`
- `macro_fact`

---

## 六、Evidence 系统增强

金融研究最重要的不是「AI 说」，而是「AI 说 + 来源证明」。

```sql
CREATE TABLE evidence (
    id          UUID PRIMARY KEY,
    fact_id     UUID,
    document_id UUID,
    page_number INT,
    section     TEXT,
    quote       TEXT,
    embedding   VECTOR(2560),
    confidence  FLOAT
);
```

效果示例：

```
用户问：为什么认为 NVIDIA 供应链有风险？

Agent 返回：
  理由：HBM supply concentration
  来源：Morgan Stanley Report, Page 23
  原文："..."
```

---

## 七、LangGraph Workflow 升级

完整节点链：

```
Document Analyzer
        |
Chunk Intelligence
        |
Entity Extraction
        |
Entity Resolution
        |
Relation Extraction
        |
Fact Extraction
        |
Claim Extraction
        |
Evidence Linking
        |
Knowledge Validation
        |
Knowledge Conflict Resolver
        |
Knowledge Merge
        |
Storage
```

---

## 八、LangGraph State 升级

生产版：

```python
class KnowledgeState(TypedDict):
    document_id: str

    document_type: str

    source_metadata: dict

    chunks: list

    entities: list

    entity_candidates: list

    relations: list

    facts: list

    claims: list

    metrics: list

    events: list

    evidence: list

    conflicts: list

    validation_results: list

    knowledge_updates: list

    storage_result: dict

    errors: list
```

---

## 九、Knowledge Conflict Agent

金融系统必须有冲突处理。

例如：

- 来源 A：AI Market CAGR 30%
- 来源 B：AI Market CAGR 45%

**不要自动覆盖。**

流程：

```
Fact A + Fact B
      |
Conflict Agent
      |
判断：
  - 时间不同？
  - 定义不同？
  - 来源可信度不同？
      |
保存（两者并存 + 标注冲突）
```

---

## 十、Qdrant Collection 最终设计

5 个 Collection：

| Collection | 用途 |
|------------|------|
| `knowledge_chunks` | 文本知识（PDF / News / Report） |
| `knowledge_facts` | 事实检索 |
| `knowledge_entities` | 实体描述 |
| `knowledge_claims` | 机构观点 |
| `research_reports` | 历史生成报告 |

```
Qdrant
├── knowledge_chunks
├── knowledge_facts
├── knowledge_entities
├── knowledge_claims
└── research_reports
```

---

## 十一、MCP Tool 设计升级

在基础 Tool 之上增加：

### Graph 查询

**get_entity_network()**

```
NVIDIA (depth=2) → TSMC, SK Hynix, Microsoft, OpenAI
```

### 时间查询

**get_timeline()**

### 证据查询

**get_evidence()**

### 投资分析专用

```python
get_company_profile()
get_supply_chain_risk()
get_competitor_analysis()
get_growth_driver()
```

---

## 十二、最终 Research Agent 流程

用户：「分析 NVIDIA 未来风险」

### 自动规划

```
Company Agent
    ↓
Supply Chain Agent
    ↓
Competition Agent
    ↓
Macro Agent
    ↓
Valuation Agent
    ↓
Risk Agent
    ↓
Report Agent
```

### 调用 MCP

```python
get_company_profile()
get_supply_chain_risk()
search_facts()
get_timeline()
semantic_search()
get_evidence()
```

### 生成报告结构

```
NVIDIA Investment Report

 1. Executive Summary
 2. Business Model
 3. Growth Drivers
 4. Supply Chain
 5. Competition
 6. Macro Environment
 7. Risks
 8. Valuation
 9. Conclusion
10. References
```

---

## 十三、与现有 AI Platform 对应

```
                    Data Layer
        (Crawl4AI / AKShare / 财报 / 新闻 / PDF)
                    |
                    ↓
          Knowledge Organization Agent
                    |
        ┌───────────┼───────────┐
        ↓           ↓           ↓
   PostgreSQL    Qdrant      MinIO
   (Entity       (Chunk      (Source
    Relation      Fact        Files)
    Fact          Claim)
    Event
    Metric
    Claim
    Evidence)
        └───────────┼───────────┘
                    ↓
               MCP Server
                    |
                    ↓
       Research Multi-Agent System
                    |
                    ↓
            Investment Report
```

---

## 结论：必须补充项

| 增强项 | 说明 |
|--------|------|
| ✅ Claim | 机构观点 |
| ✅ Metric | 金融指标 |
| ✅ Version | 知识变化 |
| ✅ Conflict Agent | 冲突处理 |
| ✅ Evidence Linking | 证据链 |
| ✅ Temporal Relation | 时间关系 |

补充后系统从 **RAG 知识库** 升级为 **AI 驱动的投资研究知识操作系统**。
