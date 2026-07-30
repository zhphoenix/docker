# State 设计

## 一、定位

统一使用 `AgentState` 作为所有 Node 的数据载体。

**核心原则**：所有 Node 只能修改 State，不直接返回结果。

---

## 二、AgentState 定义

```python
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    """统一 Agent 状态"""
    
    # 消息历史（自动追加）
    messages: Annotated[list[BaseMessage], add_messages]
    
    # 用户输入
    question: str
    
    # 执行计划（Planner 生成）
    plan: dict
    
    # 检索到的文档（Retrieve 填充）
    documents: list[dict]
    
    # 工具调用结果
    tool_results: dict
    
    # LLM 推理结果
    answer: str
    
    # 反思结果（Reflect 填充）
    reflect: dict
    
    # 元数据
    metadata: dict
```

---

## 三、各字段说明

| 字段 | 类型 | 写入 Node | 说明 |
|------|------|----------|------|
| `messages` | `list[BaseMessage]` | 所有 Node | 消息历史，使用 `add_messages` 注解自动追加 |
| `question` | `str` | API 层 | 用户原始问题 |
| `plan` | `dict` | Planner + QueryRewrite | 执行计划，包含步骤、工具选择、垂类参数、改写查询等（详见下方字段说明） |
| `documents` | `list[dict]` | Retrieve / Rerank | 检索到的文档 Chunk，含权威度标注 |
| `tool_results` | `dict` | 各 Tool Node | 工具调用结果缓存 |
| `answer` | `str` | Reason / Writer | LLM 生成的回答 |
| `reflect` | `dict` | Reflect | 反思结果：质量评分、是否需要重试 |
| `metadata` | `dict` | 各 Node | 运行元数据：耗时、token 用量等 |

---

## 四、plan 字段详细说明

Planner 和 QueryRewrite 节点共同填充 `plan` 字段：

```json
{
    "steps": ["检索年报", "分析财务数据", "行业对比"],
    "tools": ["qdrant", "financial_data"],
    "market": "cn",
    "symbol": "600519",
    "year": 2025,
    "document_type": "annual_report",
    "time_range": {"start_date": "2025-01-01", "end_date": "2025-12-31"},
    "vertical_params": {"indicator": "ROIC", "sector": "科技"},
    "enable_rewrite": true,
    "rewritten_query": "贵州茅台 2025 年报 ROIC 护城河分析",
    "keywords": ["ROIC", "护城河", "年报"]
}
```

| 字段 | 写入节点 | 说明 |
|------|----------|------|
| `steps` | Planner | 执行步骤列表 |
| `tools` | Planner | 需要调用的工具列表 |
| `market` | Planner | 市场代码（cn/hk/us） |
| `symbol` | Planner | 股票代码 |
| `year` | Planner | 目标年份 |
| `document_type` | Planner | 文档类型（annual_report/quarterly_report/announcement） |
| `time_range` | Planner/QueryRewrite | 时效过滤窗口（天级精度） |
| `vertical_params` | Planner | 垂类参数（财务指标、行业等） |
| `enable_rewrite` | Planner | 是否启用 Query 改写（默认 true） |
| `rewritten_query` | QueryRewrite | LLM 改写后的专业检索词 |
| `keywords` | QueryRewrite | 提取的关键词列表 |

---

## 五、documents 字段说明

Retrieve 节点填充的每个 document 包含以下字段：

```json
{
    "content": "贵州茅台2025年营业收入...",
    "score": 0.95,
    "source": "600519/2025",
    "market": "cn",
    "symbol": "600519",
    "year": 2025,
    "authority": "very_high"
}
```

| 字段 | 说明 |
|------|------|
| `content` | 文档 Chunk 文本内容 |
| `score` | 检索相似度分数 |
| `source` | 来源标识（symbol/year） |
| `market` | 市场代码 |
| `symbol` | 股票代码 |
| `year` | 报告年份 |
| `authority` | 权威度级别（very_high/high/medium/low），基于 source_provider 映射 |

---

## 六、State 流转示例

```text
初始 State:
{
    "question": "分析宁德时代未来三年竞争力",
    "messages": [HumanMessage(content="分析宁德时代...")],
    "plan": {},
    "documents": [],
    "tool_results": {},
    "answer": "",
    "reflect": {},
    "metadata": {}
}

↓ Planner + QueryRewrite

{
    "plan": {
        "steps": ["检索年报", "分析财务", "行业对比"],
        "tools": ["qdrant", "financial_data"],
        "market": "cn",
        "symbol": "600519",
        "enable_rewrite": true,
        "rewritten_query": "贵州茅台 2025 年报 ROIC 护城河分析",
        "keywords": ["ROIC", "护城河"]
    }
}

↓ Retrieve + Rerank

{
    "documents": [
        {"content": "...", "score": 0.95, "source": "600519/2025", "authority": "very_high"},
        {"content": "...", "score": 0.89, "source": "600519/2024", "authority": "very_high"}
    ]
}

↓ Reason

{
    "answer": "根据年报数据，宁德时代..."
}

↓ Reflect

{
    "reflect": {
        "quality": "good",
        "retry_count": 0,
        "confidence": 0.85
    }
}

↓ Finish

最终输出
```

---

## 七、设计原则

| 原则 | 说明 |
|------|------|
| 单一 State | 所有 Agent 共用一个 AgentState 定义 |
| Node 只修改 State | 不直接返回结果给调用方 |
| 消息自动追加 | 使用 `add_messages` 注解，messages 字段自动累积 |
| 不可变输入 | Node 不修改其他 Node 写入的字段 |
| 元数据记录 | 每个 Node 可写入 metadata 记录耗时等信息 |