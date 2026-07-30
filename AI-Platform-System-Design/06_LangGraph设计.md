# LangGraph 设计

## 一、定位

LangGraph 是系统的**操作系统（Workflow Engine）**，不是 AI，不负责回答。

**核心定义**：导演（Director），不是演员。

- 负责**安排工作**：理解问题 → 检索资料 → 推理 → 反思 → 输出
- 不负责**回答**：回答由 LLM（Qwen3）生成
- 不负责**存储**：存储由 PostgreSQL、Qdrant、MinIO 负责

---

## 二、部署方式

- LangGraph **内嵌 FastAPI 进程**，不作为独立服务
- 不使用官方 LangGraph Server（需要许可证）
- 不使用 LangSmith
- Checkpoint 使用 PostgreSQL（AsyncPostgresSaver）
- Redis 非必需，可按需扩展

---

## 三、Graph 结构

### 3.1 基础 Workflow（Research Agent）

```text
START
  │
  ▼
Planner        → 理解问题，生成执行计划（含垂类参数、时间窗口、文档类型）
  │
  ▼
QueryRewrite   → LLM 驱动查询改写（自然语言 → 专业金融检索词 + 垂类参数）
  │
  ▼
Retrieve       → Embedding + Qdrant 语义检索（支持权威度/时效/文档类型过滤）
  │
  ▼
Rerank         → Reranker 对 Top-K 重排序
  │
  ▼
Reason         → LLM 根据检索结果推理
  │
  ▼
Reflect        → 检查答案质量，决定是否需要重新检索
  │
  ├──── 质量不足 → 回到 Retrieve（补充检索）
  │
  ▼
Finish         → 输出最终结果
  │
  ▼
END
```

> **注意**：`QueryRewrite` 节点仅在 Research Agent 中启用，Chat Agent 和 Knowledge Agent 不包含此节点。

### 3.2 条件路由

```python
def should_continue(state: AgentState) -> str:
    """Reflect 节点后的条件路由"""
    if state["reflect"]["quality"] == "good":
        return "finish"
    elif state["reflect"]["retry_count"] >= 2:
        return "finish"  # 最多重试 2 次
    else:
        return "retrieve"  # 补充检索
```

---

## 四、Graph 构建

```python
from langgraph.graph import StateGraph, START, END
from graph.state import AgentState
from nodes.planner import planner
from nodes.query_rewrite import query_rewrite
from nodes.retrieve import retrieve
from nodes.rerank import rerank
from nodes.reason import reason
from nodes.reflect import reflect
from nodes.finish import finish

def build_research_graph() -> StateGraph:
    """Research Agent: Planner → QueryRewrite → Retrieve → Rerank → Reason → Reflect → Finish"""
    graph = StateGraph(AgentState)
    
    # 添加节点
    graph.add_node("planner", planner)
    graph.add_node("query_rewrite", query_rewrite)
    graph.add_node("retrieve", retrieve)
    graph.add_node("rerank", rerank)
    graph.add_node("reason", reason)
    graph.add_node("reflect", reflect)
    graph.add_node("finish", finish)
    
    # 添加边
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "query_rewrite")
    graph.add_edge("query_rewrite", "retrieve")
    graph.add_edge("retrieve", "rerank")
    graph.add_edge("rerank", "reason")
    graph.add_edge("reason", "reflect")
    
    # 条件边
    graph.add_conditional_edges(
        "reflect",
        should_continue,
        {"finish": "finish", "retrieve": "retrieve"}
    )
    
    graph.add_edge("finish", END)
    
    return graph.compile()
```

---

## 五、设计原则

| 原则 | 说明 |
|------|------|
| Graph 仅负责 Workflow | 不直接访问数据库，不直接创建模型 |
| Node 单一职责 | 每个 Node 只负责一件事 |
| Node 只修改 State | 不直接返回结果给调用方 |
| Tool 访问基础设施 | Node 通过 Tool 访问外部服务 |
| Checkpoint 持久化 | 使用 PostgreSQL，支持任务恢复 |
| 可扩展 | 新增 Agent 只需新增 Graph，不改现有 |

---

## 六、Agent 类型

| Agent | 用途 | Graph 复杂度 |
|-------|------|-------------|
| Chat Agent | 简单问答 + RAG | 简单（Retrieve → Reason → Finish） |
| Research Agent | 研究分析（年报、行业） | 完整 Workflow（含 QueryRewrite） |
| Knowledge Agent | 知识管理（Obsidian 双向读写 + Vault 索引维护） | 中等（Retrieve → Reason → Write Vault → Finish） |
| Investment Agent | 投研分析（DCF、竞争分析、实时行情、权威度过滤） | 完整 + 多工具 + Skill 编排 |

---

## 七、Checkpoint 配置

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def get_checkpointer():
    return await AsyncPostgresSaver.from_conn_string(
        "postgresql+asyncpg://postgres:postgres@postgres:5432/langgraph"
    )
```

**注意**：
- `AsyncPostgresSaver.from_conn_string()` 必须用 `async with`
- `langgraph-checkpoint-postgres` 需显式添加 `psycopg[binary]` 依赖

---

## 八、Knowledge Agent Graph（Vault 知识闭环）

Knowledge Agent 是 Obsidian Vault 的核心操作者，负责 Agent ↔ Vault 的双向读写。

### 8.1 Graph 结构

```text
START
  │
  ▼
Planner          → 理解任务：写入报告 / 读取笔记 / 维护索引
  │
  ▼
Retrieve         → Qdrant 语义检索 + Vault 搜索
  │
  ▼
Reason           → LLM 推理（结合 Vault 中的投资人笔记）
  │
  ▼
Write Vault      → 将结论写入 Obsidian（带 frontmatter + 标签）
  │
  ▼
Reflect          → 检查写入质量（标签完整性、链接正确性）
  │
  ▼
Finish           → 输出确认
  │
  ▼
END
```

### 8.2 Vault 写入规范

```python
# 写入研究报告时的 frontmatter 模板
vault_metadata = {
    "agent": "research",
    "symbol": "600519",
    "market": "cn",
    "type": "annual_report",
    "created": "2026-07-17",
    "status": "draft",        # draft → reviewed → final
    "tags": ["茅台", "年报", "2025"],
    "source": "qdrant",       # 知识来源
}
```

### 8.3 多 Agent 通过 Vault 异步协作

```text
Research Agent  ──写入──→  03_Investment/Reports/600519/
                                    │
Investment Agent ──读取──←  同一份报告
                                    │
Investment Agent ──写入──→  03_Investment/Companies/600519/dcf.md
                                    │
Knowledge Agent  ──整理──→  更新标签、frontmatter、双向链接
```