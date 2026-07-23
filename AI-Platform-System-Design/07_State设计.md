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
| `plan` | `dict` | Planner | 执行计划，包含步骤、工具选择 |
| `documents` | `list[dict]` | Retrieve / Rerank | 检索到的文档 Chunk |
| `tool_results` | `dict` | 各 Tool Node | 工具调用结果缓存 |
| `answer` | `str` | Reason / Writer | LLM 生成的回答 |
| `reflect` | `dict` | Reflect | 反思结果：质量评分、是否需要重试 |
| `metadata` | `dict` | 各 Node | 运行元数据：耗时、token 用量等 |

---

## 四、State 流转示例

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

↓ Planner

{
    "plan": {
        "steps": ["检索年报", "分析财务", "行业对比"],
        "tools": ["qdrant", "postgres"]
    }
}

↓ Retrieve + Rerank

{
    "documents": [
        {"content": "...", "score": 0.95, "source": "600519/2025/annual_report"},
        {"content": "...", "score": 0.89, "source": "600519/2024/annual_report"}
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

## 五、设计原则

| 原则 | 说明 |
|------|------|
| 单一 State | 所有 Agent 共用一个 AgentState 定义 |
| Node 只修改 State | 不直接返回结果给调用方 |
| 消息自动追加 | 使用 `add_messages` 注解，messages 字段自动累积 |
| 不可变输入 | Node 不修改其他 Node 写入的字段 |
| 元数据记录 | 每个 Node 可写入 metadata 记录耗时等信息 |