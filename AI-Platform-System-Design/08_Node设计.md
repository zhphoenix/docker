# Node 设计

## 一、定位

每个 Node 只负责**单一职责**，只修改 State。

---

## 二、Node 列表

| Node | 文件 | 职责 | 调用的 Tool |
|------|------|------|------------|
| Planner | `nodes/planner.py` | 理解问题，生成执行计划（含垂类参数） | LLM |
| QueryRewrite | `nodes/query_rewrite.py` | LLM 驱动查询改写（自然语言 → 专业金融检索词） | LLM |
| Retrieve | `nodes/retrieve.py` | 语义检索（支持权威度/时效/文档类型过滤） | Embedding, Qdrant |
| Rerank | `nodes/rerank.py` | 对检索结果重排序 | Reranker |
| Reason | `nodes/reason.py` | LLM 推理生成回答 | LLM |
| Reflect | `nodes/reflect.py` | 检查答案质量 | LLM |
| Writer | `nodes/writer.py` | 格式化最终输出 | - |
| Finish | `nodes/finish.py` | 结束处理，写入 State | - |

---

## 三、各 Node 详细说明

### 3.1 Planner

**职责**：理解用户问题，生成执行计划。

```python
async def planner(state: AgentState) -> dict:
    """生成执行计划"""
    # 1. 加载 planner prompt
    # 2. 调用 LLM 分析问题
    # 3. 生成计划：需要哪些步骤、用哪些工具
    # 4. 写入 state["plan"]
    return {"plan": plan}
```

**输出**：
```json
{
    "plan": {
        "steps": ["检索年报", "分析财务数据", "行业对比"],
        "tools": ["qdrant", "financial_data"],
        "market": "cn",
        "symbol": "600519",
        "year": 2025,
        "document_type": "annual_report",
        "time_range": {"start_date": "2025-01-01", "end_date": "2025-12-31"},
        "vertical_params": {"indicator": "ROIC", "sector": "科技"},
        "enable_rewrite": true
    }
}
```

### 3.2 QueryRewrite

**职责**：将用户自然语言转化为专业金融检索词，提升检索质量。

**流程位置**：Planner → **QueryRewrite** → Retrieve

**设计合规**：Query 改写是业务逻辑（Prompt 编排 + LLM 调用 + 结果解析），属于 Node 层职责（参见 09_Tool设计.md）。

```python
async def query_rewrite(state: AgentState) -> dict:
    """查询改写节点"""
    # 1. 从 plan 检查是否启用改写（enable_rewrite）
    # 2. 加载 query_rewrite prompt
    # 3. 调用 LLM 将自然语言转化为专业检索词
    # 4. 解析 JSON 输出，提取 rewritten_query / keywords / suggested_filters
    # 5. 更新 plan["rewritten_query"]、plan["keywords"]
    return {"plan": plan, "messages": [...]}
```

**输出**：
```json
{
    "rewritten_query": "贵州茅台 2025 年报 ROIC 护城河分析",
    "keywords": ["ROIC", "护城河", "年报"],
    "suggested_filters": {
        "time_range": {"start_date": "2025-01-01"},
        "document_type": "annual_report",
        "symbol": "600519"
    }
}
```

**容错机制**：LLM 调用失败时，回退到原始 query，不阻断流程。

**Prompt**：`prompts/query_rewrite.md`

### 3.3 Retrieve

**职责**：调用 Embedding 将查询向量化，调用 Qdrant 检索。支持多维过滤和权威度标注。

```python
async def retrieve(state: AgentState) -> dict:
    """语义检索"""
    # 1. 从 plan 提取改写后的查询（rewritten_query），回退到原始 question
    # 2. 调用 Embedding 服务向量化
    # 3. 构建多维过滤条件（symbol/year/document_type/published_date）
    # 4. 调用 Qdrant 检索 Top-K
    # 5. 为每个结果标注权威度（基于 source_provider 映射）
    # 6. 写入 state["documents"]
    return {"documents": documents}
```

**调用链**：
```
Planner.plan + QueryRewrite.rewritten_query → Embedding(:8001) → Qdrant(:6333) → documents（含 authority）
```

**过滤条件**：
- `symbol`：股票代码精确匹配
- `year`：报告年份
- `document_type`：文档类型（annual_report / quarterly_report / announcement）
- `published_date`：天级时效过滤（Range 条件，YYYY-MM-DD 格式）

### 3.4 Rerank

**职责**：对 Retrieve 的结果进行重排序。

```python
async def rerank(state: AgentState) -> dict:
    """重排序"""
    # 1. 获取 state["documents"]
    # 2. 调用 Reranker 服务
    # 3. 按相关性重新排序
    # 4. 更新 state["documents"]
    return {"documents": reranked_docs}
```

**调用链**：
```
documents + question → Reranker(:8002) → 重排序后的 documents
```

### 3.5 Reason

**职责**：LLM 根据检索结果推理生成回答。

```python
async def reason(state: AgentState) -> dict:
    """LLM 推理"""
    # 1. 加载 reason prompt
    # 2. 构建上下文：question + documents
    # 3. 调用 LLM(:8080)
    # 4. 写入 state["answer"]
    return {"answer": answer}
```

### 3.6 Reflect

**职责**：检查答案质量，决定是否需要重新检索。

```python
async def reflect(state: AgentState) -> dict:
    """反思检查"""
    # 1. 加载 reflect prompt
    # 2. 调用 LLM 评估答案质量
    # 3. 输出：quality(good/bad), confidence, retry_count
    # 4. 写入 state["reflect"]
    return {"reflect": reflect_result}
```

**输出**：
```json
{
    "reflect": {
        "quality": "bad",
        "reason": "缺少财务数据",
        "retry_count": 1,
        "confidence": 0.4
    }
}
```

**条件路由**：
- `quality == "good"` → Finish
- `retry_count >= 2` → Finish（强制结束）
- `quality == "bad"` → Retrieve（补充检索）

### 3.7 Writer

**职责**：格式化最终输出（可选，用于复杂报告生成）。

### 3.8 Finish

**职责**：结束处理，清理 State，准备返回。

---

## 四、Node 设计原则

| 原则 | 说明 |
|------|------|
| 单一职责 | 一个 Node 只做一件事 |
| 只修改 State | 不直接返回结果给调用方 |
| 不直接访问基础设施 | 通过 Tool 访问外部服务 |
| 无状态 | Node 本身不保存状态，所有数据在 State 中 |
| 可测试 | 每个 Node 可独立单元测试 |

---

## 五、Node 与 Tool 的关系

```text
Node（业务逻辑）
  │
  │ 调用
  ▼
Tool（基础设施访问）
  │
  │ 访问
  ▼
外部服务（LLM / Qdrant / PostgreSQL / MinIO / Docling）
```

**示例**：
- `retrieve` Node 调用 `embedding` Tool 和 `qdrant` Tool
- `reason` Node 调用 `llm` Tool
- `planner` Node 调用 `llm` Tool
- `query_rewrite` Node 调用 `llm` Tool