# 33 - Knowledge Organization Agent 代码架构设计

## 定位

构建生产级知识处理系统，而非简单 RAG Pipeline：

> 自动读取文档 → 理解内容 → 提取知识 → 建立知识关系 → 校验 → 写入 Knowledge Base → 支撑 Research Agent 查询

### 技术栈

- LangGraph
- Qwen3 系列模型（vLLM）
- Qwen3-Embedding-4B
- Qdrant
- PostgreSQL
- MCP
- Docling
- MinIO

---

## 一、整体代码架构

```
ai-platform/
├── agents/
│   └── knowledge_organization/
│       ├── graph.py                 # LangGraph 入口
│       ├── state.py                 # State 定义
│       ├── config.py                # 配置
│       │
│       ├── nodes/                   # Agent 节点
│       │   ├── document_analyzer.py
│       │   ├── chunk_processor.py
│       │   ├── entity_extractor.py
│       │   ├── entity_resolver.py
│       │   ├── relation_extractor.py
│       │   ├── fact_extractor.py
│       │   ├── event_extractor.py
│       │   ├── knowledge_validator.py
│       │   ├── knowledge_merger.py
│       │   └── storage.py
│       │
│       ├── prompts/
│       │   ├── entity_prompt.py
│       │   ├── relation_prompt.py
│       │   ├── fact_prompt.py
│       │   └── validation_prompt.py
│       │
│       ├── tools/
│       │   ├── postgres_tools.py
│       │   ├── qdrant_tools.py
│       │   ├── embedding_tools.py
│       │   └── document_tools.py
│       │
│       ├── schemas/
│       │   ├── entity.py
│       │   ├── relation.py
│       │   └── fact.py
│       │
│       └── tests/
```

---

## 二、LangGraph State 设计

文件：`state.py`

```python
from typing import TypedDict, List, Dict, Any


class KnowledgeState(TypedDict):

    # =====================
    # Document
    # =====================
    document_id: str
    document_type: str
    source_metadata: Dict[str, Any]
    raw_text: str

    # =====================
    # Processing
    # =====================
    chunks: List[Dict]
    current_chunk: int

    # =====================
    # Extracted Knowledge
    # =====================
    entities: List[Dict]
    relations: List[Dict]
    facts: List[Dict]
    events: List[Dict]

    # =====================
    # Existing Knowledge
    # =====================
    matched_entities: List[Dict]
    conflicts: List[Dict]

    # =====================
    # Validation
    # =====================
    confidence_score: float
    validation_report: Dict

    # =====================
    # Storage
    # =====================
    postgres_objects: List[Dict]
    vector_objects: List[Dict]

    # =====================
    # Control
    # =====================
    next_action: str
    errors: List[str]
```

---

## 三、Graph Workflow 设计

核心流程：

```
START
  |
  v
Document Analyzer
  |
  v
Chunk Processor
  |
  v
Entity Extractor
  |
  v
Entity Resolver
  |
  v
Relation Extractor
  |
  v
Fact Extractor
  |
  v
Knowledge Validator
  |
  v
Knowledge Merger
  |
  v
Storage Agent
  |
  v
END
```

---

## 四、graph.py

```python
from langgraph.graph import StateGraph
from .state import KnowledgeState

from .nodes.document_analyzer import document_analyzer
from .nodes.chunk_processor import chunk_processor
from .nodes.entity_extractor import entity_extractor
from .nodes.entity_resolver import entity_resolver
from .nodes.relation_extractor import relation_extractor
from .nodes.fact_extractor import fact_extractor
from .nodes.knowledge_validator import knowledge_validator
from .nodes.storage import storage


def build_graph():
    workflow = StateGraph(KnowledgeState)

    # 注册节点
    workflow.add_node("document_analyzer", document_analyzer)
    workflow.add_node("chunk_processor", chunk_processor)
    workflow.add_node("entity_extractor", entity_extractor)
    workflow.add_node("entity_resolver", entity_resolver)
    workflow.add_node("relation_extractor", relation_extractor)
    workflow.add_node("fact_extractor", fact_extractor)
    workflow.add_node("validator", knowledge_validator)
    workflow.add_node("storage", storage)

    # 入口
    workflow.set_entry_point("document_analyzer")

    # 边
    workflow.add_edge("document_analyzer", "chunk_processor")
    workflow.add_edge("chunk_processor", "entity_extractor")
    workflow.add_edge("entity_extractor", "entity_resolver")
    workflow.add_edge("entity_resolver", "relation_extractor")
    workflow.add_edge("relation_extractor", "fact_extractor")
    workflow.add_edge("fact_extractor", "validator")
    workflow.add_edge("validator", "storage")

    return workflow.compile()
```

---

## 五、Node 设计规范

每个 Node 遵循统一契约：

- **输入**：`KnowledgeState`
- **输出**：`KnowledgeState` 更新字段

### 1. Document Analyzer

文件：`nodes/document_analyzer.py`

作用：判断文档类型、行业、公司、时间。

```python
def document_analyzer(state):
    result = llm.invoke(
        ANALYZE_PROMPT.format(text=state["raw_text"])
    )

    state["document_type"] = result["type"]
    state["source_metadata"] = result

    return state
```

### 2. Entity Extractor

作用：提取实体。

Prompt：

```
You are a Knowledge Graph Entity Extraction Agent.

Extract:
- Company
- Person
- Product
- Technology
- Industry
- Event
- Metric

Return JSON only.
```

代码：

```python
def entity_extractor(state):
    entities = llm.invoke(
        ENTITY_PROMPT.format(text=state["raw_text"])
    )

    state["entities"] = entities

    return state
```

### 3. Entity Resolver

必须调用数据库，流程：

```
Extract Entity → search_entity() → Similarity → merge / create
```

代码：

```python
def entity_resolver(state):
    for entity in state["entities"]:
        result = search_entity(entity["name"])
        state["matched_entities"].append(result)

    return state
```

---

## 六、Tools 设计

### PostgreSQL Tool

文件：`tools/postgres_tools.py`

**search_entity**

```python
from langchain.tools import tool


@tool
def search_entity(name: str):
    """Search existing entity"""
    return db.query(
        """
        SELECT * FROM knowledge.entities
        WHERE canonical_name = %s
        """,
        name
    )
```

**create_fact**

```python
@tool
def create_fact(fact: dict):
    """Store knowledge fact"""
    db.insert("knowledge.facts", fact)
```

---

## 七、Router（条件路由）

不同文档走不同流程：

| 文档类型 | 侧重 |
|----------|------|
| 财报 | Metric / Fact / Financial |
| 新闻 | Event / Relation / Impact |

Graph 增加条件分支：

```
Document Analyzer
        |
      Router
      /    \
     v      v
Financial  News
Pipeline   Pipeline
```

代码：

```python
def document_router(state):
    if state["document_type"] == "Financial_Report":
        return "financial"
    return "general"
```

---

## 八、Reflection Agent

提高准确率，流程：

```
Extraction → Critic Agent → Correction → Storage
```

Critic 检查项：

- 是否真实存在
- 是否有来源
- 是否重复
- 是否冲突

---

## 九、Checkpoint 设计

生产环境必须。使用 LangGraph `PostgresSaver` 保存：

- workflow state
- node result
- error
- retry

示例场景：

```
PDF 处理到 Fact Extractor 失败
    → 恢复：从 Fact Extractor 继续
    → 不用重新跑 OCR
```

---

## 十、批处理模式

数据量预估：

- 新闻：每天 5000 篇
- PDF：每天几十份

不能同步运行，增加异步队列：

```
Redis Queue → Knowledge Worker → LangGraph
```

完整结构：

```
Crawler
  ↓
Task Queue
  ↓
Knowledge Agent Worker
  ↓
Knowledge Base
```

---

## 十一、最终生产架构

```
                 Data Pipeline
                      |
                    MinIO
                      |
                  Docling / OCR
                      |
                      v
          Knowledge Organization Agent
        ┌──────────────────────────────┐
        │  Document Analyzer           │
        │  Entity Extractor            │
        │  Relation Extractor          │
        │  Fact Extractor              │
        │  Validator                   │
        │  Merger                      │
        │  Storage                     │
        └──────────────────────────────┘
                      |
            ┌─────────┴─────────┐
            v                   v
       PostgreSQL           Qdrant
            └─────────┬─────────┘
                      v
                 MCP Server
                      |
                      v
           Research Multi-Agent
                      |
                      v
             Research Report
```

---

## 十二、开发顺序建议

不要一次写全部，按 Milestone 推进：

### Milestone 1（基础）

- State
- Graph
- Document Analyzer
- Entity Extractor
- PostgreSQL 写入

### Milestone 2（知识提取）

- Entity Resolution
- Relation Extraction
- Fact Extraction

### Milestone 3（质量保障）

- Validator
- Version
- Conflict Detection

### Milestone 4（系统集成）

- MCP Server
- Research Agent
- Report Agent

---

## 总结

本架构作为 AI Platform 中的 **Knowledge Intelligence Layer**，与已有 RAG、Qdrant、MCP、LangGraph 架构自然融合，无需重新选择技术栈。
